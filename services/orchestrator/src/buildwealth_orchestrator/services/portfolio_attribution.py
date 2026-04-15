from __future__ import annotations

# Adapted from Ghostfolio (MIT):
# apps/api/src/app/portfolio/calculator/roai/portfolio-calculator.ts
# apps/api/src/app/portfolio/portfolio.service.ts

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from buildwealth_orchestrator.schemas import (
    PortfolioAttributionPosition,
    PortfolioAttributionResponse,
    PortfolioAttributionSummary,
)
from buildwealth_orchestrator.services.engine_adapter import (
    SidecarAdapter,
    SidecarAdapterError,
)
from buildwealth_orchestrator.services.engine_policy import (
    FALLBACK_METHOD_SIDECAR_DISABLED,
    resolve_engine_call_disposition,
    sidecar_unavailable_warning,
)
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


EPSILON = 1e-9
GHOSTFOLIO_ATTRIBUTION_CONTRACT_VERSION = 1


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class GhostfolioAttributionPositionV1(BaseModel):
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
    allocation_pct: float = 0.0

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        symbol = str(value or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return symbol


class GhostfolioAttributionRequestV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    portfolio_base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: datetime | None = None
    top_n: int = Field(default=5, ge=1, le=50)
    portfolio_total_return_base: float = 0.0
    portfolio_total_value_base: float = 0.0
    positions: list[GhostfolioAttributionPositionV1] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("top_n")
    @classmethod
    def _validate_top_n(cls, value: int) -> int:
        return max(1, min(int(value), 50))


class GhostfolioAttributionPositionResultV1(BaseModel):
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


class GhostfolioAttributionSummaryV1(BaseModel):
    portfolio_total_return_base: float
    portfolio_total_value_base: float
    accounted_return_base: float
    residual_return_base: float
    contributors_count: int
    detractors_count: int


class GhostfolioAttributionResponseV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    engine: Literal["ghostfolio"] = "ghostfolio"
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    summary: GhostfolioAttributionSummaryV1
    contributors: list[GhostfolioAttributionPositionResultV1] = Field(default_factory=list)
    detractors: list[GhostfolioAttributionPositionResultV1] = Field(default_factory=list)
    positions: list[GhostfolioAttributionPositionResultV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None


class GhostfolioAttributionService:
    def __init__(
        self,
        *,
        portfolio_store: PortfolioStore,
        sidecar_adapter: SidecarAdapter | None,
        sidecar_enabled: bool,
        sidecar_path: str,
        base_currency: str = "USD",
    ) -> None:
        self.portfolio_store = portfolio_store
        self.sidecar_adapter = sidecar_adapter
        self.sidecar_enabled = sidecar_enabled
        self.sidecar_path = sidecar_path
        self.base_currency = str(base_currency or "USD").upper()

    async def analyze(
        self,
        *,
        top_n: int,
        sidecar_guard_reason: str | None = None,
    ) -> PortfolioAttributionResponse:
        request_payload = self._build_request_payload(top_n=top_n)

        disposition = resolve_engine_call_disposition(
            engine_label="Ghostfolio attribution",
            sidecar_enabled=self.sidecar_enabled,
            sidecar_adapter=self.sidecar_adapter,
            sidecar_guard_reason=sidecar_guard_reason,
            disabled_behavior="degraded_fallback",
        )

        if not disposition.use_sidecar:
            fallback = self._compute_local_fallback(
                request_payload,
                fallback_method=disposition.fallback_method or FALLBACK_METHOD_SIDECAR_DISABLED,
                warning=disposition.warning or "Ghostfolio attribution sidecar disabled; using local fallback",
            )
            return self._to_api_response(request_payload, fallback)

        if self.sidecar_adapter is not None:
            try:
                contract_response = await self.sidecar_adapter.post_json(
                    path=self.sidecar_path,
                    request_payload=request_payload.model_dump(mode="json"),
                    request_model=GhostfolioAttributionRequestV1,
                    response_model=GhostfolioAttributionResponseV1,
                )
                return self._to_api_response(request_payload, contract_response)
            except SidecarAdapterError as exc:
                fallback = self._compute_local_fallback(
                    request_payload,
                    fallback_method="local_attribution_fallback",
                    warning=sidecar_unavailable_warning(
                        engine_label="Ghostfolio attribution",
                        error=exc,
                    ),
                )
                return self._to_api_response(request_payload, fallback)

        fallback = self._compute_local_fallback(
            request_payload,
            fallback_method=FALLBACK_METHOD_SIDECAR_DISABLED,
            warning="Ghostfolio attribution sidecar adapter unavailable; using local fallback",
        )
        return self._to_api_response(request_payload, fallback)

    def _build_request_payload(self, *, top_n: int) -> GhostfolioAttributionRequestV1:
        holdings_payload = self.portfolio_store.get_holdings()
        holdings = holdings_payload.get("holdings") if isinstance(holdings_payload.get("holdings"), dict) else {}
        performance = (
            holdings_payload.get("performance")
            if isinstance(holdings_payload.get("performance"), dict)
            else {}
        )
        total_portfolio_value = _safe_float(
            holdings_payload.get("total_portfolio_value"),
            _safe_float(holdings_payload.get("total_value"), 0.0),
        )
        total_portfolio_return = _safe_float(performance.get("total_return_usd"), 0.0)

        rows: list[GhostfolioAttributionPositionV1] = []
        for key in sorted(holdings.keys()):
            holding = holdings.get(key)
            if not isinstance(holding, dict):
                continue

            symbol = _normalize_text(holding.get("symbol") or key)
            if not symbol:
                continue

            current_value = _safe_float(holding.get("current_value"), 0.0)
            cost_basis = _safe_float(holding.get("cost_basis"), 0.0)
            realized_gains = _safe_float(holding.get("realized_gains"), 0.0)
            income_return = _safe_float(holding.get("dividends_received"), 0.0)
            unrealized_gains = current_value - cost_basis
            price_return = realized_gains + unrealized_gains
            total_return = price_return + income_return
            total_return_pct = (total_return / cost_basis * 100.0) if cost_basis > EPSILON else None
            allocation_pct = (
                (current_value / total_portfolio_value) * 100.0
                if total_portfolio_value > EPSILON
                else 0.0
            )

            rows.append(
                GhostfolioAttributionPositionV1(
                    symbol=symbol.upper(),
                    name=_normalize_text(holding.get("name")),
                    account_id=_normalize_text(holding.get("account")),
                    asset_class=_normalize_text(holding.get("asset_class")),
                    current_value_base=round(current_value, 2),
                    cost_basis_base=round(cost_basis, 2),
                    price_return_base=round(price_return, 2),
                    income_return_base=round(income_return, 2),
                    total_return_base=round(total_return, 2),
                    total_return_pct=round(total_return_pct, 4) if total_return_pct is not None else None,
                    allocation_pct=round(allocation_pct, 4),
                )
            )

        as_of = _parse_datetime(
            performance.get("as_of")
            or holdings_payload.get("prices_updated_at")
            or holdings_payload.get("updated_at")
        )

        return GhostfolioAttributionRequestV1(
            request_id=uuid4().hex,
            portfolio_base_currency=str(
                holdings_payload.get("base_currency")
                or self.base_currency
            ).upper(),
            as_of=as_of,
            top_n=top_n,
            portfolio_total_return_base=round(total_portfolio_return, 2),
            portfolio_total_value_base=round(total_portfolio_value, 2),
            positions=rows,
            metadata={"source": "portfolio_store.holdings"},
        )

    def _compute_local_fallback(
        self,
        request_payload: GhostfolioAttributionRequestV1,
        *,
        fallback_method: str,
        warning: str,
    ) -> GhostfolioAttributionResponseV1:
        denominator = request_payload.portfolio_total_return_base
        if abs(denominator) <= EPSILON:
            denominator = sum(position.total_return_base for position in request_payload.positions)

        rows: list[GhostfolioAttributionPositionResultV1] = []
        for position in request_payload.positions:
            contribution_pct = (
                (position.total_return_base / denominator) * 100.0
                if abs(denominator) > EPSILON
                else 0.0
            )
            rows.append(
                GhostfolioAttributionPositionResultV1(
                    symbol=position.symbol,
                    name=position.name,
                    account_id=position.account_id,
                    asset_class=position.asset_class,
                    current_value_base=round(position.current_value_base, 2),
                    cost_basis_base=round(position.cost_basis_base, 2),
                    price_return_base=round(position.price_return_base, 2),
                    income_return_base=round(position.income_return_base, 2),
                    total_return_base=round(position.total_return_base, 2),
                    total_return_pct=position.total_return_pct,
                    contribution_pct=round(contribution_pct, 4),
                    allocation_pct=round(position.allocation_pct, 4),
                )
            )

        sorted_rows = sorted(rows, key=lambda item: item.total_return_base, reverse=True)
        contributors = [row for row in sorted_rows if row.total_return_base > 0][: request_payload.top_n]
        detractors = sorted(
            [row for row in sorted_rows if row.total_return_base < 0],
            key=lambda item: item.total_return_base,
        )[: request_payload.top_n]

        accounted_return = round(sum(row.total_return_base for row in rows), 2)
        residual_return = round(request_payload.portfolio_total_return_base - accounted_return, 2)
        warnings = [warning]
        if abs(residual_return) > 0.01:
            warnings.append(
                "Attribution has residual return not represented by open holdings (likely closed positions or cash flows)."
            )

        return GhostfolioAttributionResponseV1(
            request_id=request_payload.request_id,
            engine_status="degraded",
            fallback_method=fallback_method,
            summary=GhostfolioAttributionSummaryV1(
                portfolio_total_return_base=round(request_payload.portfolio_total_return_base, 2),
                portfolio_total_value_base=round(request_payload.portfolio_total_value_base, 2),
                accounted_return_base=accounted_return,
                residual_return_base=residual_return,
                contributors_count=len([row for row in rows if row.total_return_base > 0]),
                detractors_count=len([row for row in rows if row.total_return_base < 0]),
            ),
            contributors=contributors,
            detractors=detractors,
            positions=sorted_rows,
            warnings=warnings,
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _to_api_response(
        request_payload: GhostfolioAttributionRequestV1,
        contract_response: GhostfolioAttributionResponseV1,
    ) -> PortfolioAttributionResponse:
        return PortfolioAttributionResponse(
            request_id=contract_response.request_id,
            contract_version=contract_response.contract_version,
            engine=contract_response.engine,
            engine_status=contract_response.engine_status,
            fallback_method=contract_response.fallback_method,
            as_of=request_payload.as_of,
            top_n=request_payload.top_n,
            summary=PortfolioAttributionSummary(
                portfolio_total_return_base=contract_response.summary.portfolio_total_return_base,
                portfolio_total_value_base=contract_response.summary.portfolio_total_value_base,
                accounted_return_base=contract_response.summary.accounted_return_base,
                residual_return_base=contract_response.summary.residual_return_base,
                contributors_count=contract_response.summary.contributors_count,
                detractors_count=contract_response.summary.detractors_count,
            ),
            contributors=[
                PortfolioAttributionPosition(**row.model_dump(mode="python"))
                for row in contract_response.contributors
            ],
            detractors=[
                PortfolioAttributionPosition(**row.model_dump(mode="python"))
                for row in contract_response.detractors
            ],
            positions=[
                PortfolioAttributionPosition(**row.model_dump(mode="python"))
                for row in contract_response.positions
            ],
            warnings=list(contract_response.warnings),
            generated_at=contract_response.generated_at,
        )
