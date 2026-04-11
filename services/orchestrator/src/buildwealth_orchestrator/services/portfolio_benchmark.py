from __future__ import annotations

from datetime import date, datetime, timezone
from math import sqrt
from statistics import pstdev
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from buildwealth_orchestrator.schemas import (
    PortfolioBenchmarkResponse,
    PortfolioBenchmarkSeriesPoint,
    PortfolioBenchmarkSummary,
)
from buildwealth_orchestrator.services.engine_adapter import (
    SidecarAdapter,
    SidecarAdapterError,
)
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore


class GhostfolioBenchmarkPortfolioPointV1(BaseModel):
    date: date
    total_value_base: float
    net_external_flow_base: float = 0.0


class GhostfolioBenchmarkRequestV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    portfolio_base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    start_date: date
    end_date: date
    portfolio_series: list[GhostfolioBenchmarkPortfolioPointV1]
    benchmark_symbols: list[str]
    sampling_interval: Literal["DAILY", "WEEKLY", "MONTHLY"] = "DAILY"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("benchmark_symbols")
    @classmethod
    def _clean_symbols(cls, values: list[str]) -> list[str]:
        cleaned = [str(item).strip().upper() for item in values if str(item).strip()]
        if not cleaned:
            raise ValueError("At least one benchmark symbol is required")
        return cleaned

    @field_validator("portfolio_series")
    @classmethod
    def _validate_series(cls, values: list[GhostfolioBenchmarkPortfolioPointV1]) -> list[GhostfolioBenchmarkPortfolioPointV1]:
        if len(values) < 2:
            raise ValueError("portfolio_series must include at least 2 points")
        return sorted(values, key=lambda item: item.date)

    @model_validator(mode="after")
    def _validate_window(self) -> GhostfolioBenchmarkRequestV1:
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        if self.portfolio_series[0].date < self.start_date:
            raise ValueError("portfolio_series contains dates before start_date")
        if self.portfolio_series[-1].date > self.end_date:
            raise ValueError("portfolio_series contains dates after end_date")
        return self


class GhostfolioBenchmarkSummaryV1(BaseModel):
    portfolio_return_pct: float
    benchmark_return_pct_by_symbol: dict[str, float]
    alpha_pct_by_symbol: dict[str, float]
    tracking_error_pct: float | None = None
    max_drawdown_pct: float | None = None


class GhostfolioBenchmarkSeriesPointV1(BaseModel):
    date: date
    portfolio_index: float
    benchmark_index_by_symbol: dict[str, float]
    alpha_index_by_symbol: dict[str, float]


class GhostfolioBenchmarkResponseV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    engine: Literal["ghostfolio"] = "ghostfolio"
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    summary: GhostfolioBenchmarkSummaryV1
    series: list[GhostfolioBenchmarkSeriesPointV1]
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None


class GhostfolioBenchmarkService:
    def __init__(
        self,
        *,
        snapshot_store: SnapshotStore,
        research_service: Any,
        sidecar_adapter: SidecarAdapter | None,
        sidecar_enabled: bool,
        sidecar_path: str,
        base_currency: str = "USD",
    ) -> None:
        self.snapshot_store = snapshot_store
        self.research_service = research_service
        self.sidecar_adapter = sidecar_adapter
        self.sidecar_enabled = sidecar_enabled
        self.sidecar_path = sidecar_path
        self.base_currency = str(base_currency or "USD").upper()

    async def compare(
        self,
        *,
        benchmark_symbols: list[str],
        limit: int,
    ) -> PortfolioBenchmarkResponse:
        request_payload = self._build_request_payload(
            benchmark_symbols=benchmark_symbols,
            limit=limit,
        )

        if self.sidecar_enabled and self.sidecar_adapter is not None:
            try:
                contract_response = await self.sidecar_adapter.post_json(
                    path=self.sidecar_path,
                    request_payload=request_payload.model_dump(mode="json"),
                    request_model=GhostfolioBenchmarkRequestV1,
                    response_model=GhostfolioBenchmarkResponseV1,
                )
                return self._to_api_response(request_payload, contract_response)
            except SidecarAdapterError as exc:
                fallback = self._compute_local_fallback(
                    request_payload,
                    fallback_method="local_benchmark_fallback",
                    warning=f"Ghostfolio benchmark sidecar unavailable: {exc}",
                )
                return self._to_api_response(request_payload, fallback)

        fallback = self._compute_local_fallback(
            request_payload,
            fallback_method="sidecar_disabled",
            warning="Ghostfolio benchmark sidecar disabled; using local fallback",
        )
        return self._to_api_response(request_payload, fallback)

    def _build_request_payload(
        self,
        *,
        benchmark_symbols: list[str],
        limit: int,
    ) -> GhostfolioBenchmarkRequestV1:
        bounded_limit = max(2, min(int(limit), 3650))
        history = self.snapshot_store.recent(limit=bounded_limit)
        if len(history) < 2:
            raise ValueError("At least 2 snapshots are required for benchmark comparison")

        points = [
            GhostfolioBenchmarkPortfolioPointV1(
                date=snapshot.as_of.date(),
                total_value_base=float(snapshot.total_value_usd),
                net_external_flow_base=0.0,
            )
            for snapshot in sorted(history, key=lambda row: row.as_of)
        ]

        return GhostfolioBenchmarkRequestV1(
            request_id=uuid4().hex,
            portfolio_base_currency=self.base_currency,
            start_date=points[0].date,
            end_date=points[-1].date,
            portfolio_series=points,
            benchmark_symbols=benchmark_symbols,
            metadata={"source": "snapshot_store"},
        )

    def _compute_local_fallback(
        self,
        request_payload: GhostfolioBenchmarkRequestV1,
        *,
        fallback_method: str,
        warning: str,
    ) -> GhostfolioBenchmarkResponseV1:
        dates = [point.date for point in request_payload.portfolio_series]
        portfolio_values = [point.total_value_base for point in request_payload.portfolio_series]
        portfolio_index = self._normalize_to_index(portfolio_values)

        benchmark_index_by_symbol: dict[str, list[float]] = {}
        benchmark_return_pct_by_symbol: dict[str, float] = {}
        alpha_pct_by_symbol: dict[str, float] = {}

        for symbol in request_payload.benchmark_symbols:
            closes = self._benchmark_closes_for_symbol(symbol=symbol, dates=dates)
            indexes = self._normalize_to_index(closes)
            benchmark_index_by_symbol[symbol] = indexes
            benchmark_return = round(indexes[-1] - indexes[0], 4)
            benchmark_return_pct_by_symbol[symbol] = benchmark_return
            alpha_pct_by_symbol[symbol] = round((portfolio_index[-1] - portfolio_index[0]) - benchmark_return, 4)

        series: list[GhostfolioBenchmarkSeriesPointV1] = []
        for idx, point_date in enumerate(dates):
            benchmark_row = {
                symbol: values[idx]
                for symbol, values in benchmark_index_by_symbol.items()
            }
            alpha_row = {
                symbol: round(portfolio_index[idx] - benchmark_value, 4)
                for symbol, benchmark_value in benchmark_row.items()
            }
            series.append(
                GhostfolioBenchmarkSeriesPointV1(
                    date=point_date,
                    portfolio_index=portfolio_index[idx],
                    benchmark_index_by_symbol=benchmark_row,
                    alpha_index_by_symbol=alpha_row,
                )
            )

        tracking_error_pct = self._tracking_error_pct(portfolio_index, benchmark_index_by_symbol)

        return GhostfolioBenchmarkResponseV1(
            request_id=request_payload.request_id,
            engine_status="degraded",
            fallback_method=fallback_method,
            summary=GhostfolioBenchmarkSummaryV1(
                portfolio_return_pct=round(portfolio_index[-1] - portfolio_index[0], 4),
                benchmark_return_pct_by_symbol=benchmark_return_pct_by_symbol,
                alpha_pct_by_symbol=alpha_pct_by_symbol,
                tracking_error_pct=tracking_error_pct,
                max_drawdown_pct=self._max_drawdown_pct(portfolio_index),
            ),
            series=series,
            warnings=[warning],
            generated_at=datetime.now(timezone.utc),
        )

    def _benchmark_closes_for_symbol(self, *, symbol: str, dates: list[date]) -> list[float]:
        rows = self.research_service.get_price_history(symbol=symbol, period="1y", interval="1d")
        closes_by_date: dict[date, float] = {}
        for row in rows:
            point_date = self._parse_date(row.get("date"))
            close_value = self._parse_close(row)
            if point_date is None or close_value is None:
                continue
            closes_by_date[point_date] = close_value

        if not closes_by_date:
            return [1.0 for _ in dates]

        ordered_dates = sorted(closes_by_date.keys())
        resolved: list[float] = []
        last_close = closes_by_date[ordered_dates[0]]

        for target_date in dates:
            selected = last_close
            for source_date in ordered_dates:
                if source_date <= target_date:
                    selected = closes_by_date[source_date]
                else:
                    break
            last_close = selected
            resolved.append(selected)

        return resolved

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError:
            return None

    @staticmethod
    def _parse_close(row: dict[str, Any]) -> float | None:
        for key in ("close", "adj_close", "last", "price"):
            if key not in row:
                continue
            try:
                value = float(row.get(key))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    @staticmethod
    def _normalize_to_index(values: list[float]) -> list[float]:
        if not values:
            return []
        baseline = next((value for value in values if value > 0), 1.0)
        if baseline <= 0:
            baseline = 1.0
        return [round((value / baseline) * 100.0, 4) if value > 0 else 100.0 for value in values]

    @staticmethod
    def _max_drawdown_pct(index_series: list[float]) -> float:
        if not index_series:
            return 0.0
        peak = index_series[0]
        max_drawdown = 0.0
        for value in index_series:
            peak = max(peak, value)
            if peak <= 0:
                continue
            drawdown = ((value - peak) / peak) * 100.0
            max_drawdown = min(max_drawdown, drawdown)
        return round(max_drawdown, 4)

    @staticmethod
    def _tracking_error_pct(
        portfolio_index: list[float],
        benchmark_index_by_symbol: dict[str, list[float]],
    ) -> float | None:
        if len(portfolio_index) < 3 or not benchmark_index_by_symbol:
            return None

        benchmark_key = next(iter(benchmark_index_by_symbol.keys()))
        benchmark_index = benchmark_index_by_symbol[benchmark_key]
        if len(benchmark_index) != len(portfolio_index):
            return None

        excess_returns: list[float] = []
        for idx in range(1, len(portfolio_index)):
            prev_port = portfolio_index[idx - 1]
            prev_bench = benchmark_index[idx - 1]
            if prev_port <= 0 or prev_bench <= 0:
                continue
            port_return = (portfolio_index[idx] / prev_port) - 1.0
            bench_return = (benchmark_index[idx] / prev_bench) - 1.0
            excess_returns.append(port_return - bench_return)

        if len(excess_returns) < 2:
            return None

        return round(float(pstdev(excess_returns) * sqrt(252) * 100.0), 4)

    @staticmethod
    def _to_api_response(
        request_payload: GhostfolioBenchmarkRequestV1,
        contract_response: GhostfolioBenchmarkResponseV1,
    ) -> PortfolioBenchmarkResponse:
        return PortfolioBenchmarkResponse(
            request_id=contract_response.request_id,
            contract_version=contract_response.contract_version,
            engine=contract_response.engine,
            engine_status=contract_response.engine_status,
            fallback_method=contract_response.fallback_method,
            benchmark_symbols=request_payload.benchmark_symbols,
            start_date=request_payload.start_date,
            end_date=request_payload.end_date,
            summary=PortfolioBenchmarkSummary(
                portfolio_return_pct=contract_response.summary.portfolio_return_pct,
                benchmark_return_pct_by_symbol=contract_response.summary.benchmark_return_pct_by_symbol,
                alpha_pct_by_symbol=contract_response.summary.alpha_pct_by_symbol,
                tracking_error_pct=contract_response.summary.tracking_error_pct,
                max_drawdown_pct=contract_response.summary.max_drawdown_pct,
            ),
            series=[
                PortfolioBenchmarkSeriesPoint(
                    date=point.date,
                    portfolio_index=point.portfolio_index,
                    benchmark_index_by_symbol=point.benchmark_index_by_symbol,
                    alpha_index_by_symbol=point.alpha_index_by_symbol,
                )
                for point in contract_response.series
            ],
            warnings=list(contract_response.warnings),
            generated_at=contract_response.generated_at,
        )
