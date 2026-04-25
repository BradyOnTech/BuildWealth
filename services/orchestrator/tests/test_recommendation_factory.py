from datetime import datetime, timezone
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.portfolio_risk_alerts import calculate_portfolio_risk_alerts
from buildwealth_orchestrator.services.recommendation_factory import generate_portfolio_risk_recommendations
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def _holdings_payload() -> dict[str, object]:
    holdings = {
        "default:AAPL": {
            "symbol": "AAPL",
            "account": "default",
            "current_value": 70_000.0,
            "asset_class": "US Stocks",
            "sector": "Technology",
            "region": "US",
        },
        "default:MSFT": {
            "symbol": "MSFT",
            "account": "default",
            "current_value": 20_000.0,
            "asset_class": "US Stocks",
            "sector": "Technology",
            "region": "US",
        },
        "default:BND": {
            "symbol": "BND",
            "account": "default",
            "current_value": 10_000.0,
            "asset_class": "US Bonds",
            "sector": "Fixed Income",
            "region": "US",
        },
    }
    risk_alerts = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals={"default": {"total_value": 100_000.0}},
        allocation_breakdowns=None,
        thresholds={
            "single_holding_max_pct": 25.0,
            "top3_holdings_max_pct": 60.0,
            "account_max_pct": 100.0,
            "asset_class_max_pct": 82.0,
            "sector_max_pct": 35.0,
            "region_max_pct": 69.0,
            "hhi_max": 0.2,
            "effective_positions_min": 5.0,
        },
        generated_at="2026-04-25T12:00:00+00:00",
    )
    return {
        "updated_at": "2026-04-25T12:00:00+00:00",
        "total_value": 100_000.0,
        "holdings": holdings,
        "risk_alerts": risk_alerts,
    }


def test_portfolio_risk_factory_dry_run_generates_specific_candidates() -> None:
    result = generate_portfolio_risk_recommendations(
        holdings_payload=_holdings_payload(),
        existing_recommendations=[],
        dry_run=True,
        limit=3,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 3
    assert result.created == []
    assert result.candidates[0]["priority"] == "high"
    assert result.candidates[0]["source"] == "generator:portfolio_risk"
    assert "concentration" in result.candidates[0]["title"].lower()
    assert "$" in result.candidates[0]["detail"]
    payload = result.candidates[0]["action_payload"]
    assert payload["generator"]["dedupe_key"].startswith("portfolio_risk_alert:")
    assert payload["evidence"]["data_keys"] == ["portfolio.holdings", "portfolio.risk_alerts"]
    assert payload["suggested_action"]["estimated_rebalance_usd"] is not None


def test_portfolio_risk_factory_apply_creates_rows_and_skips_duplicates(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    first = generate_portfolio_risk_recommendations(
        holdings_payload=_holdings_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=50,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert first.generated_count >= 2
    assert len(first.created) == first.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == first.generated_count

    second = generate_portfolio_risk_recommendations(
        holdings_payload=_holdings_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=50,
        now=datetime(2026, 4, 25, 12, 35, tzinfo=timezone.utc),
    )

    assert second.generated_count == 0
    assert second.created == []
    assert second.skipped_count >= first.generated_count
    assert {item["reason"] for item in second.skipped} == {"active_duplicate"}
    assert len(inbox.list(limit=None, status="proposed")) == first.generated_count


class _FakePortfolioStore:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def get_holdings(self) -> dict[str, object]:
        return self.payload


def test_generate_portfolio_risk_route_supports_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_holdings_payload()))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.generate_portfolio_risk_recommendation_candidates(
        main.PortfolioRiskRecommendationGenerateRequest(dry_run=True, limit=2),
    )

    assert dry_run.dry_run is True
    assert dry_run.generated_count == 2
    assert dry_run.created == []
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.generate_portfolio_risk_recommendation_candidates(
        main.PortfolioRiskRecommendationGenerateRequest(dry_run=False, limit=50),
    )

    assert applied.dry_run is False
    assert applied.generated_count >= 2
    assert len(applied.created) == applied.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count

    duplicate = main.generate_portfolio_risk_recommendation_candidates(
        main.PortfolioRiskRecommendationGenerateRequest(dry_run=False, limit=50),
    )

    assert duplicate.generated_count == 0
    assert duplicate.skipped_count >= applied.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count
