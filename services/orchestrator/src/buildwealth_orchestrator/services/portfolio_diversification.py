"""Diversification quality — one honest number and the reasons behind it.

"Herfindahl index 0.714" means nothing to the person it's about. This service
converts the concentration math the app already does into a 0–100 score with
plain-language reasons, weighted by what actually protects a household:

  - how many independent positions the portfolio really behaves like (35%)
  - spread across asset classes (25%)
  - spread across regions (20%)
  - funds versus single stocks (20%)

Scope: INVESTABLE money only. A primary residence is housing first — you
cannot rebalance a kitchen — so personal, illiquid, custom-valued property is
excluded from the score and named separately. (Home/equity/location risk is a
real exposure, but it is a different lens, not a seat in this score. REIT
funds remain investable; the discriminator is personal illiquidity, not the
real-estate asset class.)

Known limit, stated rather than hidden: without fund look-through the score
treats each fund as one diversified unit. Three overlapping S&P 500 funds
will look more varied than they are.
"""

from typing import Any

from buildwealth_orchestrator.services.portfolio_rebalancing import is_untradable_position

_WEIGHTS = {
    "effective_positions": 0.35,
    "asset_class_spread": 0.25,
    "region_spread": 0.20,
    "vehicle_mix": 0.20,
}
_FUND_TYPES = {"etf", "fund", "mutual_fund", "index_fund"}


def build_diversification_payload(holdings: dict[str, Any]) -> dict[str, Any]:
    by_symbol: dict[str, float] = {}
    by_class: dict[str, float] = {}
    by_region: dict[str, float] = {}
    fund_value = 0.0
    total = 0.0
    excluded: dict[str, float] = {}

    for entry in holdings.values():
        if not isinstance(entry, dict):
            continue
        value = _safe(entry.get("current_value"))
        if value <= 0:
            continue
        if is_untradable_position(entry):
            symbol = str(entry.get("symbol") or "?").strip().upper()
            excluded[symbol] = excluded.get(symbol, 0.0) + value
            continue
        total += value
        symbol = str(entry.get("symbol") or "?").strip().upper()
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + value
        klass = str(entry.get("asset_class") or "unclassified").strip().lower()
        by_class[klass] = by_class.get(klass, 0.0) + value
        region = str(entry.get("region") or "unknown").strip().lower()
        by_region[region] = by_region.get(region, 0.0) + value
        if str(entry.get("asset_type") or "").strip().lower() in _FUND_TYPES:
            fund_value += value

    excluded_rows = [
        {"symbol": symbol, "value_usd": round(value, 2)}
        for symbol, value in sorted(excluded.items(), key=lambda item: -item[1])
    ]
    if total <= 0:
        return {
            "status": "no_data",
            "score": None,
            "label": None,
            "components": [],
            "reasons": [],
            "investable_value_usd": 0.0,
            "excluded": excluded_rows,
        }

    effective = _effective_positions(list(by_symbol.values()), total)
    components = [
        _component(
            "effective_positions",
            "Independent positions",
            # Six independent fund-sized positions is genuine household
            # diversification; don't demand a stock-picker's twenty.
            _scale(effective, low=1.0, full=6.0),
            f"The portfolio behaves like about {effective:.1f} independent position{'s' if effective >= 1.05 else ''}.",
        ),
        _component(
            "asset_class_spread",
            "Asset classes",
            _spread_score(by_class, total),
            _spread_sentence(by_class, total, "asset class"),
        ),
        _component(
            "region_spread",
            "Regions",
            _spread_score(by_region, total),
            _spread_sentence(by_region, total, "region"),
        ),
        _component(
            "vehicle_mix",
            "Funds vs single stocks",
            _scale(fund_value / total * 100.0, low=0.0, full=60.0),
            f"{fund_value / total * 100.0:.0f}% of investable value sits in diversified funds.",
        ),
    ]

    score = round(sum(c["score"] * _WEIGHTS[c["key"]] for c in components), 1)
    reasons = [c["sentence"] for c in sorted(components, key=lambda c: c["score"])[:3]]

    caveats = [
        "Funds are scored as single diversified units — overlapping funds are not yet examined (no holdings look-through).",
    ]
    if excluded_rows:
        excluded_total = sum(row["value_usd"] for row in excluded_rows)
        names = ", ".join(row["symbol"] for row in excluded_rows[:3])
        caveats.insert(
            0,
            f"Scored on invested money only: {names} (~${excluded_total:,.0f}) is treated as "
            "housing / personal property, not part of the investable mix.",
        )

    return {
        "status": "ready",
        "score": score,
        "label": _label(score),
        "components": components,
        "reasons": reasons,
        "investable_value_usd": round(total, 2),
        "excluded": excluded_rows,
        "caveats": caveats,
    }


def _label(score: float) -> str:
    if score >= 80:
        return "Well spread"
    if score >= 60:
        return "Reasonably spread"
    if score >= 40:
        return "Concentrated in places"
    return "Concentrated"


def _component(key: str, label: str, score: float, sentence: str) -> dict[str, Any]:
    return {"key": key, "label": label, "score": round(score, 1), "sentence": sentence}


def _effective_positions(values: list[float], total: float) -> float:
    if total <= 0 or not values:
        return 0.0
    hhi = sum((value / total) ** 2 for value in values)
    return round(1.0 / hhi, 2) if hhi > 0 else 0.0


def _scale(value: float, *, low: float, full: float) -> float:
    if value <= low:
        return 0.0
    if value >= full:
        return 100.0
    return (value - low) / (full - low) * 100.0


def _spread_score(weights: dict[str, float], total: float) -> float:
    # Effective number of categories (1 / HHI over weights): 80/20 across two
    # buckets behaves like ~1.5 categories, an even three-way like 3.
    if total <= 0 or not weights:
        return 0.0
    hhi = sum((value / total) ** 2 for value in weights.values())
    effective = (1.0 / hhi) if hhi > 0 else 0.0
    return _scale(effective, low=1.0, full=3.0)


def _spread_sentence(weights: dict[str, float], total: float, noun: str) -> str:
    if not weights or total <= 0:
        return f"No {noun} information recorded."
    top_key, top_value = max(weights.items(), key=lambda item: item[1])
    top_pct = top_value / total * 100.0
    meaningful = sum(1 for value in weights.values() if value / total >= 0.05)
    name = top_key.replace("_", " ")
    plural = "" if meaningful == 1 else ("es" if noun.endswith("s") else "s")
    return f"{meaningful} meaningful {noun}{plural} — {name} carries {top_pct:.0f}% of value."


def _safe(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result else 0.0
