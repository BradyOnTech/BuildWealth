from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from buildwealth_orchestrator.services.value_coercion import safe_float, utc_now_iso

PORTFOLIO_RISK_FACTORY_ID = "portfolio_risk_recommendation_factory"
PORTFOLIO_RISK_FACTORY_VERSION = "v1"
PORTFOLIO_RISK_SOURCE = "generator:portfolio_risk"
PLAN_TRACKING_FACTORY_ID = "plan_tracking_recommendation_factory"
PLAN_TRACKING_FACTORY_VERSION = "v1"
PLAN_TRACKING_SOURCE = "generator:plan_tracking"
CASH_LIQUIDITY_FACTORY_ID = "cash_liquidity_recommendation_factory"
CASH_LIQUIDITY_FACTORY_VERSION = "v1"
CASH_LIQUIDITY_SOURCE = "generator:cash_liquidity"
PROFILE_COMPLETENESS_FACTORY_ID = "profile_completeness_recommendation_factory"
PROFILE_COMPLETENESS_FACTORY_VERSION = "v1"
PROFILE_COMPLETENESS_SOURCE = "generator:profile_completeness"
STALE_ASSUMPTIONS_FACTORY_ID = "stale_assumption_recommendation_factory"
STALE_ASSUMPTIONS_FACTORY_VERSION = "v1"
STALE_ASSUMPTIONS_SOURCE = "generator:stale_assumptions"
WATCHLIST_RESEARCH_FACTORY_ID = "watchlist_research_recommendation_factory"
WATCHLIST_RESEARCH_FACTORY_VERSION = "v1"
WATCHLIST_RESEARCH_SOURCE = "generator:watchlist_research"
CASH_RESERVE_MIN_MONTHS = 3.0
CASH_RESERVE_MAX_MONTHS = 6.0
STALE_PLAN_REVIEW_DAYS = 90
STALE_DECISION_REVIEW_DAYS = 60


class RecommendationCreator(Protocol):
    def create(
        self,
        *,
        title: str,
        detail: str,
        priority: str = "medium",
        recommendation_type: str = "general",
        source: str = "manual",
        plan_id: str | None = None,
        action_payload: dict[str, Any] | None = None,
        status: str = "proposed",
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RecommendationFactoryResult:
    generated_count: int = 0
    skipped_count: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    created: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_count": self.generated_count,
            "skipped_count": self.skipped_count,
            "candidates": self.candidates,
            "created": self.created,
            "skipped": self.skipped,
            "dry_run": self.dry_run,
        }


def _now_iso(now: datetime | None) -> str:
    if now is None:
        return utc_now_iso()
    resolved = now
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).isoformat()


def _as_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        resolved = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            resolved = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc)


def _age_days(value: Any, *, now: datetime) -> int | None:
    parsed = _as_utc_datetime(value)
    if parsed is None:
        return None
    return max(0, int((now.astimezone(timezone.utc) - parsed).total_seconds() // 86_400))


def _clean_key(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text.lower().replace(" ", "_")


def _active_dedupe_keys(existing_recommendations: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for row in existing_recommendations:
        if str(row.get("status") or "proposed").strip().lower() != "proposed":
            continue
        payload = row.get("action_payload")
        if not isinstance(payload, dict):
            continue
        generator = payload.get("generator")
        if not isinstance(generator, dict):
            continue
        dedupe_key = str(generator.get("dedupe_key") or "").strip()
        if dedupe_key:
            keys.add(dedupe_key)
    return keys


def _priority_for_alert(alert: dict[str, Any]) -> str:
    state = str(alert.get("state") or "").strip().lower()
    severity = str(alert.get("severity") or "").strip().lower()
    if state == "breach" and severity in {"high", "medium"}:
        return "high"
    if state == "breach":
        return "medium"
    if state == "watch":
        return "medium"
    return "low"


def _signal_key(alert: dict[str, Any]) -> str:
    metric = str(alert.get("metric") or alert.get("id") or "risk").strip().lower()
    context = alert.get("context") if isinstance(alert.get("context"), dict) else {}
    if metric == "single_holding":
        return f"single_holding:{str(context.get('symbol') or 'unknown').strip().upper()}"
    if metric == "top3":
        symbols = context.get("symbols") if isinstance(context.get("symbols"), list) else []
        cleaned = ",".join(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip())
        return f"top3_holdings:{cleaned or 'portfolio'}"
    if metric == "account":
        return f"account:{_clean_key(context.get('account_id'))}"
    if metric == "asset_class":
        return f"asset_class:{_clean_key(context.get('asset_class'))}"
    if metric == "sector":
        return f"sector:{_clean_key(context.get('sector'))}"
    if metric == "region":
        return f"region:{_clean_key(context.get('region'))}"
    return _clean_key(metric)


def _dedupe_key(alert: dict[str, Any]) -> str:
    return f"portfolio_risk_alert:{_signal_key(alert)}"


def _format_pct(value: Any) -> str:
    numeric = safe_float(value, 0.0)
    return f"{numeric:.1f}%"


def _format_money(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:,.0f}"


def _format_signed_money(value: float | None) -> str:
    if value is None:
        return ""
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _freshness_status(snapshot_as_of: Any) -> str:
    return "fresh" if str(snapshot_as_of or "").strip() else "unknown"


def _quality_metadata(
    *,
    source: str,
    priority: str,
    evidence: dict[str, Any],
    suggested_action: dict[str, Any],
    expected_outcome: dict[str, Any],
    actionability: str,
    confidence_level: str,
    confidence_reasons: list[str],
    reversibility: str,
    blocking_context: list[str] | None = None,
) -> dict[str, Any]:
    snapshot_as_of = evidence.get("snapshot_as_of")
    freshness = _freshness_status(snapshot_as_of)
    impact_level = "high" if priority == "high" else ("medium" if priority == "medium" else "low")
    confidence_scores = {"high": 0.85, "medium": 0.65, "low": 0.4}
    actionability_reasons = {
        "previewable": ["This recommendation has a concrete suggested action that can be previewed before apply."],
        "review_only": ["This recommendation should be reviewed before any state change is made."],
        "context_gathering": ["This recommendation improves missing context before stronger advice is generated."],
    }
    freshness_reasons = (
        [f"Evidence snapshot is available as of {snapshot_as_of}."]
        if freshness == "fresh"
        else ["Evidence freshness is unknown because no source timestamp was available."]
    )
    return {
        "schema_version": 1,
        "source": source,
        "confidence_level": confidence_level,
        "confidence_score": confidence_scores.get(confidence_level, 0.4),
        "confidence_reasons": confidence_reasons,
        "freshness_status": freshness,
        "freshness_reasons": freshness_reasons,
        "actionability": actionability,
        "actionability_reasons": actionability_reasons.get(actionability, []),
        "reversibility": reversibility,
        "impact": {
            "level": impact_level,
            "summary": str(evidence.get("summary") or expected_outcome.get("expected_delta_context_quality") or "").strip(),
        },
        "blocking_context": blocking_context or [],
        "decision_grade": freshness != "unknown" and not blocking_context,
        "suggested_action_kind": suggested_action.get("kind"),
    }


def _excess_amount_usd(alert: dict[str, Any], total_market_value: float) -> float | None:
    if total_market_value <= 0:
        return None
    if str(alert.get("unit") or "").strip().lower() != "pct":
        return None
    observed = safe_float(alert.get("observed"), 0.0)
    threshold = safe_float(alert.get("threshold"), 0.0)
    if observed <= threshold:
        return None
    return round(total_market_value * ((observed - threshold) / 100.0), 2)


def _alert_subject(alert: dict[str, Any]) -> str:
    metric = str(alert.get("metric") or "").strip().lower()
    context = alert.get("context") if isinstance(alert.get("context"), dict) else {}
    if metric == "single_holding":
        return str(context.get("symbol") or "largest holding").strip().upper()
    if metric == "top3":
        symbols = context.get("symbols") if isinstance(context.get("symbols"), list) else []
        cleaned = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
        return ", ".join(cleaned[:3]) if cleaned else "top holdings"
    if metric == "account":
        return str(context.get("account_id") or "largest account").strip()
    if metric == "asset_class":
        return str(context.get("asset_class") or "largest asset class").strip()
    if metric == "sector":
        return str(context.get("sector") or "largest sector").strip()
    if metric == "region":
        return str(context.get("region") or "largest region").strip()
    return str(alert.get("label") or "portfolio concentration").strip()


def _suggested_action_kind(alert: dict[str, Any]) -> str:
    metric = str(alert.get("metric") or "").strip().lower()
    if metric == "single_holding":
        return "reduce_single_holding_concentration"
    if metric == "top3":
        return "reduce_top_holdings_concentration"
    if metric == "hhi":
        return "increase_position_diversification"
    if metric == "effective_positions":
        return "broaden_effective_positions"
    return "reduce_cluster_concentration"


def _title_for_alert(alert: dict[str, Any]) -> str:
    metric = str(alert.get("metric") or "").strip().lower()
    subject = _alert_subject(alert)
    if metric == "single_holding":
        return f"Reduce {subject} concentration risk"
    if metric == "top3":
        return "Reduce top holdings concentration"
    if metric == "hhi":
        return "Broaden portfolio diversification"
    if metric == "effective_positions":
        return "Increase effective portfolio positions"
    return f"Reduce {subject} concentration"


def _detail_for_alert(alert: dict[str, Any], *, estimated_amount_usd: float | None) -> str:
    subject = _alert_subject(alert)
    observed = _format_pct(alert.get("observed")) if alert.get("unit") == "pct" else str(alert.get("observed") or "-")
    threshold = _format_pct(alert.get("threshold")) if alert.get("unit") == "pct" else str(alert.get("threshold") or "-")
    base = f"{subject} is at {observed}, above the configured threshold of {threshold}."
    recommendation = str(alert.get("recommendation") or "").strip()
    if estimated_amount_usd is not None and estimated_amount_usd > 0:
        base += f" Consider redirecting or rebalancing about {_format_money(estimated_amount_usd)} to move back toward the threshold."
    elif recommendation:
        base += f" {recommendation}"
    return base


def _candidate_from_alert(
    alert: dict[str, Any],
    *,
    holdings_payload: dict[str, Any],
    generated_at: str,
    plan_id: str | None,
) -> dict[str, Any]:
    risk_payload = holdings_payload.get("risk_alerts") if isinstance(holdings_payload.get("risk_alerts"), dict) else {}
    metrics = risk_payload.get("metrics") if isinstance(risk_payload.get("metrics"), dict) else {}
    total_market_value = safe_float(metrics.get("total_market_value") or holdings_payload.get("total_value"), 0.0)
    estimated_amount_usd = _excess_amount_usd(alert, total_market_value)
    signal_key = _signal_key(alert)
    dedupe_key = _dedupe_key(alert)
    observed = safe_float(alert.get("observed"), 0.0)
    threshold = safe_float(alert.get("threshold"), 0.0)

    action_payload = {
        "generator": {
            "id": PORTFOLIO_RISK_FACTORY_ID,
            "version": PORTFOLIO_RISK_FACTORY_VERSION,
            "generated_at": generated_at,
            "signal_key": signal_key,
            "signal_type": "portfolio_risk_alert",
            "dedupe_key": dedupe_key,
            "severity": str(alert.get("state") or alert.get("severity") or "watch").strip().lower(),
        },
        "evidence": {
            "summary": str(alert.get("message") or "").strip(),
            "data_keys": ["portfolio.holdings", "portfolio.risk_alerts"],
            "snapshot_as_of": holdings_payload.get("updated_at") or risk_payload.get("generated_at"),
            "risk_alert": alert,
        },
        "suggested_action": {
            "kind": _suggested_action_kind(alert),
            "subject": _alert_subject(alert),
            "current_value": observed,
            "threshold": threshold,
            "unit": str(alert.get("unit") or "").strip().lower(),
            "estimated_rebalance_usd": estimated_amount_usd,
        },
        "expected_outcome": {
            "expected_delta_risk_score": -1 if str(alert.get("state") or "").strip().lower() == "breach" else 0,
            "expected_value_after": threshold,
            "unit": str(alert.get("unit") or "").strip().lower(),
        },
    }
    priority = _priority_for_alert(alert)
    action_payload["quality"] = _quality_metadata(
        source=PORTFOLIO_RISK_SOURCE,
        priority=priority,
        evidence=action_payload["evidence"],
        suggested_action=action_payload["suggested_action"],
        expected_outcome=action_payload["expected_outcome"],
        actionability="review_only",
        confidence_level="high" if action_payload["evidence"].get("snapshot_as_of") else "medium",
        confidence_reasons=[
            "Generated from structured portfolio holdings and configured risk thresholds.",
            "Recommendation is based on an active portfolio risk alert.",
        ],
        reversibility="medium",
    )

    return {
        "title": _title_for_alert(alert),
        "detail": _detail_for_alert(alert, estimated_amount_usd=estimated_amount_usd),
        "priority": priority,
        "recommendation_type": "workflow_action",
        "source": PORTFOLIO_RISK_SOURCE,
        "plan_id": plan_id,
        "action_payload": action_payload,
    }


def generate_portfolio_risk_recommendations(
    *,
    holdings_payload: dict[str, Any],
    existing_recommendations: list[dict[str, Any]],
    creator: RecommendationCreator | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> RecommendationFactoryResult:
    risk_payload = holdings_payload.get("risk_alerts") if isinstance(holdings_payload.get("risk_alerts"), dict) else {}
    alerts = risk_payload.get("alerts") if isinstance(risk_payload.get("alerts"), list) else []
    active_alerts = [
        alert
        for alert in alerts
        if isinstance(alert, dict) and str(alert.get("state") or "").strip().lower() in {"breach", "watch"}
    ]
    generated_at = _now_iso(now)
    active_keys = _active_dedupe_keys(existing_recommendations)
    bounded_limit = max(1, min(int(limit), 50))

    candidates: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for alert in active_alerts:
        dedupe_key = _dedupe_key(alert)
        if dedupe_key in active_keys:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "active_duplicate",
                    "title": _title_for_alert(alert),
                    "signal_key": _signal_key(alert),
                }
            )
            continue
        if len(candidates) >= bounded_limit:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "limit_exceeded",
                    "title": _title_for_alert(alert),
                    "signal_key": _signal_key(alert),
                }
            )
            continue

        candidate = _candidate_from_alert(alert, holdings_payload=holdings_payload, generated_at=generated_at, plan_id=plan_id)
        candidates.append(candidate)
        active_keys.add(dedupe_key)

        if not dry_run and creator is not None:
            created.append(
                creator.create(
                    title=candidate["title"],
                    detail=candidate["detail"],
                    priority=candidate["priority"],
                    recommendation_type=candidate["recommendation_type"],
                    source=candidate["source"],
                    plan_id=candidate["plan_id"],
                    action_payload=candidate["action_payload"],
                    status="proposed",
                )
            )

    return RecommendationFactoryResult(
        generated_count=len(created) if not dry_run else len(candidates),
        skipped_count=len(skipped),
        candidates=candidates,
        created=created,
        skipped=skipped,
        dry_run=dry_run,
    )


def _plan_tracking_dedupe_key(plan_id: str, signal_key: str) -> str:
    return f"plan_tracking:{_clean_key(plan_id, 'active_plan')}:{signal_key}"


def _plan_tracking_generator_payload(
    *,
    generated_at: str,
    signal_key: str,
    severity: str,
    dedupe_key: str,
) -> dict[str, Any]:
    return {
        "id": PLAN_TRACKING_FACTORY_ID,
        "version": PLAN_TRACKING_FACTORY_VERSION,
        "generated_at": generated_at,
        "signal_key": signal_key,
        "signal_type": "plan_tracking",
        "dedupe_key": dedupe_key,
        "severity": severity,
    }


def _plan_tracking_evidence(
    plan_tracking_payload: dict[str, Any],
    *,
    summary: str,
) -> dict[str, Any]:
    plan_settings = plan_tracking_payload.get("plan_settings")
    return {
        "summary": summary,
        "data_keys": ["plan.tracking", "plan.settings", "portfolio.snapshots"],
        "snapshot_as_of": plan_tracking_payload.get("window_end"),
        "plan_title": plan_tracking_payload.get("plan_title"),
        "plan_tracking": plan_tracking_payload,
        "plan_settings": plan_settings if isinstance(plan_settings, dict) else {},
    }


def _plan_title(plan_tracking_payload: dict[str, Any]) -> str:
    return str(plan_tracking_payload.get("plan_title") or "Active Plan").strip() or "Active Plan"


def _plan_id(plan_tracking_payload: dict[str, Any]) -> str:
    return str(plan_tracking_payload.get("plan_id") or "active_plan").strip() or "active_plan"


def _nested_float(
    payload: dict[str, Any],
    section_key: str,
    value_key: str,
) -> float | None:
    section = payload.get(section_key)
    if not isinstance(section, dict) or value_key not in section or section.get(value_key) is None:
        return None
    return safe_float(section.get(value_key), 0.0)


def _current_annual_contribution_usd(plan_tracking_payload: dict[str, Any]) -> float:
    direct_plan_setting = _nested_float(plan_tracking_payload, "plan_settings", "annual_contribution_usd")
    if direct_plan_setting is not None:
        return max(0.0, direct_plan_setting)

    planner_default = _nested_float(plan_tracking_payload, "planner_defaults", "annual_contribution_usd")
    if planner_default is not None:
        return max(0.0, planner_default)

    tracking_window_days = safe_float(plan_tracking_payload.get("tracking_window_days"), 0.0)
    expected_contributions = safe_float(plan_tracking_payload.get("expected_contributions_usd"), 0.0)
    if tracking_window_days <= 0 or expected_contributions <= 0:
        return 0.0

    plan_hsa_extra = _nested_float(plan_tracking_payload, "plan_settings", "hsa_extra_contribution_usd")
    default_hsa_extra = _nested_float(plan_tracking_payload, "planner_defaults", "hsa_extra_contribution_usd")
    hsa_extra = plan_hsa_extra if plan_hsa_extra is not None else (default_hsa_extra or 0.0)
    inferred_total_annual_contribution = expected_contributions * 365.0 / tracking_window_days
    return max(0.0, inferred_total_annual_contribution - max(0.0, hsa_extra))


def _candidate_from_plan_tracking(
    plan_tracking_payload: dict[str, Any],
    *,
    signal_key: str,
    title: str,
    detail: str,
    priority: str,
    recommendation_type: str,
    generated_at: str,
    severity: str,
    suggested_action: dict[str, Any],
    expected_outcome: dict[str, Any],
    plan_settings_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_id = _plan_id(plan_tracking_payload)
    dedupe_key = _plan_tracking_dedupe_key(plan_id, signal_key)
    evidence = _plan_tracking_evidence(plan_tracking_payload, summary=detail)
    action_payload = {
        "generator": _plan_tracking_generator_payload(
            generated_at=generated_at,
            signal_key=signal_key,
            severity=severity,
            dedupe_key=dedupe_key,
        ),
        "evidence": evidence,
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
    }
    action_payload["quality"] = _quality_metadata(
        source=PLAN_TRACKING_SOURCE,
        priority=priority,
        evidence=evidence,
        suggested_action=suggested_action,
        expected_outcome=expected_outcome,
        actionability="previewable" if recommendation_type == "plan_settings_update" else "review_only",
        confidence_level="high" if evidence.get("snapshot_as_of") else "medium",
        confidence_reasons=[
            "Generated from plan tracking status, plan settings, and portfolio snapshot history.",
            "Signal uses structured plan-vs-actual metrics.",
        ],
        reversibility="high" if recommendation_type == "plan_settings_update" else "medium",
    )
    if plan_settings_updates:
        action_payload["plan_settings_updates"] = plan_settings_updates
    return {
        "title": title,
        "detail": detail,
        "priority": priority,
        "recommendation_type": recommendation_type,
        "source": PLAN_TRACKING_SOURCE,
        "plan_id": plan_id,
        "action_payload": action_payload,
    }


def _plan_tracking_candidates(plan_tracking_payload: dict[str, Any], *, generated_at: str) -> list[dict[str, Any]]:
    plan_title = _plan_title(plan_tracking_payload)
    status = str(plan_tracking_payload.get("status") or "").strip().lower()
    tracking_window_days = int(safe_float(plan_tracking_payload.get("tracking_window_days"), 0.0))
    snapshot_count = int(safe_float(plan_tracking_payload.get("snapshot_count"), 0.0))
    contribution_pace_pct = safe_float(plan_tracking_payload.get("contribution_pace_pct"), 0.0)
    expected_contributions = safe_float(plan_tracking_payload.get("expected_contributions_usd"), 0.0)
    actual_contributions = safe_float(plan_tracking_payload.get("actual_contributions_usd"), 0.0)
    return_drift_pct = safe_float(plan_tracking_payload.get("return_drift_pct"), 0.0)
    actual_return_pct = safe_float(plan_tracking_payload.get("actual_annualized_return_pct"), 0.0)
    expected_return_pct = safe_float(plan_tracking_payload.get("expected_annualized_return_pct"), 0.0)
    value_drift_usd = safe_float(plan_tracking_payload.get("value_drift_usd"), 0.0)
    value_drift_pct = safe_float(plan_tracking_payload.get("value_drift_pct"), 0.0)
    current_value = safe_float(plan_tracking_payload.get("current_value_usd"), 0.0)
    projected_value = safe_float(plan_tracking_payload.get("projected_value_usd"), 0.0)

    candidates: list[dict[str, Any]] = []

    if status == "insufficient_data":
        detail = (
            f"{plan_title} needs more tracking history before BuildWealth can judge plan progress. "
            f"Current tracking has {snapshot_count} snapshot{'s' if snapshot_count != 1 else ''} over {tracking_window_days} days."
        )
        candidates.append(
            _candidate_from_plan_tracking(
                plan_tracking_payload,
                signal_key="insufficient_data",
                title=f"Build tracking history for {plan_title}",
                detail=detail,
                priority="low",
                recommendation_type="workflow_action",
                generated_at=generated_at,
                severity="watch",
                suggested_action={
                    "kind": "build_plan_tracking_history",
                    "subject": plan_title,
                    "current_value": snapshot_count,
                    "threshold": 2,
                    "unit": "snapshots",
                },
                expected_outcome={
                    "expected_delta_plan_status": "trackable",
                    "expected_snapshot_count_min": 2,
                },
            )
        )
        return candidates

    if expected_contributions > 0 and contribution_pace_pct < 90:
        shortfall = max(expected_contributions - actual_contributions, 0.0)
        estimated_monthly_increase = round(shortfall / max(tracking_window_days, 1) * 30.4375, 2)
        current_annual_contribution = round(_current_annual_contribution_usd(plan_tracking_payload), 2)
        proposed_annual_contribution = round(current_annual_contribution + (estimated_monthly_increase * 12.0), 2)
        priority = "high" if contribution_pace_pct < 60 else "medium"
        detail = (
            f"{plan_title} contribution pace is {_format_pct(contribution_pace_pct)} of target "
            f"({_format_money(actual_contributions)} actual vs {_format_money(expected_contributions)} expected). "
            f"Consider increasing annual plan contributions from {_format_money(current_annual_contribution)} "
            f"to {_format_money(proposed_annual_contribution)} — about {_format_money(estimated_monthly_increase)}/month — "
            "until the gap closes."
        )
        candidates.append(
            _candidate_from_plan_tracking(
                plan_tracking_payload,
                signal_key="contribution_pace",
                title=f"Increase contributions for {plan_title}",
                detail=detail,
                priority=priority,
                recommendation_type="plan_settings_update",
                generated_at=generated_at,
                severity="breach" if priority == "high" else "watch",
                suggested_action={
                    "kind": "increase_plan_contributions",
                    "subject": plan_title,
                    "current_value": contribution_pace_pct,
                    "threshold": 90,
                    "unit": "pct",
                    "estimated_monthly_contribution_increase_usd": estimated_monthly_increase,
                    "contribution_shortfall_usd": round(shortfall, 2),
                    "current_annual_contribution_usd": current_annual_contribution,
                    "proposed_annual_contribution_usd": proposed_annual_contribution,
                },
                expected_outcome={
                    "expected_delta_plan_status": "improved_contribution_pace",
                    "expected_contribution_pace_pct": 90,
                    "expected_delta_annual_contribution_usd": round(
                        proposed_annual_contribution - current_annual_contribution,
                        2,
                    ),
                },
                plan_settings_updates={
                    "annual_contribution_usd": proposed_annual_contribution,
                },
            )
        )

    if status == "behind" and return_drift_pct <= -2:
        priority = "high" if return_drift_pct <= -5 else "medium"
        detail = (
            f"{plan_title} is behind its return assumption: actual annualized return is {_format_pct(actual_return_pct)} "
            f"vs {_format_pct(expected_return_pct)} expected, a {_format_pct(return_drift_pct)} drift."
        )
        candidates.append(
            _candidate_from_plan_tracking(
                plan_tracking_payload,
                signal_key="return_drift",
                title=f"Review plan assumptions for {plan_title}",
                detail=detail,
                priority=priority,
                recommendation_type="workflow_action",
                generated_at=generated_at,
                severity="breach" if priority == "high" else "watch",
                suggested_action={
                    "kind": "review_return_drift",
                    "subject": plan_title,
                    "current_value": actual_return_pct,
                    "threshold": expected_return_pct,
                    "unit": "pct",
                    "return_drift_pct": return_drift_pct,
                },
                expected_outcome={
                    "expected_delta_plan_status": "validated_assumptions",
                    "expected_return_drift_pct": -2,
                },
            )
        )

    if value_drift_pct <= -5:
        priority = "high" if value_drift_pct <= -10 else "medium"
        detail = (
            f"{plan_title} is {_format_signed_money(value_drift_usd)} below projected value "
            f"({_format_pct(value_drift_pct)} drift; {_format_money(current_value)} current vs {_format_money(projected_value)} projected)."
        )
        candidates.append(
            _candidate_from_plan_tracking(
                plan_tracking_payload,
                signal_key="value_drift",
                title=f"Close plan value gap for {plan_title}",
                detail=detail,
                priority=priority,
                recommendation_type="workflow_action",
                generated_at=generated_at,
                severity="breach" if priority == "high" else "watch",
                suggested_action={
                    "kind": "close_plan_value_gap",
                    "subject": plan_title,
                    "current_value": current_value,
                    "threshold": projected_value,
                    "unit": "usd",
                    "value_drift_usd": round(value_drift_usd, 2),
                    "value_drift_pct": value_drift_pct,
                },
                expected_outcome={
                    "expected_delta_plan_status": "gap_reviewed",
                    "expected_value_drift_pct_min": -5,
                },
            )
        )

    if status == "ahead" and value_drift_usd > 0:
        detail = (
            f"{plan_title} is {_format_money(value_drift_usd)} ahead of projected value. "
            "Review whether to preserve the surplus, reduce risk, or accelerate goals."
        )
        candidates.append(
            _candidate_from_plan_tracking(
                plan_tracking_payload,
                signal_key="ahead",
                title=f"Review surplus strategy for {plan_title}",
                detail=detail,
                priority="low",
                recommendation_type="workflow_action",
                generated_at=generated_at,
                severity="opportunity",
                suggested_action={
                    "kind": "review_plan_surplus_strategy",
                    "subject": plan_title,
                    "current_value": current_value,
                    "threshold": projected_value,
                    "unit": "usd",
                    "value_drift_usd": round(value_drift_usd, 2),
                },
                expected_outcome={
                    "expected_delta_plan_status": "surplus_strategy_reviewed",
                },
            )
        )

    return candidates


def generate_plan_tracking_recommendations(
    *,
    plan_tracking_payload: dict[str, Any],
    existing_recommendations: list[dict[str, Any]],
    creator: RecommendationCreator | None = None,
    dry_run: bool = True,
    limit: int = 10,
    now: datetime | None = None,
) -> RecommendationFactoryResult:
    generated_at = _now_iso(now)
    active_keys = _active_dedupe_keys(existing_recommendations)
    bounded_limit = max(1, min(int(limit), 50))

    candidates: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in _plan_tracking_candidates(plan_tracking_payload, generated_at=generated_at):
        generator = candidate.get("action_payload", {}).get("generator", {})
        dedupe_key = str(generator.get("dedupe_key") or "").strip()
        signal_key = str(generator.get("signal_key") or "").strip()
        if dedupe_key in active_keys:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "active_duplicate",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
            continue
        if len(candidates) >= bounded_limit:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "limit_exceeded",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
            continue

        candidates.append(candidate)
        active_keys.add(dedupe_key)

        if not dry_run and creator is not None:
            created.append(
                creator.create(
                    title=candidate["title"],
                    detail=candidate["detail"],
                    priority=candidate["priority"],
                    recommendation_type=candidate["recommendation_type"],
                    source=candidate["source"],
                    plan_id=candidate["plan_id"],
                    action_payload=candidate["action_payload"],
                    status="proposed",
                )
            )

    return RecommendationFactoryResult(
        generated_count=len(created) if not dry_run else len(candidates),
        skipped_count=len(skipped),
        candidates=candidates,
        created=created,
        skipped=skipped,
        dry_run=dry_run,
    )


def _monthly_expenses_usd(financial_profile_payload: dict[str, Any]) -> float:
    expenses = financial_profile_payload.get("expense_items")
    if not isinstance(expenses, list):
        return 0.0
    return round(sum(safe_float(item.get("monthly_amount_usd"), 0.0) for item in expenses if isinstance(item, dict)), 2)


def _monthly_debt_minimums_usd(financial_profile_payload: dict[str, Any]) -> float:
    debts = financial_profile_payload.get("debt_items")
    if not isinstance(debts, list):
        return 0.0
    total = 0.0
    for item in debts:
        if not isinstance(item, dict):
            continue
        custom_payment = item.get("custom_monthly_payment_usd")
        minimum_payment = item.get("minimum_payment_usd")
        total += safe_float(custom_payment if custom_payment is not None else minimum_payment, 0.0)
    return round(total, 2)


def _cash_liquidity_dedupe_key(signal_key: str) -> str:
    return f"cash_liquidity:{signal_key}"


def _cash_liquidity_generator_payload(
    *,
    generated_at: str,
    signal_key: str,
    severity: str,
) -> dict[str, Any]:
    return {
        "id": CASH_LIQUIDITY_FACTORY_ID,
        "version": CASH_LIQUIDITY_FACTORY_VERSION,
        "generated_at": generated_at,
        "signal_key": signal_key,
        "signal_type": "cash_liquidity",
        "dedupe_key": _cash_liquidity_dedupe_key(signal_key),
        "severity": severity,
    }


def _cash_liquidity_evidence(
    *,
    summary: str,
    holdings_payload: dict[str, Any],
    financial_profile_payload: dict[str, Any],
    monthly_expenses: float,
    monthly_debt_minimums: float,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "data_keys": ["portfolio.holdings", "portfolio.cash", "financial_profile.expenses", "financial_profile.debts"],
        "snapshot_as_of": holdings_payload.get("updated_at") or holdings_payload.get("prices_updated_at"),
        "cash_liquidity": {
            "total_cash_usd": round(safe_float(holdings_payload.get("total_cash"), 0.0), 2),
            "monthly_expenses_usd": monthly_expenses,
            "monthly_debt_minimums_usd": monthly_debt_minimums,
            "monthly_outflow_usd": round(monthly_expenses + monthly_debt_minimums, 2),
            "account_cash": holdings_payload.get("account_cash") if isinstance(holdings_payload.get("account_cash"), dict) else {},
        },
        "financial_profile": {
            "updated_at": financial_profile_payload.get("updated_at"),
            "expense_items_count": len(financial_profile_payload.get("expense_items", []))
            if isinstance(financial_profile_payload.get("expense_items"), list)
            else 0,
            "debt_items_count": len(financial_profile_payload.get("debt_items", []))
            if isinstance(financial_profile_payload.get("debt_items"), list)
            else 0,
        },
    }


def _cash_liquidity_candidate(
    *,
    signal_key: str,
    title: str,
    detail: str,
    priority: str,
    generated_at: str,
    severity: str,
    suggested_action: dict[str, Any],
    expected_outcome: dict[str, Any],
    holdings_payload: dict[str, Any],
    financial_profile_payload: dict[str, Any],
    monthly_expenses: float,
    monthly_debt_minimums: float,
    plan_id: str | None,
) -> dict[str, Any]:
    evidence = _cash_liquidity_evidence(
        summary=detail,
        holdings_payload=holdings_payload,
        financial_profile_payload=financial_profile_payload,
        monthly_expenses=monthly_expenses,
        monthly_debt_minimums=monthly_debt_minimums,
    )
    action_payload = {
        "generator": _cash_liquidity_generator_payload(
            generated_at=generated_at,
            signal_key=signal_key,
            severity=severity,
        ),
        "evidence": evidence,
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
    }
    blocking_context = ["financial_profile.outflows"] if signal_key == "profile_outflow_missing" else []
    action_payload["quality"] = _quality_metadata(
        source=CASH_LIQUIDITY_SOURCE,
        priority=priority,
        evidence=evidence,
        suggested_action=suggested_action,
        expected_outcome=expected_outcome,
        actionability="context_gathering" if blocking_context else "review_only",
        confidence_level="high" if evidence.get("snapshot_as_of") and not blocking_context else "medium",
        confidence_reasons=[
            "Generated from portfolio cash plus financial-profile expense and debt outflow data.",
            "Reserve thresholds use the configured 3-to-6-month liquidity band.",
        ],
        reversibility="high",
        blocking_context=blocking_context,
    )
    return {
        "title": title,
        "detail": detail,
        "priority": priority,
        "recommendation_type": "workflow_action",
        "source": CASH_LIQUIDITY_SOURCE,
        "plan_id": plan_id,
        "action_payload": action_payload,
    }


def _cash_liquidity_candidates(
    *,
    holdings_payload: dict[str, Any],
    financial_profile_payload: dict[str, Any],
    generated_at: str,
    plan_id: str | None,
) -> list[dict[str, Any]]:
    total_cash = round(safe_float(holdings_payload.get("total_cash"), 0.0), 2)
    monthly_expenses = _monthly_expenses_usd(financial_profile_payload)
    monthly_debt_minimums = _monthly_debt_minimums_usd(financial_profile_payload)
    monthly_outflow = round(monthly_expenses + monthly_debt_minimums, 2)
    candidates: list[dict[str, Any]] = []

    if monthly_outflow <= 0:
        detail = (
            "BuildWealth cannot evaluate emergency-fund coverage yet because no monthly expenses or debt minimums "
            "are configured in the financial profile."
        )
        candidates.append(
            _cash_liquidity_candidate(
                signal_key="profile_outflow_missing",
                title="Complete cash-flow profile for liquidity review",
                detail=detail,
                priority="low",
                generated_at=generated_at,
                severity="watch",
                suggested_action={
                    "kind": "complete_financial_profile_outflows",
                    "subject": "financial profile",
                    "current_value": monthly_outflow,
                    "threshold": 1,
                    "unit": "monthly_outflow_usd",
                },
                expected_outcome={
                    "expected_delta_context_quality": "liquidity_review_enabled",
                },
                holdings_payload=holdings_payload,
                financial_profile_payload=financial_profile_payload,
                monthly_expenses=monthly_expenses,
                monthly_debt_minimums=monthly_debt_minimums,
                plan_id=plan_id,
            )
        )
        return candidates

    cash_months = round(total_cash / monthly_outflow, 2)
    minimum_reserve = round(monthly_outflow * CASH_RESERVE_MIN_MONTHS, 2)
    maximum_reserve = round(monthly_outflow * CASH_RESERVE_MAX_MONTHS, 2)

    if total_cash < 0:
        detail = (
            f"Cash is negative at {_format_signed_money(total_cash)} while monthly outflows are about "
            f"{_format_money(monthly_outflow)}. Rebuild cash above zero before adding new investing commitments."
        )
        candidates.append(
            _cash_liquidity_candidate(
                signal_key="negative_cash",
                title="Restore positive cash balance",
                detail=detail,
                priority="high",
                generated_at=generated_at,
                severity="breach",
                suggested_action={
                    "kind": "restore_positive_cash_balance",
                    "subject": "cash reserve",
                    "current_value": total_cash,
                    "threshold": 0,
                    "unit": "usd",
                    "cash_shortfall_usd": round(abs(total_cash), 2),
                    "monthly_outflow_usd": monthly_outflow,
                    "liquidity_months": cash_months,
                },
                expected_outcome={
                    "expected_delta_liquidity_status": "cash_positive",
                    "target_cash_reserve_usd": 0,
                },
                holdings_payload=holdings_payload,
                financial_profile_payload=financial_profile_payload,
                monthly_expenses=monthly_expenses,
                monthly_debt_minimums=monthly_debt_minimums,
                plan_id=plan_id,
            )
        )
        return candidates

    if cash_months < CASH_RESERVE_MIN_MONTHS:
        shortfall = round(max(minimum_reserve - total_cash, 0.0), 2)
        priority = "high" if cash_months < 1 else "medium"
        detail = (
            f"Cash covers about {cash_months:.1f} month{'s' if cash_months != 1 else ''} of outflows "
            f"({_format_money(total_cash)} cash vs {_format_money(monthly_outflow)}/month). "
            f"Build toward a 3-month reserve of {_format_money(minimum_reserve)}, a gap of {_format_money(shortfall)}."
        )
        candidates.append(
            _cash_liquidity_candidate(
                signal_key="emergency_fund_shortfall",
                title="Build emergency cash reserve",
                detail=detail,
                priority=priority,
                generated_at=generated_at,
                severity="breach" if priority == "high" else "watch",
                suggested_action={
                    "kind": "build_emergency_cash_reserve",
                    "subject": "cash reserve",
                    "current_value": cash_months,
                    "threshold": CASH_RESERVE_MIN_MONTHS,
                    "unit": "months",
                    "current_cash_usd": total_cash,
                    "target_cash_reserve_usd": minimum_reserve,
                    "cash_shortfall_usd": shortfall,
                    "monthly_outflow_usd": monthly_outflow,
                },
                expected_outcome={
                    "expected_delta_liquidity_months": round(CASH_RESERVE_MIN_MONTHS - cash_months, 2),
                    "target_liquidity_months": CASH_RESERVE_MIN_MONTHS,
                },
                holdings_payload=holdings_payload,
                financial_profile_payload=financial_profile_payload,
                monthly_expenses=monthly_expenses,
                monthly_debt_minimums=monthly_debt_minimums,
                plan_id=plan_id,
            )
        )
        return candidates

    if cash_months > CASH_RESERVE_MAX_MONTHS:
        excess_cash = round(max(total_cash - maximum_reserve, 0.0), 2)
        if excess_cash <= 0:
            return candidates
        priority = "medium" if cash_months >= 12 else "low"
        detail = (
            f"Cash covers about {cash_months:.1f} months of outflows. That is above the 6-month reserve "
            f"target of {_format_money(maximum_reserve)}, leaving about {_format_money(excess_cash)} to review for goals, debt payoff, or investing."
        )
        candidates.append(
            _cash_liquidity_candidate(
                signal_key="excess_idle_cash",
                title="Review excess idle cash",
                detail=detail,
                priority=priority,
                generated_at=generated_at,
                severity="opportunity",
                suggested_action={
                    "kind": "review_excess_idle_cash",
                    "subject": "cash reserve",
                    "current_value": cash_months,
                    "threshold": CASH_RESERVE_MAX_MONTHS,
                    "unit": "months",
                    "current_cash_usd": total_cash,
                    "target_cash_reserve_usd": maximum_reserve,
                    "excess_cash_usd": excess_cash,
                    "monthly_outflow_usd": monthly_outflow,
                },
                expected_outcome={
                    "expected_delta_cash_drag_usd": -excess_cash,
                    "target_liquidity_months": CASH_RESERVE_MAX_MONTHS,
                },
                holdings_payload=holdings_payload,
                financial_profile_payload=financial_profile_payload,
                monthly_expenses=monthly_expenses,
                monthly_debt_minimums=monthly_debt_minimums,
                plan_id=plan_id,
            )
        )

    return candidates


def generate_cash_liquidity_recommendations(
    *,
    holdings_payload: dict[str, Any],
    financial_profile_payload: dict[str, Any],
    existing_recommendations: list[dict[str, Any]],
    creator: RecommendationCreator | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> RecommendationFactoryResult:
    generated_at = _now_iso(now)
    active_keys = _active_dedupe_keys(existing_recommendations)
    bounded_limit = max(1, min(int(limit), 50))

    candidates: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in _cash_liquidity_candidates(
        holdings_payload=holdings_payload,
        financial_profile_payload=financial_profile_payload,
        generated_at=generated_at,
        plan_id=plan_id,
    ):
        generator = candidate.get("action_payload", {}).get("generator", {})
        dedupe_key = str(generator.get("dedupe_key") or "").strip()
        signal_key = str(generator.get("signal_key") or "").strip()
        if dedupe_key in active_keys:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "active_duplicate",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
            continue
        if len(candidates) >= bounded_limit:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "limit_exceeded",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
            continue

        candidates.append(candidate)
        active_keys.add(dedupe_key)

        if not dry_run and creator is not None:
            created.append(
                creator.create(
                    title=candidate["title"],
                    detail=candidate["detail"],
                    priority=candidate["priority"],
                    recommendation_type=candidate["recommendation_type"],
                    source=candidate["source"],
                    plan_id=candidate["plan_id"],
                    action_payload=candidate["action_payload"],
                    status="proposed",
                )
            )

    return RecommendationFactoryResult(
        generated_count=len(created) if not dry_run else len(candidates),
        skipped_count=len(skipped),
        candidates=candidates,
        created=created,
        skipped=skipped,
        dry_run=dry_run,
    )


def _profile_completeness_dedupe_key(gap_key: str) -> str:
    return f"profile_completeness:{_clean_key(gap_key)}"


def _profile_completeness_candidate(
    *,
    profile_readiness_payload: dict[str, Any],
    generated_at: str,
    plan_id: str | None,
) -> dict[str, Any] | None:
    gap_key = str(profile_readiness_payload.get("next_gap_key") or "").strip()
    gap_title = str(profile_readiness_payload.get("next_gap_title") or "").strip()
    gap_detail = str(profile_readiness_payload.get("next_gap_detail") or "").strip()
    if not gap_key:
        return None

    blocking_sources = profile_readiness_payload.get("blocking_recommendation_sources")
    if not isinstance(blocking_sources, list):
        blocking_sources = []
    cleaned_sources = [str(item).strip() for item in blocking_sources if str(item).strip()]
    readiness_status = str(profile_readiness_payload.get("status") or "incomplete").strip().lower()
    completion_percent = safe_float(profile_readiness_payload.get("completion_percent"), 0.0)
    dedupe_key = _profile_completeness_dedupe_key(gap_key)
    title = f"Complete {gap_title or gap_key.replace('_', ' ')}"
    source_text = ", ".join(source.replace("_", " ") for source in cleaned_sources[:3])
    detail = gap_detail or "Complete this profile section so BuildWealth can improve recommendation quality."
    if source_text:
        detail = f"{detail} This unlocks better {source_text} recommendations."

    action_payload = {
        "generator": {
            "id": PROFILE_COMPLETENESS_FACTORY_ID,
            "version": PROFILE_COMPLETENESS_FACTORY_VERSION,
            "generated_at": generated_at,
            "signal_key": gap_key,
            "signal_type": "profile_readiness_gap",
            "dedupe_key": dedupe_key,
            "severity": "blocking" if cleaned_sources else readiness_status,
        },
        "evidence": {
            "summary": detail,
            "data_keys": ["financial_profile.readiness"],
            "profile_readiness_status": readiness_status,
            "profile_completion_percent": completion_percent,
            "next_gap_key": gap_key,
            "next_gap_title": gap_title,
            "next_gap_detail": gap_detail,
            "blocking_recommendation_sources": cleaned_sources,
            "sections": profile_readiness_payload.get("sections") if isinstance(profile_readiness_payload.get("sections"), list) else [],
        },
        "suggested_action": {
            "kind": "complete_profile_section",
            "subject": gap_key,
            "title": gap_title,
            "detail": gap_detail,
        },
        "expected_outcome": {
            "expected_delta_context_quality": "profile_readiness_improved",
            "enabled_recommendation_sources": cleaned_sources,
        },
    }
    action_payload["quality"] = _quality_metadata(
        source=PROFILE_COMPLETENESS_SOURCE,
        priority="medium" if cleaned_sources else "low",
        evidence=action_payload["evidence"],
        suggested_action=action_payload["suggested_action"],
        expected_outcome=action_payload["expected_outcome"],
        actionability="context_gathering",
        confidence_level="high",
        confidence_reasons=[
            "Generated from the structured profile readiness model.",
            "The gap is the next blocking profile section in readiness order.",
        ],
        reversibility="high",
        blocking_context=[f"financial_profile.{gap_key}"],
    )
    return {
        "title": title,
        "detail": detail,
        "priority": "medium" if cleaned_sources else "low",
        "recommendation_type": "workflow_action",
        "source": PROFILE_COMPLETENESS_SOURCE,
        "plan_id": plan_id,
        "action_payload": action_payload,
    }


def generate_profile_completeness_recommendations(
    *,
    profile_readiness_payload: dict[str, Any],
    existing_recommendations: list[dict[str, Any]],
    creator: RecommendationCreator | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> RecommendationFactoryResult:
    generated_at = _now_iso(now)
    active_keys = _active_dedupe_keys(existing_recommendations)
    bounded_limit = max(1, min(int(limit), 50))

    candidates: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    candidate = _profile_completeness_candidate(
        profile_readiness_payload=profile_readiness_payload,
        generated_at=generated_at,
        plan_id=plan_id,
    )
    if candidate is not None:
        generator = candidate.get("action_payload", {}).get("generator", {})
        dedupe_key = str(generator.get("dedupe_key") or "").strip()
        signal_key = str(generator.get("signal_key") or "").strip()
        if dedupe_key in active_keys:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "active_duplicate",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
        elif len(candidates) >= bounded_limit:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "limit_exceeded",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
        else:
            candidates.append(candidate)
            active_keys.add(dedupe_key)
            if not dry_run and creator is not None:
                created.append(
                    creator.create(
                        title=candidate["title"],
                        detail=candidate["detail"],
                        priority=candidate["priority"],
                        recommendation_type=candidate["recommendation_type"],
                        source=candidate["source"],
                        plan_id=candidate["plan_id"],
                        action_payload=candidate["action_payload"],
                        status="proposed",
                    )
                )

    return RecommendationFactoryResult(
        generated_count=len(created) if not dry_run else len(candidates),
        skipped_count=len(skipped),
        candidates=candidates,
        created=created,
        skipped=skipped,
        dry_run=dry_run,
    )


def _stale_assumption_plan_id(plan_detail_payload: dict[str, Any], plan_tracking_payload: dict[str, Any]) -> str:
    return str(plan_detail_payload.get("id") or plan_tracking_payload.get("plan_id") or "active_plan").strip() or "active_plan"


def _stale_assumption_plan_title(plan_detail_payload: dict[str, Any], plan_tracking_payload: dict[str, Any]) -> str:
    return str(plan_detail_payload.get("title") or plan_tracking_payload.get("plan_title") or "Active Plan").strip() or "Active Plan"


def _stale_assumption_dedupe_key(plan_id: str, signal_key: str) -> str:
    return f"stale_assumptions:{_clean_key(plan_id, 'active_plan')}:{_clean_key(signal_key)}"


def _stale_assumption_candidate(
    *,
    plan_id: str,
    signal_key: str,
    title: str,
    detail: str,
    priority: str,
    severity: str,
    actionability: str,
    suggested_action: dict[str, Any],
    expected_outcome: dict[str, Any],
    evidence_extra: dict[str, Any],
    generated_at: str,
    blocking_context: list[str] | None = None,
) -> dict[str, Any]:
    dedupe_key = _stale_assumption_dedupe_key(plan_id, signal_key)
    evidence = {
        "summary": detail,
        "data_keys": ["plan.detail", "plan.settings", "plan.tracking", "financial_profile.readiness"],
        "snapshot_as_of": evidence_extra.get("snapshot_as_of"),
        "plan_id": plan_id,
        **evidence_extra,
    }
    action_payload = {
        "generator": {
            "id": STALE_ASSUMPTIONS_FACTORY_ID,
            "version": STALE_ASSUMPTIONS_FACTORY_VERSION,
            "generated_at": generated_at,
            "signal_key": signal_key,
            "signal_type": "stale_assumption",
            "dedupe_key": dedupe_key,
            "severity": severity,
        },
        "evidence": evidence,
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
    }
    action_payload["quality"] = _quality_metadata(
        source=STALE_ASSUMPTIONS_SOURCE,
        priority=priority,
        evidence=evidence,
        suggested_action=suggested_action,
        expected_outcome=expected_outcome,
        actionability=actionability,
        confidence_level="medium" if actionability == "context_gathering" else "high",
        confidence_reasons=[
            "Generated from active plan freshness, plan tracking, and profile readiness signals.",
            "Action is framed as review or context gathering rather than an automatic assumption change.",
        ],
        reversibility="high",
        blocking_context=blocking_context,
    )
    return {
        "title": title,
        "detail": detail,
        "priority": priority,
        "recommendation_type": "workflow_action",
        "source": STALE_ASSUMPTIONS_SOURCE,
        "plan_id": plan_id,
        "action_payload": action_payload,
    }


def _latest_decision_age_days(plan_detail_payload: dict[str, Any], *, now: datetime) -> int | None:
    decisions = plan_detail_payload.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return None
    ages = [
        age
        for item in decisions
        if isinstance(item, dict)
        for age in [_age_days(item.get("created_at") or item.get("updated_at"), now=now)]
        if age is not None
    ]
    return min(ages) if ages else None


def _stale_assumption_candidates(
    *,
    plan_detail_payload: dict[str, Any],
    plan_tracking_payload: dict[str, Any],
    profile_readiness_payload: dict[str, Any],
    generated_at: str,
    now: datetime,
) -> list[dict[str, Any]]:
    plan_id = _stale_assumption_plan_id(plan_detail_payload, plan_tracking_payload)
    plan_title = _stale_assumption_plan_title(plan_detail_payload, plan_tracking_payload)
    settings = plan_detail_payload.get("settings") if isinstance(plan_detail_payload.get("settings"), dict) else {}
    updated_age_days = _age_days(plan_detail_payload.get("updated_at"), now=now)
    candidates: list[dict[str, Any]] = []

    if updated_age_days is None or updated_age_days >= STALE_PLAN_REVIEW_DAYS:
        age_text = f"{updated_age_days} days" if updated_age_days is not None else "an unknown number of days"
        detail = (
            f"{plan_title} assumptions have not been reviewed recently; the active plan was last updated "
            f"{age_text} ago."
        )
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key="active_plan_stale",
                title=f"Review stale assumptions for {plan_title}",
                detail=detail,
                priority="medium",
                severity="watch",
                actionability="review_only",
                suggested_action={
                    "kind": "review_plan_assumptions",
                    "subject": plan_title,
                    "stale_days": updated_age_days,
                    "threshold_days": STALE_PLAN_REVIEW_DAYS,
                },
                expected_outcome={"expected_delta_assumption_quality": "plan_reviewed"},
                evidence_extra={
                    "snapshot_as_of": plan_detail_payload.get("updated_at"),
                    "plan_updated_age_days": updated_age_days,
                },
                generated_at=generated_at,
            )
        )

    expected_return_keys = [
        "expected_return_baseline",
        "expected_return_optimistic",
        "expected_return_conservative",
    ]
    missing_return_keys = [key for key in expected_return_keys if settings.get(key) is None]
    if missing_return_keys or (updated_age_days is not None and updated_age_days >= STALE_PLAN_REVIEW_DAYS):
        detail = (
            f"Expected return assumptions for {plan_title} should be reviewed before relying on long-range projections."
        )
        if missing_return_keys:
            detail += f" Missing: {', '.join(key.replace('_', ' ') for key in missing_return_keys)}."
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key="expected_returns_review",
                title=f"Review expected return assumptions for {plan_title}",
                detail=detail,
                priority="medium",
                severity="watch",
                actionability="review_only",
                suggested_action={
                    "kind": "review_expected_returns",
                    "subject": plan_title,
                    "missing_settings": missing_return_keys,
                    "stale_days": updated_age_days,
                },
                expected_outcome={"expected_delta_projection_quality": "returns_reviewed"},
                evidence_extra={
                    "snapshot_as_of": plan_detail_payload.get("updated_at"),
                    "settings": {key: settings.get(key) for key in expected_return_keys},
                },
                generated_at=generated_at,
            )
        )

    annual_contribution = safe_float(settings.get("annual_contribution_usd"), -1.0)
    tracking_expected = safe_float(plan_tracking_payload.get("expected_contributions_usd"), 0.0)
    if annual_contribution < 0 or (annual_contribution == 0 and tracking_expected > 0):
        detail = (
            f"{plan_title} contribution assumptions are missing or inconsistent with tracking data. "
            "Review contribution settings before treating plan drift as reliable."
        )
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key="contribution_assumption_weak",
                title=f"Review contribution assumptions for {plan_title}",
                detail=detail,
                priority="medium",
                severity="watch",
                actionability="review_only",
                suggested_action={
                    "kind": "review_contribution_assumptions",
                    "subject": plan_title,
                    "annual_contribution_usd": None if annual_contribution < 0 else annual_contribution,
                    "expected_contributions_usd": tracking_expected,
                },
                expected_outcome={"expected_delta_tracking_quality": "contributions_reviewed"},
                evidence_extra={
                    "snapshot_as_of": plan_tracking_payload.get("window_end") or plan_detail_payload.get("updated_at"),
                    "plan_tracking": plan_tracking_payload,
                },
                generated_at=generated_at,
            )
        )

    gap_key = str(profile_readiness_payload.get("next_gap_key") or "").strip()
    blocking_sources = profile_readiness_payload.get("blocking_recommendation_sources")
    blocking_sources = blocking_sources if isinstance(blocking_sources, list) else []

    if settings.get("marginal_tax_rate") is None and gap_key != "tax_profile":
        detail = (
            "Tax rate is missing from plan assumptions. Complete tax basics before relying on tax-sensitive "
            "plan or investment-fit guidance."
        )
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key="tax_rate_missing",
                title="Complete tax basics before assumption review",
                detail=detail,
                priority="medium",
                severity="blocking",
                actionability="context_gathering",
                suggested_action={
                    "kind": "complete_tax_assumptions",
                    "subject": "tax_profile",
                    "missing_settings": ["marginal_tax_rate"],
                },
                expected_outcome={"expected_delta_context_quality": "tax_assumptions_available"},
                evidence_extra={
                    "snapshot_as_of": profile_readiness_payload.get("updated_at") or plan_detail_payload.get("updated_at"),
                    "profile_readiness": profile_readiness_payload,
                },
                generated_at=generated_at,
                blocking_context=["financial_profile.tax_profile"],
            )
        )

    if gap_key and blocking_sources:
        signal_key = f"profile_readiness_blocking:{gap_key}"
        gap_title = str(profile_readiness_payload.get("next_gap_title") or gap_key.replace("_", " ")).strip()
        detail = str(profile_readiness_payload.get("next_gap_detail") or "").strip() or (
            f"{gap_title} is missing and blocks higher-confidence assumption reviews."
        )
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key=signal_key,
                title=f"Complete {gap_title.lower()} before assumption review",
                detail=detail,
                priority="medium",
                severity="blocking",
                actionability="context_gathering",
                suggested_action={
                    "kind": "complete_profile_context",
                    "subject": gap_key,
                    "blocking_recommendation_sources": blocking_sources,
                },
                expected_outcome={"expected_delta_context_quality": "profile_blocker_removed"},
                evidence_extra={
                    "snapshot_as_of": profile_readiness_payload.get("updated_at") or plan_detail_payload.get("updated_at"),
                    "profile_readiness": profile_readiness_payload,
                },
                generated_at=generated_at,
                blocking_context=[f"financial_profile.{gap_key}"],
            )
        )

    decision_age_days = _latest_decision_age_days(plan_detail_payload, now=now)
    if decision_age_days is None or decision_age_days >= STALE_DECISION_REVIEW_DAYS:
        age_text = f"{decision_age_days} days ago" if decision_age_days is not None else "not yet"
        detail = (
            f"The latest decision for {plan_title} was logged {age_text}. Refresh the decision log so future "
            "recommendations can learn from current intent."
        )
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key="decision_log_stale",
                title=f"Refresh plan decision log for {plan_title}",
                detail=detail,
                priority="low",
                severity="watch",
                actionability="review_only",
                suggested_action={
                    "kind": "refresh_plan_decision_log",
                    "subject": plan_title,
                    "decision_age_days": decision_age_days,
                    "threshold_days": STALE_DECISION_REVIEW_DAYS,
                },
                expected_outcome={"expected_delta_decision_trace_quality": "decision_log_refreshed"},
                evidence_extra={
                    "snapshot_as_of": plan_detail_payload.get("updated_at"),
                    "latest_decision_age_days": decision_age_days,
                },
                generated_at=generated_at,
            )
        )

    tracking_status = str(plan_tracking_payload.get("status") or "").strip().lower()
    snapshot_count = int(safe_float(plan_tracking_payload.get("snapshot_count"), 0.0))
    tracking_window_days = int(safe_float(plan_tracking_payload.get("tracking_window_days"), 0.0))
    if tracking_status == "insufficient_data" or snapshot_count < 2 or tracking_window_days < 30:
        detail = (
            f"{plan_title} has limited tracking history ({snapshot_count} snapshot"
            f"{'' if snapshot_count == 1 else 's'} over {tracking_window_days} days). "
            "Build more history before treating plan confidence as decision-grade."
        )
        candidates.append(
            _stale_assumption_candidate(
                plan_id=plan_id,
                signal_key="tracking_history_insufficient",
                title="Build tracking history before trusting plan confidence",
                detail=detail,
                priority="low",
                severity="watch",
                actionability="review_only",
                suggested_action={
                    "kind": "build_plan_tracking_history",
                    "subject": plan_title,
                    "snapshot_count": snapshot_count,
                    "tracking_window_days": tracking_window_days,
                },
                expected_outcome={"expected_delta_tracking_quality": "tracking_history_improved"},
                evidence_extra={
                    "snapshot_as_of": plan_tracking_payload.get("window_end"),
                    "plan_tracking": plan_tracking_payload,
                },
                generated_at=generated_at,
            )
        )

    return candidates


def generate_stale_assumption_recommendations(
    *,
    plan_detail_payload: dict[str, Any],
    plan_tracking_payload: dict[str, Any],
    profile_readiness_payload: dict[str, Any],
    existing_recommendations: list[dict[str, Any]],
    creator: RecommendationCreator | None = None,
    dry_run: bool = True,
    limit: int = 10,
    now: datetime | None = None,
) -> RecommendationFactoryResult:
    resolved_now = now or datetime.now(timezone.utc)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)
    generated_at = _now_iso(resolved_now)
    active_keys = _active_dedupe_keys(existing_recommendations)
    bounded_limit = max(1, min(int(limit), 50))

    candidates: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in _stale_assumption_candidates(
        plan_detail_payload=plan_detail_payload,
        plan_tracking_payload=plan_tracking_payload,
        profile_readiness_payload=profile_readiness_payload,
        generated_at=generated_at,
        now=resolved_now,
    ):
        generator = candidate.get("action_payload", {}).get("generator", {})
        dedupe_key = str(generator.get("dedupe_key") or "").strip()
        signal_key = str(generator.get("signal_key") or "").strip()
        if dedupe_key in active_keys:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "active_duplicate",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
            continue
        if len(candidates) >= bounded_limit:
            skipped.append(
                {
                    "dedupe_key": dedupe_key,
                    "reason": "limit_exceeded",
                    "title": candidate["title"],
                    "signal_key": signal_key,
                }
            )
            continue

        candidates.append(candidate)
        active_keys.add(dedupe_key)
        if not dry_run and creator is not None:
            created.append(
                creator.create(
                    title=candidate["title"],
                    detail=candidate["detail"],
                    priority=candidate["priority"],
                    recommendation_type=candidate["recommendation_type"],
                    source=candidate["source"],
                    plan_id=candidate["plan_id"],
                    action_payload=candidate["action_payload"],
                    status="proposed",
                )
            )

    return RecommendationFactoryResult(
        generated_count=len(created) if not dry_run else len(candidates),
        skipped_count=len(skipped),
        candidates=candidates,
        created=created,
        skipped=skipped,
        dry_run=dry_run,
    )


def _watchlist_research_dedupe_key(symbol: str, signal_key: str) -> str:
    return f"watchlist_research:{_clean_key(symbol)}:{_clean_key(signal_key)}"


def _watchlist_research_candidate(
    *,
    item: dict[str, Any],
    fit_payload: dict[str, Any] | None,
    generated_at: str,
    plan_id: str | None,
) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    freshness_status = str(item.get("research_freshness_status") or "").strip().lower()
    blocking_gaps = item.get("research_blocking_gaps") if isinstance(item.get("research_blocking_gaps"), list) else []
    coverage_score = safe_float(item.get("research_coverage_score"), 0.0)
    fit_payload = fit_payload if isinstance(fit_payload, dict) else {}
    fit_status = str(fit_payload.get("fit_status") or "").strip().lower()
    recommended_next_step = str(fit_payload.get("recommended_next_step") or "").strip().lower()
    portfolio_impact = (
        fit_payload.get("portfolio_impact")
        if isinstance(fit_payload.get("portfolio_impact"), dict)
        else {}
    )
    account_location = (
        portfolio_impact.get("account_location")
        if isinstance(portfolio_impact.get("account_location"), dict)
        else {}
    )

    signal_key = ""
    title = ""
    detail = ""
    priority = "medium"
    actionability = "review_only"
    suggested_action: dict[str, Any] = {}
    blocking_context: list[str] = []

    if freshness_status in {"", "partial", "stale", "degraded", "unavailable"} or blocking_gaps:
        signal_key = f"research_{freshness_status or 'unknown'}"
        title = f"Refresh research evidence for {symbol}"
        detail = (
            f"{symbol} has {freshness_status or 'unknown'} research evidence before BuildWealth can rely on "
            "it for investment-fit guidance."
        )
        priority = "medium" if freshness_status in {"partial", "stale"} else "high"
        actionability = "context_gathering"
        suggested_action = {
            "kind": "refresh_research_evidence",
            "symbol": symbol,
            "freshness_status": freshness_status or "unknown",
            "blocking_gaps": blocking_gaps,
        }
        blocking_context = [f"research.{gap}" for gap in blocking_gaps] or ["research.evidence_packet"]
    elif fit_status == "does_not_fit":
        signal_key = "fit_conflict"
        title = f"Review why {symbol} does not currently fit"
        detail = f"{symbol} currently conflicts with portfolio-fit checks. Review the fit risks before taking action."
        priority = "high"
        suggested_action = {
            "kind": "review_portfolio_fit",
            "symbol": symbol,
            "fit_status": fit_status,
            "next_step": recommended_next_step or "review_concentration",
        }
    elif fit_status == "needs_more_context":
        signal_key = f"fit_needs_context:{recommended_next_step or 'unknown'}"
        title = f"Gather context before judging {symbol}"
        detail = f"BuildWealth needs more context before it can assess whether {symbol} fits this portfolio."
        priority = "medium"
        actionability = "context_gathering"
        suggested_action = {
            "kind": recommended_next_step or "update_profile",
            "symbol": symbol,
            "fit_status": fit_status,
            "blocking_gaps": fit_payload.get("blocking_gaps") if isinstance(fit_payload.get("blocking_gaps"), list) else [],
        }
        blocking_context = [
            str(gap).replace(":", ".")
            for gap in suggested_action["blocking_gaps"]
            if str(gap).strip()
        ]
    elif fit_status == "mixed":
        signal_key = "fit_mixed_review"
        title = f"Review fit tradeoffs for {symbol}"
        detail = f"{symbol} has mixed fit signals. Compare, simulate, or discuss it before making a portfolio decision."
        priority = "low"
        suggested_action = {
            "kind": recommended_next_step or "discuss_in_copilot",
            "symbol": symbol,
            "fit_status": fit_status,
        }
    else:
        return None

    dedupe_key = _watchlist_research_dedupe_key(symbol, signal_key)
    evidence = {
        "summary": detail,
        "data_keys": ["portfolio.watchlist", "research.evidence_packet", "portfolio.fit_assessment"],
        "symbol": symbol,
        "research_evidence_packet_id": item.get("research_evidence_packet_id"),
        "provider": item.get("research_provider"),
        "freshness_status": freshness_status or "unknown",
        "confidence": item.get("research_confidence"),
        "coverage_score": coverage_score,
        "blocking_gaps": blocking_gaps,
        "watchlist_score_total": item.get("watchlist_score_total"),
        "fit_status": fit_status or None,
        "fit_score": fit_payload.get("fit_score"),
        "fit_reasons": fit_payload.get("fit_reasons") if isinstance(fit_payload.get("fit_reasons"), list) else [],
        "fit_risks": fit_payload.get("fit_risks") if isinstance(fit_payload.get("fit_risks"), list) else [],
        "account_location": account_location,
        "provider_coverage": item.get("provider_coverage") if isinstance(item.get("provider_coverage"), dict) else {},
    }
    expected_outcome = {
        "expected_delta_context_quality": "research_or_fit_reviewed",
        "expected_next_safe_action": suggested_action.get("kind"),
    }
    action_payload = {
        "generator": {
            "id": WATCHLIST_RESEARCH_FACTORY_ID,
            "version": WATCHLIST_RESEARCH_FACTORY_VERSION,
            "generated_at": generated_at,
            "signal_key": signal_key,
            "signal_type": "watchlist_research",
            "dedupe_key": dedupe_key,
            "severity": priority,
        },
        "evidence": evidence,
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
    }
    action_payload["quality"] = _quality_metadata(
        source=WATCHLIST_RESEARCH_SOURCE,
        priority=priority,
        evidence=evidence,
        suggested_action=suggested_action,
        expected_outcome=expected_outcome,
        actionability=actionability,
        confidence_level="medium" if fit_status else "low",
        confidence_reasons=[
            "Generated from watchlist research evidence and portfolio-fit context.",
            "Action is framed as refresh, review, simulate, compare, or context gathering.",
        ],
        reversibility="high",
        blocking_context=blocking_context,
    )
    return {
        "title": title,
        "detail": detail,
        "priority": priority,
        "recommendation_type": "workflow_action",
        "source": WATCHLIST_RESEARCH_SOURCE,
        "plan_id": plan_id,
        "action_payload": action_payload,
    }


def generate_watchlist_research_recommendations(
    *,
    watchlist_rank_payload: dict[str, Any],
    fit_assessments_by_symbol: dict[str, dict[str, Any]],
    existing_recommendations: list[dict[str, Any]],
    creator: RecommendationCreator | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> RecommendationFactoryResult:
    generated_at = _now_iso(now)
    active_keys = _active_dedupe_keys(existing_recommendations)
    bounded_limit = max(1, min(int(limit), 50))
    items = watchlist_rank_payload.get("items") if isinstance(watchlist_rank_payload.get("items"), list) else []

    candidates: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        candidate = _watchlist_research_candidate(
            item=item,
            fit_payload=fit_assessments_by_symbol.get(symbol),
            generated_at=generated_at,
            plan_id=plan_id,
        )
        if candidate is None:
            continue
        generator = candidate.get("action_payload", {}).get("generator", {})
        dedupe_key = str(generator.get("dedupe_key") or "").strip()
        signal_key = str(generator.get("signal_key") or "").strip()
        if dedupe_key in active_keys:
            skipped.append({"dedupe_key": dedupe_key, "reason": "active_duplicate", "title": candidate["title"], "signal_key": signal_key})
            continue
        if len(candidates) >= bounded_limit:
            skipped.append({"dedupe_key": dedupe_key, "reason": "limit_exceeded", "title": candidate["title"], "signal_key": signal_key})
            continue

        candidates.append(candidate)
        active_keys.add(dedupe_key)
        if not dry_run and creator is not None:
            created.append(
                creator.create(
                    title=candidate["title"],
                    detail=candidate["detail"],
                    priority=candidate["priority"],
                    recommendation_type=candidate["recommendation_type"],
                    source=candidate["source"],
                    plan_id=candidate["plan_id"],
                    action_payload=candidate["action_payload"],
                    status="proposed",
                )
            )

    return RecommendationFactoryResult(
        generated_count=len(created) if not dry_run else len(candidates),
        skipped_count=len(skipped),
        candidates=candidates,
        created=created,
        skipped=skipped,
        dry_run=dry_run,
    )
