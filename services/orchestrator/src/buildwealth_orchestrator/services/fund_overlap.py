"""Fund overlap — the look-through the diversification score was missing.

Three overlapping S&P 500 funds are not three positions, they are one bet
bought three times. Real holdings look-through needs constituent data from a
provider; what a local-first app can know honestly is what each fund TRACKS
(seeded per symbol) and how those targets relate:

- same `tracks` key           → near-duplicates (VOO / IVV / SPY)
- containment between keys    → one inside the other (VOO inside VTI)

Curated knowledge, so it covers the funds a normal household actually holds
and says nothing about funds it doesn't know.
"""

from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.asset_metadata_seed import load_seed_asset_metadata

# child → parent: everything the child tracks is (almost entirely) inside the
# parent. Transitive: nasdaq100 → sp500 → us_total_market.
_CONTAINMENT: dict[str, str] = {
    "sp500": "us_total_market",
    "sp500_equal_weight": "sp500",
    "nasdaq100": "sp500",
    "us_small_cap": "us_total_market",
    "us_large_value": "us_total_market",
    "us_large_growth": "us_total_market",
    "us_dividend_schwab": "us_total_market",
    "us_dividend_high_yield": "us_total_market",
    "us_dividend_growth": "us_total_market",
    "us_reit": "us_total_market",
    "intl_developed": "intl_total",
    "emerging_markets": "intl_total",
    "us_agg_bond": "us_total_bond",
    "short_treasury": "us_total_bond",
    "intermediate_treasury": "us_total_bond",
    "long_treasury": "us_total_bond",
    "us_tips": "us_total_bond",
}

_TRACKS_LABELS: dict[str, str] = {
    "us_total_market": "the total US market",
    "sp500": "the S&P 500",
    "sp500_equal_weight": "the S&P 500 (equal weight)",
    "nasdaq100": "the Nasdaq-100",
    "us_small_cap": "US small caps",
    "us_large_value": "US large-cap value",
    "us_large_growth": "US large-cap growth",
    "us_dividend_schwab": "US dividend stocks",
    "us_dividend_high_yield": "US high-dividend stocks",
    "us_dividend_growth": "US dividend growers",
    "intl_total": "total international stocks",
    "intl_developed": "international developed markets",
    "emerging_markets": "emerging markets",
    "us_agg_bond": "the US aggregate bond market",
    "us_total_bond": "the total US bond market",
    "intl_bond": "international bonds",
    "us_tips": "US inflation-protected bonds",
    "short_treasury": "short-term Treasuries",
    "tbill_cash": "Treasury bills",
    "ultra_short_bond": "ultra-short bonds",
    "intermediate_treasury": "intermediate Treasuries",
    "long_treasury": "long Treasuries",
    "us_reit": "US REITs",
    "us_real_estate": "US real estate",
    "gold": "gold",
    "silver": "silver",
    "broad_commodities": "broad commodities",
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
}


def tracks_for_symbol(symbol: str) -> str:
    record = load_seed_asset_metadata().get(str(symbol or "").strip().upper()) or {}
    return str(record.get("tracks") or "")


def tracks_label(key: str) -> str:
    return _TRACKS_LABELS.get(key, key.replace("_", " "))


def _contains(parent: str, child: str) -> bool:
    seen = set()
    current = child
    while current in _CONTAINMENT and current not in seen:
        seen.add(current)
        current = _CONTAINMENT[current]
        if current == parent:
            return True
    return False


def build_overlap_findings(value_by_symbol: dict[str, float]) -> list[dict[str, Any]]:
    """Overlap findings for a set of held fund positions.

    Returns duplicate groups first (same tracks key), then containment pairs,
    each with the symbols involved, combined value, and a plain sentence.
    """
    tracked: dict[str, list[tuple[str, float]]] = {}
    for symbol, value in value_by_symbol.items():
        if value <= 0:
            continue
        key = tracks_for_symbol(symbol)
        if key:
            tracked.setdefault(key, []).append((str(symbol).upper(), float(value)))

    findings: list[dict[str, Any]] = []

    for key, positions in sorted(tracked.items(), key=lambda item: -sum(v for _, v in item[1])):
        if len(positions) < 2:
            continue
        symbols = [symbol for symbol, _ in sorted(positions, key=lambda pair: -pair[1])]
        combined = round(sum(value for _, value in positions), 2)
        findings.append(
            {
                "kind": "duplicate",
                "tracks": key,
                "symbols": symbols,
                "combined_value_usd": combined,
                "sentence": (
                    f"{' and '.join(symbols)} all track {tracks_label(key)} — "
                    f"effectively one position (${combined:,.0f} combined)."
                    if len(symbols) > 2
                    else f"{symbols[0]} and {symbols[1]} track {tracks_label(key)} — "
                    f"effectively one position (${combined:,.0f} combined)."
                ),
            }
        )

    keys = list(tracked.keys())
    for child in keys:
        for parent in keys:
            if child == parent or not _contains(parent, child):
                continue
            child_symbols = [s for s, _ in sorted(tracked[child], key=lambda pair: -pair[1])]
            parent_symbols = [s for s, _ in sorted(tracked[parent], key=lambda pair: -pair[1])]
            child_value = round(sum(v for _, v in tracked[child]), 2)
            findings.append(
                {
                    "kind": "contained",
                    "tracks": child,
                    "within": parent,
                    "symbols": child_symbols + parent_symbols,
                    "combined_value_usd": child_value,
                    "sentence": (
                        f"{', '.join(child_symbols)} ({tracks_label(child)}) already lives inside "
                        f"{', '.join(parent_symbols)} ({tracks_label(parent)}) — "
                        f"${child_value:,.0f} of doubled-up exposure."
                    ),
                }
            )

    return findings


def merge_duplicate_positions(value_by_symbol: dict[str, float]) -> dict[str, float]:
    """Collapse same-tracks funds into one position for concentration math.

    Two funds on the same index ARE one holding; counting them separately
    flatters the diversification score. Containment is NOT merged — VTI and
    VOO are correlated but not identical, and pretending otherwise would
    overcorrect. Unknown symbols pass through untouched.
    """
    merged: dict[str, float] = {}
    seen_tracks: dict[str, str] = {}
    for symbol, value in value_by_symbol.items():
        key = tracks_for_symbol(symbol)
        if not key:
            merged[symbol] = merged.get(symbol, 0.0) + value
            continue
        if key in seen_tracks:
            merged[seen_tracks[key]] += value
        else:
            seen_tracks[key] = symbol
            merged[symbol] = merged.get(symbol, 0.0) + value
    return merged
