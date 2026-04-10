from datetime import date
from pathlib import Path

import pytest

from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.snapshot_backfill import backfill_snapshot_history
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore


class _FakeResearch:
    def __init__(self, *, history: dict[str, list[dict]], quotes: dict[str, dict] | None = None):
        self.history = history
        self.quotes = quotes or {}

    def get_price_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict]:
        _ = (period, interval)
        return self.history.get(symbol, [])

    def get_quote(self, symbol: str) -> dict:
        return self.quotes.get(symbol, {})


@pytest.fixture
def stores(tmp_path: Path) -> tuple[PortfolioStore, SnapshotStore]:
    return PortfolioStore(tmp_path / "portfolio"), SnapshotStore(tmp_path / "snapshots")


def test_backfill_snapshot_history_writes_daily_snapshots(stores: tuple[PortfolioStore, SnapshotStore]):
    portfolio_store, snapshot_store = stores
    portfolio_store.add_transaction(
        date="2026-04-08",
        symbol="AAPL",
        action="BUY",
        quantity=10,
        unit_price=100,
    )

    research = _FakeResearch(
        history={
            "AAPL": [
                {"date": "2026-04-08", "close": 100},
                {"date": "2026-04-09", "close": 110},
            ]
        }
    )

    result = backfill_snapshot_history(
        portfolio_store=portfolio_store,
        snapshot_store=snapshot_store,
        research=research,  # type: ignore[arg-type]
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
    )
    assert result["days_written"] == 2
    snapshots = snapshot_store.recent(limit=2)
    assert snapshots[0].total_value_usd == pytest.approx(1100.0, abs=0.01)
    assert snapshots[1].total_value_usd == pytest.approx(1000.0, abs=0.01)


def test_backfill_snapshot_history_applies_historical_fx_for_investment_and_value(
    stores: tuple[PortfolioStore, SnapshotStore],
):
    portfolio_store, snapshot_store = stores
    euro_account = portfolio_store.add_account("Euro Brokerage", currency="EUR")
    portfolio_store.set_fx_rate(currency="EUR", rate=1.1)
    portfolio_store.set_fx_rate_history(
        currency="EUR",
        rates_by_date={
            "2026-04-08": 1.2,
            "2026-04-09": 1.1,
        },
    )
    portfolio_store.add_transaction(
        date="2026-04-08",
        symbol="SAP",
        action="BUY",
        quantity=10,
        unit_price=100,
        account=euro_account["id"],
        currency="EUR",
    )

    research = _FakeResearch(
        history={
            "SAP": [
                {"date": "2026-04-08", "close": 100},
                {"date": "2026-04-09", "close": 100},
            ]
        }
    )

    backfill_snapshot_history(
        portfolio_store=portfolio_store,
        snapshot_store=snapshot_store,
        research=research,  # type: ignore[arg-type]
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
    )
    snapshots = snapshot_store.recent(limit=2)
    latest = snapshots[0]
    first = snapshots[1]
    assert first.total_investment_usd == pytest.approx(1200.0, abs=0.01)
    assert latest.total_value_usd == pytest.approx(1100.0, abs=0.01)


def test_backfill_snapshot_history_honors_overwrite_false(stores: tuple[PortfolioStore, SnapshotStore]):
    portfolio_store, snapshot_store = stores
    portfolio_store.add_transaction(
        date="2026-04-08",
        symbol="AAPL",
        action="BUY",
        quantity=10,
        unit_price=100,
    )

    research = _FakeResearch(
        history={
            "AAPL": [
                {"date": "2026-04-08", "close": 100},
                {"date": "2026-04-09", "close": 101},
            ]
        }
    )

    first = backfill_snapshot_history(
        portfolio_store=portfolio_store,
        snapshot_store=snapshot_store,
        research=research,  # type: ignore[arg-type]
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
        overwrite=True,
    )
    second = backfill_snapshot_history(
        portfolio_store=portfolio_store,
        snapshot_store=snapshot_store,
        research=research,  # type: ignore[arg-type]
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
        overwrite=False,
    )
    assert first["days_written"] == 2
    assert second["days_written"] == 0
    assert second["days_skipped"] == 2
