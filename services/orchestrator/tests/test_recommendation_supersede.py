"""Generators own their active recommendations: when the same signal now
reads differently, the open recommendation is refreshed in place instead of
holding its dedupe slot with stale numbers."""

from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.recommendation_factory import (
    generate_allocation_drift_recommendations,
)
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def _holdings_payload(equity_value: float) -> dict:
    return {
        "holdings": {
            "a:VTI": {"symbol": "VTI", "asset_class": "equity", "current_value": equity_value, "asset_type": "etf"},
            "a:BND": {"symbol": "BND", "asset_class": "fixed_income", "current_value": 10_000.0, "asset_type": "etf"},
        },
        "total_value": equity_value + 10_000.0,
        "risk_alerts": {"metrics": {"total_market_value": equity_value + 10_000.0}},
    }


_POLICY = {"target_asset_class_allocation_pct": {"equity": 70, "fixed_income": 30}}


def _run(inbox: RecommendationInbox, equity_value: float, *, dry_run: bool = False):
    return generate_allocation_drift_recommendations(
        holdings_payload=_holdings_payload(equity_value),
        investment_policy=_POLICY,
        existing_recommendations=inbox.list(status=None, include_archived=True, limit=None),
        creator=inbox,
        dry_run=dry_run,
    )


def test_changed_numbers_refresh_the_active_recommendation_in_place(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "inbox.json")

    first = _run(inbox, 90_000.0)  # equity 90% vs 70 target → overweight
    assert first.generated_count == 2
    original = next(rec for rec in inbox.list(status="proposed") if "Equity" in rec["title"])
    original_id = original["id"]
    original_created_at = original["created_at"]
    first_generated_at = original["action_payload"]["generator"]["generated_at"]

    # Same signals, different magnitude: nothing new is created, both open
    # recommendations are superseded in place.
    second = _run(inbox, 120_000.0)
    assert second.generated_count == 0
    assert second.refreshed_count == 2
    refreshed_entry = next(row for row in second.refreshed if row["recommendation_id"] == original_id)
    assert refreshed_entry["previous_title"] == original["title"]

    updated = inbox.get(original_id)
    assert updated["status"] == "proposed"
    assert updated["created_at"] == original_created_at
    assert updated["detail"] != original["detail"]
    generator = updated["action_payload"]["generator"]
    assert generator["refresh_count"] == 1
    assert generator["first_generated_at"] == first_generated_at

    # A second refresh keeps counting and keeps the first timestamp.
    third = _run(inbox, 150_000.0)
    assert third.refreshed_count == 2
    generator = inbox.get(original_id)["action_payload"]["generator"]
    assert generator["refresh_count"] == 2
    assert generator["first_generated_at"] == first_generated_at


def test_unchanged_story_still_skips(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "inbox.json")
    _run(inbox, 90_000.0)
    before = {rec["id"]: rec["updated_at"] for rec in inbox.list(status="proposed")}

    result = _run(inbox, 90_000.0)  # identical numbers
    assert result.generated_count == 0
    assert result.refreshed_count == 0
    assert result.skipped_count == 2
    assert all(row["reason"] == "active_duplicate" for row in result.skipped)
    after = {rec["id"]: rec["updated_at"] for rec in inbox.list(status="proposed")}
    assert after == before  # untouched


def test_dry_run_reports_refreshes_without_persisting(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "inbox.json")
    _run(inbox, 90_000.0)
    before = inbox.list(status="proposed")

    preview = _run(inbox, 120_000.0, dry_run=True)
    assert preview.refreshed_count == 2
    assert inbox.list(status="proposed") == before  # nothing written
