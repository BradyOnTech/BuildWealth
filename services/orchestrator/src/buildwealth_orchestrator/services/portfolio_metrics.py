from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict


class ConcentrationPosition(TypedDict):
    symbol: str | None
    name: str | None
    weight: float
    value_usd: float


class ConcentrationMetrics(TypedDict):
    top_positions: list[ConcentrationPosition]
    herfindahl_index: float
    effective_number_of_positions: float


def _empty_concentration_metrics() -> ConcentrationMetrics:
    return {
        "top_positions": [],
        "herfindahl_index": 0.0,
        "effective_number_of_positions": 0.0,
    }


def _to_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0
    return 0.0


def _to_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def concentration_metrics(holdings: Sequence[Mapping[str, object]]) -> ConcentrationMetrics:
    if not holdings:
        return _empty_concentration_metrics()

    ranked = sorted(holdings, key=lambda item: _to_float(item.get("value_usd")), reverse=True)
    total_value = sum(_to_float(item.get("value_usd")) for item in ranked)

    if total_value == 0:
        return _empty_concentration_metrics()

    normalized: list[ConcentrationPosition] = []
    for item in ranked:
        value_usd = _to_float(item.get("value_usd"))
        weight = value_usd / total_value
        normalized.append(
            {
                "symbol": _to_optional_text(item.get("symbol")),
                "name": _to_optional_text(item.get("name")),
                "weight": round(weight, 4),
                "value_usd": round(value_usd, 2),
            }
        )

    herfindahl = sum(item["weight"] ** 2 for item in normalized)
    effective_positions = (1 / herfindahl) if herfindahl else 0.0

    return {
        "top_positions": normalized[:10],
        "herfindahl_index": round(herfindahl, 4),
        "effective_number_of_positions": round(effective_positions, 2),
    }
