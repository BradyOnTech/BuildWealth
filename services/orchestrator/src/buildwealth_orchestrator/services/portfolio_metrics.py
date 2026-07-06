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
    """Concentration over INVESTABLE money, aggregated per symbol.

    Same scoping as the risk alerts and diversification score: a primary
    residence is housing, not a position a person can trim — and a fund held
    in three accounts is one concentration, not three.
    """
    from buildwealth_orchestrator.services.portfolio_rebalancing import is_untradable_position

    if not holdings:
        return _empty_concentration_metrics()

    value_by_symbol: dict[str, float] = {}
    name_by_symbol: dict[str, str | None] = {}
    for item in holdings:
        if is_untradable_position(dict(item)):
            continue
        value_usd = _to_float(item.get("value_usd"))
        if value_usd <= 0:
            continue
        symbol = _to_optional_text(item.get("symbol")) or "UNKNOWN"
        value_by_symbol[symbol] = value_by_symbol.get(symbol, 0.0) + value_usd
        name_by_symbol.setdefault(symbol, _to_optional_text(item.get("name")))

    total_value = sum(value_by_symbol.values())
    if total_value == 0:
        return _empty_concentration_metrics()

    normalized: list[ConcentrationPosition] = []
    for symbol, value_usd in sorted(value_by_symbol.items(), key=lambda pair: pair[1], reverse=True):
        normalized.append(
            {
                "symbol": symbol,
                "name": name_by_symbol.get(symbol),
                "weight": round(value_usd / total_value, 4),
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
