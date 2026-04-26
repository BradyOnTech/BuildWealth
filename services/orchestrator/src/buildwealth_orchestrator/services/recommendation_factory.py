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
CASH_RESERVE_MIN_MONTHS = 3.0
CASH_RESERVE_MAX_MONTHS = 6.0


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

    return {
        "title": _title_for_alert(alert),
        "detail": _detail_for_alert(alert, estimated_amount_usd=estimated_amount_usd),
        "priority": _priority_for_alert(alert),
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
    action_payload = {
        "generator": _plan_tracking_generator_payload(
            generated_at=generated_at,
            signal_key=signal_key,
            severity=severity,
            dedupe_key=dedupe_key,
        ),
        "evidence": _plan_tracking_evidence(plan_tracking_payload, summary=detail),
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
    }
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
    action_payload = {
        "generator": _cash_liquidity_generator_payload(
            generated_at=generated_at,
            signal_key=signal_key,
            severity=severity,
        ),
        "evidence": _cash_liquidity_evidence(
            summary=detail,
            holdings_payload=holdings_payload,
            financial_profile_payload=financial_profile_payload,
            monthly_expenses=monthly_expenses,
            monthly_debt_minimums=monthly_debt_minimums,
        ),
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
    }
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
