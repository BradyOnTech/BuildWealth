from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.plan_simulation_analyzer import PLAN_SIMULATION_FIELD_LABELS


def compare_saved_simulation_to_current_plan(
    *,
    plan_id: str,
    saved_simulation: dict[str, Any],
    current_settings: dict[str, Any],
) -> dict[str, Any]:
    result = _object(saved_simulation.get("result_payload"))
    saved_base_settings = _object(result.get("base_settings"))
    saved_candidate_settings = _object(result.get("candidate_settings") or result.get("branch_settings"))
    differences = _setting_differences(saved_base_settings, current_settings)
    saved_metrics = _saved_metrics(result)
    changed = bool(differences)

    title = str(saved_simulation.get("title") or "Saved Simulation").strip()
    if changed:
        summary = f"{title} was saved against older plan assumptions. Rerun it before using it for a decision."
    else:
        summary = f"{title} still matches the current plan assumptions used for comparison."

    return {
        "plan_id": plan_id,
        "saved_simulation_id": str(saved_simulation.get("id") or ""),
        "simulation": saved_simulation,
        "summary": summary,
        "changed_since_saved": changed,
        "setting_differences": differences,
        "saved_metrics": saved_metrics,
        "current_settings": current_settings,
        "saved_base_settings": saved_base_settings,
        "saved_candidate_settings": saved_candidate_settings,
        "rerun_payload": _object(saved_simulation.get("input_payload")),
    }


def _setting_differences(saved_base: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = sorted((set(saved_base.keys()) | set(current.keys())) & set(PLAN_SIMULATION_FIELD_LABELS.keys()))
    for key in keys:
        saved_value = saved_base.get(key)
        current_value = current.get(key)
        if _equivalent(saved_value, current_value):
            continue
        rows.append(
            {
                "field": key,
                "label": PLAN_SIMULATION_FIELD_LABELS.get(key, _human_text(key)),
                "saved_value": _display_value(key, saved_value),
                "current_value": _display_value(key, current_value),
            }
        )
    return rows


def _saved_metrics(result: dict[str, Any]) -> dict[str, Any]:
    baseline = _baseline_delta(result)
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
            if key in baseline:
                metrics[key] = baseline.get(key)
    monte = _object(result.get("monte_carlo_delta"))
    if "success_probability_delta" in monte:
        metrics["success_probability_delta"] = monte.get("success_probability_delta")
    return metrics


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


def _equivalent(left: Any, right: Any) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    if left_number is not None and right_number is not None:
        return abs(left_number - right_number) < 0.000001
    return str(left or "").strip() == str(right or "").strip()


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


def _display_value(key: str, value: Any) -> str:
    if value is None or value == "":
        return "Unset"
    number = _number(value)
    if number is not None and key.endswith("_usd"):
        return f"${number:,.0f}"
    if number is not None and key.endswith("_rate"):
        text = f"{number * 100:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"
    return str(value)


def _human_text(value: str) -> str:
    text = str(value or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Field"


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
