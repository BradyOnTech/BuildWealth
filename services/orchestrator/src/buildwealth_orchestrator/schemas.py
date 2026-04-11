from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Holding(BaseModel):
    symbol: str
    name: str
    data_source: str | None = None
    asset_type: str | None = None
    asset_class: str | None = None
    sector: str | None = None
    region: str | None = None
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


class PortfolioBenchmarkResponse(BaseModel):
    request_id: str
    contract_version: int
    engine: str
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    benchmark_symbols: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    summary: PortfolioBenchmarkSummary
    series: list[PortfolioBenchmarkSeriesPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None


class ScenarioRequest(BaseModel):
    current_portfolio_value_usd: float | None = None
    annual_contribution_usd: float | None = None
    years: int | None = None
    hsa_extra_contribution_usd: float | None = None


class ScenarioResult(BaseModel):
    label: Literal["baseline", "optimistic", "conservative", "hsa_delta"]
    future_value_usd: float
    real_value_usd: float
    assumptions: dict[str, float | int]


class PlanningResponse(BaseModel):
    scenarios: list[ScenarioResult]
    monte_carlo: dict[str, Any]
    engine: Literal["local", "ignidash"] = "local"
    engine_status: Literal["ok", "degraded"] = "ok"
    fallback_method: str | None = None
    warnings: list[str] = Field(default_factory=list)


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


class CsvImportRequest(BaseModel):
    path: str
    dry_run: bool = True
    delimiter: str = ","
    default_data_source: str | None = None
    default_currency: str | None = None
    archive_after_success: bool = False


class CsvImportResponse(BaseModel):
    file_path: str
    dry_run: bool
    parsed_rows: int
    valid_activities: int
    imported_activities: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
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
    top_holding_symbol: str | None = None
    top_holding_percent: float | None = None
    concentration_risk: Literal["low", "medium", "high"] = "low"
    active_plan: TodayActivePlanSummary | None = None
    onboarding_completion_percent: float = 0.0
    onboarding_ready_for_daily_review: bool = False
    inbox_open_count: int = 0
    inbox_high_priority_count: int = 0
    net_worth_usd: float | None = None
    monthly_surplus_usd: float | None = None
    savings_rate_pct: float | None = None
    financial_health_status: Literal["healthy", "needs_attention", "critical", "insufficient_data"] | None = None
    context_state: Literal["ready", "warning", "critical"] = "warning"
    context_notes: list[str] = Field(default_factory=list)
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
    state: str | None = None


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


class OnboardingStatusResponse(BaseModel):
    completion_percent: float
    ready_for_daily_review: bool
    steps: list[OnboardingStep] = Field(default_factory=list)


RecommendationStatus = Literal["proposed", "applied", "rejected", "archived"]
RecommendationPriority = Literal["high", "medium", "low"]
RecommendationType = Literal["plan_settings_update", "workflow_action", "general"]


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


class RecommendationRejectRequest(BaseModel):
    reason: str = ""


class RecommendationActionResponse(BaseModel):
    recommendation: RecommendationItem
    plan: PlanDetailResponse | None = None
    message: str


class CopilotChatRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    use_live_snapshot: bool = False
    plan_id: str | None = None


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


class PlanSettings(BaseModel):
    schema_version: int = 1
    annual_contribution_usd: float | None = None
    years: int | None = None
    hsa_extra_contribution_usd: float | None = None
    marginal_tax_rate: float | None = None
    expected_return_baseline: float | None = None
    expected_return_optimistic: float | None = None
    expected_return_conservative: float | None = None
    filing_status: str | None = None
    withdrawal_strategy: str | None = None
    updated_at: datetime | None = None


class PlanSettingsUpdateRequest(BaseModel):
    annual_contribution_usd: float | None = None
    years: int | None = None
    hsa_extra_contribution_usd: float | None = None
    marginal_tax_rate: float | None = None
    expected_return_baseline: float | None = None
    expected_return_optimistic: float | None = None
    expected_return_conservative: float | None = None
    filing_status: str | None = None
    withdrawal_strategy: str | None = None


class PlanScenarioDiffRequest(BaseModel):
    current_portfolio_value_usd: float | None = None
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
    base_result: PlanningResponse
    candidate_result: PlanningResponse
    scenario_deltas: list[ScenarioComparisonRow] = Field(default_factory=list)
    monte_carlo_delta: dict[str, float | int | None] = Field(default_factory=dict)


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
