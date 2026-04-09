import json
from pathlib import Path

import pytest

from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.price_updater import build_snapshot_from_holdings


@pytest.fixture
def store(tmp_path):
    return PortfolioStore(tmp_path / "portfolio")


class TestTransactions:
    def test_add_transaction(self, store):
        txn = store.add_transaction(
            date="2026-01-15", symbol="AAPL", action="BUY",
            quantity=10, unit_price=150.00,
        )
        assert txn["symbol"] == "AAPL"
        assert txn["quantity"] == 10
        assert txn["id"]

    def test_list_transactions(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-20", symbol="MSFT", action="BUY", quantity=5, unit_price=400)
        txns = store.list_transactions()
        assert len(txns) == 2
        # Most recent first
        assert txns[0]["symbol"] == "MSFT"

    def test_delete_transaction(self, store):
        txn = store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        assert store.delete_transaction(txn["id"]) is True
        assert len(store.list_transactions()) == 0

    def test_delete_nonexistent(self, store):
        assert store.delete_transaction("fake-id") is False

    def test_bulk_add(self, store):
        items = [
            {"date": "2026-01-15", "symbol": "AAPL", "action": "BUY", "quantity": 10, "unit_price": 150},
            {"date": "2026-01-16", "symbol": "MSFT", "action": "BUY", "quantity": 5, "unit_price": 400},
        ]
        count = store.add_transactions_bulk(items)
        assert count == 2
        assert len(store.list_transactions()) == 2

    def test_symbol_normalized_uppercase(self, store):
        txn = store.add_transaction(date="2026-01-15", symbol="aapl", action="buy", quantity=10, unit_price=150)
        assert txn["symbol"] == "AAPL"
        assert txn["action"] == "BUY"


class TestHoldings:
    def test_buy_creates_holding(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        holdings = store.get_holdings()
        assert "AAPL" in holdings["holdings"]
        assert holdings["holdings"]["AAPL"]["quantity"] == 10
        assert holdings["holdings"]["AAPL"]["cost_basis"] == 1500

    def test_multiple_buys_accumulate(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-20", symbol="AAPL", action="BUY", quantity=5, unit_price=160)
        h = store.get_holdings()["holdings"]["AAPL"]
        assert h["quantity"] == 15
        assert h["cost_basis"] == 2300

    def test_sell_reduces_holding(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="SELL", quantity=4, unit_price=170)
        h = store.get_holdings()["holdings"]["AAPL"]
        assert h["quantity"] == 6
        # Avg cost was 150, sold 4 at avg cost → remaining cost = 6 * 150 = 900
        assert h["cost_basis"] == pytest.approx(900, abs=1)

    def test_sell_all_removes_holding(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="SELL", quantity=10, unit_price=170)
        assert "AAPL" not in store.get_holdings()["holdings"]

    def test_dividend_tracked(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-03-01", symbol="AAPL", action="DIVIDEND", quantity=10, unit_price=0.25)
        h = store.get_holdings()["holdings"]["AAPL"]
        assert h["dividends_received"] == 2.50

    def test_avg_cost_per_share(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-20", symbol="AAPL", action="BUY", quantity=10, unit_price=170)
        h = store.get_holdings()["holdings"]["AAPL"]
        assert h["avg_cost_per_share"] == pytest.approx(160, abs=0.01)


class TestPriceUpdate:
    def test_update_prices(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-15", symbol="MSFT", action="BUY", quantity=5, unit_price=400)
        result = store.update_prices({"AAPL": 175.00, "MSFT": 420.00})
        assert result["holdings"]["AAPL"]["current_price"] == 175.00
        assert result["holdings"]["AAPL"]["current_value"] == 1750.00
        assert result["total_value"] == 1750 + 2100
        assert result["net_performance"] == (1750 + 2100) - (1500 + 2000)

    def test_missing_price_leaves_none(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        result = store.update_prices({})
        assert result["holdings"]["AAPL"]["current_price"] is None


class TestSnapshotGeneration:
    def test_build_snapshot(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-15", symbol="MSFT", action="BUY", quantity=5, unit_price=400)
        store.update_prices({"AAPL": 175.00, "MSFT": 420.00})

        snapshot = build_snapshot_from_holdings(store.get_holdings())
        assert snapshot.total_value_usd == 3850
        assert len(snapshot.holdings) == 2
        assert snapshot.holdings[0].symbol == "MSFT"  # Higher value first


class TestAccounts:
    def test_default_account_exists(self, store):
        accounts = store.get_accounts()
        assert len(accounts) == 1
        assert accounts[0]["name"] == "default"

    def test_add_account(self, store):
        store.add_account("Roth IRA", "roth_ira")
        accounts = store.get_accounts()
        assert len(accounts) == 2


class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path):
        dir_ = tmp_path / "portfolio"
        store1 = PortfolioStore(dir_)
        store1.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)

        store2 = PortfolioStore(dir_)
        assert len(store2.list_transactions()) == 1
        assert "AAPL" in store2.get_holdings()["holdings"]
