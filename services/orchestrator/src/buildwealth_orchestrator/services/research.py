from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.schemas import ResearchResponse


class OpenBBResearchService:
    def __init__(self, provider: str):
        self.provider = provider

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

    def options_chain(self, symbol: str) -> ResearchResponse:
        try:
            from openbb import obb  # type: ignore
        except Exception as exc:  # pragma: no cover - import-path dependent
            return ResearchResponse(
                symbol=symbol,
                provider=self.provider,
                available=False,
                message=(
                    "OpenBB is unavailable in this runtime. Install with `pip install .[openbb]` "
                    f"in services/orchestrator. Details: {exc}"
                ),
                records=[],
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
            return ResearchResponse(
                symbol=symbol,
                provider=self.provider,
                available=False,
                message=f"OpenBB request failed: {exc}",
                records=[],
            )


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
