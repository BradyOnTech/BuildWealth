from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Scoring-packaging shape and weighted-summary style are aligned with
# Ignidash analyzer conventions (`src/lib/calc/data-analyzers/*`), while
# score factors are BuildWealth-specific for recommendation ranking.
RECOMMENDATION_SCORE_MODEL_VERSION = "v1"
DEFAULT_RECOMMENDATION_SORT = "ranked"
VALID_RECOMMENDATION_SORTS = {"ranked", "created_at"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_recommendation_sort(raw_sort: Any) -> str:
    value = str(raw_sort or "").strip().lower()
    if value in VALID_RECOMMENDATION_SORTS:
        return value
    return DEFAULT_RECOMMENDATION_SORT


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clamp(value: float, *, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric:
        return default
    return numeric


def _normalized_status(row: dict[str, Any]) -> str:
    return str(row.get("status") or "proposed").strip().lower() or "proposed"


def _normalized_priority(row: dict[str, Any]) -> str:
    priority = str(row.get("priority") or "medium").strip().lower()
    if priority in {"high", "medium", "low"}:
        return priority
    return "medium"


def _normalized_recommendation_type(row: dict[str, Any]) -> str:
    recommendation_type = str(row.get("recommendation_type") or "general").strip().lower()
    if recommendation_type in {"plan_settings_update", "workflow_action", "general"}:
        return recommendation_type
    return "general"


def _coerce_action_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("action_payload")
    if isinstance(payload, dict):
        return payload
    return {}


def _scenario_preview(action_payload: dict[str, Any]) -> dict[str, Any] | None:
    preview = action_payload.get("scenario_diff_preview")
    if isinstance(preview, dict):
        return preview

    decision_closure = action_payload.get("decision_closure")
    if isinstance(decision_closure, dict):
        preview = decision_closure.get("scenario_diff_preview")
        if isinstance(preview, dict):
            return preview

    return None


def _scenario_delta_abs_usd(action_payload: dict[str, Any]) -> float:
    preview = _scenario_preview(action_payload)
    if not isinstance(preview, dict):
        return 0.0

    deltas = preview.get("scenario_deltas")
    if not isinstance(deltas, list) or not deltas:
        return 0.0

    baseline = None
    for row in deltas:
        if not isinstance(row, dict):
            continue
        if str(row.get("label") or "").strip().lower() == "baseline":
            baseline = row
            break
    candidate = baseline if isinstance(baseline, dict) else deltas[0]
    if not isinstance(candidate, dict):
        return 0.0

    delta = _safe_float(candidate.get("delta_future_value_usd"), 0.0)
    return abs(delta)


def _append_reason(reasons: list[str], text: str) -> None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return
    lowered = cleaned.lower()
    if any(existing.lower() == lowered for existing in reasons):
        return
    reasons.append(cleaned)


def score_recommendation_row(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or utc_now()
    priority = _normalized_priority(row)
    recommendation_type = _normalized_recommendation_type(row)
    status = _normalized_status(row)
    source = str(row.get("source") or "manual").strip().lower()
    action_payload = _coerce_action_payload(row)

    created_at = _parse_datetime(row.get("created_at"))
    age_days = 0
    if created_at is not None:
        age_days = max(0, int((resolved_now - created_at).total_seconds() // 86_400))

    reasons: list[str] = []

    impact = {"high": 80.0, "medium": 58.0, "low": 38.0}[priority]
    impact += {"plan_settings_update": 8.0, "workflow_action": 6.0, "general": 0.0}[recommendation_type]
    if recommendation_type == "plan_settings_update":
        _append_reason(reasons, "Plan-setting changes can materially shift long-term outcomes.")

    scenario_delta_abs = _scenario_delta_abs_usd(action_payload)
    if scenario_delta_abs >= 250_000:
        impact += 15.0
        _append_reason(reasons, "Scenario preview indicates very large projected outcome delta.")
    elif scenario_delta_abs >= 100_000:
        impact += 12.0
        _append_reason(reasons, "Scenario preview indicates large projected outcome delta.")
    elif scenario_delta_abs >= 25_000:
        impact += 8.0
        _append_reason(reasons, "Scenario preview indicates meaningful projected outcome delta.")
    elif scenario_delta_abs >= 5_000:
        impact += 5.0
        _append_reason(reasons, "Scenario preview indicates moderate projected outcome delta.")
    elif scenario_delta_abs > 0:
        impact += 2.0

    plan_updates = action_payload.get("plan_settings_updates")
    if isinstance(plan_updates, dict) and plan_updates:
        impact += 6.0
        _append_reason(reasons, "Recommendation includes explicit plan-setting updates.")

    confidence = 35.0
    evidence = action_payload.get("evidence")
    if isinstance(evidence, dict):
        confidence += 12.0
        _append_reason(reasons, "Recommendation includes structured evidence metadata.")
        if evidence.get("generated_at"):
            confidence += 5.0
        if isinstance(evidence.get("data_keys"), list) and evidence.get("data_keys"):
            confidence += 6.0
        if evidence.get("snapshot_as_of"):
            confidence += 4.0

    decision_packet = action_payload.get("decision_packet")
    if isinstance(decision_packet, dict):
        confidence += 8.0
        _append_reason(reasons, "Decision packet context is available.")
        if decision_packet.get("context_generated_at"):
            confidence += 4.0
        cited_symbols = decision_packet.get("cited_research_symbols")
        if isinstance(cited_symbols, list) and cited_symbols:
            confidence += 6.0

    bridge = action_payload.get("research_bridge")
    if isinstance(bridge, dict):
        bridge_status = str(bridge.get("status") or "").strip().lower()
        if bridge_status == "pinned":
            confidence += 5.0
        elif bridge_status in {"failed", "error"}:
            confidence -= 10.0

    preview = _scenario_preview(action_payload)
    if isinstance(preview, dict):
        preview_status = str(preview.get("status") or "").strip().lower()
        if preview_status == "captured":
            confidence += 7.0
        elif preview_status in {"error", "failed"}:
            confidence -= 12.0

    if source.startswith("workflow:"):
        confidence += 8.0
        _append_reason(reasons, "Workflow-generated recommendation includes reproducible provenance.")

    urgency = {"high": 88.0, "medium": 58.0, "low": 32.0}[priority]
    if status == "proposed":
        urgency += min(14.0, float(age_days) * 1.5)
        if age_days >= 7:
            _append_reason(reasons, "Recommendation has remained open for multiple days.")
        urgency += {"plan_settings_update": 5.0, "workflow_action": 4.0, "general": 0.0}[recommendation_type]
    else:
        urgency = max(5.0, urgency - 30.0)

    reversibility = {"workflow_action": 82.0, "general": 72.0, "plan_settings_update": 56.0}[recommendation_type]
    if isinstance(plan_updates, dict) and plan_updates:
        update_keys = {str(key).strip() for key in plan_updates.keys()}
        if update_keys & {
            "marginal_tax_rate",
            "expected_return_baseline",
            "expected_return_optimistic",
            "expected_return_conservative",
            "years",
        }:
            reversibility -= 12.0
        if update_keys & {"annual_contribution_usd", "hsa_extra_contribution_usd"}:
            reversibility += 6.0
        if "withdrawal_strategy" in update_keys:
            reversibility -= 8.0

    if priority == "high":
        reversibility -= 4.0

    impact = round(_clamp(impact), 2)
    confidence = round(_clamp(confidence), 2)
    urgency = round(_clamp(urgency), 2)
    reversibility = round(_clamp(reversibility), 2)

    total = round(
        _clamp(
            (impact * 0.40)
            + (confidence * 0.25)
            + (urgency * 0.25)
            + (reversibility * 0.10)
        ),
        2,
    )

    return {
        "impact": impact,
        "confidence": confidence,
        "urgency": urgency,
        "reversibility": reversibility,
        "total": total,
        "rank": None,
        "model_version": RECOMMENDATION_SCORE_MODEL_VERSION,
        "reasons": reasons[:8],
    }


def _sort_datetime_key(row: dict[str, Any], field: str) -> datetime:
    parsed = _parse_datetime(row.get(field))
    if parsed is not None:
        return parsed
    if field != "created_at":
        fallback = _parse_datetime(row.get("created_at"))
        if fallback is not None:
            return fallback
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def score_and_sort_recommendations(
    rows: list[dict[str, Any]],
    *,
    sort: str = DEFAULT_RECOMMENDATION_SORT,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    resolved_now = now or utc_now()
    scored_rows: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        row["score"] = score_recommendation_row(row, now=resolved_now)
        scored_rows.append(row)

    sort_mode = normalize_recommendation_sort(sort)
    if sort_mode == "created_at":
        scored_rows.sort(key=lambda row: _sort_datetime_key(row, "created_at"), reverse=True)
        for row in scored_rows:
            score = row.get("score")
            if isinstance(score, dict):
                score["rank"] = None
    else:
        proposed = [row for row in scored_rows if _normalized_status(row) == "proposed"]
        others = [row for row in scored_rows if _normalized_status(row) != "proposed"]

        proposed.sort(
            key=lambda row: (
                -_safe_float((row.get("score") or {}).get("total"), 0.0),
                -_safe_float((row.get("score") or {}).get("urgency"), 0.0),
                -_sort_datetime_key(row, "created_at").timestamp(),
            ),
        )
        for index, row in enumerate(proposed, start=1):
            score = row.get("score")
            if isinstance(score, dict):
                score["rank"] = index

        others.sort(key=lambda row: _sort_datetime_key(row, "updated_at"), reverse=True)
        scored_rows = [*proposed, *others]

    if limit is None:
        return scored_rows

    bounded_limit = max(1, min(int(limit), 5000))
    return scored_rows[:bounded_limit]
