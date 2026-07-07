from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.recommendation_factory import (
    generate_fund_overlap_recommendations,
)
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def _holdings_payload(symbols: dict[str, float]) -> dict:
    return {
        "holdings": {
            f"a:{symbol}": {
                "symbol": symbol,
                "asset_type": "etf",
                "asset_class": "equity",
                "current_value": value,
            }
            for symbol, value in symbols.items()
        },
        "updated_at": "2026-07-07T00:00:00+00:00",
    }


def test_same_index_duplicates_become_a_consolidation_review() -> None:
    result = generate_fund_overlap_recommendations(
        holdings_payload=_holdings_payload({"VOO": 30_000.0, "SPY": 20_000.0, "BND": 10_000.0}),
        existing_recommendations=[],
        dry_run=True,
    )
    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["title"] == "Two funds, one index: VOO and SPY"
    assert candidate["source"] == "generator:fund_overlap"
    # The cheaper copy is named with the honest fee arithmetic:
    # SPY at 9bps vs VOO at 3bps on $20k → ~$12/yr excess.
    evidence = candidate["action_payload"]["evidence"]
    assert evidence["cheapest_symbol"] == "VOO"
    assert evidence["annual_excess_fee_usd"] == 12.0
    assert "VOO is the cheapest" in candidate["detail"]
    # Never-trading framing: consolidation is a review, not an order.
    assert "tax consequences" in candidate["detail"]
    assert candidate["action_payload"]["quality"]["actionability"] == "review_only"
    assert candidate["action_payload"]["generator"]["dedupe_key"] == "fund_overlap:sp500"


def test_containment_never_files_recommendations() -> None:
    # VOO inside VTI is a panel insight, not a nag — tilts can be deliberate.
    result = generate_fund_overlap_recommendations(
        holdings_payload=_holdings_payload({"VTI": 50_000.0, "VOO": 20_000.0}),
        existing_recommendations=[],
        dry_run=True,
    )
    assert result.generated_count == 0


def test_home_and_unknown_symbols_are_ignored() -> None:
    payload = _holdings_payload({"VOO": 30_000.0, "SPY": 20_000.0})
    payload["holdings"]["a:HOME"] = {
        "symbol": "MY_HOME",
        "asset_type": "property",
        "asset_class": "real_estate",
        "current_value": 400_000.0,
    }
    payload["holdings"]["a:AAPL"] = {
        "symbol": "AAPL",
        "asset_type": "equity",
        "asset_class": "equity",
        "current_value": 5_000.0,
    }
    result = generate_fund_overlap_recommendations(
        holdings_payload=payload,
        existing_recommendations=[],
        dry_run=True,
    )
    assert result.generated_count == 1  # only the VOO/SPY pair


def test_overlap_recommendations_supersede_in_place(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "inbox.json")

    def run(spy_value: float):
        return generate_fund_overlap_recommendations(
            holdings_payload=_holdings_payload({"VOO": 30_000.0, "SPY": spy_value}),
            existing_recommendations=inbox.list(status=None, include_archived=True, limit=None),
            creator=inbox,
            dry_run=False,
        )

    first = run(20_000.0)
    assert first.generated_count == 1
    rec_id = first.created[0]["id"]

    # Same story → skip; changed dollars → superseded in place.
    unchanged = run(20_000.0)
    assert unchanged.generated_count == 0 and unchanged.refreshed_count == 0

    changed = run(40_000.0)
    assert changed.refreshed_count == 1
    updated = inbox.get(rec_id)
    assert "$70,000 combined" in updated["detail"]
    assert updated["action_payload"]["generator"]["refresh_count"] == 1
