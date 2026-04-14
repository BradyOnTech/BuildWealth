from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
import re
from statistics import pstdev
from typing import Any

from buildwealth_orchestrator.schemas import (
    ResearchCompareItem,
    ResearchCompareResponse,
    ResearchCompareSummary,
    ResearchResponse,
)


_SYMBOL_PATTERN = re.compile(r"[^A-Z0-9._-]+")


class OpenBBResearchService:
    def __init__(self, provider: str):
        self.provider = provider

    def _unavailable(self, symbol: str, detail: str) -> ResearchResponse:
        return ResearchResponse(
            symbol=symbol,
            provider=self.provider,
            available=False,
            message=detail,
            records=[],
        )

    def _as_records(self, value: Any, limit: int = 100) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)][:limit]
        if hasattr(value, "to_df"):
            frame = value.to_df()
            return frame.head(limit).to_dict(orient="records")
        if hasattr(value, "to_dict"):
            data = value.to_dict()
            if isinstance(data, list):
                return data[:limit]
        return []

    @staticmethod
    def _compute_price_change(records: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
        if not records:
            return None, None, None

        close_keys = ("close", "adj_close", "last")
        closes: list[float] = []
        for row in records:
            close_value = None
            for key in close_keys:
                if key in row:
                    close_value = row.get(key)
                    break

            try:
                if close_value is not None:
                    closes.append(float(close_value))
            except Exception:
                continue

        if len(closes) < 2:
            return None, None, None

        first_value = closes[0]
        last_value = closes[-1]
        if first_value == 0:
            pct_change = None
        else:
            pct_change = ((last_value - first_value) / first_value) * 100

        return first_value, last_value, pct_change

    def _call_endpoint(self, endpoint: Any, kwargs_variants: list[dict[str, Any]]) -> Any:
        attempts: list[str] = []
        for kwargs in kwargs_variants:
            try:
                return endpoint(**kwargs)
            except TypeError as exc:
                attempts.append(f"{kwargs}: {exc}")
                continue
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc

        joined = "; ".join(attempts) if attempts else "No endpoint call variants were attempted."
        raise RuntimeError(f"Unable to call OpenBB endpoint with tested kwargs. {joined}")

    @staticmethod
    def _parse_number(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric

        text = str(value or "").strip()
        if not text:
            return None

        negative_parentheses = text.startswith("(") and text.endswith(")")
        if negative_parentheses:
            text = text[1:-1].strip()

        text = text.replace(",", "").replace("$", "")
        is_percent = text.endswith("%")
        if is_percent:
            text = text[:-1].strip()
        if not text:
            return None

        try:
            numeric = float(text)
        except Exception:
            return None

        if negative_parentheses:
            numeric *= -1
        return numeric

    @classmethod
    def _extract_number(cls, row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
        for key in keys:
            if key not in row:
                continue
            numeric = cls._parse_number(row.get(key))
            if numeric is not None:
                return numeric
        return None

    @classmethod
    def _compute_history_volatility_pct(cls, records: list[dict[str, Any]], interval: str) -> float | None:
        if not records:
            return None

        close_values: list[float] = []
        for row in records:
            if not isinstance(row, dict):
                continue
            close = cls._extract_number(row, ("close", "adj_close", "last", "price"))
            if close is None:
                continue
            close_values.append(close)

        if len(close_values) < 3:
            return None

        returns: list[float] = []
        for previous, current in zip(close_values, close_values[1:]):
            if previous == 0:
                continue
            returns.append((current - previous) / previous)

        if len(returns) < 2:
            return None

        period_vol = pstdev(returns)
        normalized_interval = str(interval or "").strip().lower()
        if normalized_interval in {"1wk", "1w", "week", "weekly"}:
            annualization_factor = sqrt(52)
        elif normalized_interval in {"1mo", "1m", "month", "monthly"}:
            annualization_factor = sqrt(12)
        else:
            annualization_factor = sqrt(252)

        return period_vol * annualization_factor * 100.0

    @classmethod
    def _quote_metrics(cls, quote_row: dict[str, Any]) -> dict[str, float | None]:
        last_price = cls._extract_number(
            quote_row,
            ("last", "price", "regularMarketPrice", "close", "adj_close"),
        )
        day_change_pct = cls._extract_number(
            quote_row,
            (
                "change_percent",
                "changePercent",
                "percent_change",
                "change_pct",
                "regularMarketChangePercent",
            ),
        )
        market_cap = cls._extract_number(
            quote_row,
            ("market_cap", "marketCap", "market_capitalization"),
        )
        pe_ratio = cls._extract_number(
            quote_row,
            ("pe_ratio", "peRatio", "trailingPE", "forwardPE"),
        )
        dividend_yield = cls._extract_number(
            quote_row,
            ("dividend_yield", "dividendYield", "trailingAnnualDividendYield"),
        )
        if dividend_yield is not None and 0 < dividend_yield <= 1:
            dividend_yield *= 100

        return {
            "last_price": last_price,
            "day_change_pct": day_change_pct,
            "market_cap_usd": market_cap,
            "pe_ratio": pe_ratio,
            "dividend_yield_pct": dividend_yield,
        }

    @staticmethod
    def _score_item(
        *,
        period_change_pct: float | None,
        day_change_pct: float | None,
        volatility_pct: float | None,
    ) -> float | None:
        metrics = [metric for metric in (period_change_pct, day_change_pct, volatility_pct) if metric is not None]
        if not metrics:
            return None

        period_component = (period_change_pct or 0.0) * 0.7
        day_component = (day_change_pct or 0.0) * 0.2
        risk_component = (volatility_pct or 0.0) * -0.1
        return round(period_component + day_component + risk_component, 4)

    def options_chain(self, symbol: str) -> ResearchResponse:
        try:
            from openbb import obb  # type: ignore
        except Exception as exc:  # pragma: no cover - import-path dependent
            return self._unavailable(
                symbol=symbol,
                detail=(
                    "OpenBB is unavailable in this runtime. Install with `pip install .[openbb]` "
                    f"in services/orchestrator. Details: {exc}"
                ),
            )

        try:
            response = obb.derivatives.options.chains(symbol=symbol, provider=self.provider)
            records = self._as_records(response)
            return ResearchResponse(
                symbol=symbol,
                provider=self.provider,
                available=True,
                message=f"Fetched {len(records)} option rows",
                records=records,
            )
        except Exception as exc:  # pragma: no cover - API/provider dependent
            return self._unavailable(
                symbol=symbol,
                detail=f"OpenBB request failed: {exc}",
            )

    def price_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> ResearchResponse:
        try:
            from openbb import obb  # type: ignore
        except Exception as exc:  # pragma: no cover - import-path dependent
            return self._unavailable(
                symbol=symbol,
                detail=(
                    "OpenBB is unavailable in this runtime. Install with `pip install .[openbb]` "
                    f"in services/orchestrator. Details: {exc}"
                ),
            )

        try:
            endpoint = obb.equity.price.historical
        except Exception as exc:  # pragma: no cover - API/provider dependent
            return self._unavailable(
                symbol=symbol,
                detail=f"OpenBB historical price endpoint is unavailable: {exc}",
            )

        kwargs_variants = [
            {
                "symbol": symbol,
                "provider": self.provider,
                "period": period,
                "interval": interval,
            },
            {
                "symbol": symbol,
                "provider": self.provider,
                "interval": interval,
            },
            {
                "symbol": symbol,
                "provider": self.provider,
            },
            {"symbol": symbol},
        ]

        try:
            response = self._call_endpoint(endpoint=endpoint, kwargs_variants=kwargs_variants)
            records = self._as_records(response)
            first_close, last_close, pct_change = self._compute_price_change(records)

            message_bits = [f"Fetched {len(records)} historical rows"]
            if first_close is not None and last_close is not None and pct_change is not None:
                message_bits.append(
                    f"change {first_close:,.2f} -> {last_close:,.2f} ({pct_change:.2f}%)"
                )

            return ResearchResponse(
                symbol=symbol,
                provider=self.provider,
                available=True,
                message="; ".join(message_bits),
                records=records,
            )
        except Exception as exc:  # pragma: no cover - API/provider dependent
            return self._unavailable(symbol=symbol, detail=f"OpenBB price history request failed: {exc}")

    def quote(self, symbol: str) -> ResearchResponse:
        try:
            from openbb import obb  # type: ignore
        except Exception as exc:  # pragma: no cover - import-path dependent
            return self._unavailable(
                symbol=symbol,
                detail=(
                    "OpenBB is unavailable in this runtime. Install with `pip install .[openbb]` "
                    f"in services/orchestrator. Details: {exc}"
                ),
            )

        endpoint_candidates: list[Any] = []
        with_provider: list[dict[str, Any]] = [{"symbol": symbol, "provider": self.provider}]
        without_provider: list[dict[str, Any]] = [{"symbol": symbol}]

        with_provider_endpoint = getattr(getattr(getattr(obb, "equity", None), "price", None), "quote", None)
        if callable(with_provider_endpoint):
            endpoint_candidates.append(with_provider_endpoint)

        quote_snapshot_endpoint = getattr(
            getattr(getattr(obb, "equity", None), "price", None), "snapshot", None
        )
        if callable(quote_snapshot_endpoint):
            endpoint_candidates.append(quote_snapshot_endpoint)

        if not endpoint_candidates:
            return self._unavailable(
                symbol=symbol,
                detail="OpenBB quote endpoint is unavailable for this runtime/provider.",
            )

        last_error = ""
        for endpoint in endpoint_candidates:
            try:
                response = self._call_endpoint(
                    endpoint=endpoint,
                    kwargs_variants=[*with_provider, *without_provider],
                )
                records = self._as_records(response, limit=20)
                return ResearchResponse(
                    symbol=symbol,
                    provider=self.provider,
                    available=True,
                    message=f"Fetched {len(records)} quote row(s)",
                    records=records,
                )
            except Exception as exc:  # pragma: no cover - API/provider dependent
                last_error = str(exc)
                continue

        return self._unavailable(
            symbol=symbol,
            detail=f"OpenBB quote request failed: {last_error or 'Unknown error'}",
        )

    def compare(
        self,
        *,
        symbols: list[str],
        period: str = "6mo",
        interval: str = "1d",
        baseline_symbol: str | None = None,
    ) -> ResearchCompareResponse:
        normalized_symbols: list[str] = []
        seen: set[str] = set()
        for raw_symbol in symbols:
            symbol = _SYMBOL_PATTERN.sub("", str(raw_symbol or "").strip().upper())
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized_symbols.append(symbol)
            if len(normalized_symbols) >= 20:
                break

        warnings: list[str] = []
        items: list[ResearchCompareItem] = []
        for symbol in normalized_symbols:
            quote_response = self.quote(symbol)
            history_response = self.price_history(symbol=symbol, period=period, interval=interval)

            quote_row = (
                quote_response.records[0]
                if quote_response.available and quote_response.records and isinstance(quote_response.records[0], dict)
                else {}
            )
            quote_metrics = self._quote_metrics(quote_row)

            _, _, period_change_pct = self._compute_price_change(history_response.records)
            volatility_pct = self._compute_history_volatility_pct(history_response.records, interval=interval)
            score = self._score_item(
                period_change_pct=period_change_pct,
                day_change_pct=quote_metrics.get("day_change_pct"),
                volatility_pct=volatility_pct,
            )

            available = bool(quote_response.available or history_response.available)
            message_bits: list[str] = []
            if quote_response.message:
                message_bits.append(f"quote: {quote_response.message}")
            if history_response.message:
                message_bits.append(f"history: {history_response.message}")
            if not quote_response.available:
                warnings.append(f"{symbol}: quote unavailable ({quote_response.message})")
            if not history_response.available:
                warnings.append(f"{symbol}: history unavailable ({history_response.message})")

            items.append(
                ResearchCompareItem(
                    symbol=symbol,
                    available=available,
                    message="; ".join(message_bits) if message_bits else "No research data available.",
                    score=score,
                    last_price=quote_metrics.get("last_price"),
                    day_change_pct=quote_metrics.get("day_change_pct"),
                    period_change_pct=period_change_pct,
                    volatility_pct=volatility_pct,
                    market_cap_usd=quote_metrics.get("market_cap_usd"),
                    pe_ratio=quote_metrics.get("pe_ratio"),
                    dividend_yield_pct=quote_metrics.get("dividend_yield_pct"),
                    quote_records=len(quote_response.records),
                    history_records=len(history_response.records),
                )
            )

        ranked = sorted(
            items,
            key=lambda item: (item.score is None, -(item.score or -10_000), item.symbol),
        )
        for index, item in enumerate(ranked, start=1):
            if item.score is not None:
                item.rank = index

        period_rows = [item for item in items if item.period_change_pct is not None]
        volatility_rows = [item for item in items if item.volatility_pct is not None]

        resolved_baseline = (
            str(baseline_symbol or "").strip().upper()
            if baseline_symbol
            else None
        )
        if resolved_baseline and resolved_baseline not in normalized_symbols:
            resolved_baseline = None
        if resolved_baseline is None and normalized_symbols:
            resolved_baseline = normalized_symbols[0]

        baseline_relative_return_pct: dict[str, float] = {}
        baseline_period_return: float | None = None
        if resolved_baseline:
            baseline_item = next((row for row in items if row.symbol == resolved_baseline), None)
            baseline_period_return = baseline_item.period_change_pct if baseline_item else None
        if baseline_period_return is not None:
            for item in items:
                if item.period_change_pct is None:
                    continue
                baseline_relative_return_pct[item.symbol] = round(
                    item.period_change_pct - baseline_period_return,
                    4,
                )

        summary = ResearchCompareSummary(
            requested_symbols=len(normalized_symbols),
            compared_symbols=len(items),
            available_symbols=sum(1 for item in items if item.available),
            baseline_symbol=resolved_baseline,
            ranked_symbols=[item.symbol for item in ranked if item.rank is not None],
            best_period_return_symbol=(
                max(period_rows, key=lambda item: item.period_change_pct or -10_000).symbol if period_rows else None
            ),
            worst_period_return_symbol=(
                min(period_rows, key=lambda item: item.period_change_pct or 10_000).symbol if period_rows else None
            ),
            highest_volatility_symbol=(
                max(volatility_rows, key=lambda item: item.volatility_pct or -10_000).symbol if volatility_rows else None
            ),
            lowest_volatility_symbol=(
                min(volatility_rows, key=lambda item: item.volatility_pct or 10_000).symbol if volatility_rows else None
            ),
            baseline_relative_return_pct=baseline_relative_return_pct,
        )

        deduped_warnings: list[str] = []
        seen_warnings: set[str] = set()
        for warning in warnings:
            lowered = warning.lower()
            if lowered in seen_warnings:
                continue
            seen_warnings.add(lowered)
            deduped_warnings.append(warning)

        return ResearchCompareResponse(
            provider=self.provider,
            period=str(period or "6mo").strip() or "6mo",
            interval=str(interval or "1d").strip() or "1d",
            generated_at=datetime.now(timezone.utc),
            symbols=normalized_symbols,
            summary=summary,
            items=ranked,
            warnings=deduped_warnings,
        )

    def get_quote(self, symbol: str) -> dict[str, Any]:
        response = self.quote(symbol)
        if not response.available or not response.records:
            return {}
        row = response.records[0]
        return row if isinstance(row, dict) else {}

    def get_price_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict[str, Any]]:
        response = self.price_history(symbol=symbol, period=period, interval=interval)
        if not response.available:
            return []
        return [row for row in response.records if isinstance(row, dict)]


def concentration_metrics(holdings: list[dict[str, Any]]) -> dict[str, Any]:
    if not holdings:
        return {
            "top_positions": [],
            "herfindahl_index": 0.0,
            "effective_number_of_positions": 0.0,
        }

    ranked = sorted(holdings, key=lambda item: float(item.get("value_usd", 0.0)), reverse=True)
    total_value = sum(float(item.get("value_usd", 0.0)) for item in ranked)

    if total_value == 0:
        return {
            "top_positions": [],
            "herfindahl_index": 0.0,
            "effective_number_of_positions": 0.0,
        }

    normalized = []
    for item in ranked:
        weight = float(item.get("value_usd", 0.0)) / total_value
        normalized.append(
            {
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "weight": round(weight, 4),
                "value_usd": round(float(item.get("value_usd", 0.0)), 2),
            }
        )

    herfindahl = sum(item["weight"] ** 2 for item in normalized)
    effective_positions = (1 / herfindahl) if herfindahl else 0.0

    return {
        "top_positions": normalized[:10],
        "herfindahl_index": round(herfindahl, 4),
        "effective_number_of_positions": round(effective_positions, 2),
    }
