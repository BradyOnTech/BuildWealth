"""Diversification quality: honest score, plain reasons."""

from buildwealth_orchestrator.services.portfolio_diversification import (
    build_diversification_payload,
)


def _entry(symbol, value, asset_class="equity", region="united states", asset_type="etf"):
    return {
        "symbol": symbol, "current_value": value,
        "asset_class": asset_class, "region": region, "asset_type": asset_type,
    }


def test_concentrated_single_asset_scores_low_with_plain_reasons() -> None:
    payload = build_diversification_payload({
        "a:HOME": _entry("HOME", 420_000, asset_class="real_estate", asset_type="property"),
        "a:VTI": _entry("VTI", 40_000),
        "a:CASH": _entry("CASH", 40_000, asset_class="cash", asset_type="cash"),
    })

    assert payload["status"] == "ready"
    assert payload["score"] < 40
    assert payload["label"] == "Concentrated"
    sentences = " ".join(payload["reasons"])
    assert "behaves like about" in sentences
    assert any("look-through" in caveat for caveat in payload["caveats"])


def test_spread_fund_portfolio_scores_high() -> None:
    payload = build_diversification_payload({
        "a:VTI": _entry("VTI", 30_000),
        "a:VXUS": _entry("VXUS", 20_000, region="global ex-us"),
        "a:BND": _entry("BND", 20_000, asset_class="fixed_income"),
        "a:VNQ": _entry("VNQ", 10_000, asset_class="real_estate"),
        "a:SGOV": _entry("SGOV", 10_000, asset_class="cash"),
        "a:SCHD": _entry("SCHD", 10_000),
    })

    assert payload["score"] >= 70
    assert payload["label"] in ("Well spread", "Reasonably spread")
    by_key = {c["key"]: c for c in payload["components"]}
    assert by_key["vehicle_mix"]["score"] == 100.0
    assert by_key["region_spread"]["score"] > 0


def test_empty_portfolio_is_no_data() -> None:
    payload = build_diversification_payload({})
    assert payload["status"] == "no_data"
    assert payload["score"] is None
