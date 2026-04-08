from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from buildwealth_orchestrator.schemas import (
    PortfolioSnapshot,
    SnapshotHistoryResponse,
    SyncStatusResponse,
    TodayActivePlanSummary,
    TodayChecklistItem,
    TodayDashboardResponse,
    TodayRecommendation,
)
from buildwealth_orchestrator.services.research import concentration_metrics

PLAN_SETTINGS_KEYS = (
    "annual_contribution_usd",
    "years",
    "hsa_extra_contribution_usd",
    "marginal_tax_rate",
    "expected_return_baseline",
    "expected_return_optimistic",
    "expected_return_conservative",
)


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Accept ISO payloads with trailing Z.
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _settings_completion_percent(settings: dict[str, Any]) -> float:
    set_count = 0
    for key in PLAN_SETTINGS_KEYS:
        if settings.get(key) is not None:
            set_count += 1
    return round((set_count / len(PLAN_SETTINGS_KEYS)) * 100, 1)


def _concentration_risk(top_holding_percent: float | None) -> str:
    if top_holding_percent is None:
        return "low"
    if top_holding_percent >= 35:
        return "high"
    if top_holding_percent >= 20:
        return "medium"
    return "low"


def _build_checklist(
    *,
    snapshot_as_of: datetime | None,
    snapshot_age_minutes: int | None,
    snapshot_points: int,
    active_plan: TodayActivePlanSummary | None,
    latest_decision_at: datetime | None,
) -> list[TodayChecklistItem]:
    items: list[TodayChecklistItem] = []

    if snapshot_as_of is None:
        items.append(
            TodayChecklistItem(
                id="sync-first-snapshot",
                title="Run first portfolio sync",
                status="incomplete",
                detail="No local snapshot exists yet.",
                action_hint="Run Sync Now",
            )
        )
    elif snapshot_age_minutes is not None and snapshot_age_minutes > (24 * 60):
        items.append(
            TodayChecklistItem(
                id="sync-refresh",
                title="Refresh stale portfolio snapshot",
                status="attention",
                detail=f"Latest snapshot is {snapshot_age_minutes // 60}h old.",
                action_hint="Run Sync Now",
            )
        )
    else:
        items.append(
            TodayChecklistItem(
                id="sync-fresh",
                title="Portfolio snapshot freshness",
                status="complete",
                detail="Snapshot is fresh enough for daily analysis.",
            )
        )

    if active_plan is None:
        items.append(
            TodayChecklistItem(
                id="plan-active",
                title="Set an active plan",
                status="incomplete",
                detail="No active plan is configured.",
                action_hint="Create or activate a plan",
            )
        )
    else:
        plan_status = "complete" if active_plan.settings_completion_percent >= 57 else "attention"
        items.append(
            TodayChecklistItem(
                id="plan-assumptions",
                title="Plan assumptions coverage",
                status=plan_status,
                detail=(
                    f"Settings completion is {active_plan.settings_completion_percent:.1f}% "
                    f"for active plan '{active_plan.title}'."
                ),
                action_hint="Fill missing plan settings",
            )
        )

    if snapshot_points < 5:
        items.append(
            TodayChecklistItem(
                id="history-depth",
                title="Build trend history",
                status="attention",
                detail=f"Only {snapshot_points} snapshot points available.",
                action_hint="Run sync daily to build stronger trend context",
            )
        )
    else:
        items.append(
            TodayChecklistItem(
                id="history-depth",
                title="Trend history depth",
                status="complete",
                detail=f"{snapshot_points} snapshots available for time-window analysis.",
            )
        )

    if latest_decision_at is None:
        items.append(
            TodayChecklistItem(
                id="decision-log",
                title="Log at least one plan decision",
                status="attention",
                detail="No decisions recorded yet in the active plan.",
                action_hint="Use Copilot + Plan Workspace to log your next decision",
            )
        )
    else:
        days_ago = int((datetime.now(timezone.utc) - latest_decision_at).days)
        if days_ago > 14:
            items.append(
                TodayChecklistItem(
                    id="decision-log",
                    title="Refresh decision log",
                    status="attention",
                    detail=f"Last plan decision was {days_ago} days ago.",
                    action_hint="Run a weekly workflow and log a new decision",
                )
            )
        else:
            items.append(
                TodayChecklistItem(
                    id="decision-log",
                    title="Decision cadence",
                    status="complete",
                    detail=f"Recent plan decision logged {days_ago} day(s) ago.",
                )
            )

    return items


def _build_recommendations(
    *,
    snapshot_as_of: datetime | None,
    concentration_risk: str,
    top_holding_symbol: str | None,
    active_plan: TodayActivePlanSummary | None,
) -> list[TodayRecommendation]:
    recommendations: list[TodayRecommendation] = []

    if snapshot_as_of is None:
        recommendations.append(
            TodayRecommendation(
                id="sync-now",
                title="Run initial sync before asking Copilot",
                detail="Copilot answers are strongest once portfolio snapshot context is available.",
                priority="high",
            )
        )

    if concentration_risk == "high":
        symbol = top_holding_symbol or "top holding"
        recommendations.append(
            TodayRecommendation(
                id="concentration-review",
                title="Run concentration-risk workflow",
                detail=f"Allocation concentration is high around {symbol}.",
                priority="high",
            )
        )

    if active_plan is None:
        recommendations.append(
            TodayRecommendation(
                id="create-plan",
                title="Create a plan baseline",
                detail="Set an active plan so scenario diff and recommendations can be tracked over time.",
                priority="high",
            )
        )
    elif active_plan.settings_completion_percent < 57:
        recommendations.append(
            TodayRecommendation(
                id="fill-plan-settings",
                title="Complete plan assumptions",
                detail=(
                    "Fill annual contribution, years, tax rate, and expected returns to improve scenario "
                    "quality and recommendation relevance."
                ),
                priority="medium",
            )
        )

    if not recommendations:
        recommendations.append(
            TodayRecommendation(
                id="weekly-review",
                title="Run weekly change summary",
                detail="Use workflow templates to compare current portfolio vs previous snapshot and log actions.",
                priority="low",
            )
        )

    return recommendations


def build_today_dashboard_payload(
    *,
    now: datetime,
    currency: str,
    state: str,
    sync_status: SyncStatusResponse,
    latest_snapshot: PortfolioSnapshot | None,
    snapshot_history: SnapshotHistoryResponse,
    active_plan_detail: dict[str, Any] | None,
    onboarding_completion_percent: float = 0.0,
    onboarding_ready_for_daily_review: bool = False,
    inbox_open_count: int = 0,
    inbox_high_priority_count: int = 0,
) -> TodayDashboardResponse:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    snapshot_as_of = latest_snapshot.as_of if latest_snapshot is not None else None
    snapshot_age_minutes = None
    if snapshot_as_of is not None:
        snapshot_age_minutes = max(0, int((now - snapshot_as_of).total_seconds() // 60))

    top_holding_symbol = None
    top_holding_percent = None
    concentration_risk = "low"
    total_value = None
    net_performance_usd = None
    net_performance_percent = None

    if latest_snapshot is not None:
        total_value = round(latest_snapshot.total_value_usd, 2)
        net_performance_usd = round(latest_snapshot.net_performance_usd, 2)
        net_performance_percent = round(latest_snapshot.net_performance_percent, 4)

        if latest_snapshot.holdings:
            top = latest_snapshot.holdings[0]
            top_holding_symbol = top.symbol
            top_holding_percent = round(float(top.allocation_percent), 2)

        metrics = concentration_metrics(
            [
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "value_usd": item.value_usd,
                }
                for item in latest_snapshot.holdings
            ]
        )
        top_positions = metrics.get("top_positions", [])
        if top_positions and isinstance(top_positions, list):
            first = top_positions[0]
            try:
                top_weight = float(first.get("weight", 0.0)) * 100
                top_holding_percent = round(top_weight, 2)
                top_holding_symbol = str(first.get("symbol") or top_holding_symbol or "")
            except Exception:
                pass

    concentration_risk = _concentration_risk(top_holding_percent)

    active_plan_summary = None
    latest_decision_at = None
    if active_plan_detail is not None:
        settings = active_plan_detail.get("settings", {})
        decisions = active_plan_detail.get("decisions", [])
        artifacts = active_plan_detail.get("artifacts", [])
        active_plan_summary = TodayActivePlanSummary(
            id=str(active_plan_detail.get("id") or ""),
            title=str(active_plan_detail.get("title") or "Untitled Plan"),
            updated_at=_as_datetime(active_plan_detail.get("updated_at")),
            settings_completion_percent=_settings_completion_percent(
                settings if isinstance(settings, dict) else {}
            ),
            decisions_count=len(decisions) if isinstance(decisions, list) else 0,
            artifacts_count=len(artifacts) if isinstance(artifacts, list) else 0,
        )
        if isinstance(decisions, list) and decisions:
            latest_decision_at = _as_datetime(decisions[0].get("created_at"))

    checklist = _build_checklist(
        snapshot_as_of=snapshot_as_of,
        snapshot_age_minutes=snapshot_age_minutes,
        snapshot_points=int(snapshot_history.window_points),
        active_plan=active_plan_summary,
        latest_decision_at=latest_decision_at,
    )

    recommendations = _build_recommendations(
        snapshot_as_of=snapshot_as_of,
        concentration_risk=concentration_risk,
        top_holding_symbol=top_holding_symbol,
        active_plan=active_plan_summary,
    )

    workflow_steps = [
        "Check snapshot freshness and daily checklist.",
        "Review concentration/trend deltas and top recommendations.",
        "Ask Copilot a focused question with active plan context.",
        "Run one workflow template and compare outcomes.",
        "Log one decision in Plan Workspace.",
    ]

    context_notes: list[str] = []
    context_state: Literal["ready", "warning", "critical"] = "ready"
    if snapshot_as_of is None:
        context_state = "critical"
        context_notes.append("No portfolio snapshot is available yet. Run sync before making decisions.")
    elif snapshot_age_minutes is not None and snapshot_age_minutes > (24 * 60):
        context_notes.append("Portfolio snapshot is older than 24 hours.")

    if not onboarding_ready_for_daily_review:
        context_notes.append("Unified financial profile is incomplete.")
    if active_plan_summary is None:
        context_notes.append("No active plan is set.")
    if inbox_high_priority_count > 0:
        context_notes.append(f"{inbox_high_priority_count} high-priority recommendation(s) need review.")

    if context_state != "critical" and context_notes:
        context_state = "warning"
    if not context_notes:
        context_notes.append("Context is fresh and ready for daily review.")

    return TodayDashboardResponse(
        generated_at=now,
        currency=currency,
        state=state,
        sync_status=sync_status,
        snapshot_as_of=snapshot_as_of,
        snapshot_age_minutes=snapshot_age_minutes,
        snapshot_points_30d=int(snapshot_history.window_points),
        total_value_usd=total_value,
        net_performance_usd=net_performance_usd,
        net_performance_percent=net_performance_percent,
        top_holding_symbol=top_holding_symbol or None,
        top_holding_percent=top_holding_percent,
        concentration_risk=concentration_risk,
        active_plan=active_plan_summary,
        onboarding_completion_percent=onboarding_completion_percent,
        onboarding_ready_for_daily_review=onboarding_ready_for_daily_review,
        inbox_open_count=max(0, int(inbox_open_count)),
        inbox_high_priority_count=max(0, int(inbox_high_priority_count)),
        context_state=context_state,
        context_notes=context_notes,
        checklist=checklist,
        recommendations=recommendations,
        workflow_steps=workflow_steps,
    )
