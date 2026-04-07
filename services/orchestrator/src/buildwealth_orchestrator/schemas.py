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
