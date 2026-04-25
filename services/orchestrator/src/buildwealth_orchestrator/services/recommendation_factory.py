from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from buildwealth_orchestrator.services.value_coercion import safe_float, utc_now_iso

PORTFOLIO_RISK_FACTORY_ID = "portfolio_risk_recommendation_factory"
PORTFOLIO_RISK_FACTORY_VERSION = "v1"
PORTFOLIO_RISK_SOURCE = "generator:portfolio_risk"


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
