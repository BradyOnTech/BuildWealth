from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from buildwealth_orchestrator.schemas import (
    PortfolioSnapshot,
    ProfileReadinessSummary,
    SnapshotHistoryResponse,
    SyncStatusResponse,
    TodayActivePlanSummary,
    TodayChecklistItem,
    TodayCommandCard,
    TodayDashboardResponse,
    TodayRecommendation,
)
from buildwealth_orchestrator.services.portfolio_metrics import concentration_metrics

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


def _build_command_cards(
    *,
    context_state: Literal["ready", "warning", "critical"],
    context_notes: list[str],
    profile_readiness: ProfileReadinessSummary | None,
    onboarding_completion_percent: float,
    active_plan: TodayActivePlanSummary | None,
    concentration_risk: str,
    top_holding_symbol: str | None,
    top_holding_percent: float | None,
    snapshot_as_of: datetime | None,
    snapshot_age_minutes: int | None,
) -> list[TodayCommandCard]:
    profile_percent = (
        profile_readiness.completion_percent
        if profile_readiness is not None
        else onboarding_completion_percent
    )
    profile_status: Literal["ready", "warning", "critical"] = "ready"
    profile_detail = "Profile context is ready for daily recommendations."
    profile_action_label: str | None = None
    profile_href: str | None = None
    if profile_readiness is not None and profile_readiness.next_gap_title:
        profile_status = "warning"
        profile_detail = f"Next gap: {profile_readiness.next_gap_title}."
        profile_action_label = "Complete context"
        profile_href = "#copilot?intent=complete-context"
    elif profile_percent < 80:
        profile_status = "warning"
        profile_detail = "Profile context is incomplete."
        profile_action_label = "Complete context"
        profile_href = "#copilot?intent=complete-context"

    data_action_label: str | None = None
    data_href: str | None = None
    if context_state == "critical" or snapshot_as_of is None:
        data_action_label = "Run sync"
        data_href = "#atelier"
    elif snapshot_age_minutes is not None and snapshot_age_minutes > (24 * 60):
        data_action_label = "Refresh data"
        data_href = "#atelier"

    plan_status: Literal["ready", "warning", "critical"] = "ready"
    plan_detail = "Active plan assumptions are complete enough for daily review."
    plan_metric_value: str | None = None
    plan_action_label: str | None = "Review plan"
    plan_href: str | None = "#plan"
    if active_plan is None:
        plan_status = "warning"
        plan_detail = "No active plan is set."
        plan_action_label = "Set active plan"
    else:
        plan_metric_value = f"{round(active_plan.settings_completion_percent)}%"
        if active_plan.settings_completion_percent < 57:
            plan_status = "warning"
            plan_detail = "Plan assumptions need more context before recommendations can be trusted."

    risk_status: Literal["ready", "warning", "critical"] = "ready"
    if concentration_risk == "high":
        risk_status = "critical"
    elif concentration_risk == "medium":
        risk_status = "warning"
    risk_detail = "Portfolio concentration is low enough for routine review."
    if risk_status != "ready":
        symbol = top_holding_symbol or "top holding"
        risk_detail = f"Top holding concentration is {concentration_risk} around {symbol}."

    return [
        TodayCommandCard(
            id="profile-readiness",
            title="Profile readiness",
            status=profile_status,
            detail=profile_detail,
            metric_label="Complete",
            metric_value=f"{round(profile_percent)}%",
            action_label=profile_action_label,
            href=profile_href,
        ),
        TodayCommandCard(
            id="data-trust",
            title="Data trust",
            status=context_state,
            detail=context_notes[0] if context_notes else "Context is fresh and ready for daily review.",
            metric_label="Snapshot",
            metric_value=(
                f"{snapshot_age_minutes // 60}h old"
                if snapshot_age_minutes is not None and snapshot_age_minutes >= 60
                else f"{snapshot_age_minutes}m old"
                if snapshot_age_minutes is not None
                else "Missing"
            ),
            action_label=data_action_label,
            href=data_href,
        ),
        TodayCommandCard(
            id="plan-posture",
            title="Plan posture",
            status=plan_status,
            detail=plan_detail,
            metric_label="Assumptions",
            metric_value=plan_metric_value,
            action_label=plan_action_label,
            href=plan_href,
        ),
        TodayCommandCard(
            id="portfolio-risk",
            title="Portfolio risk",
            status=risk_status,
            detail=risk_detail,
            metric_label="Top holding",
            metric_value=f"{round(top_holding_percent)}%" if top_holding_percent is not None else "Unknown",
            action_label="Review risk" if risk_status != "ready" else "Open portfolio",
            href="#portfolio",
        ),
    ]


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
    profile_readiness: ProfileReadinessSummary | None = None,
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
        top_positions = metrics["top_positions"]
        if top_positions:
            first = top_positions[0]
            top_weight = float(first["weight"]) * 100
            top_holding_percent = round(top_weight, 2)
            top_holding_symbol = first["symbol"] or top_holding_symbol

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
    if profile_readiness is not None and profile_readiness.next_gap_title:
        context_notes.append(f"Profile readiness: next gap is {profile_readiness.next_gap_title}.")
    if active_plan_summary is None:
        context_notes.append("No active plan is set.")
    if inbox_high_priority_count > 0:
        context_notes.append(f"{inbox_high_priority_count} high-priority recommendation(s) need review.")

    if context_state != "critical" and context_notes:
        context_state = "warning"
    if not context_notes:
        context_notes.append("Context is fresh and ready for daily review.")

    command_cards = _build_command_cards(
        context_state=context_state,
        context_notes=context_notes,
        profile_readiness=profile_readiness,
        onboarding_completion_percent=onboarding_completion_percent,
        active_plan=active_plan_summary,
        concentration_risk=concentration_risk,
        top_holding_symbol=top_holding_symbol,
        top_holding_percent=top_holding_percent,
        snapshot_as_of=snapshot_as_of,
        snapshot_age_minutes=snapshot_age_minutes,
    )

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
        profile_readiness=profile_readiness,
        inbox_open_count=max(0, int(inbox_open_count)),
        inbox_high_priority_count=max(0, int(inbox_high_priority_count)),
        context_state=context_state,
        context_notes=context_notes,
        command_cards=command_cards,
        checklist=checklist,
        recommendations=recommendations,
        workflow_steps=workflow_steps,
    )
