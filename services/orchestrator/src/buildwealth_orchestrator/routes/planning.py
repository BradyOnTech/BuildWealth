"""Planning routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "planning_assumption_defaults",
    "plan_scenarios",
    "planning_income_projection",
    "planning_expense_projection",
    "planning_debt_projection",
    "planning_social_security_projection",
    "planning_rmd_projection",
    "planning_tax_estimate",
    "planning_contribution_allocation",
]


@router.post("/api/planning/scenarios", response_model=m.PlanningResponse)
async def plan_scenarios(
    request: m.ScenarioRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanningResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    m.require_permission(resolved_services.context, "portfolio.read")
    m.require_permission(resolved_services.context, "profile.read")
    profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
    planning_accounts = m.build_planning_accounts_from_portfolio(resolved_services.portfolio_store)
    household_members = profile_payload.get("household_members")
    profile_members = [item for item in household_members if isinstance(item, dict)] if isinstance(household_members, list) else []
    primary_member = next(
        (item for item in profile_members if str(item.get("relationship") or "").strip().lower() == "self"),
        profile_members[0] if profile_members else None,
    )
    current_age = 35
    if isinstance(primary_member, dict) and primary_member.get("birth_year") is not None:
        current_age = max(
            0,
            min(120, m.utc_now().year - m._coerce_int(primary_member.get("birth_year"), m.utc_now().year - 35)),
        )
    current_value = request.current_portfolio_value_usd
    if current_value is None:
        try:
            latest_snapshot = resolved_services.snapshot_store.latest()
            current_value = m.portfolio_value_with_cash(latest_snapshot)
        except FileNotFoundError:
            holdings = (
                resolved_services.current_portfolio()
                if isinstance(resolved_services, m.WorkspaceServices)
                else resolved_services.portfolio_store.get_holdings()
            )
            current_value = m._coerce_float(holdings.get("total_value"), 0.0)
            positions = holdings.get("holdings")
            if abs(current_value) <= 1e-9 and not (isinstance(positions, dict) and positions):
                current_value = m._coerce_float(holdings.get("total_cash"), 0.0)
            current_value = max(0.0, current_value)

    resolved_years = (
        int(request.years)
        if request.years is not None
        else int(m.scenario_engine.years_to_retirement)
    )
    planning_settings_for_run: dict[str, m.Any] = {"years": resolved_years}
    if request.state_tax_rate is not None:
        planning_settings_for_run["state_tax_rate"] = request.state_tax_rate
    if request.roth_conversion_annual_amount_usd is not None:
        planning_settings_for_run["roth_conversion_annual_amount_usd"] = request.roth_conversion_annual_amount_usd
    if request.roth_conversion_start_age is not None:
        planning_settings_for_run["roth_conversion_start_age"] = request.roth_conversion_start_age
    if request.roth_conversion_end_age is not None:
        planning_settings_for_run["roth_conversion_end_age"] = request.roth_conversion_end_age
    if request.drawdown_order is not None:
        planning_settings_for_run["drawdown_order"] = request.drawdown_order
    if request.simulation_mode is not None:
        planning_settings_for_run["simulation_mode"] = request.simulation_mode
    if request.simulation_monte_carlo_variant is not None:
        planning_settings_for_run["simulation_monte_carlo_variant"] = request.simulation_monte_carlo_variant
    if request.simulation_historical_start_year is not None:
        planning_settings_for_run["simulation_historical_start_year"] = request.simulation_historical_start_year
    if request.simulation_seed is not None:
        planning_settings_for_run["simulation_seed"] = request.simulation_seed
    if request.household_mode is not None:
        planning_settings_for_run["household_mode"] = request.household_mode
    if request.household_partner_income_usd is not None:
        planning_settings_for_run["household_partner_income_usd"] = request.household_partner_income_usd
    if request.household_partner_income_growth_rate is not None:
        planning_settings_for_run["household_partner_income_growth_rate"] = request.household_partner_income_growth_rate
    if request.household_partner_retirement_age is not None:
        planning_settings_for_run["household_partner_retirement_age"] = request.household_partner_retirement_age
    if request.household_partner_social_security_annual_usd is not None:
        planning_settings_for_run["household_partner_social_security_annual_usd"] = (
            request.household_partner_social_security_annual_usd
        )
    if request.household_partner_social_security_claiming_age is not None:
        planning_settings_for_run["household_partner_social_security_claiming_age"] = (
            request.household_partner_social_security_claiming_age
        )
    if request.household_shared_goal_target_usd is not None:
        planning_settings_for_run["household_shared_goal_target_usd"] = request.household_shared_goal_target_usd
    if request.household_shared_goal_target_year is not None:
        planning_settings_for_run["household_shared_goal_target_year"] = request.household_shared_goal_target_year
    if request.filing_status is not None:
        planning_settings_for_run["filing_status"] = request.filing_status
    request_household_overrides_provided = any(
        value is not None
        for value in (
            request.household_mode,
            request.household_partner_income_usd,
            request.household_partner_income_growth_rate,
            request.household_partner_retirement_age,
            request.household_partner_social_security_annual_usd,
            request.household_partner_social_security_claiming_age,
            request.household_shared_goal_target_usd,
            request.household_shared_goal_target_year,
            request.filing_status,
        )
    )
    active_assumption_set: dict[str, m.Any] | None = None
    service = m.plan_simulation_service
    timeline_projection: m.TimelineImpactProjectionResponse | None = None
    active_timeline_payload: dict[str, m.Any] | None = None
    active_withdrawal_strategy: str | None = None
    active_drawdown_order: str | None = None
    active_retirement_age: int | None = None
    active_plan_detail: dict[str, m.Any] | None = None
    active_plan_id = resolved_services.plan_workspace.get_active_plan_id()
    if active_plan_id:
        try:
            active_plan_detail = resolved_services.plan_workspace.get_plan(active_plan_id)
            active_timeline = m.resolve_plan_timeline_payload(active_plan_detail)
            active_timeline_payload = active_timeline
            active_retirement_age = m.resolve_timeline_retirement_age(active_timeline)
            timeline_strategy = m.resolve_timeline_withdrawal_strategy(active_timeline)
            timeline_drawdown_order = m.resolve_timeline_drawdown_order(active_timeline)
            active_settings = active_plan_detail.get("settings")
            if isinstance(active_settings, dict):
                active_withdrawal_strategy = str(active_settings.get("withdrawal_strategy") or "").strip() or None
                active_drawdown_order = str(active_settings.get("drawdown_order") or "").strip() or None
                planning_settings_for_run.update(active_settings)
            planning_settings_for_run["years"] = resolved_years
            assumption_sets_payload = m.resolve_plan_assumption_sets(active_plan_detail)
            planning_settings_for_run, active_assumption_set = m.apply_assumption_set_to_settings(
                plan_settings=planning_settings_for_run,
                assumption_sets_payload=assumption_sets_payload,
                assumption_set_id=None,
            )
            service = m.build_plan_simulation_service_for_plan_settings(planning_settings_for_run)
            if not active_withdrawal_strategy:
                active_withdrawal_strategy = timeline_strategy
            if not active_drawdown_order:
                active_drawdown_order = timeline_drawdown_order
            timeline_projection = m.build_timeline_projection_for_plan_settings(
                plan_settings=planning_settings_for_run,
                timeline_payload=active_timeline,
            )
        except m.PlanNotFoundError:
            timeline_projection = None
            active_plan_detail = None
            active_timeline_payload = None
            active_withdrawal_strategy = None
            active_drawdown_order = None
            active_retirement_age = None

    if request.simulation_mode is not None:
        planning_settings_for_run["simulation_mode"] = request.simulation_mode
    if request.simulation_monte_carlo_variant is not None:
        planning_settings_for_run["simulation_monte_carlo_variant"] = request.simulation_monte_carlo_variant
    if request.simulation_historical_start_year is not None:
        planning_settings_for_run["simulation_historical_start_year"] = request.simulation_historical_start_year
    if request.simulation_seed is not None:
        planning_settings_for_run["simulation_seed"] = request.simulation_seed

    # Per-request assumption overrides (Simulation Studio sliders). A baseline
    # return override shifts optimistic/conservative by the same delta so the
    # scenario spread keeps its shape around the new center.
    assumption_overrides_provided = any(
        value is not None
        for value in (request.expected_return_baseline, request.return_volatility, request.inflation_rate)
    )
    if assumption_overrides_provided:
        engine_before = service.scenario_engine
        if request.expected_return_baseline is not None:
            delta = float(request.expected_return_baseline) - float(engine_before.baseline_return)
            planning_settings_for_run["expected_return_baseline"] = float(request.expected_return_baseline)
            planning_settings_for_run["expected_return_optimistic"] = float(engine_before.optimistic_return) + delta
            planning_settings_for_run["expected_return_conservative"] = float(engine_before.conservative_return) + delta
        if request.return_volatility is not None:
            planning_settings_for_run["return_volatility"] = float(request.return_volatility)
        if request.inflation_rate is not None:
            planning_settings_for_run["inflation_rate"] = float(request.inflation_rate)
        service = m.build_plan_simulation_service_for_plan_settings(planning_settings_for_run)

    resolved_start_year = m.utc_now().year
    household_settings = m._resolve_household_settings(
        plan_settings=planning_settings_for_run,
        start_year=resolved_start_year,
        years=resolved_years,
    )

    income_projection = m.build_income_projection_for_plan_settings(
        planning_settings_for_run, profile_payload=profile_payload
    )
    expense_projection = m.build_expense_projection_for_plan_settings(
        planning_settings_for_run, profile_payload=profile_payload
    )
    debt_projection = m.build_debt_projection_for_plan_settings(
        planning_settings_for_run, profile_payload=profile_payload
    )
    income_projection_payload = income_projection.model_dump(mode="json") if income_projection is not None else None
    expense_projection_payload = expense_projection.model_dump(mode="json") if expense_projection is not None else None
    if request.expense_scale is not None and isinstance(expense_projection_payload, dict):
        expense_projection_payload = m.scale_expense_projection_payload(
            expense_projection_payload,
            scale=float(request.expense_scale),
        )
    (
        income_projection_payload,
        expense_projection_payload,
        household_adjustments_payload,
    ) = m._apply_household_adjustments_to_projection_payloads(
        income_projection=income_projection_payload,
        expense_projection=expense_projection_payload,
        household_settings=household_settings,
        start_year=resolved_start_year,
        start_age=current_age,
        years=resolved_years,
    )

    resolved_annual_contribution = (
        float(request.annual_contribution_usd)
        if request.annual_contribution_usd is not None
        else float(service.scenario_engine.annual_contribution_usd)
    )
    resolved_current_value = float(current_value)
    if timeline_projection is not None:
        resolved_current_value = max(
            0.0,
            resolved_current_value + float(timeline_projection.first_year_portfolio_impact_usd),
        )
        resolved_annual_contribution = max(
            0.0,
            resolved_annual_contribution + float(timeline_projection.first_year_contribution_impact_usd),
        )

    contribution_rules_payload: dict[str, m.Any] | None = None
    if active_plan_detail is not None:
        contribution_rules_payload = m.resolve_plan_contribution_rules(active_plan_detail)
    contribution_allocation = m.build_contribution_allocation_for_plan_settings(
        plan_settings={
            **planning_settings_for_run,
            "annual_contribution_usd": resolved_annual_contribution,
        },
        contribution_rules_payload=contribution_rules_payload,
        accounts_override=planning_accounts,
    )
    social_security_projection: m.SocialSecurityProjectionResponse | None = None
    rmd_projection: m.RmdProjectionResponse | None = None
    if active_timeline_payload is not None:
        social_security_projection = m.build_social_security_projection_for_plan_settings(
            plan_settings=planning_settings_for_run,
            timeline_payload=active_timeline_payload,
            income_projection=income_projection,
            start_year=m.utc_now().year,
        )
        rmd_projection = m.build_rmd_projection_for_plan_settings(
            plan_settings=planning_settings_for_run,
            timeline_payload=active_timeline_payload,
            start_year=m.utc_now().year,
            accounts_override=planning_accounts,
        )

    tax_profile = profile_payload.get("tax_profile")
    filing_status: str | None = None
    state_tax_rate: float | None = None
    include_irmaa = bool(request.include_irmaa)
    if isinstance(tax_profile, dict):
        filing_status = m._resolve_filing_status_for_household(
            filing_status=tax_profile.get("filing_status"),
            household_mode=str(household_settings.get("household_mode") or m.HOUSEHOLD_MODE_INDIVIDUAL),
        )
        if tax_profile.get("state_tax_rate") is not None:
            state_tax_rate = max(
                0.0,
                min(1.0, m._coerce_float(tax_profile.get("state_tax_rate"), 0.0)),
            )

    if planning_settings_for_run.get("filing_status"):
        filing_status = m._resolve_filing_status_for_household(
            filing_status=planning_settings_for_run.get("filing_status"),
            household_mode=str(household_settings.get("household_mode") or m.HOUSEHOLD_MODE_INDIVIDUAL),
        )
    if filing_status is None:
        filing_status = m._resolve_filing_status_for_household(
            filing_status=None,
            household_mode=str(household_settings.get("household_mode") or m.HOUSEHOLD_MODE_INDIVIDUAL),
        )
    if planning_settings_for_run.get("state_tax_rate") is not None:
        state_tax_rate = max(
            0.0,
            min(1.0, m._coerce_float(planning_settings_for_run.get("state_tax_rate"), 0.0)),
        )
    roth_conversion_annual_amount = max(
        0.0,
        m._coerce_float(planning_settings_for_run.get("roth_conversion_annual_amount_usd"), 0.0),
    )
    roth_conversion_start_age: int | None = None
    roth_conversion_end_age: int | None = None
    if planning_settings_for_run.get("roth_conversion_start_age") is not None:
        roth_conversion_start_age = max(
            0,
            min(120, m._coerce_int(planning_settings_for_run.get("roth_conversion_start_age"), 0)),
        )
    if planning_settings_for_run.get("roth_conversion_end_age") is not None:
        roth_conversion_end_age = max(
            0,
            min(120, m._coerce_int(planning_settings_for_run.get("roth_conversion_end_age"), 0)),
        )
    if (
        roth_conversion_start_age is not None
        and roth_conversion_end_age is not None
        and roth_conversion_start_age > roth_conversion_end_age
    ):
        roth_conversion_start_age, roth_conversion_end_age = (
            roth_conversion_end_age,
            roth_conversion_start_age,
        )
    if not active_drawdown_order:
        active_drawdown_order = str(planning_settings_for_run.get("drawdown_order") or "").strip() or None
    if (
        active_retirement_age is None
        and isinstance(primary_member, dict)
        and primary_member.get("retirement_age") is not None
    ):
        active_retirement_age = max(18, min(100, m._coerce_int(primary_member.get("retirement_age"), 65)))
    if request.target_retirement_age is not None:
        active_retirement_age = max(18, min(100, int(request.target_retirement_age)))
    requested_drawdown_order = str(request.drawdown_order or "").strip() or None
    if requested_drawdown_order is not None:
        active_drawdown_order = requested_drawdown_order

    result = await service.run(
        current_portfolio_value_usd=resolved_current_value,
        annual_contribution_usd=resolved_annual_contribution,
        years=request.years,
        hsa_extra_contribution_usd=request.hsa_extra_contribution_usd,
        accounts=planning_accounts,
        income_projection=income_projection_payload,
        expense_projection=expense_projection_payload,
        debt_projection=debt_projection.model_dump(mode="json") if debt_projection is not None else None,
        timeline_projection=timeline_projection.model_dump(mode="json") if timeline_projection is not None else None,
        contribution_allocation=(
            contribution_allocation.model_dump(mode="json")
            if contribution_allocation is not None
            else None
        ),
        social_security_projection=(
            social_security_projection.model_dump(mode="json")
            if social_security_projection is not None
            else None
        ),
        rmd_projection=(
            rmd_projection.model_dump(mode="json")
            if rmd_projection is not None
            else None
        ),
        filing_status=filing_status,
        state_tax_rate=state_tax_rate,
        include_irmaa=include_irmaa,
        roth_conversion_annual_amount_usd=roth_conversion_annual_amount,
        roth_conversion_start_age=roth_conversion_start_age,
        roth_conversion_end_age=roth_conversion_end_age,
        drawdown_order=active_drawdown_order,
        household_mode=str(household_settings.get("household_mode") or m.HOUSEHOLD_MODE_INDIVIDUAL),
        household_partner_income_usd=household_settings.get("household_partner_income_usd"),
        household_partner_income_growth_rate=household_settings.get("household_partner_income_growth_rate"),
        household_partner_retirement_age=household_settings.get("household_partner_retirement_age"),
        household_partner_social_security_annual_usd=household_settings.get("household_partner_social_security_annual_usd"),
        household_partner_social_security_claiming_age=household_settings.get("household_partner_social_security_claiming_age"),
        household_shared_goal_target_usd=household_settings.get("household_shared_goal_target_usd"),
        household_shared_goal_target_year=household_settings.get("household_shared_goal_target_year"),
        household_shared_goal_annual_funding_usd=household_adjustments_payload.get("shared_goal_annual_funding_usd"),
        household_partner_income_added_first_year_usd=household_adjustments_payload.get("partner_income_added_first_year_usd"),
        household_partner_income_added_total_usd=household_adjustments_payload.get("partner_income_added_total_usd"),
        start_year=resolved_start_year,
        start_age=current_age,
        withdrawal_strategy=active_withdrawal_strategy,
        retirement_age=active_retirement_age,
        simulation_mode=planning_settings_for_run.get("simulation_mode"),
        simulation_monte_carlo_variant=planning_settings_for_run.get("simulation_monte_carlo_variant"),
        simulation_historical_start_year=planning_settings_for_run.get("simulation_historical_start_year"),
        simulation_seed=planning_settings_for_run.get("simulation_seed"),
        assumption_set_id=(
            str(active_assumption_set.get("id"))
            if isinstance(active_assumption_set, dict) and active_assumption_set.get("id")
            else None
        ),
        assumption_set_name=(
            str(active_assumption_set.get("name"))
            if isinstance(active_assumption_set, dict) and active_assumption_set.get("name")
            else None
        ),
    )
    if request_household_overrides_provided:
        household_source = "scenario_request_overrides"
    elif active_plan_detail is not None:
        household_source = "active_plan_settings"
    else:
        household_source = "scenario_request_defaults"
    household_context = m._build_household_response_context(
        household_settings=household_settings,
        household_adjustments=household_adjustments_payload,
        filing_status=filing_status,
        source=household_source,
    )
    return m._apply_household_context_to_planning_response(
        response=result,
        household_context=household_context,
    )


@router.post("/api/planning/income-projection", response_model=m.IncomeProjectionResponse)
def planning_income_projection(
    request: m.IncomeProjectionRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.IncomeProjectionResponse:
    resolved_services = m.route_workspace_services(services, permission="profile.read")
    if request.income_items is not None:
        income_items = [item.model_dump(mode="json") for item in request.income_items]
    else:
        profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
        raw_items = profile_payload.get("income_items")
        income_items = raw_items if isinstance(raw_items, list) else []

    payload = m.project_income_schedule(
        income_items,
        start_year=request.start_year or m.utc_now().year,
        years=request.years,
        default_annual_growth_rate=(
            m.settings.planner_inflation
            if request.default_annual_growth_rate is None
            else float(request.default_annual_growth_rate)
        ),
    )
    return m.IncomeProjectionResponse(**payload)


@router.post("/api/planning/expense-projection", response_model=m.ExpenseProjectionResponse)
def planning_expense_projection(
    request: m.ExpenseProjectionRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ExpenseProjectionResponse:
    resolved_services = m.route_workspace_services(services, permission="profile.read")
    if request.expense_items is not None:
        expense_items = [item.model_dump(mode="json") for item in request.expense_items]
    else:
        profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
        raw_items = profile_payload.get("expense_items")
        expense_items = raw_items if isinstance(raw_items, list) else []

    payload = m.project_expense_schedule(
        expense_items,
        start_year=request.start_year or m.utc_now().year,
        years=request.years,
        default_inflation_rate=(
            m.settings.planner_inflation
            if request.default_inflation_rate is None
            else float(request.default_inflation_rate)
        ),
    )
    return m.ExpenseProjectionResponse(**payload)


@router.post("/api/planning/debt-projection", response_model=m.DebtProjectionResponse)
def planning_debt_projection(
    request: m.DebtProjectionRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.DebtProjectionResponse:
    resolved_services = m.route_workspace_services(services, permission="profile.read")
    if request.debt_items is not None:
        debt_items = [item.model_dump(mode="json") for item in request.debt_items]
    else:
        profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
        raw_items = profile_payload.get("debt_items")
        debt_items = raw_items if isinstance(raw_items, list) else []

    payload = m.project_debt_payoff(
        debt_items,
        start_date=request.start_date or m.utc_now().date().replace(day=1),
        max_years=request.max_years,
        strategy=request.strategy,
        monthly_accelerated_payment_usd=request.monthly_accelerated_payment_usd,
    )
    return m.DebtProjectionResponse(**payload)


@router.post("/api/planning/social-security-projection", response_model=m.SocialSecurityProjectionResponse)
def planning_social_security_projection(
    request: m.SocialSecurityProjectionRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.SocialSecurityProjectionResponse:
    resolved_services = m.route_workspace_services(services, permission="profile.read")
    earnings_history = (
        [item.model_dump(mode="json") for item in request.earnings_history]
        if request.earnings_history is not None
        else []
    )

    estimated_annual_earnings_usd = request.estimated_annual_earnings_usd
    if estimated_annual_earnings_usd is None and not earnings_history:
        profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
        income_rows = profile_payload.get("income_items")
        if isinstance(income_rows, list):
            estimated_annual_earnings_usd = max(
                0.0,
                sum(
                    max(0.0, m._coerce_float(item.get("monthly_amount_usd"), 0.0))
                    for item in income_rows
                    if isinstance(item, dict)
                )
                * 12.0,
            )

    payload = m.project_social_security_income(
        start_year=request.start_year or m.utc_now().year,
        years=request.years,
        current_age=request.current_age,
        birth_year=request.birth_year,
        claiming_age=request.claiming_age,
        life_expectancy_age=request.life_expectancy_age,
        fra_monthly_benefit_usd=request.fra_monthly_benefit_usd,
        estimated_annual_earnings_usd=estimated_annual_earnings_usd,
        earnings_history=earnings_history,
        cola_rate=request.cola_rate,
        claim_age_options=request.claim_age_options,
        pia_bend_point_1_usd=request.pia_bend_point_1_usd,
        pia_bend_point_2_usd=request.pia_bend_point_2_usd,
    )
    return m.SocialSecurityProjectionResponse(**payload)


@router.post("/api/planning/rmd-projection", response_model=m.RmdProjectionResponse)
def planning_rmd_projection(
    request: m.RmdProjectionRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RmdProjectionResponse:
    resolved_services = m.route_workspace_services(services, permission="portfolio.read")
    if request.accounts is not None:
        accounts = [item.model_dump(mode="json") for item in request.accounts]
    else:
        accounts = m.build_planning_accounts_from_portfolio(resolved_services.portfolio_store)

    payload = m.project_rmd_schedule(
        accounts=accounts,
        start_year=request.start_year or m.utc_now().year,
        years=request.years,
        current_age=request.current_age,
        birth_year=request.birth_year,
        expected_return=request.expected_return,
        start_age_override=request.start_age_override,
    )
    return m.RmdProjectionResponse(**payload)


@router.post("/api/planning/tax-estimate", response_model=m.TaxEstimateResponse)
def planning_tax_estimate(request: m.TaxEstimateRequest) -> m.TaxEstimateResponse:
    return m.TaxEstimateResponse(
        **m.estimate_federal_tax(
            tax_year=request.tax_year,
            filing_status=request.filing_status,
            earned_income_usd=request.earned_income_usd,
            ordinary_income_usd=request.ordinary_income_usd,
            short_term_capital_gains_usd=request.short_term_capital_gains_usd,
            long_term_capital_gains_usd=request.long_term_capital_gains_usd,
            qualified_dividends_usd=request.qualified_dividends_usd,
            interest_income_usd=request.interest_income_usd,
            social_security_income_usd=request.social_security_income_usd,
            tax_exempt_interest_income_usd=request.tax_exempt_interest_income_usd,
            pre_tax_contributions_usd=request.pre_tax_contributions_usd,
            state_tax_rate=request.state_tax_rate,
            state_tax_deduction_usd=request.state_tax_deduction_usd,
            age=request.age,
            include_irmaa=request.include_irmaa,
            medicare_months_covered=request.medicare_months_covered,
            tax_withholding_usd=request.tax_withholding_usd,
        )
    )


@router.post("/api/planning/contribution-allocation", response_model=m.ContributionAllocationResponse)
def planning_contribution_allocation(
    request: m.ContributionAllocationRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ContributionAllocationResponse:
    resolved_services = m.route_workspace_services(services, permission="portfolio.read")
    accounts = [item.model_dump(mode="json") for item in request.accounts] or m.build_planning_accounts_from_portfolio(
        resolved_services.portfolio_store,
    )
    if not accounts:
        raise m.HTTPException(status_code=400, detail="No accounts available to allocate contributions.")

    base_rule = request.base_rule if isinstance(request.base_rule, dict) else {"type": "save"}
    rules = list(request.rules)
    profile_id = request.profile_id

    if not rules and (profile_id is None or profile_id == "tax_optimized_high_earner"):
        generated = m.build_tax_optimized_high_earner_rules(
            accounts,
            employer_match_target_usd=request.employer_match_target_usd,
        )
        rules = generated.get("rules", [])
        base_rule = generated.get("base_rule", base_rule)
        profile_id = generated.get("profile_id", "tax_optimized_high_earner")

    payload = m.allocate_contributions(
        annual_contribution_usd=request.annual_contribution_usd,
        age=request.age,
        accounts=accounts,
        rules=rules,
        base_rule=base_rule,
        profile_id=profile_id,
    )
    return m.ContributionAllocationResponse(**payload)


@router.get("/api/planning/assumption-defaults")
def planning_assumption_defaults(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """The values the engine actually falls back to when a plan leaves an
    assumption unset — plus their provenance. The UI must never say
    'app default' without showing the number."""
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    profile = resolved_services.financial_profile_store.get()
    tax_profile = profile.get("tax_profile") if isinstance(profile.get("tax_profile"), dict) else {}

    def default(value: m.Any, source: str = "buildwealth_default") -> dict[str, m.Any]:
        return {"value": value, "source": source}

    marginal = tax_profile.get("marginal_tax_rate")
    filing = tax_profile.get("filing_status")
    profile_horizon = m.resolve_profile_plan_horizon(profile)
    profile_contribution = m.resolve_profile_annual_contribution(profile)
    has_cash_flow = bool(profile.get("income_items")) and bool(profile.get("expense_items"))
    has_retirement_horizon = profile_horizon != m.settings.planner_years_to_retirement

    return {
        "defaults": {
            "annual_contribution_usd": default(
                profile_contribution,
                "profile_cash_flow" if has_cash_flow else "buildwealth_default",
            ),
            "years": default(
                profile_horizon,
                "profile_retirement_horizon" if has_retirement_horizon else "buildwealth_default",
            ),
            "expected_return_baseline": default(m.settings.planner_expected_return_baseline),
            "inflation_rate": default(m.settings.planner_inflation),
            "marginal_tax_rate": (
                default(float(marginal), "profile")
                if marginal
                else default(m.settings.planner_marginal_tax_rate)
            ),
            "filing_status": (
                default(str(filing), "profile") if filing else default("single")
            ),
            "withdrawal_strategy": default("cashflow_only"),
            "drawdown_order": default("smart account order"),
            "simulation_mode": default("fixed"),
        },
        "profile_mismatch": (
            {
                "field": "marginal_tax_rate",
                "profile_value": float(marginal),
                "engine_default": m.settings.planner_marginal_tax_rate,
            }
            if marginal and abs(float(marginal) - m.settings.planner_marginal_tax_rate) > 1e-9
            else None
        ),
    }
