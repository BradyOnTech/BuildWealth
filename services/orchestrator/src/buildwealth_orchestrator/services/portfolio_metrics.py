from __future__ import annotations

from typing import Any


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
