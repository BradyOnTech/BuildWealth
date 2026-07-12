from __future__ import annotations

import pytest

from buildwealth_orchestrator.services.fund_composition import (
    FundCompositionService,
    load_seed_fund_compositions,
)


def _holding(symbol: str, account: str, value: float, asset_type: str, **extra) -> dict:
    return {
        "symbol": symbol,
        "account": account,
        "current_value": value,
        "asset_type": asset_type,
        **extra,
    }


@pytest.fixture()
def synthetic_payload() -> dict:
    # Two overlapping covered funds, one direct stock, one unknown fund.
    return {
        "holdings": {
            "brokerage:VTI": _holding("VTI", "brokerage", 50_000.0, "ETF"),
            "brokerage:VOO": _holding("VOO", "brokerage", 30_000.0, "etf"),
            "brokerage:AAPL": _holding(
                "AAPL",
                "brokerage",
                15_000.0,
                "STOCK",
                sector="Information Technology",
                region="US",
            ),
            "brokerage:MYSTERY": _holding("MYSTERY", "brokerage", 5_000.0, "FUND"),
        },
        "accounts": [{"id": "brokerage"}],
    }


def test_seed_loads_and_normalizes() -> None:
    compositions = load_seed_fund_compositions()

    for symbol in ("VTI", "VOO", "SPY", "IVV", "QQQ", "SCHD", "VXUS", "VEA", "VWO", "BND", "AGG", "BNDX"):
        assert symbol in compositions

    vti = compositions["VTI"]
    assert vti["as_of"] == "2025-12-31"
    assert vti["source"] == "seed_estimate"
    assert vti["asset_class"] == "equity"
    # Sector weights internally consistent: sum to ~1.0, keys normalized.
    for record in compositions.values():
        sector_total = sum(record["sector_weights"].values())
        assert 0.97 <= sector_total <= 1.03
        region_total = sum(record["region_weights"].values())
        assert 0.97 <= region_total <= 1.03
        for key in list(record["sector_weights"]) + list(record["region_weights"]):
            assert key == key.lower()
            assert " " not in key
        # Top-10 sums well under 1.0 — these are top holdings, not the fund.
        top_total = sum(h["weight"] for h in record["top_holdings"])
        assert top_total < 0.7
    # Bond funds carry bond sectors and no top holdings.
    assert compositions["BND"]["asset_class"] == "bond"
    assert compositions["BND"]["top_holdings"] == []
    assert set(compositions["BND"]["sector_weights"]) == {"government", "corporate", "securitized"}


def test_composition_for_is_case_insensitive_and_unknown_safe() -> None:
    service = FundCompositionService()
    assert service.composition_for("vti")["symbol"] == "VTI"
    assert service.composition_for("MYSTERY") is None
    assert service.composition_for("") is None


def test_coverage_math(synthetic_payload: dict) -> None:
    report = FundCompositionService().look_through_report(synthetic_payload)
    coverage = report["coverage"]

    assert report["total_portfolio_value_usd"] == 100_000.0
    assert coverage["covered_value_usd"] == 80_000.0
    assert coverage["total_fund_value_usd"] == 85_000.0
    assert coverage["covered_fund_count"] == 2
    assert coverage["unknown_funds"] == ["MYSTERY"]
    assert [f["symbol"] for f in coverage["covered_funds"]] == ["VTI", "VOO"]


def test_effective_exposure_combines_fund_and_direct(synthetic_payload: dict) -> None:
    service = FundCompositionService()
    report = service.look_through_report(synthetic_payload)
    rows = report["effective_company_exposure"]

    assert rows == sorted(rows, key=lambda r: -r["exposure_usd"])
    assert len(rows) <= 15

    aapl = next(row for row in rows if row["symbol"] == "AAPL")
    vti_weight = next(
        h["weight"] for h in service.composition_for("VTI")["top_holdings"] if h["symbol"] == "AAPL"
    )
    voo_weight = next(
        h["weight"] for h in service.composition_for("VOO")["top_holdings"] if h["symbol"] == "AAPL"
    )
    expected = 50_000.0 * vti_weight + 30_000.0 * voo_weight + 15_000.0
    assert aapl["exposure_usd"] == pytest.approx(expected, abs=0.02)
    assert aapl["exposure_pct"] == pytest.approx(expected / 100_000.0 * 100.0, abs=0.02)

    via = {entry["fund"]: entry["usd"] for entry in aapl["via"]}
    assert via["direct"] == 15_000.0
    assert via["VTI"] == pytest.approx(50_000.0 * vti_weight, abs=0.01)
    assert via["VOO"] == pytest.approx(30_000.0 * voo_weight, abs=0.01)
    # AAPL is by far the biggest effective position here.
    assert rows[0]["symbol"] == "AAPL"


def test_sector_and_region_aggregation(synthetic_payload: dict) -> None:
    service = FundCompositionService()
    report = service.look_through_report(synthetic_payload)

    sectors = {row["key"]: row for row in report["sector_exposure"]}
    vti_tech = service.composition_for("VTI")["sector_weights"]["information_technology"]
    voo_tech = service.composition_for("VOO")["sector_weights"]["information_technology"]
    expected_tech = 50_000.0 * vti_tech + 30_000.0 * voo_tech + 15_000.0
    assert sectors["information_technology"]["exposure_usd"] == pytest.approx(expected_tech, abs=0.02)

    regions = {row["key"]: row for row in report["region_exposure"]}
    # Direct AAPL region "US" merges into the funds' "united_states" bucket.
    assert regions["united_states"]["exposure_usd"] == pytest.approx(95_000.0, abs=0.02)
    assert "us" not in regions

    for rows in (report["sector_exposure"], report["region_exposure"]):
        assert rows == sorted(rows, key=lambda r: -r["exposure_usd"])


def test_vti_voo_overlap_pair(synthetic_payload: dict) -> None:
    report = FundCompositionService().look_through_report(synthetic_payload)
    pairs = report["pairwise_fund_overlap"]

    assert len(pairs) == 1
    pair = pairs[0]
    assert {pair["fund_a"], pair["fund_b"]} == {"VTI", "VOO"}
    assert pair["overlap_weight"] >= 0.15
    assert pair["basis"] == "top_10_holdings"
    assert "AAPL" in pair["shared_top_holdings"]
    assert any("top-10" in note or "top_10" in note for note in report["notes"])


def test_empty_and_malformed_payloads_are_quiet() -> None:
    service = FundCompositionService()
    for payload in ({}, {"holdings": {}}, {"holdings": None}, None):
        report = service.look_through_report(payload)  # type: ignore[arg-type]
        assert report["coverage"]["covered_fund_count"] == 0
        assert report["effective_company_exposure"] == []
        assert report["pairwise_fund_overlap"] == []
