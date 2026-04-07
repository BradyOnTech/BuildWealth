from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Holding(BaseModel):
    symbol: str
    name: str
    data_source: str | None = None
    asset_class: str | None = None
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
    holdings: list[Holding] = Field(default_factory=list)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


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


class ChatRequest(BaseModel):
    question: str
    refresh_snapshot: bool = True


class ChatResponse(BaseModel):
    answer: str
    route: str
    data: dict[str, Any] = Field(default_factory=dict)


class OptionsChainRequest(BaseModel):
    symbol: str


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


class PlanDetailResponse(BaseModel):
    id: str
    title: str
    description: str = ""
    created_at: datetime
    updated_at: datetime
    is_active: bool = False
    files: PlanFiles
    decisions: list[PlanDecision] = Field(default_factory=list)


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
