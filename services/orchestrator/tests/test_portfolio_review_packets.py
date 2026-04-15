from datetime import datetime, timezone

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import Holding, PortfolioReviewPacketRequest, PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_review_packets import (
    PortfolioReviewPacketStore,
    build_portfolio_review_packet,
    build_portfolio_review_packet_markdown,
)


def _snapshot(as_of: str, value: float) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime.fromisoformat(as_of),
        base_currency="USD",
        total_value_usd=value,
        total_investment_usd=0.0,
        net_performance_usd=0.0,
        net_performance_percent=0.0,
        holdings=[Holding(symbol="AAPL", name="Apple", value_usd=value)],
    )


def test_build_portfolio_review_packet_includes_expected_sections() -> None:
    holdings_payload = {
        "updated_at": "2026-04-15T12:00:00+00:00",
        "prices_updated_at": "2026-04-15T12:00:00+00:00",
        "total_portfolio_value": 110000.0,
        "total_value": 100000.0,
        "total_cash": 10000.0,
        "holdings": {
            "default:AAPL": {
                "symbol": "AAPL",
                "account": "default",
                "current_value": 60000,
                "asset_class": "US Stocks",
                "sector": "Technology",
                "region": "US",
            },
            "default:BND": {
                "symbol": "BND",
                "account": "default",
                "current_value": 40000,
                "asset_class": "US Bonds",
                "sector": "Fixed Income",
                "region": "US",
            },
        },
        "account_totals": {
            "default": {"total_value": 110000.0},
        },
        "allocation_breakdowns": {
            "asset_class": [{"key": "US Stocks", "value": 60000, "allocation_pct": 60.0}],
            "sector": [{"key": "Technology", "value": 60000, "allocation_pct": 60.0}],
            "region": [{"key": "US", "value": 100000, "allocation_pct": 100.0}],
        },
        "performance": {
            "twr_return_pct": 8.1,
            "xirr_annualized_return_pct": 7.5,
            "total_return_usd": 8100.0,
            "total_return_pct": 8.1,
            "realized_gains_usd": 1200.0,
            "unrealized_gains_usd": 6900.0,
            "income_received_usd": 400.0,
        },
        "risk_policy": {"thresholds": {"single_holding_max_pct": 25.0}},
        "risk_alerts": {
            "status": "warning",
            "breach_count": 1,
            "watch_count": 2,
            "alerts": [
                {
                    "id": "single_holding_concentration",
                    "label": "Top holding concentration",
                    "state": "breach",
                    "severity": "medium",
                    "observed": 60.0,
                    "threshold": 25.0,
                }
            ],
        },
        "lot_audit": {
            "events": [
                {
                    "event_id": "lot-1",
                    "transaction_date": "2026-04-01",
                    "action": "SELL",
                }
            ]
        },
        "corporate_actions": {
            "events": [
                {
                    "event_id": "corp-1",
                    "transaction_date": "2026-04-05",
                    "action": "STOCK_SPLIT",
                }
            ],
            "summary_by_symbol": {"AAPL": {"events": 1}},
        },
    }
    transactions = [
        {"date": "2026-04-01", "action": "BUY", "quantity": 5, "unit_price": 100, "fee": 1},
        {"date": "2026-04-02", "action": "SELL", "quantity": 2, "unit_price": 120, "fee": 1},
    ]
    snapshots = [
        _snapshot("2026-04-01T00:00:00+00:00", 100000),
        _snapshot("2026-04-15T00:00:00+00:00", 110000),
    ]
    recommendations = [
        {"id": "rec-1", "status": "proposed"},
        {"id": "rec-2", "status": "applied"},
    ]
    watchlist = [{"symbol": "NVDA"}, {"symbol": "MSFT"}]

    packet = build_portfolio_review_packet(
        generated_at="2026-04-15T12:00:00+00:00",
        period_days=30,
        holdings_payload=holdings_payload,
        transactions=transactions,
        snapshots=snapshots,
        watchlist_items=watchlist,
        recommendations=recommendations,
        plan_detail={"id": "plan-a", "title": "Plan A", "decisions": [], "artifacts": [], "top_next_actions": []},
    )
    markdown = build_portfolio_review_packet_markdown(title="Packet A", packet=packet)

    assert packet["meta"]["period_days"] == 30
    assert packet["summary"]["risk_status"] == "warning"
    assert packet["summary"]["recommendations_total"] == 2
    assert packet["activity"]["transactions"]["period_transactions_count"] == 2
    assert packet["activity"]["audit"]["corporate_actions_period_events"] == 1
    assert packet["snapshots"]["period_snapshots_count"] == 2
    assert packet["plan"]["plan_id"] == "plan-a"
    assert "## Portfolio Summary" in markdown
    assert "## Risk" in markdown
    assert "## Recommendations" in markdown


def test_portfolio_review_packet_store_write_list_read(tmp_path) -> None:
    store = PortfolioReviewPacketStore(tmp_path / "review-packets")
    packet_payload = {
        "meta": {
            "generated_at": "2026-04-15T12:00:00+00:00",
            "period_start": "2026-03-17",
            "period_end": "2026-04-15",
            "period_days": 30,
        },
        "summary": {
            "holdings_as_of": "2026-04-15T12:00:00+00:00",
            "total_portfolio_value_usd": 12345.67,
            "risk_status": "ok",
            "risk_breach_count": 0,
            "risk_watch_count": 0,
            "recommendations_open": 1,
            "recommendations_total": 3,
        },
    }

    summary = store.write(
        packet_payload=packet_payload,
        markdown="# Test Packet\n",
        title="Test Packet",
    )
    assert summary["packet_id"].startswith("portfolio-review-")
    assert summary["title"] == "Test Packet"

    listed = store.list(limit=10)
    assert len(listed) == 1
    assert listed[0]["packet_id"] == summary["packet_id"]

    detail = store.read(summary["packet_id"])
    assert detail["summary"]["packet_id"] == summary["packet_id"]
    assert detail["markdown"].startswith("# Test Packet")


def test_create_portfolio_review_packet_route_writes_plan_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class FakePortfolioStore:
        def get_holdings(self) -> dict[str, object]:
            return {
                "updated_at": "2026-04-15T12:00:00+00:00",
                "prices_updated_at": "2026-04-15T12:00:00+00:00",
                "total_portfolio_value": 1000.0,
                "total_value": 1000.0,
                "total_cash": 0.0,
                "holdings": {},
                "account_totals": {},
                "allocation_breakdowns": {},
                "performance": {},
                "risk_policy": {"thresholds": {}},
                "risk_alerts": {"status": "ok", "breach_count": 0, "watch_count": 0, "alerts": []},
                "lot_audit": {"events": []},
                "corporate_actions": {"events": [], "summary_by_symbol": {}},
            }

        def list_transactions(self, limit: int = 1000) -> list[dict[str, object]]:
            assert limit == 200
            return []

        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "AAPL"}]

    class FakeSnapshotStore:
        def recent(self, limit: int = 365) -> list[PortfolioSnapshot]:
            assert limit == 60
            return []

    class FakeRecommendationInbox:
        def list(self, **kwargs) -> list[dict[str, object]]:
            assert kwargs["limit"] == 40
            assert kwargs["plan_id"] == "plan-test"
            return [{"id": "rec-1", "status": "proposed"}]

    class FakePlanWorkspace:
        def get_plan(self, plan_id: str) -> dict[str, object]:
            assert plan_id == "plan-test"
            return {"id": "plan-test", "title": "Test Plan", "decisions": [], "artifacts": [], "top_next_actions": []}

        def write_artifact(self, *, plan_id: str, title: str, markdown: str, kind: str = "workflow") -> dict[str, object]:
            assert plan_id == "plan-test"
            assert "Portfolio Review Packet" in title
            assert kind == "portfolio_review_packet"
            assert "## Portfolio Summary" in markdown
            return {
                "id": "artifact-123",
                "file_name": "artifact-123.md",
                "title": title,
                "created_at": "2026-04-15T12:00:00+00:00",
            }

    store = PortfolioReviewPacketStore(tmp_path / "review-packets")

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "snapshot_store", FakeSnapshotStore())
    monkeypatch.setattr(main, "recommendation_inbox", FakeRecommendationInbox())
    monkeypatch.setattr(main, "plan_workspace", FakePlanWorkspace())
    monkeypatch.setattr(main, "portfolio_review_packet_store", store)

    response = main.create_portfolio_review_packet(
        PortfolioReviewPacketRequest(
            plan_id="plan-test",
            include_transactions_limit=200,
            include_snapshot_history_limit=60,
            include_recommendations_limit=40,
            period_days=30,
        )
    )

    assert response.summary.packet_id.startswith("portfolio-review-")
    assert response.summary.recommendations_total == 1
    assert response.plan_artifact is not None
    assert response.plan_artifact.id == "artifact-123"
