from __future__ import annotations

from buildwealth_orchestrator.services.fund_overlap import (
    build_overlap_findings,
    merge_duplicate_positions,
    tracks_for_symbol,
)
from buildwealth_orchestrator.services.portfolio_diversification import build_diversification_payload


def test_tracks_come_from_the_seed() -> None:
    assert tracks_for_symbol("VTI") == "us_total_market"
    assert tracks_for_symbol("vti") == "us_total_market"
    assert tracks_for_symbol("SPY") == "sp500"
    assert tracks_for_symbol("AAPL") == ""  # stocks track nothing
    assert tracks_for_symbol("UNKNOWN") == ""


def test_same_index_funds_are_flagged_as_duplicates() -> None:
    findings = build_overlap_findings({"VOO": 30_000.0, "SPY": 20_000.0, "BND": 10_000.0})
    duplicates = [f for f in findings if f["kind"] == "duplicate"]
    assert len(duplicates) == 1
    assert duplicates[0]["symbols"] == ["VOO", "SPY"]
    assert duplicates[0]["combined_value_usd"] == 50_000.0
    assert "track the S&P 500" in duplicates[0]["sentence"]
    assert "effectively one position" in duplicates[0]["sentence"]


def test_containment_is_flagged_transitively() -> None:
    # QQQ (Nasdaq-100) is inside the S&P 500, which is inside the total
    # market — holding QQQ next to VTI is doubled-up exposure.
    findings = build_overlap_findings({"QQQ": 15_000.0, "VTI": 60_000.0})
    contained = [f for f in findings if f["kind"] == "contained"]
    assert len(contained) == 1
    assert contained[0]["tracks"] == "nasdaq100"
    assert contained[0]["within"] == "us_total_market"
    assert "already lives inside" in contained[0]["sentence"]


def test_unrelated_funds_produce_no_findings() -> None:
    assert build_overlap_findings({"VTI": 50_000.0, "VXUS": 20_000.0, "BND": 10_000.0}) == []


def test_merge_collapses_duplicates_but_not_containment() -> None:
    merged = merge_duplicate_positions({"VOO": 30_000.0, "SPY": 20_000.0, "VTI": 50_000.0, "AAPL": 5_000.0})
    # VOO+SPY collapse into whichever came first; VTI stays separate
    # (correlated is not identical), stocks pass through.
    assert merged["VOO"] == 50_000.0
    assert "SPY" not in merged
    assert merged["VTI"] == 50_000.0
    assert merged["AAPL"] == 5_000.0


def test_diversification_score_stops_flattering_duplicate_funds() -> None:
    def holdings(symbols: dict[str, float]) -> dict:
        return {
            f"a:{symbol}": {
                "symbol": symbol,
                "asset_type": "etf",
                "asset_class": "equity",
                "region": "US",
                "current_value": value,
            }
            for symbol, value in symbols.items()
        }

    # Three same-index funds vs one fund of the same total value: with the
    # merge, both portfolios must score the same effective positions.
    triple = build_diversification_payload(holdings({"VOO": 20_000.0, "IVV": 20_000.0, "SPY": 20_000.0, "BND": 30_000.0}))
    single = build_diversification_payload(holdings({"VOO": 60_000.0, "BND": 30_000.0}))
    triple_effective = next(c for c in triple["components"] if c["key"] == "effective_positions")
    single_effective = next(c for c in single["components"] if c["key"] == "effective_positions")
    assert triple_effective["score"] == single_effective["score"]

    # And the overlap is named in the payload.
    duplicate = [f for f in triple["overlap"] if f["kind"] == "duplicate"]
    assert duplicate and duplicate[0]["combined_value_usd"] == 60_000.0
