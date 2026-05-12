from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MONEY_CHANGE_HIGH_USD = 10_000.0
ONE_TIME_EVENT_HIGH_USD = 25_000.0
FUTURE_VALUE_HIGH_USD = 50_000.0
FUTURE_VALUE_HIGH_PCT = 0.05
SUCCESS_PROBABILITY_HIGH_DELTA = 0.05
RATE_CHANGE_HIGH_POINTS = 0.01
YEARS_CHANGE_HIGH = 2.0
MULTI_FIELD_HIGH_COUNT = 3

HIGH_REVIEW_FIELDS = {
    "withdrawal_strategy",
    "drawdown_order",
    "filing_status",
    "roth_conversion_annual_amount_usd",
    "roth_conversion_start_age",
    "roth_conversion_end_age",
}

FIELD_LABELS: dict[str, str] = {
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
    "drawdown_order": "Withdrawal order",
    "filing_status": "Tax filing status",
    "roth_conversion_annual_amount_usd": "Annual Roth conversion",
    "roth_conversion_start_age": "Roth conversion start age",
    "roth_conversion_end_age": "Roth conversion end age",
}


def classify_plan_lever_impact(
    *,
    plan_id: str,
    source: str = "simulation",
    input_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
    explanation_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a what-if change before it can become an active-plan decision."""

    inputs = _object(input_payload)
    result = _object(result_payload)
    explanation = _object(explanation_payload)

    materiality_reasons = _materiality_reasons(inputs=inputs, result=result)
    readiness_reasons = _readiness_reasons(result=result, explanation=explanation)
    materiality_level = "high" if materiality_reasons else "low"
    readiness_level = "high" if readiness_reasons else "low"
    review_level = "high" if materiality_level == "high" or readiness_level == "high" else "low"

    if review_level == "high":
        summary = "High review: read the explanation, check the assumptions, and save a decision note before changing the active plan."
        actions = [
            "Review the simulation explanation.",
            "Check the changed assumptions.",
            "Save a decision note before applying this to the active plan.",
        ]
    else:
        summary = "Low review: this looks like a small, well-explained experiment that can stay in the normal simulation workflow."
        actions = [
            "Review the result summary.",
            "Save the simulation if you may want to compare it later.",
        ]

    return {
        "plan_id": plan_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": _source_label(source),
        "review_level": review_level,
        "summary": summary,
        "stage_one": {
            "name": "Change size",
            "level": materiality_level,
            "summary": _stage_summary(
                materiality_level,
                "This change is big enough to slow down and review.",
                "The changed values look small enough for normal review.",
            ),
            "reasons": materiality_reasons,
        },
        "stage_two": {
            "name": "Result trust",
            "level": readiness_level,
            "summary": _stage_summary(
                readiness_level,
                "The result needs extra review before it supports a decision.",
                "The result is explained clearly enough for normal review.",
            ),
            "reasons": readiness_reasons,
        },
        "recommended_actions": actions,
        "thresholds": {
            "money_change_high_usd": MONEY_CHANGE_HIGH_USD,
            "one_time_event_high_usd": ONE_TIME_EVENT_HIGH_USD,
            "future_value_high_usd": FUTURE_VALUE_HIGH_USD,
            "future_value_high_pct": FUTURE_VALUE_HIGH_PCT,
            "success_probability_high_delta": SUCCESS_PROBABILITY_HIGH_DELTA,
            "rate_change_high_points": RATE_CHANGE_HIGH_POINTS,
            "years_change_high": YEARS_CHANGE_HIGH,
            "multi_field_high_count": MULTI_FIELD_HIGH_COUNT,
        },
        "trace": {
            "source_code": str(source or "simulation"),
            "changed_fields": _changed_field_names(result),
            "input_keys": sorted(inputs.keys()),
            "result_sections": sorted(result.keys()),
            "explanation_sections": sorted(explanation.keys()),
        },
    }


def _materiality_reasons(*, inputs: dict[str, Any], result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    changed_fields = _changed_fields(result)

    if len(changed_fields) >= MULTI_FIELD_HIGH_COUNT:
        reasons.append(f"{len(changed_fields)} assumptions changed at once.")

    for field, left, right in changed_fields:
        label = FIELD_LABELS.get(field, _human_text(field))
        if field in HIGH_REVIEW_FIELDS:
            reasons.append(f"{label} affects taxes, withdrawals, or retirement timing.")
            continue

        delta = _numeric_delta(left, right)
        if delta is None:
            continue

        abs_delta = abs(delta)
        if field.endswith("_usd") and abs_delta >= MONEY_CHANGE_HIGH_USD:
            reasons.append(f"{label} changed by {_money(abs_delta)} or more.")
        elif field in {"expected_return_baseline", "expected_return_optimistic", "expected_return_conservative", "inflation_rate", "marginal_tax_rate", "state_tax_rate"} and abs_delta >= RATE_CHANGE_HIGH_POINTS:
            reasons.append(f"{label} changed by at least one percentage point.")
        elif field == "years" and abs_delta >= YEARS_CHANGE_HIGH:
            reasons.append(f"{label} changed by {int(abs_delta)} years.")

    for event in _branch_events(inputs, result):
        amount = abs(_number(event.get("amount_usd")) or 0.0)
        frequency = str(event.get("recurring_frequency") or "one_time").strip().lower()
        label = str(event.get("label") or "What-if event").strip()
        if frequency == "one_time" and amount >= ONE_TIME_EVENT_HIGH_USD:
            reasons.append(f"{label} changes one-time cash flow by {_money(amount)} or more.")
        elif frequency != "one_time" and amount >= MONEY_CHANGE_HIGH_USD:
            reasons.append(f"{label} changes recurring cash flow by {_money(amount)} or more.")

    baseline = _baseline_delta(result)
    if baseline:
        base_future = abs(_number(baseline.get("base_future_value_usd")) or 0.0)
        for key, label in (
            ("delta_future_value_usd", "Future value"),
            ("delta_real_value_usd", "Inflation-adjusted value"),
        ):
            delta = abs(_number(baseline.get(key)) or 0.0)
            if delta >= FUTURE_VALUE_HIGH_USD:
                reasons.append(f"{label} changes by {_money(delta)} or more.")
            elif base_future and delta / base_future >= FUTURE_VALUE_HIGH_PCT:
                reasons.append(f"{label} changes by at least 5% of the active-plan result.")

    success = _number(_object(result.get("monte_carlo_delta")).get("success_probability_delta"))
    if success is not None and abs(success) >= SUCCESS_PROBABILITY_HIGH_DELTA:
        reasons.append("Success probability changes by at least five percentage points.")

    return _dedupe(reasons)


def _readiness_reasons(*, result: dict[str, Any], explanation: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    warnings = _warnings(result, explanation)
    if warnings:
        reasons.append("The simulation has model warnings to review.")

    confidence = str(explanation.get("confidence_level") or "").strip().lower()
    if confidence == "low":
        reasons.append("The explanation has low confidence.")

    outcome = str(explanation.get("outcome_label") or "").strip().lower()
    if outcome == "worse":
        reasons.append("The result weakens the active plan.")
    elif outcome == "mixed":
        reasons.append("The result has trade-offs.")

    if result and not _baseline_delta(result):
        reasons.append("The result does not include a clear active-plan comparison.")

    return _dedupe(reasons)


def _changed_fields(result: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    base = _object(result.get("base_settings"))
    candidate = _object(result.get("candidate_settings") or result.get("branch_settings"))
    fields: list[tuple[str, Any, Any]] = []
    for key in sorted(set(base.keys()) | set(candidate.keys())):
        if key == "updated_at":
            continue
        left = base.get(key)
        right = candidate.get(key)
        if left == right:
            continue
        if left in (None, "") and right in (None, ""):
            continue
        fields.append((key, left, right))
    return fields


def _changed_field_names(result: dict[str, Any]) -> list[str]:
    return [field for field, _, _ in _changed_fields(result)]


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


def _branch_events(inputs: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in (inputs.get("branch_events"), result.get("branch_events")):
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
    return rows


def _warnings(result: dict[str, Any], explanation: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for payload in (
        result.get("warnings"),
        _object(result.get("base_result")).get("warnings"),
        _object(result.get("candidate_result") or result.get("branch_result")).get("warnings"),
        explanation.get("warnings"),
    ):
        if isinstance(payload, list):
            values.extend(str(item).strip() for item in payload if str(item).strip())
    return _dedupe(values)


def _numeric_delta(left: Any, right: Any) -> float | None:
    left_number = _number(left)
    right_number = _number(right)
    if left_number is None and right_number is None:
        return None
    if left_number is None:
        return right_number
    if right_number is None:
        return -left_number
    return right_number - left_number


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _human_text(value: str) -> str:
    text = str(value or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Changed field"


def _source_label(source: str) -> str:
    normalized = str(source or "").strip().lower()
    if normalized == "scenario_diff":
        return "Simulation"
    if normalized == "scenario_branch":
        return "What-if simulation"
    if normalized == "withdrawal_strategy":
        return "Strategy comparison"
    return "Simulation"


def _stage_summary(level: str, high: str, low: str) -> str:
    return high if level == "high" else low
