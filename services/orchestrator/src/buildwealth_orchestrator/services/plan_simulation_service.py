from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from buildwealth_orchestrator.schemas import (
    ContributionAllocationResponse,
    DebtProjectionResponse,
    ExpenseProjectionResponse,
    IncomeProjectionResponse,
    PlanningResponse,
    RmdProjectionResponse,
    SocialSecurityProjectionResponse,
    TimelineImpactProjectionResponse,
)
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


@dataclass(frozen=True)
class _ScenarioRunInputs:
    current_portfolio_value_usd: float
    annual_contribution_usd: float | None = None
    years: int | None = None
    hsa_extra_contribution_usd: float | None = None
    accounts: list[dict[str, Any]] | None = None
    income_projection: dict[str, Any] | None = None
    expense_projection: dict[str, Any] | None = None
    debt_projection: dict[str, Any] | None = None
    timeline_projection: dict[str, Any] | None = None
    contribution_allocation: dict[str, Any] | None = None
    social_security_projection: dict[str, Any] | None = None
    rmd_projection: dict[str, Any] | None = None
    assumption_set_id: str | None = None
    assumption_set_name: str | None = None
    filing_status: str | None = None
    state_tax_rate: float | None = None
    include_irmaa: bool = True
    roth_conversion_annual_amount_usd: float | None = None
    roth_conversion_start_age: int | None = None
    roth_conversion_end_age: int | None = None
    drawdown_order: str | list[str] | None = None
    household_mode: str | None = None
    household_partner_income_usd: float | None = None
    household_partner_income_growth_rate: float | None = None
    household_partner_retirement_age: int | None = None
    household_partner_social_security_annual_usd: float | None = None
    household_partner_social_security_claiming_age: int | None = None
    household_shared_goal_target_usd: float | None = None
    household_shared_goal_target_year: int | None = None
    household_shared_goal_annual_funding_usd: float | None = None
    household_partner_income_added_first_year_usd: float | None = None
    household_partner_income_added_total_usd: float | None = None
    start_year: int | None = None
    start_age: int = 35
    withdrawal_strategy: str | None = None
    retirement_age: int | None = None
    simulation_mode: str | None = None
    simulation_monte_carlo_variant: str | None = None
    simulation_historical_start_year: int | None = None
    simulation_seed: int | None = None


class BuildWealthScenarioService:
    def __init__(
        self,
        *,
        scenario_engine: ScenarioEngine,
    ) -> None:
        self.scenario_engine = scenario_engine

    async def run(
        self,
        *,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float | None = None,
        years: int | None = None,
        hsa_extra_contribution_usd: float | None = None,
        accounts: list[dict[str, Any]] | None = None,
        income_projection: dict[str, Any] | None = None,
        expense_projection: dict[str, Any] | None = None,
        debt_projection: dict[str, Any] | None = None,
        timeline_projection: dict[str, Any] | None = None,
        contribution_allocation: dict[str, Any] | None = None,
        social_security_projection: dict[str, Any] | None = None,
        rmd_projection: dict[str, Any] | None = None,
        assumption_set_id: str | None = None,
        assumption_set_name: str | None = None,
        filing_status: str | None = None,
        state_tax_rate: float | None = None,
        include_irmaa: bool = True,
        roth_conversion_annual_amount_usd: float | None = None,
        roth_conversion_start_age: int | None = None,
        roth_conversion_end_age: int | None = None,
        drawdown_order: str | list[str] | None = None,
        household_mode: str | None = None,
        household_partner_income_usd: float | None = None,
        household_partner_income_growth_rate: float | None = None,
        household_partner_retirement_age: int | None = None,
        household_partner_social_security_annual_usd: float | None = None,
        household_partner_social_security_claiming_age: int | None = None,
        household_shared_goal_target_usd: float | None = None,
        household_shared_goal_target_year: int | None = None,
        household_shared_goal_annual_funding_usd: float | None = None,
        household_partner_income_added_first_year_usd: float | None = None,
        household_partner_income_added_total_usd: float | None = None,
        start_year: int | None = None,
        start_age: int = 35,
        withdrawal_strategy: str | None = None,
        retirement_age: int | None = None,
        simulation_mode: str | None = None,
        simulation_monte_carlo_variant: str | None = None,
        simulation_historical_start_year: int | None = None,
        simulation_seed: int | None = None,
    ) -> PlanningResponse:
        inputs = _ScenarioRunInputs(
            current_portfolio_value_usd=current_portfolio_value_usd,
            annual_contribution_usd=annual_contribution_usd,
            years=years,
            hsa_extra_contribution_usd=hsa_extra_contribution_usd,
            accounts=accounts,
            income_projection=income_projection,
            expense_projection=expense_projection,
            debt_projection=debt_projection,
            timeline_projection=timeline_projection,
            contribution_allocation=contribution_allocation,
            social_security_projection=social_security_projection,
            rmd_projection=rmd_projection,
            assumption_set_id=assumption_set_id,
            assumption_set_name=assumption_set_name,
            filing_status=filing_status,
            state_tax_rate=state_tax_rate,
            include_irmaa=include_irmaa,
            roth_conversion_annual_amount_usd=roth_conversion_annual_amount_usd,
            roth_conversion_start_age=roth_conversion_start_age,
            roth_conversion_end_age=roth_conversion_end_age,
            drawdown_order=drawdown_order,
            household_mode=household_mode,
            household_partner_income_usd=household_partner_income_usd,
            household_partner_income_growth_rate=household_partner_income_growth_rate,
            household_partner_retirement_age=household_partner_retirement_age,
            household_partner_social_security_annual_usd=household_partner_social_security_annual_usd,
            household_partner_social_security_claiming_age=household_partner_social_security_claiming_age,
            household_shared_goal_target_usd=household_shared_goal_target_usd,
            household_shared_goal_target_year=household_shared_goal_target_year,
            household_shared_goal_annual_funding_usd=household_shared_goal_annual_funding_usd,
            household_partner_income_added_first_year_usd=household_partner_income_added_first_year_usd,
            household_partner_income_added_total_usd=household_partner_income_added_total_usd,
            start_year=start_year,
            start_age=start_age,
            withdrawal_strategy=withdrawal_strategy,
            retirement_age=retirement_age,
            simulation_mode=simulation_mode,
            simulation_monte_carlo_variant=simulation_monte_carlo_variant,
            simulation_historical_start_year=simulation_historical_start_year,
            simulation_seed=simulation_seed,
        )

        local_result = self._build_local_result(inputs)
        local_projection_updates = self._build_local_projection_updates(inputs)
        return self._build_local_only_response(
            local_result=local_result,
            local_projection_updates=local_projection_updates,
        )

    def _build_local_result(self, inputs: _ScenarioRunInputs) -> PlanningResponse:
        return self.scenario_engine.run(
            current_portfolio_value_usd=inputs.current_portfolio_value_usd,
            annual_contribution_usd=inputs.annual_contribution_usd,
            years=inputs.years,
            hsa_extra_contribution_usd=inputs.hsa_extra_contribution_usd,
            accounts=inputs.accounts,
            income_projection=inputs.income_projection,
            expense_projection=inputs.expense_projection,
            debt_projection=inputs.debt_projection,
            timeline_projection=inputs.timeline_projection,
            contribution_allocation=inputs.contribution_allocation,
            social_security_projection=inputs.social_security_projection,
            rmd_projection=inputs.rmd_projection,
            assumption_set_id=inputs.assumption_set_id,
            assumption_set_name=inputs.assumption_set_name,
            filing_status=inputs.filing_status,
            state_tax_rate=inputs.state_tax_rate,
            include_irmaa=inputs.include_irmaa,
            roth_conversion_annual_amount_usd=inputs.roth_conversion_annual_amount_usd,
            roth_conversion_start_age=inputs.roth_conversion_start_age,
            roth_conversion_end_age=inputs.roth_conversion_end_age,
            drawdown_order=inputs.drawdown_order,
            start_year=inputs.start_year,
            start_age=inputs.start_age,
            withdrawal_strategy=inputs.withdrawal_strategy,
            retirement_age=inputs.retirement_age,
            simulation_mode=inputs.simulation_mode,
            simulation_monte_carlo_variant=inputs.simulation_monte_carlo_variant,
            simulation_historical_start_year=inputs.simulation_historical_start_year,
            simulation_seed=inputs.simulation_seed,
        )

    @staticmethod
    def _build_local_projection_updates(inputs: _ScenarioRunInputs) -> dict[str, Any]:
        return {
            "income_projection": (
                IncomeProjectionResponse(**inputs.income_projection)
                if inputs.income_projection is not None
                else None
            ),
            "expense_projection": (
                ExpenseProjectionResponse(**inputs.expense_projection)
                if inputs.expense_projection is not None
                else None
            ),
            "debt_projection": (
                DebtProjectionResponse(**inputs.debt_projection)
                if inputs.debt_projection is not None
                else None
            ),
            "timeline_projection": (
                TimelineImpactProjectionResponse(**inputs.timeline_projection)
                if inputs.timeline_projection is not None
                else None
            ),
            "contribution_allocation": (
                ContributionAllocationResponse(**inputs.contribution_allocation)
                if inputs.contribution_allocation is not None
                else None
            ),
            "social_security_projection": (
                SocialSecurityProjectionResponse(**inputs.social_security_projection)
                if inputs.social_security_projection is not None
                else None
            ),
            "rmd_projection": (
                RmdProjectionResponse(**inputs.rmd_projection)
                if inputs.rmd_projection is not None
                else None
            ),
        }

    @staticmethod
    def _build_local_only_response(
        *,
        local_result: PlanningResponse,
        local_projection_updates: dict[str, Any],
    ) -> PlanningResponse:
        return local_result.model_copy(update=local_projection_updates)
