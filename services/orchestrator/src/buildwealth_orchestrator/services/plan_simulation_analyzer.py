from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


PLAN_SIMULATION_FIELD_LABELS: dict[str, str] = {
    "annual_contribution_usd": "Annual contribution",
    "current_portfolio_value_usd": "Portfolio value",
    "years": "Years horizon",
    "expected_return_baseline": "Expected return",
    "expected_return_optimistic": "Optimistic return",
    "expected_return_conservative": "Conservative return",
    "inflation_rate": "Inflation",
    "marginal_tax_rate": "Marginal tax",
    "state_tax_rate": "State tax",
    "withdrawal_strategy": "Withdrawal strategy",
    "drawdown_order": "Drawdown order",
    "filing_status": "Filing status",
    "simulation_mode": "Simulation mode",
    "roth_conversion_annual_amount_usd": "Annual Roth conversion",
    "roth_conversion_start_age": "Roth conversion start age",
    "roth_conversion_end_age": "Roth conversion end age",
}


def explain_plan_simulation(
    *,
    plan_id: str,
    source: str = "simulation",
    input_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a plain-language explanation from a plan simulation result."""

    inputs = _object(input_payload)
    result = _object(result_payload)
    baseline = _baseline_delta(result)
    warnings = _warning_list(result)
    assumption_traces = _assumption_traces(result, inputs)
    drivers = _drivers(result, baseline, assumption_traces)
    metrics = _metrics(result, baseline)
    outcome_label = _outcome_label(metrics)
    confidence_level, confidence_reasons = _confidence(
        baseline=baseline,
        warnings=warnings,
        assumption_traces=assumption_traces,
        result=result,
    )

    return {
        "plan_id": plan_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": _source_label(source),
        "outcome_label": outcome_label,
        "summary": _summary(outcome_label, metrics, warnings),
        "drivers": drivers,
        "assumption_traces": assumption_traces,
        "warnings": warnings,
        "confidence_level": confidence_level,
        "confidence_reasons": confidence_reasons,
        "metrics": metrics,
        "trace": {
            "source_code": str(source or "simulation"),
            "input_keys": sorted(inputs.keys()),
            "result_sections": sorted(result.keys()),
            "assumption_fields": [row["field"] for row in assumption_traces],
        },
    }


def _baseline_delta(result: dict[str, Any]) -> dict[str, Any] | None:
    rows = result.get("scenario_deltas")
    if not isinstance(rows, list):
        return None
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return None
    for row in candidates:
        if str(row.get("label") or "").strip().lower() == "baseline":
            return row
    return candidates[0]


def _metrics(result: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    monte = _object(result.get("monte_carlo_delta"))
    metrics: dict[str, Any] = {}
    if baseline:
        for key in (
            "delta_future_value_usd",
            "delta_real_value_usd",
            "base_future_value_usd",
            "candidate_future_value_usd",
            "base_real_value_usd",
            "candidate_real_value_usd",
        ):
            value = _number(baseline.get(key))
            if value is not None:
                metrics[key] = value
    success_delta = _number(monte.get("success_probability_delta"))
    if success_delta is not None:
        metrics["success_probability_delta"] = success_delta
    return metrics


def _outcome_label(metrics: dict[str, Any]) -> str:
    future = _number(metrics.get("delta_future_value_usd"))
    real = _number(metrics.get("delta_real_value_usd"))
    success = _number(metrics.get("success_probability_delta"))
    positives = sum(1 for value in (future, real, success) if value is not None and value > 0)
    negatives = sum(1 for value in (future, real, success) if value is not None and value < 0)
    if positives and not negatives:
        return "better"
    if negatives and not positives:
        return "worse"
    if positives and negatives:
        return "mixed"
    return "unclear"


def _summary(outcome_label: str, metrics: dict[str, Any], warnings: list[str]) -> str:
    future = _number(metrics.get("delta_future_value_usd"))
    real = _number(metrics.get("delta_real_value_usd"))
    success = _number(metrics.get("success_probability_delta"))
    if outcome_label == "better":
        lead = "This simulation improves the active plan."
    elif outcome_label == "worse":
        lead = "This simulation weakens the active plan."
    elif outcome_label == "mixed":
        lead = "This simulation has trade-offs."
    else:
        lead = "This simulation needs more context before the result is useful."

    parts = [lead]
    if future is not None:
        parts.append(f"Future value changes by {_money_phrase(future)}.")
    if real is not None:
        parts.append(f"Inflation-adjusted value changes by {_money_phrase(real)}.")
    if success is not None:
        parts.append(f"Success probability changes by {_percent_phrase(success)}.")
    if warnings:
        parts.append("Review the model warnings before using this for a decision.")
    return " ".join(parts)


def _drivers(
    result: dict[str, Any],
    baseline: dict[str, Any] | None,
    assumption_traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if baseline:
        future = _number(baseline.get("delta_future_value_usd"))
        if future is not None:
            rows.append(
                {
                    "label": "Future value",
                    "direction": _direction(future),
                    "detail": f"The candidate result is {_money_phrase(future)} versus the active plan.",
                    "amount_usd": future,
                }
            )
        real = _number(baseline.get("delta_real_value_usd"))
        if real is not None:
            rows.append(
                {
                    "label": "Inflation-adjusted value",
                    "direction": _direction(real),
                    "detail": f"After inflation, the candidate result is {_money_phrase(real)} versus the active plan.",
                    "amount_usd": real,
                }
            )

    monte = _object(result.get("monte_carlo_delta"))
    success = _number(monte.get("success_probability_delta"))
    if success is not None:
        rows.append(
            {
                "label": "Success probability",
                "direction": _direction(success),
                "detail": f"The chance of success changes by {_percent_phrase(success)}.",
                "amount_usd": None,
            }
        )

    for trace in assumption_traces[:3]:
        rows.append(
            {
                "label": trace["label"],
                "direction": "neutral",
                "detail": trace["explanation"],
                "amount_usd": None,
            }
        )
    return rows[:6]


def _assumption_traces(result: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    base = _object(result.get("base_settings"))
    candidate = _object(result.get("candidate_settings") or result.get("branch_settings"))
    compare_settings = _object(inputs.get("compare_settings"))
    if not base and not candidate:
        return []

    keys = set(base.keys()) | set(candidate.keys()) | set(compare_settings.keys())
    rows: list[dict[str, Any]] = []
    for key in sorted(keys):
        if key not in PLAN_SIMULATION_FIELD_LABELS:
            continue
        left = base.get(key)
        right = candidate.get(key)
        if left == right:
            continue
        label = PLAN_SIMULATION_FIELD_LABELS[key]
        rows.append(
            {
                "field": key,
                "label": label,
                "base_value": _display_value(key, left),
                "candidate_value": _display_value(key, right),
                "explanation": f"{label} changed from {_display_value(key, left)} to {_display_value(key, right)}.",
            }
        )
    return rows


def _confidence(
    *,
    baseline: dict[str, Any] | None,
    warnings: list[str],
    assumption_traces: list[dict[str, Any]],
    result: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not result:
        return "low", ["No simulation result payload was provided."]
    if baseline:
        reasons.append("The result includes comparable active-plan and candidate deltas.")
    else:
        reasons.append("The result does not include comparable active-plan and candidate deltas.")
    if assumption_traces:
        reasons.append("Changed assumptions are visible and traceable.")
    else:
        reasons.append("No changed assumptions were visible in the payload.")
    if warnings:
        reasons.append("Model warnings need review before a decision.")

    if baseline and assumption_traces and not warnings:
        return "high", reasons
    if baseline and (assumption_traces or not warnings):
        return "medium", reasons
    return "low", reasons


def _warning_list(result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for value in (
        result.get("warnings"),
        _object(result.get("base_result")).get("warnings"),
        _object(result.get("candidate_result")).get("warnings"),
        _object(result.get("branch_result")).get("warnings"),
    ):
        if isinstance(value, list):
            warnings.extend(str(item).strip() for item in value if str(item).strip())
    simulation_delta = _object(result.get("simulation_delta"))
    if str(simulation_delta.get("status") or "").strip().lower() == "degraded":
        warnings.append(str(simulation_delta.get("summary") or "Simulation used a degraded comparison."))
    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        key = warning.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped[:6]


def _source_label(source: str) -> str:
    normalized = str(source or "").strip().lower()
    if normalized == "scenario_branch":
        return "What-if simulation"
    if normalized == "withdrawal_strategy":
        return "Strategy comparison"
    return "Simulation"


def _direction(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _money_phrase(value: float) -> str:
    if value < 0:
        return f"-${abs(value):,.0f}"
    sign = "+" if value > 0 else ""
    return f"{sign}${value:,.0f}"


def _percent_phrase(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f}%"


def _display_value(key: str, value: Any) -> str:
    if value is None or value == "":
        return "not set"
    numeric = _number(value)
    if numeric is not None:
        if key.endswith("_usd") or key == "current_portfolio_value_usd":
            return f"${numeric:,.0f}"
        if "rate" in key or "return" in key:
            return f"{numeric * 100:.1f}%"
        if numeric.is_integer():
            return str(int(numeric))
    return str(value).replace("_", " ")


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
