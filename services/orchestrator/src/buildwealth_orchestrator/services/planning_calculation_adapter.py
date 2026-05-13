from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from buildwealth_orchestrator.schemas import (
    ContributionAllocationResponse,
    DebtProjectionResponse,
    ExpenseProjectionResponse,
    IncomeProjectionResponse,
    PlanningResponse,
    RmdProjectionResponse,
    ScenarioResult,
    ScenarioTimelinePoint,
    SocialSecurityProjectionResponse,
    TimelineImpactProjectionResponse,
)
from buildwealth_orchestrator.services.contribution_rules import (
    normalize_account_type,
    tax_treatment_for_account_type,
)
from buildwealth_orchestrator.services.engine_adapter import CalculationAdapter, CalculationAdapterError
from buildwealth_orchestrator.services.engine_policy import (
    ENGINE_STATUS_DEGRADED,
    degraded_response_update,
    resolve_engine_call_disposition,
    calculation_unavailable_warning,
)
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine

PLAN_SIMULATION_CONTRACT_VERSION = 1
PLAN_SIMULATION_ENGINE_LABEL = "Plan simulation"


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
    contract_guard_reason: str | None = None


class RemoteScenarioAccountV1(BaseModel):
    account_id: str
    account_type: str
    tax_treatment: Literal["taxable", "tax_deferred", "tax_free"] = "taxable"
    balance: float
    annual_contribution: float = 0.0


class RemoteScenarioOverrideV1(BaseModel):
    scenario_id: str
    label: str
    overrides: dict[str, float | str | bool | None] = Field(default_factory=dict)


class RemoteScenarioRequestV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    start_year: int
    horizon_years: int
    household: dict[str, int]
    accounts: list[RemoteScenarioAccountV1]
    baseline_assumptions: dict[str, float]
    scenario_overrides: list[RemoteScenarioOverrideV1]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenario_overrides")
    @classmethod
    def _validate_overrides(cls, values: list[RemoteScenarioOverrideV1]) -> list[RemoteScenarioOverrideV1]:
        if not values:
            raise ValueError("scenario_overrides must not be empty")
        return values


class RemoteScenarioSummaryV1(BaseModel):
    ending_balance_nominal: float
    ending_balance_real: float
    total_contributions: float | None = None
    total_taxes: float | None = None
    success_probability: float | None = None


class RemoteScenarioTimelinePointV1(BaseModel):
    year: int
    age: int
    starting_balance: float
    ending_balance: float
    contributions: float | None = None
    income: float | None = None
    expenses: float | None = None
    taxes: float | None = None
    growth: float | None = None
    withdrawals: float | None = None
    ending_balance_real: float | None = None


class RemoteScenarioOutputV1(BaseModel):
    scenario_id: str
    label: str
    summary: RemoteScenarioSummaryV1
    timeline: list[RemoteScenarioTimelinePointV1] = Field(default_factory=list)


class RemoteScenarioResponseV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    engine: Literal["simulation"] = "simulation"
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    scenarios: list[RemoteScenarioOutputV1]
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None


class BuildWealthScenarioService:
    def __init__(
        self,
        *,
        scenario_engine: ScenarioEngine,
        calculation_adapter: CalculationAdapter | None,
        calculation_adapter_enabled: bool,
        calculation_adapter_path: str,
        currency: str = "USD",
        default_tax_rate: float = 0.25,
    ) -> None:
        self.scenario_engine = scenario_engine
        self.calculation_adapter = calculation_adapter
        self.calculation_adapter_enabled = calculation_adapter_enabled
        self.calculation_adapter_path = calculation_adapter_path
        self.currency = str(currency or "USD").upper()
        self.default_tax_rate = float(default_tax_rate)

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
        contract_guard_reason: str | None = None,
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
            contract_guard_reason=contract_guard_reason,
        )

        local_result = self._build_local_result(inputs)
        local_projection_updates = self._build_local_projection_updates(inputs)

        disposition = resolve_engine_call_disposition(
            engine_label=PLAN_SIMULATION_ENGINE_LABEL,
            calculation_adapter_enabled=self.calculation_adapter_enabled,
            calculation_adapter=self.calculation_adapter,
            contract_guard_reason=inputs.contract_guard_reason,
            disabled_behavior="local_ok",
            adapter_missing_behavior="local_ok",
        )
        if not disposition.use_calculation_adapter:
            if disposition.engine_status == ENGINE_STATUS_DEGRADED:
                return self._build_degraded_local_response(
                    local_result=local_result,
                    local_projection_updates=local_projection_updates,
                    fallback_method=disposition.fallback_method,
                    warning=disposition.warning,
                )
            return self._build_local_only_response(
                local_result=local_result,
                local_projection_updates=local_projection_updates,
            )

        if self.calculation_adapter is None:
            return self._build_local_only_response(
                local_result=local_result,
                local_projection_updates=local_projection_updates,
            )

        request_payload = self._build_request_payload(inputs=inputs)
        return await self._run_calculation_adapter_path(
            local_result=local_result,
            local_projection_updates=local_projection_updates,
            request_payload=request_payload,
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

    @staticmethod
    def _build_degraded_local_response(
        *,
        local_result: PlanningResponse,
        local_projection_updates: dict[str, Any],
        fallback_method: str | None,
        warning: str | None,
    ) -> PlanningResponse:
        return local_result.model_copy(
            update={
                **degraded_response_update(
                    fallback_method=fallback_method,
                    warning=warning,
                ),
                **local_projection_updates,
            }
        )

    async def _run_calculation_adapter_path(
        self,
        *,
        local_result: PlanningResponse,
        local_projection_updates: dict[str, Any],
        request_payload: RemoteScenarioRequestV1,
    ) -> PlanningResponse:
        try:
            response_payload = await self._request_calculation_service_response(request_payload=request_payload)
            return self._build_merged_calculation_service_response(
                local_result=local_result,
                local_projection_updates=local_projection_updates,
                response_payload=response_payload,
            )
        except CalculationAdapterError as exc:
            return local_result.model_copy(
                update={
                    **degraded_response_update(
                        engine="local",
                        fallback_method="local_scenario_engine_fallback",
                        warning=calculation_unavailable_warning(
                            engine_label=PLAN_SIMULATION_ENGINE_LABEL,
                            error=exc,
                        ),
                    ),
                    **local_projection_updates,
                }
            )

    async def _request_calculation_service_response(
        self,
        *,
        request_payload: RemoteScenarioRequestV1,
    ) -> RemoteScenarioResponseV1:
        if self.calculation_adapter is None:
            raise CalculationAdapterError("CalculationAdapter adapter is not configured")
        return await self.calculation_adapter.post_json(
            path=self.calculation_adapter_path,
            request_payload=request_payload.model_dump(mode="json"),
            request_model=RemoteScenarioRequestV1,
            response_model=RemoteScenarioResponseV1,
        )

    def _build_merged_calculation_service_response(
        self,
        *,
        local_result: PlanningResponse,
        local_projection_updates: dict[str, Any],
        response_payload: RemoteScenarioResponseV1,
    ) -> PlanningResponse:
        scenarios = self._merge_calculation_service_scenarios(
            local_scenarios=local_result.scenarios,
            calculation_service_scenarios=response_payload.scenarios,
        )
        return PlanningResponse(
            scenarios=scenarios,
            monte_carlo=local_result.monte_carlo,
            simulation=local_result.simulation,
            engine="simulation",
            engine_status=response_payload.engine_status,
            fallback_method=response_payload.fallback_method,
            warnings=list(response_payload.warnings),
            **local_projection_updates,
        )

    def _build_request_payload(
        self,
        *,
        inputs: _ScenarioRunInputs,
    ) -> RemoteScenarioRequestV1:
        resolved_years = int(self.scenario_engine.years_to_retirement if inputs.years is None else inputs.years)
        resolved_contribution = float(
            self.scenario_engine.annual_contribution_usd
            if inputs.annual_contribution_usd is None
            else inputs.annual_contribution_usd
        )
        resolved_hsa = float(
            self.scenario_engine.hsa_delta_default
            if inputs.hsa_extra_contribution_usd is None
            else inputs.hsa_extra_contribution_usd
        )

        first_year_income = 0.0
        if inputs.income_projection:
            first_year_income = float(inputs.income_projection.get("first_year_gross_income_usd") or 0.0)

        first_year_expenses = 0.0
        if inputs.expense_projection:
            first_year_expenses = float(inputs.expense_projection.get("first_year_expenses_usd") or 0.0)

        first_year_debt_payments = 0.0
        if inputs.debt_projection:
            selected = inputs.debt_projection.get("selected_scenario")
            if isinstance(selected, dict):
                first_year_debt_payments = float(selected.get("first_year_payments_usd") or 0.0)

        timeline_income_impact = 0.0
        timeline_expense_impact = 0.0
        timeline_debt_impact = 0.0
        if inputs.timeline_projection:
            timeline_income_impact = float(inputs.timeline_projection.get("first_year_income_impact_usd") or 0.0)
            timeline_expense_impact = float(inputs.timeline_projection.get("first_year_expense_impact_usd") or 0.0)
            timeline_debt_impact = float(inputs.timeline_projection.get("first_year_debt_payment_impact_usd") or 0.0)

        baseline_assumptions = {
            "annual_return_rate": float(self.scenario_engine.baseline_return),
            "annual_inflation_rate": float(self.scenario_engine.inflation),
            "effective_tax_rate": self.default_tax_rate,
            "annual_income": first_year_income + timeline_income_impact,
            "annual_expenses": first_year_expenses + timeline_expense_impact,
            "annual_debt_payments": first_year_debt_payments + timeline_debt_impact,
        }

        scenario_overrides = [
            RemoteScenarioOverrideV1(
                scenario_id="baseline",
                label="baseline",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.baseline_return),
                    "annual_contribution": resolved_contribution,
                    "horizon_years": resolved_years,
                },
            ),
            RemoteScenarioOverrideV1(
                scenario_id="optimistic",
                label="optimistic",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.optimistic_return),
                    "annual_contribution": resolved_contribution,
                    "horizon_years": resolved_years,
                },
            ),
            RemoteScenarioOverrideV1(
                scenario_id="conservative",
                label="conservative",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.conservative_return),
                    "annual_contribution": resolved_contribution,
                    "horizon_years": resolved_years,
                },
            ),
            RemoteScenarioOverrideV1(
                scenario_id="hsa_delta",
                label="hsa_delta",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.baseline_return),
                    "annual_contribution": resolved_contribution + resolved_hsa,
                    "horizon_years": resolved_years,
                },
            ),
        ]

        mapped_accounts = self._map_accounts(
            current_portfolio_value_usd=inputs.current_portfolio_value_usd,
            annual_contribution_usd=resolved_contribution,
            accounts=inputs.accounts,
        )

        metadata: dict[str, Any] = {
            "source": "buildwealth_orchestrator",
            "annual_contribution_usd": resolved_contribution,
        }
        if inputs.income_projection:
            metadata["income_projection"] = inputs.income_projection
        if inputs.expense_projection:
            metadata["expense_projection"] = inputs.expense_projection
        if inputs.debt_projection:
            metadata["debt_projection"] = inputs.debt_projection
        if inputs.timeline_projection:
            metadata["timeline_projection"] = inputs.timeline_projection
        if inputs.contribution_allocation:
            metadata["contribution_allocation"] = inputs.contribution_allocation
        if inputs.social_security_projection:
            metadata["social_security_projection"] = inputs.social_security_projection
        if inputs.rmd_projection:
            metadata["rmd_projection"] = inputs.rmd_projection
        if inputs.assumption_set_id:
            metadata["assumption_set_id"] = str(inputs.assumption_set_id)
        if inputs.assumption_set_name:
            metadata["assumption_set_name"] = str(inputs.assumption_set_name)
        if inputs.filing_status:
            metadata["filing_status"] = inputs.filing_status
        if inputs.state_tax_rate is not None:
            metadata["state_tax_rate"] = float(inputs.state_tax_rate)
        metadata["include_irmaa"] = bool(inputs.include_irmaa)
        if inputs.roth_conversion_annual_amount_usd is not None:
            metadata["roth_conversion_annual_amount_usd"] = float(inputs.roth_conversion_annual_amount_usd)
        if inputs.roth_conversion_start_age is not None:
            metadata["roth_conversion_start_age"] = int(inputs.roth_conversion_start_age)
        if inputs.roth_conversion_end_age is not None:
            metadata["roth_conversion_end_age"] = int(inputs.roth_conversion_end_age)
        drawdown_order_text = (
            ", ".join(str(item).strip() for item in inputs.drawdown_order if str(item).strip())
            if isinstance(inputs.drawdown_order, list)
            else str(inputs.drawdown_order or "").strip()
        )
        if drawdown_order_text:
            metadata["drawdown_order"] = drawdown_order_text
        if inputs.household_mode:
            metadata["household_mode"] = str(inputs.household_mode).strip().lower()
        if inputs.household_partner_income_usd is not None:
            metadata["household_partner_income_usd"] = float(inputs.household_partner_income_usd)
        if inputs.household_partner_income_growth_rate is not None:
            metadata["household_partner_income_growth_rate"] = float(inputs.household_partner_income_growth_rate)
        if inputs.household_partner_retirement_age is not None:
            metadata["household_partner_retirement_age"] = int(inputs.household_partner_retirement_age)
        if inputs.household_partner_social_security_annual_usd is not None:
            metadata["household_partner_social_security_annual_usd"] = float(inputs.household_partner_social_security_annual_usd)
        if inputs.household_partner_social_security_claiming_age is not None:
            metadata["household_partner_social_security_claiming_age"] = int(inputs.household_partner_social_security_claiming_age)
        if inputs.household_shared_goal_target_usd is not None:
            metadata["household_shared_goal_target_usd"] = float(inputs.household_shared_goal_target_usd)
        if inputs.household_shared_goal_target_year is not None:
            metadata["household_shared_goal_target_year"] = int(inputs.household_shared_goal_target_year)
        if inputs.household_shared_goal_annual_funding_usd is not None:
            metadata["household_shared_goal_annual_funding_usd"] = float(inputs.household_shared_goal_annual_funding_usd)
        if inputs.household_partner_income_added_first_year_usd is not None:
            metadata["household_partner_income_added_first_year_usd"] = float(inputs.household_partner_income_added_first_year_usd)
        if inputs.household_partner_income_added_total_usd is not None:
            metadata["household_partner_income_added_total_usd"] = float(inputs.household_partner_income_added_total_usd)
        if inputs.withdrawal_strategy:
            metadata["withdrawal_strategy"] = inputs.withdrawal_strategy
        if inputs.retirement_age is not None:
            metadata["retirement_age"] = int(inputs.retirement_age)
        if inputs.simulation_mode:
            metadata["simulation_mode"] = str(inputs.simulation_mode).strip().lower()
        if inputs.simulation_monte_carlo_variant:
            metadata["simulation_monte_carlo_variant"] = str(inputs.simulation_monte_carlo_variant).strip().lower()
        if inputs.simulation_historical_start_year is not None:
            metadata["simulation_historical_start_year"] = int(inputs.simulation_historical_start_year)
        if inputs.simulation_seed is not None:
            metadata["simulation_seed"] = int(inputs.simulation_seed)

        return RemoteScenarioRequestV1(
            request_id=uuid4().hex,
            currency=self.currency,
            start_year=inputs.start_year or datetime.now(timezone.utc).year,
            horizon_years=resolved_years,
            household={"current_age": 35, "retirement_age": 35 + resolved_years},
            accounts=mapped_accounts,
            baseline_assumptions=baseline_assumptions,
            scenario_overrides=scenario_overrides,
            metadata=metadata,
        )

    def _map_accounts(
        self,
        *,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float,
        accounts: list[dict[str, Any]] | None,
    ) -> list[RemoteScenarioAccountV1]:
        if not accounts:
            return [
                RemoteScenarioAccountV1(
                    account_id="primary",
                    account_type="portfolio",
                    tax_treatment="taxable",
                    balance=float(current_portfolio_value_usd),
                    annual_contribution=annual_contribution_usd,
                )
            ]

        mapped: list[RemoteScenarioAccountV1] = []
        for index, account in enumerate(accounts, start=1):
            account_id = str(account.get("account_id") or account.get("id") or f"account-{index}").strip()
            if not account_id:
                account_id = f"account-{index}"

            account_type = normalize_account_type(account.get("account_type") or account.get("type"))
            tax_treatment_raw = account.get("tax_treatment")
            if isinstance(tax_treatment_raw, str):
                candidate_treatment = tax_treatment_raw.strip()
            else:
                candidate_treatment = ""
            if candidate_treatment in {"taxable", "tax_deferred", "tax_free"}:
                tax_treatment = cast(Literal["taxable", "tax_deferred", "tax_free"], candidate_treatment)
            else:
                tax_treatment = tax_treatment_for_account_type(account_type)

            balance = float(account.get("balance_usd") or account.get("balance") or 0.0)
            annual_contribution = float(
                account.get("annual_contribution_usd")
                or account.get("annual_contribution")
                or account.get("total_contribution_usd")
                or 0.0
            )

            mapped.append(
                RemoteScenarioAccountV1(
                    account_id=account_id,
                    account_type=account_type,
                    tax_treatment=tax_treatment,
                    balance=balance,
                    annual_contribution=annual_contribution,
                )
            )

        if mapped:
            return mapped
        return [
            RemoteScenarioAccountV1(
                account_id="primary",
                account_type="portfolio",
                tax_treatment="taxable",
                balance=float(current_portfolio_value_usd),
                annual_contribution=annual_contribution_usd,
            )
        ]

    @staticmethod
    def _merge_calculation_service_scenarios(
        *,
        local_scenarios: list[ScenarioResult],
        calculation_service_scenarios: list[RemoteScenarioOutputV1],
    ) -> list[ScenarioResult]:
        by_label: dict[str, RemoteScenarioOutputV1] = {}
        for row in calculation_service_scenarios:
            key = str(row.scenario_id or row.label).strip().lower()
            if key in {"baseline", "optimistic", "conservative", "hsa_delta"}:
                by_label[key] = row

        merged: list[ScenarioResult] = []
        for local in local_scenarios:
            key = str(local.label).strip().lower()
            calculation_service = by_label.get(key)
            if calculation_service is None:
                merged.append(local)
                continue

            timeline_points = [
                ScenarioTimelinePoint(
                    year=int(item.year),
                    age=int(item.age),
                    starting_balance_usd=round(float(item.starting_balance), 2),
                    ending_balance_usd=round(float(item.ending_balance), 2),
                    contributions_usd=round(float(item.contributions or 0.0), 2),
                    income_usd=round(float(item.income or 0.0), 2),
                    expenses_usd=round(float(item.expenses or 0.0), 2),
                    taxes_usd=round(float(item.taxes or 0.0), 2),
                    growth_usd=round(float(item.growth or 0.0), 2),
                    withdrawals_usd=round(float(item.withdrawals or 0.0), 2),
                    ending_balance_real_usd=(
                        round(float(item.ending_balance_real), 2)
                        if item.ending_balance_real is not None
                        else None
                    ),
                )
                for item in calculation_service.timeline
            ]

            merged.append(
                ScenarioResult(
                    label=local.label,
                    future_value_usd=round(float(calculation_service.summary.ending_balance_nominal), 2),
                    real_value_usd=round(float(calculation_service.summary.ending_balance_real), 2),
                    assumptions=dict(local.assumptions),
                    timeline_points=timeline_points,
                    account_balance_points=list(local.account_balance_points),
                )
            )

        return merged
