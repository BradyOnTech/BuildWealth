from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from buildwealth_orchestrator.services.timeline_defaults import (
    TIMELINE_DEFAULT_IMPACT_BY_EVENT,
    TIMELINE_EVENT_TYPE_VALUES,
    TIMELINE_FREQUENCY_VALUES,
    TIMELINE_IMPACT_TYPE_VALUES,
)


class Holding(BaseModel):
    symbol: str
    name: str
    data_source: str | None = None
    asset_type: str | None = None
    asset_class: str | None = None
    sector: str | None = None
    region: str | None = None
    metadata_source: str | None = None
    expense_ratio: float | None = None
    allocation_percent: float = 0.0
    value_usd: float = 0.0
    quantity: float = 0.0
    market_price: float | None = None
    net_performance_usd: float | None = None
    net_performance_percent: float | None = None


class PortfolioSnapshot(BaseModel):
    as_of: datetime
    base_currency: str = "USD"
    total_value_usd: float = 0.0
    total_investment_usd: float = 0.0
    net_performance_usd: float = 0.0
    net_performance_percent: float = 0.0
    twr_return_pct: float | None = None
    twr_annualized_return_pct: float | None = None
    xirr_annualized_return_pct: float | None = None
    price_return_usd: float | None = None
    income_return_usd: float | None = None
    total_return_usd: float | None = None
    price_return_pct: float | None = None
    income_return_pct: float | None = None
    total_return_pct: float | None = None
    holdings: list[Holding] = Field(default_factory=list)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class SnapshotHistoryPoint(BaseModel):
    as_of: datetime
    total_value_usd: float
    net_performance_usd: float
    net_performance_percent: float
    holdings_count: int


class SnapshotHistoryResponse(BaseModel):
    points: list[SnapshotHistoryPoint] = Field(default_factory=list)
    window_points: int
    latest_as_of: datetime | None = None
    oldest_as_of: datetime | None = None
    delta_total_value_usd: float | None = None
    delta_total_value_percent: float | None = None
    delta_net_performance_usd: float | None = None
    top_holding_value_changes: list[dict[str, Any]] = Field(default_factory=list)


class EngineStatusItem(BaseModel):
    name: str
    enabled: bool
    reachable: bool
    contract_version: int | None = None
    expected_contract_version: int | None = None
    contract_compatible: bool | None = None
    degraded_count: int = 0
    last_error: str | None = None
    last_checked_at: datetime | None = None


class EngineStatusResponse(BaseModel):
    as_of: datetime
    engines: list[EngineStatusItem] = Field(default_factory=list)


# Internal shared response envelopes.
# Guardrail: keep inheritance depth to one internal base layer.
# Public inheritors: PortfolioBenchmarkResponse, PortfolioAttributionResponse.
class _EngineContractResponseBase(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None


class PortfolioBenchmarkSummary(BaseModel):
    portfolio_return_pct: float
    benchmark_return_pct_by_symbol: dict[str, float] = Field(default_factory=dict)
    alpha_pct_by_symbol: dict[str, float] = Field(default_factory=dict)
    tracking_error_pct: float | None = None
    max_drawdown_pct: float | None = None


class PortfolioBenchmarkSeriesPoint(BaseModel):
    date: date
    portfolio_index: float
    benchmark_index_by_symbol: dict[str, float] = Field(default_factory=dict)
    alpha_index_by_symbol: dict[str, float] = Field(default_factory=dict)


class PortfolioBenchmarkResponse(_EngineContractResponseBase):
    engine: str
    benchmark_symbols: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    summary: PortfolioBenchmarkSummary
    series: list[PortfolioBenchmarkSeriesPoint] = Field(default_factory=list)


class PortfolioAttributionSummary(BaseModel):
    portfolio_total_return_base: float
    portfolio_total_value_base: float
    accounted_return_base: float
    residual_return_base: float
    contributors_count: int
    detractors_count: int


class PortfolioAttributionPosition(BaseModel):
    symbol: str
    name: str | None = None
    account_id: str | None = None
    asset_class: str | None = None
    current_value_base: float = 0.0
    cost_basis_base: float = 0.0
    price_return_base: float = 0.0
    income_return_base: float = 0.0
    total_return_base: float = 0.0
    total_return_pct: float | None = None
    contribution_pct: float = 0.0
    allocation_pct: float = 0.0


class PortfolioAttributionResponse(_EngineContractResponseBase):
    engine: str
    as_of: datetime | None = None
    top_n: int = 5
    summary: PortfolioAttributionSummary
    contributors: list[PortfolioAttributionPosition] = Field(default_factory=list)
    detractors: list[PortfolioAttributionPosition] = Field(default_factory=list)
    positions: list[PortfolioAttributionPosition] = Field(default_factory=list)


class ScenarioRequest(BaseModel):
    current_portfolio_value_usd: float | None = None
    annual_contribution_usd: float | None = None
    years: int | None = None
    hsa_extra_contribution_usd: float | None = None
    state_tax_rate: float | None = Field(default=None, ge=0, le=1)
    include_irmaa: bool = True
    household_mode: str | None = None
    household_partner_income_usd: float | None = Field(default=None, ge=0)
    household_partner_income_growth_rate: float | None = Field(default=None, ge=-1, le=1)
    household_partner_retirement_age: int | None = Field(default=None, ge=0, le=120)
    household_partner_social_security_annual_usd: float | None = Field(default=None, ge=0)
    household_partner_social_security_claiming_age: int | None = Field(default=None, ge=0, le=120)
    household_shared_goal_target_usd: float | None = Field(default=None, ge=0)
    household_shared_goal_target_year: int | None = Field(default=None, ge=1900, le=2500)
    filing_status: str | None = None
    drawdown_order: str | None = None
    simulation_mode: str | None = None
    simulation_monte_carlo_variant: str | None = None
    simulation_historical_start_year: int | None = Field(default=None, ge=1928, le=2024)
    simulation_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    roth_conversion_annual_amount_usd: float | None = Field(default=None, ge=0)
    roth_conversion_start_age: int | None = Field(default=None, ge=0, le=120)
    roth_conversion_end_age: int | None = Field(default=None, ge=0, le=120)


class IncomeProjectionIncomeInput(BaseModel):
    id: str = ""
    label: str
    monthly_amount_usd: float = Field(ge=0)
    is_pre_tax: bool = False
    annual_growth_rate: float | None = Field(default=None, ge=-1, le=1)
    start_date: datetime | None = None
    end_date: datetime | None = None


class IncomeProjectionRequest(BaseModel):
    start_year: int | None = Field(default=None, ge=1900, le=2500)
    years: int = Field(default=30, ge=1, le=80)
    default_annual_growth_rate: float | None = Field(default=None, ge=-1, le=1)
    income_items: list[IncomeProjectionIncomeInput] | None = None


class IncomeProjectionYearPoint(BaseModel):
    year: int
    gross_income_usd: float
    pre_tax_income_usd: float
    post_tax_income_usd: float
    active_income_items: int


class IncomeProjectionResponse(BaseModel):
    start_year: int
    years: int
    default_annual_growth_rate: float
    income_items_count: int
    first_year_gross_income_usd: float
    final_year_gross_income_usd: float
    cumulative_gross_income_usd: float
    annualized_income_growth_rate: float | None = None
    yearly_points: list[IncomeProjectionYearPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExpenseProjectionExpenseInput(BaseModel):
    id: str = ""
    label: str
    monthly_amount_usd: float = Field(ge=0)
    category: str = "general"
    is_fixed: bool = True
    inflation_rate: float | None = Field(default=None, ge=-1, le=1)
    start_date: datetime | None = None
    end_date: datetime | None = None


class ExpenseProjectionRequest(BaseModel):
    start_year: int | None = Field(default=None, ge=1900, le=2500)
    years: int = Field(default=30, ge=1, le=80)
    default_inflation_rate: float | None = Field(default=None, ge=-1, le=1)
    expense_items: list[ExpenseProjectionExpenseInput] | None = None


class ExpenseProjectionYearPoint(BaseModel):
    year: int
    total_expenses_usd: float
    fixed_expenses_usd: float
    variable_expenses_usd: float
    active_expense_items: int


class ExpenseProjectionResponse(BaseModel):
    start_year: int
    years: int
    default_inflation_rate: float
    expense_items_count: int
    first_year_expenses_usd: float
    final_year_expenses_usd: float
    cumulative_expenses_usd: float
    annualized_expense_growth_rate: float | None = None
    yearly_points: list[ExpenseProjectionYearPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DebtProjectionDebtInput(BaseModel):
    id: str = ""
    label: str
    balance_usd: float = Field(ge=0)
    interest_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_payment_usd: float = Field(gt=0)
    payoff_strategy: Literal["minimum", "snowball", "avalanche", "custom"] = "minimum"
    custom_monthly_payment_usd: float | None = Field(default=None, ge=0)


class DebtProjectionRequest(BaseModel):
    start_date: date | None = None
    max_years: int = Field(default=40, ge=1, le=80)
    strategy: Literal["minimum", "snowball", "avalanche", "custom"] = "minimum"
    monthly_accelerated_payment_usd: float = Field(default=0.0, ge=0)
    debt_items: list[DebtProjectionDebtInput] | None = None


class DebtProjectionMonthPoint(BaseModel):
    month_index: int
    as_of: date
    total_balance_usd: float
    payment_usd: float
    interest_paid_usd: float
    principal_paid_usd: float
    active_debts: int


class DebtProjectionDebtSummary(BaseModel):
    id: str
    label: str
    original_balance_usd: float
    remaining_balance_usd: float
    interest_paid_usd: float
    principal_paid_usd: float
    paid_off: bool


class DebtProjectionScenario(BaseModel):
    strategy: Literal["minimum", "snowball", "avalanche", "custom"]
    months_to_payoff: int
    payoff_date: date
    paid_off: bool
    remaining_balance_usd: float
    total_interest_paid_usd: float
    total_principal_paid_usd: float
    total_paid_usd: float
    first_year_payments_usd: float
    month_points: list[DebtProjectionMonthPoint] = Field(default_factory=list)
    debt_summaries: list[DebtProjectionDebtSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DebtProjectionResponse(BaseModel):
    start_date: date
    max_years: int
    debt_items_count: int
    strategy: Literal["minimum", "snowball", "avalanche", "custom"]
    monthly_accelerated_payment_usd: float
    minimum_scenario: DebtProjectionScenario
    selected_scenario: DebtProjectionScenario
    payoff_months_saved_vs_minimum: int | None = None
    interest_saved_vs_minimum_usd: float
    warnings: list[str] = Field(default_factory=list)


class SocialSecurityEarningsPoint(BaseModel):
    year: int = Field(ge=1900, le=2500)
    earnings_usd: float = Field(ge=0)


class SocialSecurityProjectionRequest(BaseModel):
    start_year: int | None = Field(default=None, ge=1900, le=2500)
    years: int = Field(default=30, ge=1, le=80)
    current_age: int = Field(default=35, ge=0, le=120)
    birth_year: int | None = Field(default=None, ge=1900, le=2500)
    claiming_age: int | None = Field(default=None, ge=62, le=70)
    life_expectancy_age: int | None = Field(default=None, ge=67, le=120)
    fra_monthly_benefit_usd: float | None = Field(default=None, ge=0)
    estimated_annual_earnings_usd: float | None = Field(default=None, ge=0)
    earnings_history: list[SocialSecurityEarningsPoint] | None = None
    cola_rate: float = Field(default=0.02, ge=-0.2, le=0.2)
    claim_age_options: list[int] | None = None
    pia_bend_point_1_usd: float = Field(default=1226.0, gt=0)
    pia_bend_point_2_usd: float = Field(default=7391.0, gt=0)


class SocialSecurityProjectionClaimOption(BaseModel):
    claiming_age: int
    monthly_benefit_usd: float
    annual_benefit_usd: float
    cumulative_lifetime_benefits_usd: float


class SocialSecurityProjectionYearPoint(BaseModel):
    year: int
    age: int
    annual_benefit_usd: float
    cumulative_benefits_usd: float


class SocialSecurityProjectionResponse(BaseModel):
    start_year: int
    years: int
    current_age: int
    birth_year: int | None = None
    fra_age: float
    life_expectancy_age: int
    selected_claiming_age: int
    optimal_claiming_age: int
    fra_monthly_benefit_usd: float
    estimated_aime_usd: float
    estimated_pia_monthly_usd: float
    selected_monthly_benefit_usd: float
    selected_annual_benefit_usd: float
    cola_rate: float
    pia_bend_point_1_usd: float
    pia_bend_point_2_usd: float
    claim_options: list[SocialSecurityProjectionClaimOption] = Field(default_factory=list)
    yearly_points: list[SocialSecurityProjectionYearPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RmdProjectionAccountInput(BaseModel):
    account_id: str
    account_type: str = "ira"
    balance_usd: float = Field(default=0.0, ge=0)


class RmdProjectionRequest(BaseModel):
    start_year: int | None = Field(default=None, ge=1900, le=2500)
    years: int = Field(default=30, ge=1, le=80)
    current_age: int = Field(default=35, ge=0, le=120)
    birth_year: int | None = Field(default=None, ge=1900, le=2500)
    expected_return: float = Field(default=0.04, ge=-0.95, le=1.0)
    start_age_override: int | None = Field(default=None, ge=72, le=120)
    accounts: list[RmdProjectionAccountInput] | None = None


class RmdProjectionAccountDistribution(BaseModel):
    account_id: str
    account_type: str
    starting_balance_usd: float
    rmd_usd: float


class RmdProjectionYearPoint(BaseModel):
    year: int
    age: int
    lookup_age: int | None = None
    life_expectancy_factor: float | None = None
    total_eligible_balance_start_usd: float
    total_rmd_usd: float
    cumulative_rmds_usd: float
    account_rmds: list[RmdProjectionAccountDistribution] = Field(default_factory=list)


class RmdProjectionResponse(BaseModel):
    start_year: int
    years: int
    current_age: int
    birth_year: int | None = None
    rmd_start_age: int
    expected_return: float
    eligible_account_count: int
    total_initial_eligible_balance_usd: float
    total_projected_rmds_usd: float
    yearly_points: list[RmdProjectionYearPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TimelineImpactYearPoint(BaseModel):
    year: int
    income_impact_usd: float
    expense_impact_usd: float
    portfolio_impact_usd: float
    contribution_impact_usd: float
    debt_payment_impact_usd: float
    net_cashflow_impact_usd: float
    events_applied: int


class TimelineImpactProjectionResponse(BaseModel):
    start_year: int
    years: int
    events_count: int
    first_year_income_impact_usd: float
    first_year_expense_impact_usd: float
    first_year_portfolio_impact_usd: float
    first_year_contribution_impact_usd: float
    first_year_debt_payment_impact_usd: float
    cumulative_net_cashflow_impact_usd: float
    yearly_points: list[TimelineImpactYearPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContributionAllocationAccountInput(BaseModel):
    account_id: str
    account_name: str | None = None
    account_type: str = "taxableBrokerage"
    balance_usd: float = Field(default=0.0, ge=0)


class ContributionAllocationRequest(BaseModel):
    annual_contribution_usd: float = Field(ge=0)
    age: int = Field(default=35, ge=0, le=120)
    accounts: list[ContributionAllocationAccountInput] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    base_rule: dict[str, Any] = Field(default_factory=lambda: {"type": "save"})
    profile_id: str | None = None
    employer_match_target_usd: float = Field(default=6000.0, ge=0)


class ContributionAllocationAccountResult(BaseModel):
    account_id: str
    account_name: str
    account_type: str
    balance_usd: float = 0.0
    employee_contribution_usd: float = 0.0
    employer_match_usd: float = 0.0
    total_contribution_usd: float = 0.0
    applied_rule_ids: list[str] = Field(default_factory=list)


class ContributionAllocationRuleResult(BaseModel):
    rule_id: str
    account_id: str
    account_type: str
    rank: int
    contribution_type: str
    requested_employee_contribution_usd: float | None = None
    employee_contribution_usd: float = 0.0
    employer_match_usd: float = 0.0
    limited_by: list[str] = Field(default_factory=list)


class ContributionAllocationResponse(BaseModel):
    profile_id: str | None = None
    base_rule_type: str
    annual_contribution_target_usd: float
    employee_contributions_usd: float
    employer_match_usd: float
    total_contributions_usd: float
    unallocated_contribution_usd: float
    allocations: list[ContributionAllocationAccountResult] = Field(default_factory=list)
    rule_results: list[ContributionAllocationRuleResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TaxEstimateRequest(BaseModel):
    tax_year: int = Field(default=2026, ge=1900, le=2500)
    filing_status: Literal[
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
    ] = "single"
    earned_income_usd: float = 0.0
    ordinary_income_usd: float = 0.0
    short_term_capital_gains_usd: float = 0.0
    long_term_capital_gains_usd: float = 0.0
    qualified_dividends_usd: float = 0.0
    interest_income_usd: float = 0.0
    social_security_income_usd: float = 0.0
    tax_exempt_interest_income_usd: float = Field(default=0.0, ge=0)
    pre_tax_contributions_usd: float = Field(default=0.0, ge=0)
    state_tax_rate: float = Field(default=0.0, ge=0, le=1)
    state_tax_deduction_usd: float = Field(default=0.0, ge=0)
    age: int | None = Field(default=None, ge=0, le=120)
    include_irmaa: bool = True
    medicare_months_covered: int = Field(default=12, ge=0, le=12)
    tax_withholding_usd: float = Field(default=0.0, ge=0)


class TaxEstimateResponse(BaseModel):
    tax_year: int
    filing_status: str
    gross_income_usd: float
    adjusted_gross_income_usd: float
    standard_deduction_usd: float
    taxable_ordinary_income_usd: float
    taxable_capital_gains_income_usd: float
    taxable_social_security_income_usd: float
    modified_adjusted_gross_income_usd: float
    federal_income_tax_usd: float
    capital_gains_tax_usd: float
    state_taxable_income_usd: float
    state_income_tax_usd: float
    state_tax_rate: float
    niit_tax_usd: float
    niit_income_subject_usd: float
    niit_threshold_usd: float
    irmaa_applied: bool = False
    irmaa_bracket_label: str | None = None
    irmaa_medicare_months: int = 0
    irmaa_part_b_monthly_surcharge_usd: float = 0.0
    irmaa_part_d_monthly_surcharge_usd: float = 0.0
    irmaa_total_monthly_surcharge_usd: float = 0.0
    irmaa_annual_surcharge_usd: float = 0.0
    fica_social_security_tax_usd: float
    fica_medicare_tax_usd: float
    total_fica_tax_usd: float
    total_estimated_tax_usd: float
    effective_tax_rate: float | None = None
    top_marginal_federal_income_tax_rate: float
    top_marginal_capital_gains_tax_rate: float
    tax_withholding_usd: float
    amount_due_usd: float
    refund_usd: float
    warnings: list[str] = Field(default_factory=list)


class ScenarioTimelinePoint(BaseModel):
    year: int
    age: int
    starting_balance_usd: float
    ending_balance_usd: float
    contributions_usd: float = 0.0
    income_usd: float = 0.0
    social_security_income_usd: float = 0.0
    expenses_usd: float = 0.0
    taxes_usd: float = 0.0
    federal_taxes_usd: float = 0.0
    state_taxes_usd: float = 0.0
    irmaa_surcharges_usd: float = 0.0
    growth_usd: float = 0.0
    withdrawals_usd: float = 0.0
    rmds_usd: float = 0.0
    roth_conversions_usd: float = 0.0
    ending_balance_real_usd: float | None = None


class ScenarioAccountBalancePoint(BaseModel):
    year: int
    account_id: str
    account_type: str
    tax_treatment: Literal["taxable", "tax_deferred", "tax_free"]
    starting_balance_usd: float
    contribution_usd: float = 0.0
    withdrawal_usd: float = 0.0
    rmd_withdrawal_usd: float = 0.0
    roth_conversion_out_usd: float = 0.0
    roth_conversion_in_usd: float = 0.0
    growth_usd: float = 0.0
    ending_balance_usd: float


class ScenarioResult(BaseModel):
    label: Literal["baseline", "optimistic", "conservative", "hsa_delta"]
    future_value_usd: float
    real_value_usd: float
    assumptions: dict[str, float | int | str | bool | None]
    timeline_points: list[ScenarioTimelinePoint] = Field(default_factory=list)
    account_balance_points: list[ScenarioAccountBalancePoint] = Field(default_factory=list)


class HouseholdPlanningContext(BaseModel):
    mode: str = "individual"
    source: str | None = None
    enabled: bool = False
    filing_status: str | None = None
    partner_income_usd: float = 0.0
    partner_income_growth_rate: float = 0.0
    partner_retirement_age: int | None = None
    partner_social_security_annual_usd: float = 0.0
    partner_social_security_claiming_age: int | None = None
    shared_goal_target_usd: float = 0.0
    shared_goal_target_year: int | None = None
    shared_goal_annual_funding_usd: float = 0.0
    partner_income_added_first_year_usd: float = 0.0
    partner_income_added_total_usd: float = 0.0


class PlanningResponse(BaseModel):
    scenarios: list[ScenarioResult]
    monte_carlo: dict[str, Any]
    simulation: dict[str, Any] = Field(default_factory=dict)
    engine: Literal["local", "ignidash"] = "local"
    engine_status: Literal["ok", "degraded"] = "ok"
    fallback_method: str | None = None
    warnings: list[str] = Field(default_factory=list)
    household: HouseholdPlanningContext | None = None
    income_projection: IncomeProjectionResponse | None = None
    expense_projection: ExpenseProjectionResponse | None = None
    debt_projection: DebtProjectionResponse | None = None
    timeline_projection: TimelineImpactProjectionResponse | None = None
    contribution_allocation: ContributionAllocationResponse | None = None
    social_security_projection: SocialSecurityProjectionResponse | None = None
    rmd_projection: RmdProjectionResponse | None = None


class ChatRequest(BaseModel):
    question: str
    refresh_snapshot: bool = True


class ChatResponse(BaseModel):
    answer: str
    route: str
    data: dict[str, Any] = Field(default_factory=dict)


class OptionsChainRequest(BaseModel):
    symbol: str


class PriceHistoryRequest(BaseModel):
    symbol: str
    period: str = "1y"
    interval: str = "1d"


class ResearchResponse(BaseModel):
    symbol: str
    provider: str
    available: bool
    message: str
    records: list[dict[str, Any]] = Field(default_factory=list)


class ResearchCompareRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    period: str = "6mo"
    interval: str = "1d"
    baseline_symbol: str | None = None

    @model_validator(mode="after")
    def _normalize_symbols(self) -> "ResearchCompareRequest":
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in self.symbols:
            symbol = str(raw or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized.append(symbol)
            if len(normalized) >= 20:
                break
        self.symbols = normalized
        if self.baseline_symbol is not None:
            resolved = str(self.baseline_symbol or "").strip().upper()
            self.baseline_symbol = resolved or None
        self.period = str(self.period or "6mo").strip() or "6mo"
        self.interval = str(self.interval or "1d").strip() or "1d"
        return self


class ResearchCompareItem(BaseModel):
    symbol: str
    available: bool
    message: str
    rank: int | None = None
    score: float | None = None
    last_price: float | None = None
    day_change_pct: float | None = None
    period_change_pct: float | None = None
    volatility_pct: float | None = None
    market_cap_usd: float | None = None
    pe_ratio: float | None = None
    dividend_yield_pct: float | None = None
    quote_records: int = 0
    history_records: int = 0
    research_evidence_packet_id: str | None = None
    research_provider: str | None = None
    research_freshness_status: str | None = None
    research_confidence: str | None = None
    research_coverage_score: float | None = None
    research_blocking_gaps: list[str] = Field(default_factory=list)


class ResearchCompareSummary(BaseModel):
    requested_symbols: int
    compared_symbols: int
    available_symbols: int
    baseline_symbol: str | None = None
    ranked_symbols: list[str] = Field(default_factory=list)
    best_period_return_symbol: str | None = None
    worst_period_return_symbol: str | None = None
    highest_volatility_symbol: str | None = None
    lowest_volatility_symbol: str | None = None
    baseline_relative_return_pct: dict[str, float] = Field(default_factory=dict)


class ResearchCompareResponse(BaseModel):
    provider: str
    period: str
    interval: str
    generated_at: datetime
    symbols: list[str] = Field(default_factory=list)
    summary: ResearchCompareSummary
    items: list[ResearchCompareItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchEvidencePacketRequest(BaseModel):
    symbol: str
    period: str = "6mo"
    interval: str = "1d"

    @model_validator(mode="after")
    def _normalize_fields(self) -> "ResearchEvidencePacketRequest":
        self.symbol = str(self.symbol or "").strip().upper()
        self.period = str(self.period or "6mo").strip() or "6mo"
        self.interval = str(self.interval or "1d").strip() or "1d"
        return self


class ResearchEvidencePacket(BaseModel):
    packet_id: str
    symbol: str
    name: str | None = None
    asset_type: str | None = None
    sector: str | None = None
    provider: str
    period: str
    interval: str
    generated_at: datetime
    coverage: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ResearchDossierRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    period: str = "6mo"
    interval: str = "1d"
    baseline_symbol: str | None = None
    thesis: str = ""
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    plan_id: str | None = None
    save_to_plan: bool = True
    include_portfolio_fit: bool = True

    @model_validator(mode="after")
    def _normalize_fields(self) -> "ResearchDossierRequest":
        normalized_symbols: list[str] = []
        seen: set[str] = set()
        for raw in self.symbols:
            symbol = str(raw or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized_symbols.append(symbol)
            if len(normalized_symbols) >= 20:
                break
        self.symbols = normalized_symbols
        self.period = str(self.period or "6mo").strip() or "6mo"
        self.interval = str(self.interval or "1d").strip() or "1d"
        baseline = str(self.baseline_symbol or "").strip().upper()
        self.baseline_symbol = baseline or None
        self.thesis = str(self.thesis or "").strip()
        self.risks = [str(item or "").strip() for item in self.risks if str(item or "").strip()][:12]
        self.catalysts = [str(item or "").strip() for item in self.catalysts if str(item or "").strip()][:12]
        plan_id = str(self.plan_id or "").strip()
        self.plan_id = plan_id or None
        return self


class ResearchDossierResponse(BaseModel):
    provider: str
    period: str
    interval: str
    generated_at: datetime
    symbols: list[str] = Field(default_factory=list)
    baseline_symbol: str | None = None
    headline: str
    thesis: str = ""
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)
    evidence_packets: list[dict[str, Any]] = Field(default_factory=list)
    compare: ResearchCompareResponse
    portfolio_fit: dict[str, Any] = Field(default_factory=dict)
    dossier_markdown: str
    artifact: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ResearchDossierLookupItem(BaseModel):
    artifact_id: str
    file_name: str
    title: str
    created_at: datetime | None = None
    plan_id: str
    symbols: list[str] = Field(default_factory=list)
    content_preview: str = ""
    thesis_review: dict[str, Any] = Field(default_factory=dict)


class ResearchDossierLookupResponse(BaseModel):
    plan_id: str | None = None
    count: int = 0
    items: list[ResearchDossierLookupItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime


class WatchlistRankItem(BaseModel):
    symbol: str
    data_source: str = "OPENBB"
    note: str = ""
    thesis: str = ""
    thesis_reviewed_at: str | None = None
    thesis_expires_at: str | None = None
    thesis_reference_price_usd: float | None = None
    thesis_revision_history: list[dict[str, Any]] = Field(default_factory=list)
    target_price_usd: float | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    quote_available: bool = False
    quote_message: str = ""
    quote_price: float | None = None
    quote_change_pct: float | None = None
    history_available: bool = False
    history_message: str = ""
    period_label: str = "2y"
    period_first_close: float | None = None
    period_last_close: float | None = None
    period_change_pct: float | None = None
    all_time_high: float | None = None
    performance_from_high_pct: float | None = None
    market_condition: str = "UNKNOWN"
    trend50d: str = "UNKNOWN"
    trend200d: str = "UNKNOWN"
    history_records: int = 0
    research_evidence_packet_id: str | None = None
    research_provider: str | None = None
    research_freshness_status: str | None = None
    research_confidence: str | None = None
    research_coverage_score: float | None = None
    research_blocking_gaps: list[str] = Field(default_factory=list)
    provider_coverage: dict[str, Any] = Field(default_factory=dict)
    watchlist_rank: int | None = None
    watchlist_score_total: float | None = None
    watchlist_score: dict[str, Any] = Field(default_factory=dict)
    watchlist_score_reasons: list[str] = Field(default_factory=list)


class WatchlistRankResponse(BaseModel):
    period: str = "2y"
    interval: str = "1d"
    count: int = 0
    score_model: str = "watchlist_v1"
    sorted_by: str = "ranked"
    items: list[WatchlistRankItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime


class PortfolioFitAssessmentRequest(BaseModel):
    symbol: str
    amount_usd: float | None = Field(default=None, gt=0)
    proposed_account_id: str | None = None
    period: str = "6mo"
    interval: str = "1d"

    @model_validator(mode="after")
    def _normalize_fields(self) -> "PortfolioFitAssessmentRequest":
        self.symbol = str(self.symbol or "").strip().upper()
        proposed_account = str(self.proposed_account_id or "").strip()
        self.proposed_account_id = proposed_account or None
        self.period = str(self.period or "6mo").strip() or "6mo"
        self.interval = str(self.interval or "1d").strip() or "1d"
        return self


class PortfolioFitAssessmentResponse(BaseModel):
    symbol: str
    fit_status: Literal["fits", "mixed", "does_not_fit", "needs_more_context"]
    fit_score: float
    fit_reasons: list[str] = Field(default_factory=list)
    fit_risks: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    portfolio_impact: dict[str, Any] = Field(default_factory=dict)
    plan_impact: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    simulation_required: bool = False
    recommended_next_step: Literal[
        "research_more",
        "compare_alternatives",
        "simulate_trade",
        "review_concentration",
        "review_policy_restriction",
        "review_sector_exposure",
        "review_asset_class_exposure",
        "review_account_location",
        "review_cash_floor",
        "review_simplicity",
        "update_profile",
        "create_dossier",
        "discuss_in_copilot",
    ]


class CsvTemplateOption(BaseModel):
    id: str
    name: str
    description: str


class CsvImportRequest(BaseModel):
    path: str
    dry_run: bool = True
    delimiter: str = ","
    broker_template: str = "auto"
    default_data_source: str | None = None
    default_currency: str | None = None
    archive_after_success: bool = False


class CsvImportReconciliationRow(BaseModel):
    row_number: int
    status: Literal["accepted", "rejected"]
    confidence_flag: Literal["high", "medium", "low"] = "low"
    confidence_score: float = 0.0
    confidence_reasons: list[str] = Field(default_factory=list)
    normalization_flags: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    transaction_fingerprint: str | None = None
    raw_row: dict[str, str] = Field(default_factory=dict)
    normalized_row: dict[str, Any] = Field(default_factory=dict)


class CsvImportReconciliationReport(BaseModel):
    schema_version: int = 1
    parser_confidence_flag: Literal["high", "medium", "low"] = "low"
    parser_confidence_score: float = 0.0
    parser_confidence_flags: list[str] = Field(default_factory=list)
    total_rows: int = 0
    accepted_count: int = 0
    normalized_count: int = 0
    rejected_count: int = 0
    accepted_rows: list[CsvImportReconciliationRow] = Field(default_factory=list)
    normalized_rows: list[CsvImportReconciliationRow] = Field(default_factory=list)
    rejected_rows: list[CsvImportReconciliationRow] = Field(default_factory=list)


class CsvImportResponse(BaseModel):
    file_path: str
    dry_run: bool
    selected_template: str = "generic"
    detected_template: str = "generic"
    parsed_rows: int
    valid_activities: int
    imported_activities: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    reconciliation_report: CsvImportReconciliationReport = Field(
        default_factory=CsvImportReconciliationReport
    )
    ghostfolio_response: dict[str, Any] | None = None


class SyncStatusResponse(BaseModel):
    running: bool
    runs_total: int
    runs_failed: int
    last_trigger: str | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_error: str | None = None
    last_snapshot_path: str | None = None
    last_ignidash_payload_path: str | None = None


class TodayChecklistItem(BaseModel):
    id: str
    title: str
    status: Literal["complete", "incomplete", "attention"]
    detail: str
    action_hint: str | None = None


class TodayRecommendation(BaseModel):
    id: str
    title: str
    detail: str
    priority: Literal["high", "medium", "low"] = "medium"


class TopNextAction(BaseModel):
    recommendation_id: str | None = None
    title: str
    detail: str
    priority: Literal["high", "medium", "low"] = "medium"
    recommendation_type: Literal["plan_settings_update", "workflow_action", "general"] = "general"
    source: str = "manual"
    plan_id: str | None = None
    score_total: float | None = None
    score_rank: int | None = None
    score_reasons: list[str] = Field(default_factory=list)
    quality_summary: str | None = None
    quality_actionability: str | None = None
    quality_decision_grade: bool | None = None
    blocking_context: list[str] = Field(default_factory=list)
    action_hint: str | None = None


class TodayCommandCard(BaseModel):
    id: str
    title: str
    status: Literal["ready", "warning", "critical"] = "ready"
    detail: str
    metric_label: str | None = None
    metric_value: str | None = None
    action_label: str | None = None
    href: str | None = None


class TodayActivePlanSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime | None = None
    settings_completion_percent: float = 0.0
    decisions_count: int = 0
    artifacts_count: int = 0


class TodayDashboardResponse(BaseModel):
    generated_at: datetime
    currency: str
    state: str
    sync_status: SyncStatusResponse
    snapshot_as_of: datetime | None = None
    snapshot_age_minutes: int | None = None
    snapshot_points_30d: int = 0
    total_value_usd: float | None = None
    net_performance_usd: float | None = None
    net_performance_percent: float | None = None
    recent_change_usd: float | None = None
    recent_change_percent: float | None = None
    top_holding_symbol: str | None = None
    top_holding_percent: float | None = None
    concentration_risk: Literal["low", "medium", "high"] = "low"
    active_plan: TodayActivePlanSummary | None = None
    onboarding_completion_percent: float = 0.0
    onboarding_ready_for_daily_review: bool = False
    profile_readiness: ProfileReadinessSummary | None = None
    inbox_open_count: int = 0
    inbox_high_priority_count: int = 0
    net_worth_usd: float | None = None
    monthly_surplus_usd: float | None = None
    savings_rate_pct: float | None = None
    emergency_fund_months: float | None = None
    financial_health_status: Literal["healthy", "needs_attention", "critical", "insufficient_data"] | None = None
    context_state: Literal["ready", "warning", "critical"] = "warning"
    context_notes: list[str] = Field(default_factory=list)
    command_cards: list[TodayCommandCard] = Field(default_factory=list)
    top_next_actions: list[TopNextAction] = Field(default_factory=list)
    checklist: list[TodayChecklistItem] = Field(default_factory=list)
    recommendations: list[TodayRecommendation] = Field(default_factory=list)
    workflow_steps: list[str] = Field(default_factory=list)


class IncomeItem(BaseModel):
    id: str
    label: str
    monthly_amount_usd: float = Field(ge=0)
    source_type: str = "salary"
    is_pre_tax: bool = False
    annual_growth_rate: float | None = Field(default=None, ge=-1, le=1)
    start_date: datetime | None = None
    end_date: datetime | None = None


class ExpenseItem(BaseModel):
    id: str
    label: str
    monthly_amount_usd: float = Field(ge=0)
    category: str = "general"
    is_fixed: bool = True
    inflation_rate: float | None = Field(default=None, ge=-1, le=1)
    start_date: datetime | None = None
    end_date: datetime | None = None


class DebtItem(BaseModel):
    id: str
    label: str
    balance_usd: float = Field(ge=0)
    interest_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_payment_usd: float | None = Field(default=None, ge=0)
    payoff_strategy: Literal["minimum", "snowball", "avalanche", "custom"] = "minimum"
    custom_monthly_payment_usd: float | None = Field(default=None, ge=0)


class GoalItem(BaseModel):
    id: str
    label: str
    target_amount_usd: float = Field(ge=0)
    target_date: datetime | None = None
    priority: Literal["high", "medium", "low"] = "medium"
    notes: str = ""


class TaxProfile(BaseModel):
    filing_status: (
        Literal[
            "single",
            "married_filing_jointly",
            "married_filing_separately",
            "head_of_household",
        ]
        | None
    ) = None
    marginal_tax_rate: float | None = Field(default=None, ge=0, le=1)
    effective_tax_rate: float | None = Field(default=None, ge=0, le=1)
    state_tax_rate: float | None = Field(default=None, ge=0, le=1)
    state: str | None = None


class InvestmentPolicy(BaseModel):
    max_single_symbol_exposure_pct: float | None = Field(default=None, ge=0, le=100)
    max_sector_exposure_pct: float | None = Field(default=None, ge=0, le=100)
    minimum_research_confidence: Literal["low", "medium", "high"] | None = None
    minimum_cash_runway_months: float | None = Field(default=None, ge=0)
    max_asset_class_exposure_pct: dict[str, float] = Field(default_factory=dict)
    simplicity_preference: Literal["low", "medium", "high"] | None = None
    tax_sensitivity: Literal["low", "medium", "high"] | None = None
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] | None = None
    preferred_account_locations: dict[str, list[str]] = Field(default_factory=dict)
    restricted_symbols: list[str] = Field(default_factory=list)
    restricted_sectors: list[str] = Field(default_factory=list)


class ProfileFlags(BaseModel):
    no_debt: bool = False
    no_goals: bool = False


class PhysicalAssetItem(BaseModel):
    id: str
    label: str
    current_value_usd: float = Field(ge=0)
    asset_type: Literal["real_estate", "vehicle", "jewelry", "equipment", "collectible", "other"] = "other"
    annual_growth_rate: float | None = Field(default=None, ge=-1, le=1)
    purchase_date: datetime | None = None


class FinancialProfileRequest(BaseModel):
    income_items: list[IncomeItem] = Field(default_factory=list)
    expense_items: list[ExpenseItem] = Field(default_factory=list)
    debt_items: list[DebtItem] = Field(default_factory=list)
    goal_items: list[GoalItem] = Field(default_factory=list)
    physical_assets: list[PhysicalAssetItem] = Field(default_factory=list)
    tax_profile: TaxProfile = Field(default_factory=TaxProfile)
    investment_policy: InvestmentPolicy = Field(default_factory=InvestmentPolicy)
    flags: ProfileFlags = Field(default_factory=ProfileFlags)
    notes: str = ""


class FinancialProfileResponse(FinancialProfileRequest):
    schema_version: int = 1
    updated_at: datetime


class OnboardingStep(BaseModel):
    id: str
    title: str
    status: Literal["complete", "incomplete", "attention"]
    detail: str


class ProfileReadinessSection(BaseModel):
    key: str
    title: str
    status: Literal["complete", "incomplete", "attention"]
    detail: str
    required_for: list[str] = Field(default_factory=list)
    blocking_recommendations: bool = False


class ProfileReadinessSummary(BaseModel):
    completion_percent: float = 0.0
    status: Literal["ready", "attention", "incomplete"] = "incomplete"
    next_gap_key: str | None = None
    next_gap_title: str | None = None
    next_gap_detail: str | None = None
    blocking_recommendation_sources: list[str] = Field(default_factory=list)
    sections: list[ProfileReadinessSection] = Field(default_factory=list)


class OnboardingStatusResponse(BaseModel):
    completion_percent: float
    ready_for_daily_review: bool
    steps: list[OnboardingStep] = Field(default_factory=list)
    profile_readiness: ProfileReadinessSummary | None = None


RecommendationStatus = Literal["proposed", "applied", "rejected", "archived"]
RecommendationPriority = Literal["high", "medium", "low"]
RecommendationType = Literal["plan_settings_update", "workflow_action", "general"]


class RecommendationScore(BaseModel):
    impact: float = 0.0
    confidence: float = 0.0
    urgency: float = 0.0
    reversibility: float = 0.0
    total: float = 0.0
    rank: int | None = None
    model_version: str = "v1"
    reasons: list[str] = Field(default_factory=list)
    calibration: dict[str, Any] = Field(default_factory=dict)


class RecommendationItem(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    title: str
    detail: str
    priority: RecommendationPriority = "medium"
    status: RecommendationStatus = "proposed"
    recommendation_type: RecommendationType = "general"
    source: str = "manual"
    plan_id: str | None = None
    action_payload: dict[str, Any] = Field(default_factory=dict)
    score: RecommendationScore | None = None
    resolution_note: str = ""
    resolved_at: datetime | None = None


class RecommendationCreateRequest(BaseModel):
    title: str
    detail: str
    priority: RecommendationPriority = "medium"
    recommendation_type: RecommendationType = "general"
    source: str = "manual"
    plan_id: str | None = None
    action_payload: dict[str, Any] = Field(default_factory=dict)


class RecommendationUpdateRequest(BaseModel):
    title: str | None = None
    detail: str | None = None
    priority: RecommendationPriority | None = None
    recommendation_type: RecommendationType | None = None
    source: str | None = None
    plan_id: str | None = None
    action_payload: dict[str, Any] | None = None


class RecommendationApplyRequest(BaseModel):
    plan_id: str | None = None
    plan_settings_updates: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    decision_status: str = "accepted"
    create_decision_packet: bool = True
    capture_scenario_diff: bool = True
    decision_packet_research_symbols: list[str] = Field(default_factory=list)
    pin_research_bridge: bool = True
    research_bridge_symbols: list[str] = Field(default_factory=list)
    research_bridge_template_id: str | None = None
    research_bridge_assumption_set_id: str | None = None


class RecommendationPreviewRequest(BaseModel):
    plan_id: str | None = None
    plan_settings_updates: dict[str, Any] = Field(default_factory=dict)
    capture_scenario_diff: bool = True
    decision_status: str = "accepted"


class RecommendationRejectRequest(BaseModel):
    plan_id: str | None = None
    reason: str = ""
    capture_scenario_diff: bool = True
    create_decision_packet: bool = False
    decision_packet_research_symbols: list[str] = Field(default_factory=list)


class RecommendationOutcomeUpdateRequest(BaseModel):
    plan_id: str | None = None
    realized_delta_future_value_usd: float | None = None
    realized_delta_real_value_usd: float | None = None
    observed_at: datetime | None = None
    observation_window_days: int | None = Field(default=None, ge=0, le=3650)
    measurement_source: str = ""
    note: str = ""
    process_outcome: str = ""
    evidence_sufficiency: str = ""


class PortfolioRiskRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class PlanTrackingRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class CashLiquidityRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ProfileCompletenessRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class StaleAssumptionRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class WatchlistResearchRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    period: str = "6mo"
    interval: str = "1d"


class ResearchThesisExpirationRecommendationGenerateRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    stale_after_days: int = Field(default=30, ge=1, le=3650)


class RecommendationFactoryRunAllRequest(BaseModel):
    dry_run: bool = True
    plan_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class RecommendationFactoryResponse(BaseModel):
    generated_count: int = 0
    skipped_count: int = 0
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    created: list[RecommendationItem] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = True


class RecommendationFactoryRunAllResponse(BaseModel):
    generated_count: int = 0
    skipped_count: int = 0
    factory_count: int = 0
    factories: dict[str, RecommendationFactoryResponse] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = True


class RecommendationActionResponse(BaseModel):
    recommendation: RecommendationItem
    plan: PlanDetailResponse | None = None
    decision_packet_artifact: PlanArtifactSummary | None = None
    decision_closure_artifact: PlanArtifactSummary | None = None
    suggested_research_symbols: list[str] = Field(default_factory=list)
    research_bridge: dict[str, Any] = Field(default_factory=dict)
    decision_closure: dict[str, Any] = Field(default_factory=dict)
    message: str


class RecommendationPreviewResponse(BaseModel):
    recommendation: RecommendationItem
    preview: dict[str, Any] = Field(default_factory=dict)
    suggested_research_symbols: list[str] = Field(default_factory=list)
    message: str


class RecommendationClosureAnalyticsResponse(BaseModel):
    generated_at: datetime
    count: int = 0
    plan_id: str | None = None
    statuses: list[str] = Field(default_factory=list)
    include_pending_realized: bool = True
    summary: dict[str, Any] = Field(default_factory=dict)
    calibration_model_version: str = "calibration_v1"
    calibration_summary: dict[str, Any] = Field(default_factory=dict)
    calibration_by_type: list[dict[str, Any]] = Field(default_factory=list)
    calibration_by_source: list[dict[str, Any]] = Field(default_factory=list)
    calibration_windows: list[dict[str, Any]] = Field(default_factory=list)
    process_calibration_summary: dict[str, Any] = Field(default_factory=dict)
    process_calibration_by_outcome: list[dict[str, Any]] = Field(default_factory=list)
    process_calibration_by_evidence_sufficiency: list[dict[str, Any]] = Field(default_factory=list)
    by_status: list[dict[str, Any]] = Field(default_factory=list)
    by_type: list[dict[str, Any]] = Field(default_factory=list)
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)


class CopilotContextOptions(BaseModel):
    include_research: bool = False
    include_plan_projection: bool = False
    force_refresh: bool = False
    detail_level: Literal["light", "full"] = "light"
    research_symbols: list[str] = Field(default_factory=list)
    research_period: str = "6mo"
    research_interval: str = "1d"
    research_symbol_limit: int = Field(default=5, ge=0, le=20)
    summary_max_chars: int = Field(default=1800, ge=300, le=12000)


class CopilotContextScope(BaseModel):
    plan_id: str | None = None
    use_live_snapshot: bool = False
    include_research: bool = False
    include_plan_projection: bool = False
    detail_level: Literal["light", "full"] = "full"


class CopilotContextCacheLayer(BaseModel):
    hit: bool = False
    written: bool = False
    ttl_seconds: float | None = None


class CopilotContextCacheMetadata(BaseModel):
    enabled: bool = False
    read_enabled: bool | None = None
    write_enabled: bool | None = None
    force_refresh: bool = False
    bypass_reason: str | None = None
    research: CopilotContextCacheLayer = Field(default_factory=CopilotContextCacheLayer)
    baseline_projection: CopilotContextCacheLayer = Field(default_factory=CopilotContextCacheLayer)


class CopilotContextFreshness(BaseModel):
    generated_at: datetime | None = None
    snapshot_as_of: datetime | None = None
    snapshot_age_seconds: float | None = None
    snapshot_stale: bool | None = None
    snapshot_stale_threshold_seconds: float | None = None


class CopilotContextCoverage(BaseModel):
    score_pct: float = 0.0
    checks: dict[str, bool] = Field(default_factory=dict)
    missing_sections: list[str] = Field(default_factory=list)


class CopilotContextWarningQuality(BaseModel):
    count: int = 0
    has_warnings: bool = False


class CopilotContextSummaryQuality(BaseModel):
    max_chars: int = 0
    full_chars: int = 0
    actual_chars: int = 0
    truncated: bool = False


class CopilotContextQuality(BaseModel):
    freshness: CopilotContextFreshness = Field(default_factory=CopilotContextFreshness)
    coverage: CopilotContextCoverage = Field(default_factory=CopilotContextCoverage)
    warnings: CopilotContextWarningQuality = Field(default_factory=CopilotContextWarningQuality)
    summary: CopilotContextSummaryQuality = Field(default_factory=CopilotContextSummaryQuality)


class CopilotContextResponse(BaseModel):
    generated_at: datetime
    scope: CopilotContextScope = Field(default_factory=CopilotContextScope)
    cache: CopilotContextCacheMetadata = Field(default_factory=CopilotContextCacheMetadata)
    location_state: str = ""
    currency: str = "USD"
    warnings: list[str] = Field(default_factory=list)
    quality: CopilotContextQuality = Field(default_factory=CopilotContextQuality)
    planning_defaults: dict[str, Any] = Field(default_factory=dict)
    financial_picture: dict[str, Any] = Field(default_factory=dict)
    planning: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] = Field(default_factory=dict)
    decisions: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class CopilotContextCacheStoreStats(BaseModel):
    name: Literal["research", "baseline_projection"]
    max_entries: int
    entries: int
    lookup_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    write_count: int = 0
    eviction_count: int = 0
    expired_pruned: int
    hit_rate_pct: float = 0.0


class CopilotContextCacheStatusResponse(BaseModel):
    as_of: datetime
    enabled: bool
    stores: list[CopilotContextCacheStoreStats] = Field(default_factory=list)


class RuntimeTelemetryApiLatencyRoute(BaseModel):
    method: str
    path: str
    request_count: int = 0
    server_error_count: int = 0
    server_error_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    max_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    last_status_code: int | None = None
    last_requested_at: datetime | None = None


class RuntimeTelemetryApiLatencySummary(BaseModel):
    as_of: datetime
    request_count: int = 0
    server_error_count: int = 0
    server_error_rate_pct: float = 0.0
    window_sample_count: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    max_latency_ms: float = 0.0
    last_request_at: datetime | None = None
    routes: list[RuntimeTelemetryApiLatencyRoute] = Field(default_factory=list)


class RuntimeTelemetryContextFreshnessSummary(BaseModel):
    as_of: datetime | None = None
    last_context_generated_at: datetime | None = None
    snapshot_as_of: datetime | None = None
    snapshot_age_seconds: float | None = None
    snapshot_stale: bool | None = None
    snapshot_stale_threshold_seconds: float | None = None
    coverage_score_pct: float | None = None
    missing_sections: list[str] = Field(default_factory=list)
    warning_count: int = 0


class RuntimeTelemetryCacheStoreSummary(BaseModel):
    name: str
    max_entries: int
    entries: int
    utilization_pct: float = 0.0
    lookup_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    write_count: int = 0
    eviction_count: int = 0
    expired_pruned: int = 0
    hit_rate_pct: float = 0.0
    quality_status: Literal["healthy", "mixed", "cold", "warming"] = "warming"


class RuntimeTelemetryCacheQualitySummary(BaseModel):
    as_of: datetime
    enabled: bool = False
    total_lookup_count: int = 0
    total_hit_count: int = 0
    combined_hit_rate_pct: float = 0.0
    stores: list[RuntimeTelemetryCacheStoreSummary] = Field(default_factory=list)


class RuntimeTelemetryResponse(BaseModel):
    as_of: datetime
    api_latency: RuntimeTelemetryApiLatencySummary
    context_freshness: RuntimeTelemetryContextFreshnessSummary
    cache_quality: RuntimeTelemetryCacheQualitySummary


class CopilotChatRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    use_live_snapshot: bool = False
    plan_id: str | None = None
    context_options: CopilotContextOptions = Field(default_factory=CopilotContextOptions)


class CopilotToolTrace(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class CopilotChatResponse(BaseModel):
    conversation_id: str
    answer: str
    tool_calls: list[CopilotToolTrace] = Field(default_factory=list)
    model: str | None = None
    created_at: datetime


class CopilotConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str


class CopilotConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[dict[str, Any]] = Field(default_factory=list)


TimelineEventType = Literal[*TIMELINE_EVENT_TYPE_VALUES]
TimelineImpactType = Literal[*TIMELINE_IMPACT_TYPE_VALUES]
TimelineFrequency = Literal[*TIMELINE_FREQUENCY_VALUES]


class PlanTimelineEvent(BaseModel):
    id: str = ""
    date: date
    label: str
    event_type: TimelineEventType = "milestone"
    impact_type: TimelineImpactType | None = None
    amount_usd: float = 0.0
    recurring_frequency: TimelineFrequency = "one_time"
    end_date: date | None = None
    account_id: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _apply_default_impact_type(self) -> "PlanTimelineEvent":
        if self.impact_type is None:
            self.impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(self.event_type, "portfolio")
        return self


class PlanTimelineRetirement(BaseModel):
    target_retirement_age: int | None = Field(default=None, ge=18, le=100)
    withdrawal_strategy: str | None = None
    drawdown_order: str | None = None
    social_security_birth_year: int | None = Field(default=None, ge=1900, le=2500)
    social_security_claiming_age: int | None = Field(default=None, ge=62, le=70)
    social_security_life_expectancy_age: int | None = Field(default=None, ge=67, le=120)
    social_security_fra_monthly_benefit_usd: float | None = Field(default=None, ge=0)
    social_security_estimated_annual_earnings_usd: float | None = Field(default=None, ge=0)
    rmd_birth_year: int | None = Field(default=None, ge=1900, le=2500)
    rmd_start_age: int | None = Field(default=None, ge=72, le=120)


class PlanTimelineResponse(BaseModel):
    schema_version: int = 2
    events: list[PlanTimelineEvent] = Field(default_factory=list)
    retirement: PlanTimelineRetirement = Field(default_factory=PlanTimelineRetirement)


class PlanTimelineUpdateRequest(BaseModel):
    events: list[PlanTimelineEvent] = Field(default_factory=list)
    retirement: PlanTimelineRetirement = Field(default_factory=PlanTimelineRetirement)


class PlanContributionRulesResponse(BaseModel):
    schema_version: int = 2
    base_rule: dict[str, Any] = Field(default_factory=lambda: {"type": "save"})
    rules: list[dict[str, Any]] = Field(default_factory=list)
    profile_id: str | None = None
    employer_match_target_usd: float = Field(default=6000.0, ge=0)
    age: int = Field(default=35, ge=0, le=120)


class PlanContributionRulesUpdateRequest(BaseModel):
    base_rule: dict[str, Any] = Field(default_factory=lambda: {"type": "save"})
    rules: list[dict[str, Any]] = Field(default_factory=list)
    profile_id: str | None = None
    employer_match_target_usd: float = Field(default=6000.0, ge=0)
    age: int = Field(default=35, ge=0, le=120)


class PlanAssumptionSet(BaseModel):
    id: str
    name: str
    expected_return_baseline: float | None = Field(default=None, ge=-0.95, le=1)
    expected_return_optimistic: float | None = Field(default=None, ge=-0.95, le=1)
    expected_return_conservative: float | None = Field(default=None, ge=-0.95, le=1)
    inflation_rate: float | None = Field(default=None, ge=-1, le=1)
    marginal_tax_rate: float | None = Field(default=None, ge=0, le=1)
    state_tax_rate: float | None = Field(default=None, ge=0, le=1)
    simulation_mode: str | None = None
    simulation_monte_carlo_variant: str | None = None
    simulation_historical_start_year: int | None = Field(default=None, ge=1928, le=2024)
    simulation_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    roth_conversion_annual_amount_usd: float | None = Field(default=None, ge=0)
    roth_conversion_start_age: int | None = Field(default=None, ge=0, le=120)
    roth_conversion_end_age: int | None = Field(default=None, ge=0, le=120)


class PlanAssumptionSetsResponse(BaseModel):
    schema_version: int = 2
    active_assumption_set_id: str = "default"
    sets: list[PlanAssumptionSet] = Field(default_factory=list)


class PlanAssumptionSetsUpdateRequest(BaseModel):
    active_assumption_set_id: str | None = None
    sets: list[PlanAssumptionSet] = Field(default_factory=list)


class PlanScenarioBranchTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    branch_name: str = "What-If Branch"
    assumption_set_id: str | None = None
    compare_settings: dict[str, Any] = Field(default_factory=dict)
    branch_events: list[dict[str, Any]] = Field(default_factory=list)


class PlanScenarioBranchTemplatesResponse(BaseModel):
    schema_version: int = 2
    default_template_id: str | None = None
    templates: list[PlanScenarioBranchTemplate] = Field(default_factory=list)


class PlanScenarioBranchTemplatesUpdateRequest(BaseModel):
    default_template_id: str | None = None
    templates: list[PlanScenarioBranchTemplate] = Field(default_factory=list)


class PlanResearchBridgeRequest(BaseModel):
    branch_template_id: str | None = None
    template_name: str | None = None
    branch_name: str | None = None
    assumption_set_id: str | None = None
    symbols: list[str] = Field(default_factory=list)
    max_symbols: int = Field(default=5, ge=1, le=20)


class PlanResearchBridgePinnedItem(BaseModel):
    symbol: str
    data_source: str = "OPENBB"
    thesis: str = ""
    note: str = ""
    target_price_usd: float | None = None
    tags: list[str] = Field(default_factory=list)


class PlanResearchBridgeResponse(BaseModel):
    plan_id: str
    template_id: str
    template_name: str
    pinned_symbols: list[str] = Field(default_factory=list)
    pinned_items: list[PlanResearchBridgePinnedItem] = Field(default_factory=list)
    decision_summary: str = ""
    artifact_id: str | None = None
    artifact_title: str | None = None
    pinned_at: datetime | None = None
    branch_templates: PlanScenarioBranchTemplatesResponse


class PlanSummary(BaseModel):
    id: str
    title: str
    description: str = ""
    created_at: datetime
    updated_at: datetime
    is_active: bool = False


class PlanDecision(BaseModel):
    id: str
    created_at: datetime
    summary: str
    rationale: str = ""
    status: str = "proposed"


class PlanFiles(BaseModel):
    plan_markdown: str = ""
    plan_yaml: str = ""
    tasks_markdown: str = ""
    context_markdown: str = ""
    timeline_json: str = ""
    contribution_rules_json: str = ""
    assumption_sets_json: str = ""
    branch_templates_json: str = ""


# Internal shared plan-settings payload.
# Guardrail: keep inheritance depth to one internal base layer.
# Public inheritors: PlanSettings, PlanSettingsUpdateRequest.
class _PlanSettingsBase(BaseModel):
    annual_contribution_usd: float | None = None
    years: int | None = None
    hsa_extra_contribution_usd: float | None = None
    marginal_tax_rate: float | None = None
    state_tax_rate: float | None = None
    simulation_mode: str | None = None
    simulation_monte_carlo_variant: str | None = None
    simulation_historical_start_year: int | None = None
    simulation_seed: int | None = None
    household_mode: str | None = None
    household_partner_income_usd: float | None = None
    household_partner_income_growth_rate: float | None = None
    household_partner_retirement_age: int | None = None
    household_partner_social_security_annual_usd: float | None = None
    household_partner_social_security_claiming_age: int | None = None
    household_shared_goal_target_usd: float | None = None
    household_shared_goal_target_year: int | None = None
    roth_conversion_annual_amount_usd: float | None = None
    roth_conversion_start_age: int | None = None
    roth_conversion_end_age: int | None = None
    inflation_rate: float | None = None
    expected_return_baseline: float | None = None
    expected_return_optimistic: float | None = None
    expected_return_conservative: float | None = None
    filing_status: str | None = None
    withdrawal_strategy: str | None = None
    drawdown_order: str | None = None


class PlanSettings(_PlanSettingsBase):
    schema_version: int = 1
    updated_at: datetime | None = None


class PlanSettingsUpdateRequest(_PlanSettingsBase):
    pass


# Internal shared scenario-comparison request fields.
# Guardrail: keep inheritance depth to one internal base layer.
# Public inheritors: PlanScenarioDiffRequest, PlanWithdrawalStrategyCompareRequest,
# PlanScenarioBranchRequest.
class _PlanScenarioComparisonRequestBase(BaseModel):
    current_portfolio_value_usd: float | None = None
    assumption_set_id: str | None = None


class PlanScenarioDiffRequest(_PlanScenarioComparisonRequestBase):
    candidate_assumption_set_id: str | None = None
    compare_settings: PlanSettingsUpdateRequest = Field(default_factory=PlanSettingsUpdateRequest)


class ScenarioComparisonRow(BaseModel):
    label: Literal["baseline", "optimistic", "conservative", "hsa_delta"]
    base_future_value_usd: float
    candidate_future_value_usd: float
    delta_future_value_usd: float
    base_real_value_usd: float
    candidate_real_value_usd: float
    delta_real_value_usd: float


class PlanScenarioDiffResponse(BaseModel):
    plan_id: str
    current_portfolio_value_usd: float
    base_settings: PlanSettings
    candidate_settings: PlanSettings
    base_assumption_set: PlanAssumptionSet | None = None
    candidate_assumption_set: PlanAssumptionSet | None = None
    base_result: PlanningResponse
    candidate_result: PlanningResponse
    scenario_deltas: list[ScenarioComparisonRow] = Field(default_factory=list)
    monte_carlo_delta: dict[str, float | int | None] = Field(default_factory=dict)
    simulation_delta: dict[str, Any] = Field(default_factory=dict)


class PlanWithdrawalStrategyCompareRequest(_PlanScenarioComparisonRequestBase):
    strategies: list[str] = Field(default_factory=list)
    include_raw_results: bool = False


class PlanWithdrawalStrategyComparisonRow(BaseModel):
    strategy: str
    baseline_future_value_usd: float | None = None
    baseline_real_value_usd: float | None = None
    total_withdrawals_usd: float = 0.0
    total_taxes_usd: float = 0.0
    total_federal_taxes_usd: float = 0.0
    total_state_taxes_usd: float = 0.0
    total_irmaa_surcharges_usd: float = 0.0
    total_roth_conversions_usd: float = 0.0
    total_rmds_usd: float = 0.0
    terminal_age: int | None = None
    terminal_balance_usd: float | None = None
    monte_carlo_p10_future_value_usd: float = 0.0
    monte_carlo_p50_future_value_usd: float = 0.0
    monte_carlo_p90_future_value_usd: float = 0.0
    simulation_mode: str | None = None
    simulation_monte_carlo_variant: str | None = None
    average_effective_tax_rate: float | None = None
    engine: Literal["local", "ignidash"] = "local"
    engine_status: Literal["ok", "degraded"] = "ok"
    fallback_method: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PlanWithdrawalStrategyCompareResponse(BaseModel):
    plan_id: str
    current_portfolio_value_usd: float
    assumption_set: PlanAssumptionSet | None = None
    strategies: list[str] = Field(default_factory=list)
    comparisons: list[PlanWithdrawalStrategyComparisonRow] = Field(default_factory=list)
    best_strategy_by_metric: dict[str, str | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw_results: dict[str, Any] = Field(default_factory=dict)


class PlanScenarioBranchEvent(BaseModel):
    label: str
    event_type: TimelineEventType = "milestone"
    impact_type: TimelineImpactType | None = None
    amount_usd: float
    recurring_frequency: TimelineFrequency = "one_time"
    start_year_offset: int = Field(default=0, ge=0, le=80)
    duration_months: int | None = Field(default=None, ge=1, le=960)
    account_id: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _apply_default_impact_type(self) -> "PlanScenarioBranchEvent":
        if self.impact_type is None:
            self.impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(self.event_type, "portfolio")
        return self


class PlanScenarioBranchRequest(_PlanScenarioComparisonRequestBase):
    branch_name: str = "What-If Branch"
    branch_template_id: str | None = None
    compare_settings: PlanSettingsUpdateRequest = Field(default_factory=PlanSettingsUpdateRequest)
    branch_events: list[PlanScenarioBranchEvent] = Field(default_factory=list)


class PlanScenarioBranchResponse(BaseModel):
    plan_id: str
    branch_name: str
    branch_template_id: str | None = None
    branch_template_name: str | None = None
    current_portfolio_value_usd: float
    base_settings: PlanSettings
    branch_settings: PlanSettings
    assumption_set: PlanAssumptionSet | None = None
    branch_events: list[PlanTimelineEvent] = Field(default_factory=list)
    base_result: PlanningResponse
    branch_result: PlanningResponse
    scenario_deltas: list[ScenarioComparisonRow] = Field(default_factory=list)
    monte_carlo_delta: dict[str, float | int | None] = Field(default_factory=dict)
    simulation_delta: dict[str, Any] = Field(default_factory=dict)


class PlanArtifactSummary(BaseModel):
    id: str
    file_name: str
    title: str
    created_at: datetime


class PlanArtifactResponse(BaseModel):
    id: str
    file_name: str
    title: str
    created_at: datetime
    content: str
    thesis_review: dict[str, Any] = Field(default_factory=dict)
    thesis_revision_history: list[dict[str, Any]] = Field(default_factory=list)


class PlanRecommendationClosureSummaryRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    statuses: list[str] = Field(default_factory=lambda: ["applied", "rejected"])
    include_pending_realized: bool = True
    write_artifact: bool = True


class PlanRecommendationClosureSummaryResponse(BaseModel):
    plan_id: str
    analytics: RecommendationClosureAnalyticsResponse
    artifact: PlanArtifactSummary | None = None
    decision_summary: str = ""


class PlanDetailResponse(BaseModel):
    id: str
    title: str
    description: str = ""
    created_at: datetime
    updated_at: datetime
    is_active: bool = False
    schema_version: int = 1
    files: PlanFiles
    settings: PlanSettings
    decisions: list[PlanDecision] = Field(default_factory=list)
    artifacts: list[PlanArtifactSummary] = Field(default_factory=list)
    top_next_actions: list[TopNextAction] = Field(default_factory=list)


class PlanCreateRequest(BaseModel):
    title: str
    description: str = ""


class PlanUpdateRequest(BaseModel):
    plan_markdown: str | None = None
    tasks_markdown: str | None = None


class PlanDecisionCreateRequest(BaseModel):
    summary: str
    rationale: str = ""
    status: str = "proposed"


class WorkflowTemplateResponse(BaseModel):
    id: str
    title: str
    description: str
    default_params: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    workflow_id: str
    plan_id: str | None = None
    use_live_snapshot: bool = False
    save_to_plan: bool = True
    create_recommendations: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    generated_at: datetime
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    report_markdown: str
    artifact: PlanArtifactSummary | None = None
    recommendations: list[RecommendationItem] = Field(default_factory=list)


class PortfolioReviewPacketRequest(BaseModel):
    period_days: int = Field(default=90, ge=7, le=3650)
    plan_id: str | None = None
    title: str | None = None
    include_snapshot_history_limit: int = Field(default=365, ge=1, le=3650)
    include_transactions_limit: int = Field(default=1000, ge=1, le=10000)
    include_recommendations_limit: int = Field(default=1000, ge=1, le=10000)
    include_archived_recommendations: bool = False
    save_to_plan_artifacts: bool = True


class PortfolioReviewPacketSummary(BaseModel):
    packet_id: str
    title: str
    generated_at: datetime
    period_start: date
    period_end: date
    holdings_as_of: datetime | None = None
    total_portfolio_value_usd: float = 0.0
    risk_status: Literal["ok", "warning", "critical"] = "ok"
    risk_breach_count: int = 0
    risk_watch_count: int = 0
    recommendations_open: int = 0
    recommendations_total: int = 0
    storage: dict[str, str] = Field(default_factory=dict)


class PortfolioReviewPacketResponse(BaseModel):
    summary: PortfolioReviewPacketSummary
    packet: dict[str, Any] = Field(default_factory=dict)
    markdown: str = ""
    plan_artifact: PlanArtifactSummary | None = None


class PortfolioReviewPacketListResponse(BaseModel):
    items: list[PortfolioReviewPacketSummary] = Field(default_factory=list)


class SimulateTradeRequest(BaseModel):
    symbol: str
    action: Literal["buy", "sell"]
    amount_usd: float = Field(gt=0)
    name: str | None = None


class SimulatedHolding(BaseModel):
    symbol: str
    name: str
    current_value_usd: float
    new_value_usd: float
    current_allocation_pct: float
    new_allocation_pct: float
    allocation_change_pct: float


class SimulateTradeResponse(BaseModel):
    symbol: str
    action: Literal["buy", "sell"]
    amount_usd: float
    name: str

    current_total_value_usd: float
    new_total_value_usd: float

    current_top_holding_symbol: str | None = None
    current_top_holding_pct: float = 0.0
    new_top_holding_symbol: str | None = None
    new_top_holding_pct: float = 0.0

    current_concentration_risk: Literal["low", "medium", "high"]
    new_concentration_risk: Literal["low", "medium", "high"]
    concentration_change: Literal["improved", "unchanged", "worsened"]

    current_holdings_count: int
    new_holdings_count: int

    top_holdings: list[SimulatedHolding]
    highlights: list[str]


class GoalProgressItem(BaseModel):
    goal_id: str
    label: str
    target_amount_usd: float
    target_date: datetime | None = None
    priority: Literal["high", "medium", "low"] = "medium"

    current_savings_usd: float
    progress_pct: float
    remaining_usd: float

    monthly_savings_available_usd: float
    months_to_target: float | None = None
    estimated_completion_date: datetime | None = None
    required_monthly_usd: float | None = None

    status: Literal["on_track", "ahead", "behind", "achieved", "no_deadline"]
    status_detail: str


class GoalProgressResponse(BaseModel):
    generated_at: datetime
    monthly_surplus_usd: float
    goal_count: int
    goals: list[GoalProgressItem]
    summary: str


class AffordabilityRequest(BaseModel):
    description: str = ""
    monthly_amount_usd: float | None = Field(default=None, ge=0)
    purchase_price_usd: float | None = Field(default=None, ge=0)
    loan_rate_pct: float | None = Field(default=None, ge=0, le=100)
    loan_term_years: int | None = Field(default=None, ge=1, le=50)
    down_payment_pct: float | None = Field(default=None, ge=0, le=100)


class AffordabilityResponse(BaseModel):
    description: str
    assessment: Literal["affordable", "stretch", "not_affordable", "insufficient_data"]
    assessment_detail: str

    # Proposed expense
    proposed_monthly_usd: float
    is_loan_estimate: bool

    # Loan estimate details (only if purchase_price provided)
    loan_principal_usd: float | None = None
    down_payment_usd: float | None = None
    estimated_monthly_payment_usd: float | None = None
    loan_rate_pct: float | None = None
    loan_term_years: int | None = None

    # Current state
    current_monthly_surplus_usd: float
    current_savings_rate_pct: float
    current_dti_pct: float

    # After expense
    new_monthly_surplus_usd: float
    new_savings_rate_pct: float
    new_dti_pct: float

    # Impact
    surplus_change_usd: float
    savings_rate_change_pct: float
    dti_change_pct: float

    # Plan impact (if plan data available)
    current_annual_savings_usd: float
    new_annual_savings_usd: float
    annual_savings_reduction_usd: float
    plan_impact_detail: str | None = None

    highlights: list[str]


class FinancialHealthResponse(BaseModel):
    generated_at: datetime

    # Net worth
    portfolio_value_usd: float
    physical_assets_value_usd: float
    total_assets_usd: float
    total_debt_usd: float
    net_worth_usd: float

    # Cash flow
    gross_monthly_income_usd: float
    total_monthly_expenses_usd: float
    total_monthly_debt_payments_usd: float
    monthly_surplus_usd: float

    # Ratios
    savings_rate_pct: float
    debt_to_income_ratio_pct: float
    emergency_fund_months: float

    # Assessment
    status: Literal["healthy", "needs_attention", "critical", "insufficient_data"]
    status_detail: str
    highlights: list[str]

    # Breakdown context
    income_item_count: int
    expense_item_count: int
    debt_item_count: int
    goal_item_count: int
    physical_asset_item_count: int


class PlanTrackingResponse(BaseModel):
    plan_id: str
    plan_title: str
    status: Literal["on_track", "ahead", "behind", "insufficient_data"]
    status_detail: str
    tracking_window_days: int
    window_start: datetime
    window_end: datetime

    starting_value_usd: float
    current_value_usd: float
    projected_value_usd: float
    value_drift_usd: float
    value_drift_pct: float

    actual_annualized_return_pct: float
    expected_annualized_return_pct: float
    return_drift_pct: float
    actual_return_method: Literal["modified_dietz", "snapshot_delta"]
    expected_return_method: Literal["plan_setting", "asset_mix_inferred", "planner_default"]

    actual_contributions_usd: float
    expected_contributions_usd: float
    contribution_pace_pct: float

    market_growth_usd: float
    snapshot_count: int


class DurableStorageStatusResponse(BaseModel):
    strategy: str
    data_root: str
    storage_dir: str
    database_path: str
    database_exists: bool
    document_count: int
    latest_migration_id: str | None = None
    latest_migration_at: datetime | None = None
    latest_source_checksum: str | None = None
    latest_database_checksum: str | None = None
    latest_rollback_check_passed: bool | None = None


class DurableStorageMigrationRequest(BaseModel):
    run_rollback_check: bool = True


class DurableStorageMigrationResponse(BaseModel):
    migration_id: str
    strategy: str
    created_at: datetime
    data_root: str
    storage_dir: str
    database_path: str
    backup_dir: str
    previous_database_backup_path: str | None = None
    documents_migrated: int
    total_bytes: int
    source_checksum: str
    database_checksum: str
    rollback_check_performed: bool
    rollback_check_passed: bool
    report_path: str


class DurableStorageRollbackRequest(BaseModel):
    migration_id: str | None = None


class DurableStorageRollbackResponse(BaseModel):
    migration_id: str
    restored_at: datetime
    backup_dir: str
    files_restored: int
    bytes_restored: int
    database_restored: bool
    database_removed: bool


class BackupSummary(BaseModel):
    backup_id: str
    archive_path: str
    size_bytes: int
    created_at: datetime


class BackupListResponse(BaseModel):
    strategy: str
    data_root: str
    backup_dir: str
    backups: list[BackupSummary] = Field(default_factory=list)


class BackupCreateRequest(BaseModel):
    reason: str | None = None


class BackupCreateResponse(BaseModel):
    backup_id: str
    strategy: str
    archive_path: str
    created_at: datetime
    files_backed_up: int
    total_bytes: int
    archive_size_bytes: int
    aggregate_checksum: str
    reason: str | None = None


class BackupRestoreRequest(BaseModel):
    backup_id: str
    create_pre_restore_backup: bool = True


class BackupRestoreResponse(BaseModel):
    backup_id: str
    strategy: str
    restored_at: datetime
    archive_path: str
    files_restored: int
    bytes_restored: int
    pre_restore_backup_id: str | None = None


class StorageProtectionPolicyResponse(BaseModel):
    schema_version: int
    protection_level: Literal["standard", "hardened"]
    auto_apply_on_startup: bool
    include_backups: bool
    updated_at: datetime
    last_applied_at: datetime | None = None


class StorageProtectionTargetStatus(BaseModel):
    path: str
    exists: bool
    files_scanned: int = 0
    directories_scanned: int = 0
    non_compliant_files: int = 0
    non_compliant_directories: int = 0
    sample_non_compliant_paths: list[str] = Field(default_factory=list)
    compliant: bool | None = None


class StorageProtectionStatusResponse(BaseModel):
    supported: bool
    strategy: str
    policy: StorageProtectionPolicyResponse
    targets: list[StorageProtectionTargetStatus] = Field(default_factory=list)
    total_non_compliant_files: int = 0
    total_non_compliant_directories: int = 0


class StorageProtectionPolicyUpdateRequest(BaseModel):
    protection_level: Literal["standard", "hardened"] | None = None
    auto_apply_on_startup: bool | None = None
    include_backups: bool | None = None


class StorageProtectionApplyRequest(BaseModel):
    protection_level: Literal["standard", "hardened"] | None = None
    include_backups: bool | None = None


class StorageProtectionApplyResponse(BaseModel):
    applied_at: datetime
    supported: bool
    protection_level: Literal["standard", "hardened"]
    include_backups: bool
    files_scanned: int
    directories_scanned: int
    files_updated: int
    directories_updated: int
    non_compliant_files_after: int
    non_compliant_directories_after: int
    warnings: list[str] = Field(default_factory=list)


class GitPolicyResponse(BaseModel):
    enabled: bool
    workspace_dir: str
    autogit_enabled: bool
    auto_push_enabled: bool
    auto_checkpoint_idle_seconds: int
    remote_name: str
    include_plans: bool
    include_recommendations: bool
    include_review_packets: bool
    include_snapshot_checkpoints: bool
    include_financial_profile: bool
    updated_at: datetime | None = None


class GitPolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    workspace_dir: str | None = None
    autogit_enabled: bool | None = None
    auto_push_enabled: bool | None = None
    auto_checkpoint_idle_seconds: int | None = None
    remote_name: str | None = None
    include_plans: bool | None = None
    include_recommendations: bool | None = None
    include_review_packets: bool | None = None
    include_snapshot_checkpoints: bool | None = None
    include_financial_profile: bool | None = None


class GitChangedFile(BaseModel):
    path: str
    status: str


class GitCommitSummary(BaseModel):
    hash: str
    short_hash: str
    date: datetime
    message: str


class GitRemoteStatusResponse(BaseModel):
    has_remote: bool
    name: str | None = None
    url: str | None = None
    ahead: int = 0
    behind: int = 0


class GitStatusResponse(BaseModel):
    status: str
    message: str
    workspace_dir: str
    branch: str | None = None
    dirty: bool = False
    changed_files: list[GitChangedFile] = Field(default_factory=list)
    last_commit: GitCommitSummary | None = None
    has_remote: bool = False
    remote: GitRemoteStatusResponse | None = None


class GitInitResponse(BaseModel):
    status: str
    message: str
    workspace_dir: str


class GitHistoryResponse(BaseModel):
    commits: list[GitCommitSummary] = Field(default_factory=list)


class GitDiffResponse(BaseModel):
    status: str
    message: str
    workspace_dir: str
    ref: str | None = None
    path: str | None = None
    diff: str
    truncated: bool = False


class GitRestorePreviewFile(BaseModel):
    path: str
    status: str
    historical_excerpt: str | None = None
    current_excerpt: str | None = None
    diff: str
    truncated: bool = False


class GitRestorePreviewResponse(BaseModel):
    status: str
    message: str
    workspace_dir: str
    ref: str
    path: str | None = None
    preview_token: str | None = None
    preview_expires_at: datetime | None = None
    read_only: bool = True
    files: list[GitRestorePreviewFile] = Field(default_factory=list)
    total_files: int = 0
    warnings: list[str] = Field(default_factory=list)


class GitAutoGitPendingEvent(BaseModel):
    event_type: str
    event_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    due_at: datetime


class GitAutoGitLastResult(BaseModel):
    status: str
    message: str
    event_type: str
    event_count: int
    ran_at: datetime
    commit: GitCommitSummary | None = None


class GitAutoGitStateResponse(BaseModel):
    enabled: bool
    autogit_enabled: bool
    auto_checkpoint_idle_seconds: int
    pending_event: GitAutoGitPendingEvent | None = None
    last_result: GitAutoGitLastResult | None = None
    status: str = "idle"


class GitRemoteConnectRequest(BaseModel):
    remote_url: str
    remote_name: str = "origin"


class GitRemoteOperationRequest(BaseModel):
    remote_name: str = "origin"


class GitRemoteOperationResponse(BaseModel):
    status: str
    message: str
    workspace_dir: str
    branch: str | None = None
    remote_name: str
    remote: GitRemoteStatusResponse | None = None


class GitCheckpointRequest(BaseModel):
    message: str | None = None
    event_type: str = "manual_checkpoint"


class GitCheckpointResponse(BaseModel):
    status: str
    message: str
    workspace_dir: str
    files_written: int
    files_removed: int
    sections: dict[str, int] = Field(default_factory=dict)
    commit: GitCommitSummary | None = None


class GitRestoreApplyRequest(BaseModel):
    ref: str
    paths: list[str] = Field(min_length=1, max_length=50)
    confirmation: str
    preview_token: str | None = None
    rationale: str | None = None
    create_checkpoint_before_apply: bool = True
    create_checkpoint_after_apply: bool = True


class GitRestoreApplyFileResult(BaseModel):
    path: str
    status: str
    artifact_type: str
    artifact_id: str
    action: str


class GitRestoreApplyResponse(BaseModel):
    status: str
    message: str
    ref: str
    applied_files: int
    files: list[GitRestoreApplyFileResult] = Field(default_factory=list)
    before_checkpoint: GitCheckpointResponse | None = None
    after_checkpoint: GitCheckpointResponse | None = None
    warnings: list[str] = Field(default_factory=list)


class GitActivityEvent(BaseModel):
    id: str
    created_at: datetime
    event_type: str
    title: str
    message: str = ""
    status: str = "ok"
    ref: str | None = None
    paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitActivitySummary(BaseModel):
    total_matched: int = 0
    event_type_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)


class GitActivityResponse(BaseModel):
    events: list[GitActivityEvent] = Field(default_factory=list)
    summary: GitActivitySummary = Field(default_factory=GitActivitySummary)


class GitActivityCleanupRequest(BaseModel):
    dry_run: bool = True
    max_events: int | None = Field(default=None, ge=0, le=100_000)
    max_age_days: int | None = Field(default=None, ge=0, le=3650)
    include_protected: bool = False
    export_confirmed: bool = False


class GitActivityCleanupResponse(BaseModel):
    dry_run: bool
    message: str
    total_events: int
    events_removed: int
    events_retained: int
    protected_events_skipped: int
    max_events: int | None = None
    max_age_days: int | None = None
    include_protected: bool = False
    removable_event_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
