from __future__ import annotations

from datetime import date

from buildwealth_orchestrator.services.tax_strategy import (
    build_roth_conversion_ladder,
    build_tax_loss_harvest_report,
)

TODAY = date(2026, 7, 12)


def _holdings_payload() -> dict:
    return {
        "accounts": [
            {"id": "brokerage", "type": "taxable"},
            {"id": "ira", "type": "retirement"},
        ],
        "holdings": {
            "brokerage:LOSER": {
                "symbol": "LOSER",
                "account": "brokerage",
                "current_price": 50.0,
                "lots": [
                    # Long-term loss: bought years ago at 100.
                    {"lot_id": "a", "acquired_date": "2023-01-10", "remaining_quantity": 10.0, "unit_cost": 100.0},
                    # Short-term loss: bought 2 months ago at 80.
                    {"lot_id": "b", "acquired_date": "2026-05-10", "remaining_quantity": 5.0, "unit_cost": 80.0},
                    # Tiny loss under the floor: ignored.
                    {"lot_id": "c", "acquired_date": "2026-05-10", "remaining_quantity": 1.0, "unit_cost": 51.0},
                ],
            },
            "brokerage:WINNER": {
                "symbol": "WINNER",
                "account": "brokerage",
                "current_price": 200.0,
                "lots": [
                    {"lot_id": "d", "acquired_date": "2024-01-01", "remaining_quantity": 3.0, "unit_cost": 100.0},
                ],
            },
            "ira:LOSER": {
                "symbol": "LOSER",
                "account": "ira",
                "current_price": 50.0,
                "lots": [
                    {"lot_id": "e", "acquired_date": "2023-01-10", "remaining_quantity": 100.0, "unit_cost": 100.0},
                ],
            },
        },
    }


def _profile() -> dict:
    return {"tax_profile": {"marginal_tax_rate": 0.24, "state_tax_rate": 0.05, "filing_status": "single"}}


def test_tlh_finds_taxable_losses_and_skips_retirement_and_winners() -> None:
    report = build_tax_loss_harvest_report(
        holdings_payload=_holdings_payload(),
        transactions=[],
        profile_payload=_profile(),
        now=TODAY,
    )
    assert report["candidate_count"] == 2
    symbols = {(c["symbol"], c["lot_id"]) for c in report["candidates"]}
    assert symbols == {("LOSER", "a"), ("LOSER", "b")}
    # Largest loss first.
    assert report["candidates"][0]["lot_id"] == "a"
    assert report["total_harvestable_loss_usd"] == -650.0


def test_tlh_terms_and_benefit_rates() -> None:
    report = build_tax_loss_harvest_report(
        holdings_payload=_holdings_payload(),
        transactions=[],
        profile_payload=_profile(),
        now=TODAY,
    )
    by_lot = {c["lot_id"]: c for c in report["candidates"]}
    long_term = by_lot["a"]
    short_term = by_lot["b"]
    assert long_term["term"] == "long"
    assert short_term["term"] == "short"
    # Long: 500 loss * (15% + 5%); Short: 150 loss * (24% + 5%).
    assert long_term["estimated_tax_benefit_usd"] == 100.0
    assert short_term["estimated_tax_benefit_usd"] == 43.5


def test_tlh_flags_wash_sale_risk_across_accounts() -> None:
    transactions = [
        {"symbol": "LOSER", "action": "BUY", "date": "2026-07-01", "account": "ira"},
        {"symbol": "WINNER", "action": "BUY", "date": "2026-01-01", "account": "brokerage"},
    ]
    report = build_tax_loss_harvest_report(
        holdings_payload=_holdings_payload(),
        transactions=transactions,
        profile_payload=_profile(),
        now=TODAY,
    )
    assert all(c["wash_sale_risk"] for c in report["candidates"])
    assert all("2026-07-01" in c["recent_buy_dates"] for c in report["candidates"])

    stale = build_tax_loss_harvest_report(
        holdings_payload=_holdings_payload(),
        transactions=[{"symbol": "LOSER", "action": "BUY", "date": "2026-05-01"}],
        profile_payload=_profile(),
        now=TODAY,
    )
    assert not any(c["wash_sale_risk"] for c in stale["candidates"])


def test_roth_ladder_fills_bracket_and_drains_balance() -> None:
    result = build_roth_conversion_ladder(
        traditional_balance_usd=400_000,
        filing_status="married_filing_jointly",
        annual_ordinary_income_usd=90_000,
        target_bracket_rate=0.22,
        years=8,
        annual_growth_rate=0.05,
        state_tax_rate=0.07,
        age=58,
        tax_year=2026,
    )
    schedule = result["schedule"]
    # MFJ 2026: 22% bracket tops at 211,400 taxable; income taxable is
    # 90,000 - 32,200 = 57,800 -> headroom 153,600.
    assert schedule[0]["conversion_usd"] == 153_600.0
    assert schedule[0]["estimated_tax_usd"] > 0
    assert 0.10 < schedule[0]["effective_rate_on_conversion"] < 0.35
    assert result["remaining_balance_usd"] == 0.0
    assert result["total_converted_usd"] > 400_000  # growth converted too
    assert result["average_rate_on_conversions"] is not None


def test_roth_ladder_no_headroom_year_is_explicit() -> None:
    result = build_roth_conversion_ladder(
        traditional_balance_usd=100_000,
        filing_status="single",
        annual_ordinary_income_usd=500_000,  # already above the 24% ceiling
        target_bracket_rate=0.24,
        years=2,
        annual_growth_rate=0.0,
        tax_year=2026,
    )
    assert all(row["conversion_usd"] == 0.0 for row in result["schedule"])
    assert result["total_converted_usd"] == 0.0
    assert result["remaining_balance_usd"] == 100_000.0


def test_roth_ladder_defaults_unknown_bracket_to_24() -> None:
    result = build_roth_conversion_ladder(
        traditional_balance_usd=50_000,
        filing_status="single",
        annual_ordinary_income_usd=60_000,
        target_bracket_rate=0.19,  # not a real bracket
        years=3,
        tax_year=2026,
    )
    assert result["inputs"]["target_bracket_rate"] == 0.24
