from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Scoring-packaging shape and weighted-summary style are aligned with
# Ignidash analyzer conventions (`src/lib/calc/data-analyzers/*`), while
# score factors are BuildWealth-specific for recommendation ranking.
RECOMMENDATION_SCORE_MODEL_VERSION = "v1"
RECOMMENDATION_CALIBRATION_MODEL_VERSION = "calibration_v1"
DEFAULT_RECOMMENDATION_SORT = "ranked"
VALID_RECOMMENDATION_SORTS = {"ranked", "created_at"}
PROCESS_OUTCOME_WEIGHTS = {
    "useful_review": 1.0,
    "acted_elsewhere": 0.5,
    "deferred": 0.0,
    "insufficient_evidence": -0.6,
    "not_useful": -1.0,
}


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


def _decision_closure(row: dict[str, Any]) -> dict[str, Any]:
    direct = row.get("decision_closure")
    if isinstance(direct, dict):
        return direct
    payload = _coerce_action_payload(row)
    closure = payload.get("decision_closure")
    if isinstance(closure, dict):
        return closure
    return {}


def _same_direction(left: float, right: float) -> bool:
    if left == 0 or right == 0:
        return left == right
    return (left > 0 and right > 0) or (left < 0 and right < 0)


def _expected_vs_realized_metrics(row: dict[str, Any]) -> dict[str, Any]:
    closure = _decision_closure(row)
    metrics = closure.get("expected_vs_realized")
    if isinstance(metrics, dict):
        return metrics

    expected = closure.get("expected_outcome")
    realized = closure.get("realized_outcome")
    if not isinstance(expected, dict) or not isinstance(realized, dict):
        return {}

    expected_future = _safe_float(expected.get("expected_delta_future_value_usd"), 0.0)
    realized_future = _safe_float(realized.get("realized_delta_future_value_usd"), 0.0)
    if expected_future == 0.0 and realized_future == 0.0:
        return {}
    return {
        "status": "measured",
        "future_value_gap_usd": realized_future - expected_future,
        "future_value_direction_match": _same_direction(expected_future, realized_future),
    }


def _decision_process_calibration(row: dict[str, Any]) -> dict[str, Any]:
    closure = _decision_closure(row)
    calibration = closure.get("decision_process_calibration")
    return calibration if isinstance(calibration, dict) else {}


def _normalized_source(row: dict[str, Any]) -> str:
    return str(row.get("source") or "manual").strip().lower() or "manual"


def _empty_calibration_bucket(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "measured_count": 0,
        "direction_match_count": 0,
        "future_value_abs_error_total_usd": 0.0,
        "process_count": 0,
        "process_score_total": 0.0,
        "useful_process_count": 0,
        "weak_process_count": 0,
    }


def _add_calibration_observation(bucket: dict[str, Any], metrics: dict[str, Any]) -> None:
    bucket["measured_count"] = int(bucket.get("measured_count") or 0) + 1
    if bool(metrics.get("future_value_direction_match")):
        bucket["direction_match_count"] = int(bucket.get("direction_match_count") or 0) + 1
    gap = _safe_float(metrics.get("future_value_gap_usd"), 0.0)
    bucket["future_value_abs_error_total_usd"] = _safe_float(bucket.get("future_value_abs_error_total_usd"), 0.0) + abs(gap)


def _add_process_calibration_observation(bucket: dict[str, Any], calibration: dict[str, Any]) -> None:
    outcome = str(calibration.get("process_outcome") or "").strip().lower()
    if outcome not in PROCESS_OUTCOME_WEIGHTS:
        return
    weight = PROCESS_OUTCOME_WEIGHTS[outcome]
    bucket["process_count"] = int(bucket.get("process_count") or 0) + 1
    bucket["process_score_total"] = _safe_float(bucket.get("process_score_total"), 0.0) + weight
    if weight > 0:
        bucket["useful_process_count"] = int(bucket.get("useful_process_count") or 0) + 1
    elif weight < 0:
        bucket["weak_process_count"] = int(bucket.get("weak_process_count") or 0) + 1


def _finalize_calibration_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    measured_count = int(bucket.get("measured_count") or 0)
    direction_match_count = int(bucket.get("direction_match_count") or 0)
    process_count = int(bucket.get("process_count") or 0)
    useful_process_count = int(bucket.get("useful_process_count") or 0)
    weak_process_count = int(bucket.get("weak_process_count") or 0)
    match_rate = round((direction_match_count / measured_count) * 100.0, 2) if measured_count else None
    mean_abs_error = (
        round(_safe_float(bucket.get("future_value_abs_error_total_usd"), 0.0) / measured_count, 2)
        if measured_count
        else None
    )
    process_score = round(_safe_float(bucket.get("process_score_total"), 0.0) / process_count, 2) if process_count else None
    process_useful_rate = round((useful_process_count / process_count) * 100.0, 2) if process_count else None
    adjustment = 0.0
    if measured_count >= 2 and match_rate is not None:
        if match_rate >= 75.0:
            adjustment = 8.0
        elif match_rate >= 60.0:
            adjustment = 4.0
        elif match_rate <= 25.0:
            adjustment = -10.0
        elif match_rate <= 40.0:
            adjustment = -6.0
        if mean_abs_error is not None and mean_abs_error >= 100_000.0:
            adjustment -= 3.0
    if process_count >= 2 and process_score is not None:
        if process_score >= 0.6:
            adjustment += 6.0
        elif process_score >= 0.25:
            adjustment += 3.0
        elif process_score <= -0.6:
            adjustment -= 8.0
        elif process_score <= -0.25:
            adjustment -= 4.0
    return {
        "key": str(bucket.get("key") or ""),
        "measured_count": measured_count,
        "direction_match_count": direction_match_count,
        "future_value_direction_match_rate_pct": match_rate,
        "mean_future_value_abs_error_usd": mean_abs_error,
        "process_count": process_count,
        "useful_process_count": useful_process_count,
        "weak_process_count": weak_process_count,
        "process_useful_rate_pct": process_useful_rate,
        "process_score": process_score,
        "confidence_adjustment": round(_clamp(adjustment, min_value=-12.0, max_value=10.0), 2),
    }


def build_recommendation_calibration_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    by_type: dict[str, dict[str, Any]] = {}

    for row in rows:
        metrics = _expected_vs_realized_metrics(row)
        process_calibration = _decision_process_calibration(row)
        has_measured_metrics = str(metrics.get("status") or "").strip().lower() == "measured"
        has_process_calibration = (
            str(process_calibration.get("process_outcome") or "").strip().lower()
            in PROCESS_OUTCOME_WEIGHTS
        )
        if not has_measured_metrics and not has_process_calibration:
            continue

        source = _normalized_source(row)
        recommendation_type = _normalized_recommendation_type(row)
        source_bucket = by_source.setdefault(source, _empty_calibration_bucket(source))
        type_bucket = by_type.setdefault(recommendation_type, _empty_calibration_bucket(recommendation_type))
        if has_measured_metrics:
            _add_calibration_observation(source_bucket, metrics)
            _add_calibration_observation(type_bucket, metrics)
        if has_process_calibration:
            _add_process_calibration_observation(source_bucket, process_calibration)
            _add_process_calibration_observation(type_bucket, process_calibration)

    return {
        "model_version": RECOMMENDATION_CALIBRATION_MODEL_VERSION,
        "by_source": {key: _finalize_calibration_bucket(bucket) for key, bucket in by_source.items()},
        "by_type": {key: _finalize_calibration_bucket(bucket) for key, bucket in by_type.items()},
    }


def _calibration_summary_for_row(
    row: dict[str, Any],
    calibration_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    profile = calibration_profile if isinstance(calibration_profile, dict) else {}
    by_source = profile.get("by_source") if isinstance(profile.get("by_source"), dict) else {}
    by_type = profile.get("by_type") if isinstance(profile.get("by_type"), dict) else {}
    source_key = _normalized_source(row)
    type_key = _normalized_recommendation_type(row)
    source_bucket = by_source.get(source_key) if isinstance(by_source.get(source_key), dict) else None
    type_bucket = by_type.get(type_key) if isinstance(by_type.get(type_key), dict) else None

    source_delta = _safe_float(source_bucket.get("confidence_adjustment") if source_bucket else 0.0, 0.0)
    type_delta = _safe_float(type_bucket.get("confidence_adjustment") if type_bucket else 0.0, 0.0)
    confidence_delta = round(_clamp(source_delta + (type_delta * 0.5), min_value=-12.0, max_value=10.0), 2)
    return {
        "model_version": RECOMMENDATION_CALIBRATION_MODEL_VERSION,
        "source_key": source_key,
        "type_key": type_key,
        "source": source_bucket,
        "type": type_bucket,
        "confidence_delta": confidence_delta,
        "applied": confidence_delta != 0.0,
    }


def _append_calibration_reason(reasons: list[str], calibration: dict[str, Any]) -> None:
    confidence_delta = _safe_float(calibration.get("confidence_delta"), 0.0)
    if confidence_delta == 0.0:
        return

    source_bucket = calibration.get("source") if isinstance(calibration.get("source"), dict) else None
    type_bucket = calibration.get("type") if isinstance(calibration.get("type"), dict) else None
    source_count = int(source_bucket.get("measured_count") or 0) if source_bucket else 0
    source_rate = source_bucket.get("future_value_direction_match_rate_pct") if source_bucket else None
    source_process_count = int(source_bucket.get("process_count") or 0) if source_bucket else 0
    source_process_rate = source_bucket.get("process_useful_rate_pct") if source_bucket else None
    type_count = int(type_bucket.get("measured_count") or 0) if type_bucket else 0
    type_rate = type_bucket.get("future_value_direction_match_rate_pct") if type_bucket else None

    if source_count >= 2 and source_rate is not None:
        _append_reason(
            reasons,
            f"Calibration adjusted confidence {confidence_delta:+.1f}: {calibration.get('source_key')} has {float(source_rate):.1f}% direction-match rate across {source_count} measured outcomes.",
        )
    elif source_process_count >= 2 and source_process_rate is not None:
        _append_reason(
            reasons,
            f"Calibration adjusted confidence {confidence_delta:+.1f}: {calibration.get('source_key')} has {float(source_process_rate):.1f}% useful process outcomes across {source_process_count} calibrated reviews.",
        )
    elif type_count >= 2 and type_rate is not None:
        _append_reason(
            reasons,
            f"Calibration adjusted confidence {confidence_delta:+.1f}: {calibration.get('type_key')} recommendations have {float(type_rate):.1f}% direction-match rate across {type_count} measured outcomes.",
        )


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


def _quality_payload(action_payload: dict[str, Any]) -> dict[str, Any]:
    quality = action_payload.get("quality")
    if isinstance(quality, dict):
        return quality
    return {}


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
    calibration_profile: dict[str, Any] | None = None,
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

    quality = _quality_payload(action_payload)
    quality_impact = quality.get("impact") if isinstance(quality.get("impact"), dict) else {}
    quality_impact_level = str(quality_impact.get("level") or "").strip().lower()
    if quality_impact_level == "high":
        impact += 6.0
        _append_reason(reasons, "Quality metadata marks this as high impact.")
    elif quality_impact_level == "medium":
        impact += 3.0
    elif quality_impact_level == "low":
        impact -= 2.0

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

        citation_quality = evidence.get("citation_quality")
        if isinstance(citation_quality, dict):
            citation_status = str(citation_quality.get("status") or "").strip().lower()
            citation_required = bool(citation_quality.get("required"))
            if citation_status == "satisfied":
                confidence += 10.0
                _append_reason(reasons, "Research symbols are dossier-cited with artifact references.")
            elif citation_status == "partial":
                confidence += 2.0
                _append_reason(reasons, "Research evidence citations are only partially complete.")
                if citation_required:
                    confidence -= 8.0
                    _append_reason(reasons, "Copilot recommendation is missing dossier coverage for some symbols.")
            elif citation_status == "missing":
                if citation_required:
                    confidence -= 18.0
                    _append_reason(reasons, "Copilot recommendation is missing required dossier evidence citations.")
                else:
                    confidence -= 4.0
                    _append_reason(reasons, "Recommendation has research symbols but no dossier citations.")

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

    if quality:
        confidence_score = _safe_float(quality.get("confidence_score"), -1.0)
        if confidence_score >= 0.0:
            confidence += round(confidence_score * 18.0, 2)
        confidence_level = str(quality.get("confidence_level") or "").strip().lower()
        if confidence_level == "high":
            confidence += 5.0
        elif confidence_level == "low":
            confidence -= 5.0

        freshness_status = str(quality.get("freshness_status") or "").strip().lower()
        if freshness_status == "fresh":
            confidence += 6.0
            _append_reason(reasons, "Quality metadata reports fresh evidence.")
        elif freshness_status == "stale":
            confidence -= 8.0
            _append_reason(reasons, "Quality metadata reports stale evidence.")
        elif freshness_status == "unknown":
            confidence -= 6.0
            _append_reason(reasons, "Quality metadata has unknown evidence freshness.")

        blocking_context = quality.get("blocking_context")
        blocking_count = len(blocking_context) if isinstance(blocking_context, list) else 0
        if blocking_count:
            confidence -= min(18.0, blocking_count * 6.0)
            _append_reason(reasons, "Recommendation is blocked by missing context.")

        if bool(quality.get("decision_grade")):
            confidence += 8.0
            _append_reason(reasons, "Recommendation is decision-grade based on quality metadata.")
        else:
            confidence -= 4.0

    calibration = _calibration_summary_for_row(row, calibration_profile)
    confidence += _safe_float(calibration.get("confidence_delta"), 0.0)
    _append_calibration_reason(reasons, calibration)

    urgency = {"high": 88.0, "medium": 58.0, "low": 32.0}[priority]
    if status == "proposed":
        urgency += min(14.0, float(age_days) * 1.5)
        if age_days >= 7:
            _append_reason(reasons, "Recommendation has remained open for multiple days.")
        urgency += {"plan_settings_update": 5.0, "workflow_action": 4.0, "general": 0.0}[recommendation_type]
    else:
        urgency = max(5.0, urgency - 30.0)

    reversibility = {"workflow_action": 82.0, "general": 72.0, "plan_settings_update": 56.0}[recommendation_type]
    if quality:
        actionability = str(quality.get("actionability") or "").strip().lower()
        if actionability == "previewable":
            urgency += 5.0
            confidence += 4.0
            _append_reason(reasons, "Recommendation can be previewed before apply.")
        elif actionability == "review_only":
            urgency += 2.0
            _append_reason(reasons, "Recommendation needs review before action.")
        elif actionability == "context_gathering":
            urgency -= 8.0
            _append_reason(reasons, "Recommendation gathers missing context before stronger advice.")

        quality_reversibility = str(quality.get("reversibility") or "").strip().lower()
        if quality_reversibility == "high":
            reversibility += 8.0
        elif quality_reversibility == "medium":
            reversibility += 2.0
        elif quality_reversibility == "low":
            reversibility -= 10.0

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
        "calibration": calibration,
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
    calibration_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    resolved_now = now or utc_now()
    calibration_profile = build_recommendation_calibration_profile(calibration_rows or rows)
    scored_rows: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        row["score"] = score_recommendation_row(row, now=resolved_now, calibration_profile=calibration_profile)
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
