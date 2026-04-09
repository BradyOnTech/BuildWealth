from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.schemas import ResearchResponse


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
