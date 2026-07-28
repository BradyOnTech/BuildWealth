"""Dashboard routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_peer_benchmark",
    "get_morning_brief",
    "mark_morning_brief_seen",
    "today_dashboard",
    "refresh_today_research_readiness",
    "record_today_review_checkpoint",
    "onboarding_status",
    "get_financial_health",
    "check_affordability",
    "get_goal_progress",
]


@router.get("/api/peer-benchmark")
def get_peer_benchmark(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Where the household stands versus US households its age (SCF 2022),
    computed locally from public survey data — no peer network involved."""
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem, TaxProfile

    resolved_services = m.route_workspace_services(services, permission="profile.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        snap = None
    health = m.compute_financial_health(
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
        goal_items=[GoalItem(**g) for g in profile.get("goal_items", [])],
        physical_assets=[PhysicalAssetItem(**a) for a in profile.get("physical_assets", [])],
        snapshot=snap,
        tax_profile=TaxProfile(**profile.get("tax_profile", {})),
    )
    return m.build_peer_benchmark(
        net_worth_usd=health.net_worth_usd,
        profile_payload=profile,
        current_year=m.datetime.now(m.timezone.utc).year,
    )


def _morning_brief_service(services: m.Any) -> m.Any:
    from buildwealth_orchestrator.services.morning_brief import MorningBriefService

    seen_path = services.today_review_checkpoint_store.path.parent / "brief_seen.json"
    return MorningBriefService(
        recommendation_inbox=services.recommendation_inbox,
        portfolio_store=services.portfolio_store,
        financial_profile_store=services.financial_profile_store,
        snapshot_store=services.snapshot_store,
        context_intelligence_service=services.context_intelligence_service,
        seen_path=seen_path,
    )


@router.get("/api/dashboard/brief")
def get_morning_brief(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Digest of what changed since the user last marked the brief seen."""
    resolved_services = m.route_workspace_services(services, permission="workspace.read")
    service = _morning_brief_service(resolved_services)
    brief = service.build()
    if brief.get("first_visit"):
        # Bootstrap the cursor: the first visit renders nothing, so without
        # this write the baseline would never exist and the panel never shows.
        service.mark_seen()
    return brief


@router.post("/api/dashboard/brief/seen")
def mark_morning_brief_seen(
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    resolved_services = m.route_workspace_services(services, permission="workspace.read")
    return _morning_brief_service(resolved_services).mark_seen()


@router.get("/api/dashboard/today", response_model=m.TodayDashboardResponse)
def today_dashboard(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.TodayDashboardResponse:
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(services, permission="workspace.read")
        return m.build_today_dashboard_response(resolved_services)
    return m.build_today_dashboard_response()


@router.post("/api/dashboard/today/research-readiness/refresh", response_model=m.TodayDashboardResponse)
def refresh_today_research_readiness(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.TodayDashboardResponse:
    m.today_research_evidence_cache.clear()
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(services, permission="workspace.read")
        return m.build_today_dashboard_response(resolved_services)
    return m.build_today_dashboard_response()


@router.post("/api/dashboard/today/review-checkpoint", response_model=m.TodayDashboardResponse)
def record_today_review_checkpoint(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.TodayDashboardResponse:
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(
            services,
            permission="workspace.read",
            http_request=http_request,
            require_write_token=True,
        )
        dashboard = m.build_today_dashboard_response(resolved_services)
        resolved_services.today_review_checkpoint_store.save(
            m._today_review_checkpoint_from_dashboard(dashboard)
        )
        return m.build_today_dashboard_response(resolved_services)
    dashboard = m.build_today_dashboard_response()
    m.today_review_checkpoint_store.save(m._today_review_checkpoint_from_dashboard(dashboard))
    return m.build_today_dashboard_response()


@router.get("/api/onboarding/status", response_model=m.OnboardingStatusResponse)
def onboarding_status(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.OnboardingStatusResponse:
    m.require_permission(services.context, "profile.read")
    try:
        latest_snapshot = services.snapshot_store.latest()
    except FileNotFoundError:
        latest_snapshot = None
    active_plan_detail = None
    active_plan_id = services.plan_workspace.get_active_plan_id()
    if active_plan_id:
        try:
            active_plan_detail = services.plan_workspace.get_plan(active_plan_id)
        except m.PlanNotFoundError:
            active_plan_detail = None
    return m.build_onboarding_status_response(
        profile_payload=m.get_financial_profile_payload(services.financial_profile_store),
        latest_snapshot=latest_snapshot,
        active_plan_detail=active_plan_detail,
        load_fallbacks=False,
    )


@router.get("/api/financial-health", response_model=m.FinancialHealthResponse)
def get_financial_health(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.FinancialHealthResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem, TaxProfile

    resolved_services = m.route_workspace_services(services, permission="profile.read")
    m.require_permission(resolved_services.context, "portfolio.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        snap = None
    return m.compute_financial_health(
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
        goal_items=[GoalItem(**g) for g in profile.get("goal_items", [])],
        physical_assets=[PhysicalAssetItem(**a) for a in profile.get("physical_assets", [])],
        snapshot=snap,
        tax_profile=TaxProfile(**profile.get("tax_profile", {})),
    )


@router.post("/api/affordability", response_model=m.AffordabilityResponse)
def check_affordability(
    request: m.AffordabilityRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.AffordabilityResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, IncomeItem, TaxProfile

    resolved_services = m.route_workspace_services(services, permission="profile.read")
    m.require_permission(resolved_services.context, "portfolio.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        snap = None
    return m.assess_affordability(
        description=request.description,
        monthly_amount_usd=request.monthly_amount_usd,
        purchase_price_usd=request.purchase_price_usd,
        loan_rate_pct=request.loan_rate_pct,
        loan_term_years=request.loan_term_years,
        down_payment_pct=request.down_payment_pct,
        financing_mode=request.financing_mode,
        available_cash_usd=m.estimate_liquid_cash_value(snap),
        tax_profile=TaxProfile(**profile.get("tax_profile", {})),
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
    )


@router.get("/api/goals/progress", response_model=m.GoalProgressResponse)
def get_goal_progress(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GoalProgressResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, TaxProfile

    resolved_services = m.route_workspace_services(services, permission="profile.read")
    m.require_permission(resolved_services.context, "portfolio.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
        portfolio_value = m.portfolio_value_with_cash(snap)
    except FileNotFoundError:
        portfolio_value = 0.0

    income_items = [IncomeItem(**i) for i in profile.get("income_items", [])]
    expense_items = [ExpenseItem(**e) for e in profile.get("expense_items", [])]
    debt_items = [DebtItem(**d) for d in profile.get("debt_items", [])]
    goal_items = [GoalItem(**g) for g in profile.get("goal_items", [])]

    cash_flow = m.compute_monthly_cash_flow(
        income_items=income_items,
        expense_items=expense_items,
        debt_items=debt_items,
        tax_profile=TaxProfile(**profile.get("tax_profile", {})),
    )
    monthly_surplus = cash_flow["monthly_surplus"]

    return m.compute_goal_progress(
        goals=goal_items,
        monthly_surplus_usd=monthly_surplus,
        portfolio_value_usd=portfolio_value,
    )
