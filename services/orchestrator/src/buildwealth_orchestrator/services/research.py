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
    ResearchDossierResponse,
    ResearchEvidencePacket,
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

    @staticmethod
    def _normalize_symbol_list(symbols: list[str], *, max_symbols: int = 20) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_symbol in symbols:
            symbol = _SYMBOL_PATTERN.sub("", str(raw_symbol or "").strip().upper())
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized.append(symbol)
            if len(normalized) >= max_symbols:
                break
        return normalized

    @staticmethod
    def _normalize_text_list(items: list[str] | None, *, max_items: int = 12) -> list[str]:
        if not isinstance(items, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_item in items:
            item = str(raw_item or "").strip()
            if not item:
                continue
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(item)
            if len(normalized) >= max_items:
                break
        return normalized

    @staticmethod
    def _freshness_status(*, available_symbols: int, compared_symbols: int, warning_count: int) -> str:
        if compared_symbols <= 0 or available_symbols <= 0:
            return "degraded"
        if available_symbols == compared_symbols and warning_count == 0:
            return "fresh"
        return "partial"

    @classmethod
    def _identity_value(cls, row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = row.get(key)
            text = str(value or "").strip()
            if text:
                return text
        return None

    @classmethod
    def _drawdown_from_high_pct(cls, records: list[dict[str, Any]]) -> float | None:
        close_values: list[float] = []
        for row in records:
            if not isinstance(row, dict):
                continue
            close = cls._extract_number(row, ("close", "adj_close", "last", "price"))
            if close is not None:
                close_values.append(close)

        if not close_values:
            return None
        high = max(close_values)
        if high == 0:
            return None
        return round(((close_values[-1] - high) / high) * 100.0, 4)

    @classmethod
    def _history_close_values(cls, records: list[dict[str, Any]]) -> list[float]:
        close_values: list[float] = []
        for row in records:
            if not isinstance(row, dict):
                continue
            close = cls._extract_number(row, ("close", "adj_close", "last", "price"))
            if close is not None:
                close_values.append(close)
        return close_values

    @classmethod
    def _history_trend(cls, records: list[dict[str, Any]], *, days: int) -> str:
        closes_desc = list(reversed(cls._history_close_values(records)))
        if len(closes_desc) < 2 * days:
            return "UNKNOWN"
        recent_avg = sum(closes_desc[:days]) / float(days)
        past_avg = sum(closes_desc[days : 2 * days]) / float(days)
        if recent_avg > past_avg:
            return "UP"
        if recent_avg < past_avg:
            return "DOWN"
        return "NEUTRAL"

    @staticmethod
    def _evidence_freshness_status(*, quote_available: bool, history_available: bool) -> str:
        if quote_available and history_available:
            return "fresh"
        if quote_available or history_available:
            return "partial"
        return "degraded"

    @staticmethod
    def _evidence_confidence(*, quote_available: bool, history_available: bool) -> str:
        if quote_available and history_available:
            return "high"
        if quote_available or history_available:
            return "medium"
        return "low"

    @classmethod
    def _build_portfolio_fit(
        cls,
        *,
        symbols: list[str],
        include_portfolio_fit: bool,
        portfolio_weights_pct: dict[str, float] | None,
    ) -> dict[str, Any]:
        if not include_portfolio_fit:
            return {}

        normalized_weights: dict[str, float] = {}
        if isinstance(portfolio_weights_pct, dict):
            for raw_symbol, raw_weight in portfolio_weights_pct.items():
                symbol = _SYMBOL_PATTERN.sub("", str(raw_symbol or "").strip().upper())
                if not symbol:
                    continue
                numeric_weight = cls._parse_number(raw_weight)
                if numeric_weight is None:
                    continue
                normalized_weights[symbol] = max(0.0, numeric_weight)

        portfolio_symbols = sorted(normalized_weights.keys())
        overlap = [symbol for symbol in symbols if symbol in normalized_weights]
        new_candidates = [symbol for symbol in symbols if symbol not in normalized_weights]
        overlap_weight_pct = round(sum(normalized_weights.get(symbol, 0.0) for symbol in overlap), 2)
        overlap_ratio = round((len(overlap) / len(symbols) * 100.0), 2) if symbols else 0.0

        fit_label = "none"
        if overlap_ratio >= 60:
            fit_label = "high_overlap"
        elif overlap_ratio >= 25:
            fit_label = "mixed"
        elif symbols:
            fit_label = "mostly_new"

        overlap_ranked = sorted(overlap, key=lambda symbol: normalized_weights.get(symbol, 0.0), reverse=True)

        return {
            "portfolio_symbols_considered": portfolio_symbols,
            "existing_symbols": overlap,
            "new_symbols": new_candidates,
            "overlap_ratio_pct": overlap_ratio,
            "overlap_weight_pct": overlap_weight_pct,
            "highest_weight_overlap_symbols": overlap_ranked[:5],
            "fit_label": fit_label,
        }

    @staticmethod
    def _build_dossier_markdown(
        *,
        headline: str,
        compare: ResearchCompareResponse,
        thesis: str,
        risks: list[str],
        catalysts: list[str],
        key_takeaways: list[str],
        freshness: dict[str, Any],
        portfolio_fit: dict[str, Any],
    ) -> str:
        lines: list[str] = [
            f"# Research Dossier: {', '.join(compare.symbols)}",
            "",
            f"- Generated: {compare.generated_at.isoformat()}",
            f"- Provider: {compare.provider}",
            f"- Period/Interval: {compare.period} / {compare.interval}",
            f"- Baseline: {compare.summary.baseline_symbol or 'n/a'}",
            "",
            "## Headline",
            "",
            headline,
            "",
            "## Thesis",
            "",
            thesis or "- Thesis not provided.",
            "",
            "## Scorecard",
            "",
            "| Rank | Symbol | Period Return | Volatility | Score | Availability |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]

        for item in compare.items:
            period = f"{item.period_change_pct:.2f}%" if item.period_change_pct is not None else "-"
            volatility = f"{item.volatility_pct:.2f}%" if item.volatility_pct is not None else "-"
            score = f"{item.score:.3f}" if item.score is not None else "-"
            availability = "available" if item.available else "partial"
            rank = str(item.rank) if item.rank is not None else "-"
            lines.append(f"| {rank} | {item.symbol} | {period} | {volatility} | {score} | {availability} |")

        lines.extend(
            [
                "",
                "## Key Takeaways",
                "",
            ]
        )
        if key_takeaways:
            lines.extend([f"- {item}" for item in key_takeaways])
        else:
            lines.append("- No takeaways available from current inputs.")

        lines.extend(
            [
                "",
                "## Risks",
                "",
            ]
        )
        if risks:
            lines.extend([f"- {item}" for item in risks])
        else:
            lines.append("- No explicit risks provided.")

        lines.extend(
            [
                "",
                "## Catalysts",
                "",
            ]
        )
        if catalysts:
            lines.extend([f"- {item}" for item in catalysts])
        else:
            lines.append("- No explicit catalysts provided.")

        lines.extend(
            [
                "",
                "## Freshness",
                "",
                f"- Status: {freshness.get('status', 'unknown')}",
                f"- Available symbols: {freshness.get('available_symbols', 0)} / {freshness.get('compared_symbols', 0)}",
                f"- Warning count: {freshness.get('warning_count', 0)}",
            ]
        )

        if portfolio_fit:
            existing_symbols = portfolio_fit.get("existing_symbols", [])
            if not isinstance(existing_symbols, list):
                existing_symbols = []
            new_symbols = portfolio_fit.get("new_symbols", [])
            if not isinstance(new_symbols, list):
                new_symbols = []
            lines.extend(
                [
                    "",
                    "## Portfolio Fit",
                    "",
                    f"- Fit label: {portfolio_fit.get('fit_label', 'unknown')}",
                    f"- Existing overlap symbols: {', '.join(existing_symbols) if existing_symbols else 'none'}",
                    f"- New candidate symbols: {', '.join(new_symbols) if new_symbols else 'none'}",
                    f"- Existing overlap weight: {portfolio_fit.get('overlap_weight_pct', 0.0)}%",
                ]
            )

        if compare.warnings:
            lines.extend(
                [
                    "",
                    "## Data Warnings",
                    "",
                ]
            )
            lines.extend([f"- {warning}" for warning in compare.warnings[:20]])

        return "\n".join(lines).strip() + "\n"

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
        normalized_symbols = self._normalize_symbol_list(symbols, max_symbols=20)

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

    def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchEvidencePacket:
        normalized_symbols = self._normalize_symbol_list([symbol], max_symbols=1)
        normalized_symbol = normalized_symbols[0] if normalized_symbols else ""
        if not normalized_symbol:
            raise ValueError("Research evidence packet requires a symbol.")
        resolved_period = str(period or "6mo").strip() or "6mo"
        resolved_interval = str(interval or "1d").strip() or "1d"

        quote_response = self.quote(normalized_symbol)
        history_response = self.price_history(
            symbol=normalized_symbol,
            period=resolved_period,
            interval=resolved_interval,
        )

        quote_row = (
            quote_response.records[0]
            if quote_response.available and quote_response.records and isinstance(quote_response.records[0], dict)
            else {}
        )
        quote_metrics = self._quote_metrics(quote_row)
        first_close, last_close, period_change_pct = self._compute_price_change(history_response.records)
        volatility_pct = self._compute_history_volatility_pct(
            history_response.records,
            interval=resolved_interval,
        )

        warnings: list[str] = []
        if not quote_response.available:
            warnings.append(f"{normalized_symbol}: quote unavailable ({quote_response.message})")
        if not history_response.available:
            warnings.append(f"{normalized_symbol}: history unavailable ({history_response.message})")

        blocking_gaps: list[str] = []
        if not quote_response.available:
            blocking_gaps.append("quote")
        if not history_response.available:
            blocking_gaps.append("history")

        quote_available = bool(quote_response.available)
        history_available = bool(history_response.available)
        available_endpoints = sum(1 for item in (quote_available, history_available) if item)
        generated_at = datetime.now(timezone.utc)

        close_values = self._history_close_values(history_response.records)
        all_time_high = max(close_values) if close_values else None

        return ResearchEvidencePacket(
            packet_id=f"research-evidence:{self.provider}:{normalized_symbol}:{resolved_period}:{resolved_interval}",
            symbol=normalized_symbol,
            name=self._identity_value(quote_row, ("name", "shortName", "longName", "company_name")),
            asset_type=self._identity_value(quote_row, ("asset_type", "assetType", "security_type", "type")),
            provider=self.provider,
            period=resolved_period,
            interval=resolved_interval,
            generated_at=generated_at,
            coverage={
                "provider": self.provider,
                "endpoints_attempted": ["quote", "price_history"],
                "quote_available": quote_available,
                "history_available": history_available,
                "quote_message": quote_response.message,
                "history_message": history_response.message,
                "warnings": warnings,
            },
            freshness={
                "generated_at": generated_at.isoformat(),
                "status": self._evidence_freshness_status(
                    quote_available=quote_available,
                    history_available=history_available,
                ),
                "quote_as_of": self._identity_value(quote_row, ("date", "timestamp", "as_of", "updated_at")),
                "history_start": self._identity_value(
                    history_response.records[0] if history_response.records else {},
                    ("date", "timestamp"),
                ),
                "history_end": self._identity_value(
                    history_response.records[-1] if history_response.records else {},
                    ("date", "timestamp"),
                ),
            },
            metrics={
                "last_price": quote_metrics.get("last_price") if quote_metrics.get("last_price") is not None else last_close,
                "day_change_pct": quote_metrics.get("day_change_pct"),
                "period_first_close": first_close,
                "period_last_close": last_close,
                "period_change_pct": round(period_change_pct, 4) if period_change_pct is not None else None,
                "volatility_pct": round(volatility_pct, 4) if volatility_pct is not None else None,
                "market_cap_usd": quote_metrics.get("market_cap_usd"),
                "pe_ratio": quote_metrics.get("pe_ratio"),
                "dividend_yield_pct": quote_metrics.get("dividend_yield_pct"),
            },
            risk={
                "drawdown_from_high_pct": self._drawdown_from_high_pct(history_response.records),
                "all_time_high": all_time_high,
                "trend50d": self._history_trend(history_response.records, days=50),
                "trend200d": self._history_trend(history_response.records, days=200),
                "volatility_pct": round(volatility_pct, 4) if volatility_pct is not None else None,
                "data_gaps": blocking_gaps,
            },
            quality={
                "coverage_score": round((available_endpoints / 2.0) * 100.0, 2),
                "confidence": self._evidence_confidence(
                    quote_available=quote_available,
                    history_available=history_available,
                ),
                "blocking_gaps": blocking_gaps,
                "decision_ready": quote_available and history_available,
            },
            provenance={
                "source": "openbb",
                "provider": self.provider,
                "quote_records": len(quote_response.records),
                "history_records": len(history_response.records),
                "quote_message": quote_response.message,
                "history_message": history_response.message,
                "warnings": warnings,
            },
        )

    def dossier(
        self,
        *,
        symbols: list[str],
        period: str = "6mo",
        interval: str = "1d",
        baseline_symbol: str | None = None,
        thesis: str = "",
        risks: list[str] | None = None,
        catalysts: list[str] | None = None,
        include_portfolio_fit: bool = True,
        portfolio_weights_pct: dict[str, float] | None = None,
    ) -> ResearchDossierResponse:
        normalized_symbols = self._normalize_symbol_list(symbols, max_symbols=20)
        compare = self.compare(
            symbols=normalized_symbols,
            period=period,
            interval=interval,
            baseline_symbol=baseline_symbol,
        )

        normalized_risks = self._normalize_text_list(risks, max_items=12)
        normalized_catalysts = self._normalize_text_list(catalysts, max_items=12)
        normalized_thesis = str(thesis or "").strip()

        warnings = list(compare.warnings)
        if not compare.items:
            warnings.append("No symbols were available to build a dossier.")

        freshness = {
            "generated_at": compare.generated_at.isoformat(),
            "status": self._freshness_status(
                available_symbols=compare.summary.available_symbols,
                compared_symbols=compare.summary.compared_symbols,
                warning_count=len(warnings),
            ),
            "available_symbols": compare.summary.available_symbols,
            "compared_symbols": compare.summary.compared_symbols,
            "warning_count": len(warnings),
            "quote_records_total": sum(item.quote_records for item in compare.items),
            "history_records_total": sum(item.history_records for item in compare.items),
        }

        portfolio_fit = self._build_portfolio_fit(
            symbols=compare.symbols,
            include_portfolio_fit=include_portfolio_fit,
            portfolio_weights_pct=portfolio_weights_pct,
        )

        best_symbol = compare.summary.best_period_return_symbol
        worst_symbol = compare.summary.worst_period_return_symbol
        highest_vol_symbol = compare.summary.highest_volatility_symbol

        headline = f"Research dossier for {', '.join(compare.symbols)}."
        if best_symbol and worst_symbol and best_symbol != worst_symbol:
            headline = f"{best_symbol} leads {compare.period} performance while {worst_symbol} trails."
        elif best_symbol:
            headline = f"{best_symbol} is the leading performer in this comparison window."

        key_takeaways: list[str] = []
        if best_symbol:
            best_item = next((item for item in compare.items if item.symbol == best_symbol), None)
            if best_item and best_item.period_change_pct is not None:
                key_takeaways.append(
                    f"{best_symbol} delivered the strongest period return at {best_item.period_change_pct:.2f}%."
                )
        if worst_symbol and worst_symbol != best_symbol:
            worst_item = next((item for item in compare.items if item.symbol == worst_symbol), None)
            if worst_item and worst_item.period_change_pct is not None:
                key_takeaways.append(
                    f"{worst_symbol} had the weakest period return at {worst_item.period_change_pct:.2f}%."
                )
        if highest_vol_symbol:
            highest_vol_item = next((item for item in compare.items if item.symbol == highest_vol_symbol), None)
            if highest_vol_item and highest_vol_item.volatility_pct is not None:
                key_takeaways.append(
                    f"{highest_vol_symbol} shows the highest estimated volatility at {highest_vol_item.volatility_pct:.2f}%."
                )

        baseline_deltas = compare.summary.baseline_relative_return_pct
        if baseline_deltas and compare.summary.baseline_symbol:
            outperformers = [
                symbol
                for symbol, delta in sorted(baseline_deltas.items(), key=lambda item: item[1], reverse=True)
                if symbol != compare.summary.baseline_symbol and delta > 0
            ]
            if outperformers:
                key_takeaways.append(
                    f"{', '.join(outperformers[:3])} outperformed baseline {compare.summary.baseline_symbol} over this period."
                )

        if portfolio_fit:
            overlap_symbols = portfolio_fit.get("existing_symbols", [])
            new_symbols = portfolio_fit.get("new_symbols", [])
            if isinstance(overlap_symbols, list):
                if overlap_symbols:
                    key_takeaways.append(
                        f"Portfolio overlap includes {', '.join(overlap_symbols[:4])}; overlap weight is {portfolio_fit.get('overlap_weight_pct', 0.0)}%."
                    )
                elif isinstance(new_symbols, list) and new_symbols:
                    key_takeaways.append(
                        f"All compared symbols are currently new to the portfolio: {', '.join(new_symbols[:4])}."
                    )

        if not key_takeaways:
            key_takeaways.append("Data was limited; collect additional research before decisioning.")

        dossier_markdown = self._build_dossier_markdown(
            headline=headline,
            compare=compare,
            thesis=normalized_thesis,
            risks=normalized_risks,
            catalysts=normalized_catalysts,
            key_takeaways=key_takeaways,
            freshness=freshness,
            portfolio_fit=portfolio_fit,
        )

        return ResearchDossierResponse(
            provider=self.provider,
            period=compare.period,
            interval=compare.interval,
            generated_at=compare.generated_at,
            symbols=compare.symbols,
            baseline_symbol=compare.summary.baseline_symbol,
            headline=headline,
            thesis=normalized_thesis,
            risks=normalized_risks,
            catalysts=normalized_catalysts,
            key_takeaways=key_takeaways,
            freshness=freshness,
            compare=compare,
            portfolio_fit=portfolio_fit,
            dossier_markdown=dossier_markdown,
            warnings=warnings,
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
