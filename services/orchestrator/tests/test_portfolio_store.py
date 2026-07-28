import json

import pytest

from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.price_updater import build_snapshot_from_holdings


def _position_key(symbol: str, account: str = "default") -> str:
    return f"{account}:{symbol}"


def _position(holdings_payload: dict, symbol: str, account: str = "default") -> dict:
    return holdings_payload["holdings"][_position_key(symbol, account)]


@pytest.fixture
def store(tmp_path):
    return PortfolioStore(tmp_path / "portfolio")


class TestAssetMetadataSeed:
    def test_default_asset_metadata_payload_seeds_large_catalog(self):
        payload = PortfolioStore._default_asset_metadata_payload()
        symbols = payload.get("symbols", {})
        assert isinstance(symbols, dict)
        assert len(symbols) >= 500
        assert "AAPL" in symbols
        assert "SPY" in symbols

    def test_seed_merge_preserves_existing_custom_metadata(self, store):
        store.upsert_asset_metadata(
            "AAPL",
            {
                "asset_class": "US Stocks",
                "sector": "Custom Sector",
                "metadata_source": "manual_override",
            },
        )
        metadata = store.get_asset_metadata_map()["AAPL"]
        assert metadata["sector"] == "Custom Sector"
        assert metadata["metadata_source"] == "manual_override"

    def test_seed_backfills_expense_ratio_but_never_overwrites(self, store):
        # A fresh store picks up the seed's expense ratio for known funds.
        assert store.get_asset_metadata_map()["VTI"]["expense_ratio"] == 0.0003

        # A user-saved ratio wins over the seed on subsequent loads.
        store.upsert_asset_metadata("VTI", {"expense_ratio": 0.001})
        assert store.get_asset_metadata_map()["VTI"]["expense_ratio"] == 0.001

    def test_unknown_symbol_gets_deterministic_fallback_metadata(self, store):
        store.add_transaction(
            date="2026-01-01",
            symbol="ZZZZ",
            action="BUY",
            quantity=1,
            unit_price=100,
        )
        holding = _position(store.get_holdings(), "ZZZZ")
        assert holding["asset_class"] == "US Stocks"
        assert holding["region"] == "US"
        assert holding["metadata_source"] == "fallback"

    def test_crypto_pair_gets_fallback_crypto_classification(self, store):
        store.add_transaction(
            date="2026-01-01",
            symbol="SOL-USD",
            action="BUY",
            quantity=1,
            unit_price=120,
        )
        holding = _position(store.get_holdings(), "SOL-USD")
        assert holding["asset_class"] == "Crypto"
        assert holding["metadata_source"] == "fallback"


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
        assert _position_key("AAPL") in holdings["holdings"]
        assert _position(holdings, "AAPL")["quantity"] == 10
        assert _position(holdings, "AAPL")["cost_basis"] == 1500

    def test_multiple_buys_accumulate(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-20", symbol="AAPL", action="BUY", quantity=5, unit_price=160)
        h = _position(store.get_holdings(), "AAPL")
        assert h["quantity"] == 15
        assert h["cost_basis"] == 2300

    def test_sell_reduces_holding(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="SELL", quantity=4, unit_price=170)
        h = _position(store.get_holdings(), "AAPL")
        assert h["quantity"] == 6
        # Avg cost was 150, sold 4 at avg cost → remaining cost = 6 * 150 = 900
        assert h["cost_basis"] == pytest.approx(900, abs=1)
        assert h["lot_count"] == 1

    def test_sell_all_removes_holding(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="SELL", quantity=10, unit_price=170)
        assert _position_key("AAPL") not in store.get_holdings()["holdings"]

    def test_dividend_tracked(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-03-01", symbol="AAPL", action="DIVIDEND", quantity=10, unit_price=0.25)
        h = _position(store.get_holdings(), "AAPL")
        assert h["dividends_received"] == 2.50

    def test_avg_cost_per_share(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-20", symbol="AAPL", action="BUY", quantity=10, unit_price=170)
        h = _position(store.get_holdings(), "AAPL")
        assert h["avg_cost_per_share"] == pytest.approx(160, abs=0.01)

    def test_buy_fee_included_in_cost_basis(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150, fee=7.25)
        h = _position(store.get_holdings(), "AAPL")
        assert h["cost_basis"] == pytest.approx(1507.25, abs=0.01)

    def test_sell_tracks_realized_gain_after_fee(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="SELL", quantity=4, unit_price=120, fee=8)
        h = _position(store.get_holdings(), "AAPL")
        assert h["realized_gains"] == pytest.approx(72.0, abs=0.01)

    def test_same_symbol_different_accounts_stays_split(self, store):
        store.add_account("Roth IRA", "roth_ira")
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=4, unit_price=100, account="default")
        store.add_transaction(date="2026-01-16", symbol="AAPL", action="BUY", quantity=6, unit_price=110, account="Roth IRA")
        holdings = store.get_holdings()
        assert _position_key("AAPL", "default") in holdings["holdings"]
        assert _position_key("AAPL", "roth_ira") in holdings["holdings"]
        assert holdings["holdings_by_symbol"]["AAPL"]["quantity"] == pytest.approx(10.0)

    def test_unpriced_holding_never_reports_a_total_loss(self, store):
        store.add_transaction(
            date="2026-01-15",
            symbol="VTI",
            action="BUY",
            quantity=10,
            unit_price=200,
        )

        holdings = store.get_holdings()

        assert holdings["valuation_status"] == "unavailable"
        assert holdings["unpriced_holdings_count"] == 1
        assert holdings["unpriced_cost_basis"] == 2000
        assert holdings["net_performance"] is None
        assert holdings["net_performance_pct"] is None


class TestExtendedActivities:
    def test_cash_deposit_and_buy_updates_account_cash(self, store):
        store.add_transaction(date="2026-01-01", symbol="", action="CASH_DEPOSIT", quantity=1, unit_price=1000)
        store.add_transaction(date="2026-01-02", symbol="AAPL", action="BUY", quantity=2, unit_price=100)
        holdings = store.get_holdings()
        assert holdings["account_cash"]["default"] == pytest.approx(800.0, abs=0.01)
        assert holdings["total_cash"] == pytest.approx(800.0, abs=0.01)
        assert holdings["total_portfolio_value"] == pytest.approx(800.0, abs=0.01)

    def test_transfer_actions_adjust_cash_balance(self, store):
        store.add_transaction(date="2026-01-01", symbol="", action="TRANSFER_IN", quantity=1, unit_price=500)
        store.add_transaction(date="2026-01-02", symbol="", action="TRANSFER_OUT", quantity=1, unit_price=125)
        holdings = store.get_holdings()
        assert holdings["account_cash"]["default"] == pytest.approx(375.0, abs=0.01)
        account_total = holdings["account_totals"]["default"]
        assert account_total["cash_balance"] == pytest.approx(375.0, abs=0.01)
        assert account_total["total_value"] == pytest.approx(375.0, abs=0.01)

    def test_stock_split_scales_quantity_and_unit_cost(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=2, unit_price=100)
        store.add_transaction(date="2026-01-02", symbol="AAPL", action="STOCK_SPLIT", quantity=2, unit_price=0)
        holding = _position(store.get_holdings(), "AAPL")
        assert holding["quantity"] == pytest.approx(4.0, abs=1e-6)
        assert holding["cost_basis"] == pytest.approx(200.0, abs=0.01)
        assert holding["avg_cost_per_share"] == pytest.approx(50.0, abs=0.01)
        assert holding["lots"][0]["remaining_quantity"] == pytest.approx(4.0, abs=1e-6)
        assert holding["lots"][0]["unit_cost"] == pytest.approx(50.0, abs=1e-6)

    def test_merger_consumes_lots_and_credits_cash(self, store):
        store.add_transaction(date="2026-01-01", symbol="", action="CASH_DEPOSIT", quantity=1, unit_price=1000)
        store.add_transaction(date="2026-01-02", symbol="AAPL", action="BUY", quantity=10, unit_price=10)
        store.add_transaction(date="2026-01-03", symbol="AAPL", action="MERGER", quantity=4, unit_price=15, fee=1)
        holdings = store.get_holdings()
        holding = _position(holdings, "AAPL")
        assert holding["quantity"] == pytest.approx(6.0, abs=1e-6)
        assert holding["realized_gains"] == pytest.approx(19.0, abs=0.01)
        assert holdings["account_cash"]["default"] == pytest.approx(959.0, abs=0.01)

    def test_lot_audit_records_sell_consumed_lots(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=3, unit_price=100)
        store.add_transaction(date="2026-01-02", symbol="AAPL", action="BUY", quantity=2, unit_price=120)
        store.add_transaction(date="2026-01-03", symbol="AAPL", action="SELL", quantity=4, unit_price=130)

        holdings = store.get_holdings()
        lot_audit = holdings["lot_audit"]
        events = lot_audit["events"]
        sell_event = next(event for event in events if event["action"] == "SELL")
        consumed = sell_event["details"]["lots_consumed"]
        assert len(consumed) >= 1
        assert sum(item["quantity_consumed"] for item in consumed) == pytest.approx(4.0, abs=1e-6)

    def test_corporate_action_payload_records_split_and_merger(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=10)
        store.add_transaction(date="2026-01-02", symbol="AAPL", action="STOCK_SPLIT", quantity=2, unit_price=0)
        store.add_transaction(
            date="2026-01-03",
            symbol="AAPL",
            action="MERGER",
            quantity=4,
            unit_price=12,
            note='{"target_symbol":"MSFT","exchange_ratio":0.5}',
        )

        holdings = store.get_holdings()
        corporate = holdings["corporate_actions"]
        events = corporate["events"]
        assert [event["action"] for event in events] == ["STOCK_SPLIT", "MERGER"]
        split_event = events[0]
        assert split_event["details"]["split_factor"] == pytest.approx(2.0, abs=1e-6)
        merger_event = events[1]
        assert merger_event["details"]["target_symbol"] == "MSFT"
        assert merger_event["details"]["exchange_ratio"] == pytest.approx(0.5, abs=1e-6)
        summary = corporate["summary_by_symbol"]["AAPL"]
        assert summary["events"] == 2
        assert summary["stock_split_events"] == 1
        assert summary["merger_events"] == 1


class TestPriceUpdate:
    def test_update_prices(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-15", symbol="MSFT", action="BUY", quantity=5, unit_price=400)
        result = store.update_prices({"AAPL": 175.00, "MSFT": 420.00})
        assert _position(result, "AAPL")["current_price"] == 175.00
        assert _position(result, "AAPL")["current_value"] == 1750.00
        assert result["total_value"] == 1750 + 2100
        assert result["net_performance"] == (1750 + 2100) - (1500 + 2000)

    def test_missing_price_leaves_none(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        result = store.update_prices({})
        assert _position(result, "AAPL")["current_price"] is None

    def test_price_persists_across_holdings_rebuild(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.update_prices({"AAPL": 175.00})
        store.add_transaction(date="2026-01-20", symbol="AAPL", action="BUY", quantity=1, unit_price=155)
        result = store.get_holdings()
        assert _position(result, "AAPL")["current_price"] == 175.00
        assert _position(result, "AAPL")["current_value"] == pytest.approx(1925.00, abs=0.01)

    def test_performance_summary_populated_after_pricing(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        result = store.update_prices({"AAPL": 175.00})
        performance = result["performance"]
        assert performance["ending_value"] == 1750.0
        assert performance["net_contributions"] == 1500.0
        assert performance["gross_contributions"] == 1500.0
        assert performance["twr_return_pct"] == pytest.approx(16.67, abs=0.01)
        assert performance["xirr_annualized_return_pct"] is not None
        assert performance["price_return_usd"] == pytest.approx(250.0, abs=0.01)
        assert performance["income_return_usd"] == pytest.approx(0.0, abs=0.01)
        assert performance["total_return_usd"] == pytest.approx(250.0, abs=0.01)

    def test_performance_keeps_realized_return_after_position_closed(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="SELL", quantity=10, unit_price=120)

        holdings = store.get_holdings()
        assert _position_key("AAPL") not in holdings["holdings"]
        performance = holdings["performance"]
        assert performance["realized_gains_usd"] == pytest.approx(200.0, abs=0.01)
        assert performance["price_return_usd"] == pytest.approx(200.0, abs=0.01)
        assert performance["total_return_usd"] == pytest.approx(200.0, abs=0.01)

        repriced = store.update_prices({})
        repriced_performance = repriced["performance"]
        assert repriced_performance["realized_gains_usd"] == pytest.approx(200.0, abs=0.01)
        assert repriced_performance["total_return_usd"] == pytest.approx(200.0, abs=0.01)


class TestManualPriceOverrides:
    def test_manual_price_override_takes_precedence_over_live_prices(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.update_prices({"AAPL": 120.0})

        store.set_manual_price(symbol="AAPL", price=95.0)
        holdings = store.get_holdings()
        holding = _position(holdings, "AAPL")
        assert holding["current_price"] == pytest.approx(95.0, abs=0.0001)
        assert holding["price_source"] == "MANUAL"
        assert holdings["manual_prices"]["AAPL"]["price"] == pytest.approx(95.0, abs=0.0001)

        updated = store.update_prices({"AAPL": 130.0})
        assert _position(updated, "AAPL")["current_price"] == pytest.approx(95.0, abs=0.0001)
        assert _position(updated, "AAPL")["price_source"] == "MANUAL"

    def test_clear_manual_price_restores_live_price_updates(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.update_prices({"AAPL": 120.0})
        store.set_manual_price(symbol="AAPL", price=95.0)

        assert store.clear_manual_price("AAPL") is True
        result = store.update_prices({"AAPL": 130.0})
        assert _position(result, "AAPL")["current_price"] == pytest.approx(130.0, abs=0.0001)
        assert _position(result, "AAPL")["price_source"] == "LIVE"

    def test_set_manual_price_requires_positive_price(self, store):
        with pytest.raises(ValueError):
            store.set_manual_price(symbol="AAPL", price=0)


class TestFxRates:
    def test_non_base_currency_position_converts_to_base_currency(self, store):
        euro_account = store.add_account("Euro Brokerage", currency="EUR")
        store.set_fx_rate(currency="EUR", rate=1.1)
        store.add_transaction(
            date="2026-01-01",
            symbol="SAP",
            action="BUY",
            quantity=10,
            unit_price=100,
            account=euro_account["id"],
            currency="EUR",
        )

        holdings = store.update_prices({"SAP": 120})
        position = _position(holdings, "SAP", euro_account["id"])
        assert position["currency"] == "EUR"
        assert holdings["base_currency"] == "USD"
        assert position["cost_basis_native"] == pytest.approx(1000.0, abs=0.01)
        assert position["cost_basis"] == pytest.approx(1100.0, abs=0.01)
        assert position["current_price_native"] == pytest.approx(120.0, abs=0.0001)
        assert position["current_price"] == pytest.approx(132.0, abs=0.0001)
        assert position["current_value_native"] == pytest.approx(1200.0, abs=0.01)
        assert position["current_value"] == pytest.approx(1320.0, abs=0.01)

    def test_updating_fx_rate_revalues_base_totals(self, store):
        euro_account = store.add_account("Euro Brokerage", currency="EUR")
        store.set_fx_rate(currency="EUR", rate=1.1)
        store.add_transaction(
            date="2026-01-01",
            symbol="SAP",
            action="BUY",
            quantity=10,
            unit_price=100,
            account=euro_account["id"],
            currency="EUR",
        )
        initial = store.update_prices({"SAP": 100})
        initial_position = _position(initial, "SAP", euro_account["id"])
        assert initial_position["current_value_native"] == pytest.approx(1000.0, abs=0.01)
        assert initial_position["current_value"] == pytest.approx(1100.0, abs=0.01)

        store.set_fx_rate(currency="EUR", rate=1.2)
        repriced = store.get_holdings()
        repriced_position = _position(repriced, "SAP", euro_account["id"])
        assert repriced_position["current_value_native"] == pytest.approx(1000.0, abs=0.01)
        assert repriced_position["current_value"] == pytest.approx(1200.0, abs=0.01)
        assert repriced["total_value"] == pytest.approx(1200.0, abs=0.01)

    def test_performance_uses_fx_converted_contributions(self, store):
        euro_account = store.add_account("Euro Brokerage", currency="EUR")
        store.set_fx_rate(currency="EUR", rate=1.2)
        store.add_transaction(
            date="2026-01-01",
            symbol="SAP",
            action="BUY",
            quantity=10,
            unit_price=100,
            account=euro_account["id"],
            currency="EUR",
        )
        holdings = store.update_prices({"SAP": 100})
        performance = holdings["performance"]
        assert performance["gross_contributions"] == pytest.approx(1200.0, abs=0.01)
        assert performance["ending_value"] == pytest.approx(1200.0, abs=0.01)

    def test_cannot_clear_base_currency_fx_rate(self, store):
        assert store.clear_fx_rate("USD") is False

    def test_historical_fx_rate_is_used_for_performance_cash_flows(self, store):
        euro_account = store.add_account("Euro Brokerage", currency="EUR")
        store.set_fx_rate(currency="EUR", rate=1.0)
        store.set_fx_rate_history(
            currency="EUR",
            rates_by_date={
                "2026-01-01": 1.2,
            },
        )
        store.add_transaction(
            date="2026-01-01",
            symbol="SAP",
            action="BUY",
            quantity=10,
            unit_price=100,
            account=euro_account["id"],
            currency="EUR",
        )
        holdings = store.update_prices({"SAP": 100})
        performance = holdings["performance"]
        assert performance["gross_contributions"] == pytest.approx(1200.0, abs=0.01)
        assert performance["ending_value"] == pytest.approx(1000.0, abs=0.01)

    def test_historical_fx_uses_latest_prior_rate_when_date_missing(self, store):
        euro_account = store.add_account("Euro Brokerage", currency="EUR")
        store.set_fx_rate(currency="EUR", rate=1.0)
        store.set_fx_rate_history(
            currency="EUR",
            rates_by_date={
                "2026-01-01": 1.3,
            },
        )
        store.add_transaction(
            date="2026-01-05",
            symbol="SAP",
            action="BUY",
            quantity=10,
            unit_price=100,
            account=euro_account["id"],
            currency="EUR",
        )
        holdings = store.update_prices({"SAP": 100})
        performance = holdings["performance"]
        assert performance["gross_contributions"] == pytest.approx(1300.0, abs=0.01)

    def test_update_fx_market_data_sets_rates_and_history(self, store):
        store.update_fx_market_data(
            rates_by_currency={"EUR": 1.11},
            history_by_currency={"EUR": {"2026-01-01": 1.2}},
        )
        fx_rates = store.get_fx_rates()
        assert fx_rates["rates"]["EUR"] == pytest.approx(1.11, abs=1e-6)
        fx_history = store.get_fx_rates_history()
        assert fx_history["pairs"]["EURUSD"]["2026-01-01"] == pytest.approx(1.2, abs=1e-6)


class TestCustomAssets:
    def test_create_custom_asset_sets_manual_metadata_and_position(self, store):
        created = store.create_custom_asset(
            name="Austin Rental Condo",
            value=250000,
            account="default",
            asset_type="real_estate",
            asset_class="Real Estate",
            region="US",
        )

        assert created["symbol"].startswith("MANUAL_")
        holdings = store.get_holdings()
        row = holdings["holdings_by_symbol"][created["symbol"]]
        assert row["name"] == "Austin Rental Condo"
        assert row["asset_type"] == "real_estate"
        assert row["data_source"] == "MANUAL"
        assert row["is_custom_asset"] is True
        assert row["price_source"] == "MANUAL"
        assert row["current_price"] == pytest.approx(250000.0, abs=0.0001)
        assert row["current_value"] == pytest.approx(250000.0, abs=0.01)
        assert holdings["manual_prices"][created["symbol"]]["price"] == pytest.approx(250000.0, abs=0.0001)

    def test_list_custom_assets_returns_manual_custom_positions(self, store):
        created = store.create_custom_asset(
            name="Private Startup Stake",
            value=50000,
            account="default",
            asset_type="private_equity",
        )
        rows = store.list_custom_assets()
        assert any(row["symbol"] == created["symbol"] for row in rows)

    def test_create_custom_asset_requires_positive_value(self, store):
        with pytest.raises(ValueError):
            store.create_custom_asset(name="Invalid Asset", value=0)


class TestWatchlist:
    def test_watchlist_upsert_and_delete(self, store):
        created = store.upsert_watchlist_item(
            symbol="nvda",
            note="AI compute beneficiary",
            thesis="AI compute thesis",
            thesis_reference_price_usd=900,
            target_price_usd=1200,
            tags=["ai", "semis", "ai"],
        )
        assert created["symbol"] == "NVDA"
        assert created["data_source"] == "OPENBB"
        assert created["thesis"] == "AI compute thesis"
        assert created["thesis_reference_price_usd"] == pytest.approx(900.0, abs=1e-6)
        assert created["target_price_usd"] == pytest.approx(1200.0, abs=1e-6)
        assert created["tags"] == ["ai", "semis"]

        updated = store.upsert_watchlist_item(
            symbol="NVDA",
            note="Updated thesis",
            target_price_usd=1250,
            tags="ai, quality",
        )
        assert updated["symbol"] == "NVDA"
        assert updated["note"] == "Updated thesis"
        assert updated["target_price_usd"] == pytest.approx(1250.0, abs=1e-6)
        assert updated["tags"] == ["ai", "quality"]

        rows = store.list_watchlist()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "NVDA"
        assert store.list_watchlist_symbols() == ["NVDA"]

        assert store.delete_watchlist_item("NVDA") is True
        assert store.delete_watchlist_item("NVDA") is False
        assert store.list_watchlist() == []

    def test_watchlist_payload_migrates_from_legacy_list(self, tmp_path):
        portfolio_dir = tmp_path / "portfolio"
        portfolio_dir.mkdir(parents=True)
        (portfolio_dir / "transactions.json").write_text("[]", encoding="utf-8")
        (portfolio_dir / "accounts.json").write_text(
            json.dumps({"accounts": [{"id": "default", "name": "Default Brokerage", "type": "taxable"}]}),
            encoding="utf-8",
        )
        (portfolio_dir / "holdings.json").write_text(json.dumps(PortfolioStore._default_holdings_payload()), encoding="utf-8")
        (portfolio_dir / "asset_metadata.json").write_text(json.dumps(PortfolioStore._default_asset_metadata_payload()), encoding="utf-8")
        (portfolio_dir / "cost_basis_methods.json").write_text(
            json.dumps(PortfolioStore._default_cost_basis_methods_payload()),
            encoding="utf-8",
        )
        (portfolio_dir / "manual_prices.json").write_text(json.dumps(PortfolioStore._default_manual_prices_payload()), encoding="utf-8")
        (portfolio_dir / "fx_rates.json").write_text(json.dumps(PortfolioStore._default_fx_rates_payload()), encoding="utf-8")
        (portfolio_dir / "fx_rates_history.json").write_text(
            json.dumps(PortfolioStore._default_fx_rates_history_payload()),
            encoding="utf-8",
        )
        (portfolio_dir / "watchlist.json").write_text(
            json.dumps(["aapl", {"symbol": "msft", "tags": "quality,megacap"}]),
            encoding="utf-8",
        )

        store = PortfolioStore(portfolio_dir)
        rows = store.list_watchlist()
        assert [row["symbol"] for row in rows] == ["AAPL", "MSFT"]
        assert rows[1]["tags"] == ["quality", "megacap"]


class TestRiskPolicy:
    def test_default_risk_policy_present_in_holdings_payload(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        holdings = store.update_prices({"AAPL": 100})
        assert holdings["risk_policy"]["schema_version"] == 1
        assert "single_holding_max_pct" in holdings["risk_policy"]["thresholds"]
        assert holdings["risk_alerts"]["schema_version"] == 1
        assert isinstance(holdings["risk_alerts"]["alerts"], list)

    def test_set_risk_policy_thresholds_persists_and_rebuilds_alerts(self, store):
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.add_transaction(date="2026-01-02", symbol="MSFT", action="BUY", quantity=10, unit_price=100)
        baseline = store.update_prices({"AAPL": 100, "MSFT": 100})

        assert baseline["risk_alerts"]["breach_count"] >= 1

        updated = store.set_risk_policy_thresholds(
            {
                "single_holding_max_pct": 60,
                "top3_holdings_max_pct": 100,
                "asset_class_max_pct": 100,
                "sector_max_pct": 100,
                "region_max_pct": 100,
                "hhi_max": 1,
                "effective_positions_min": 1,
            }
        )
        assert updated["thresholds"]["single_holding_max_pct"] == pytest.approx(60.0, abs=0.01)

        holdings = store.get_holdings()
        assert holdings["risk_policy"]["thresholds"]["single_holding_max_pct"] == pytest.approx(60.0, abs=0.01)
        assert holdings["risk_alerts"]["breach_count"] == 0


class TestCostBasisMethods:
    def test_lifo_method_changes_realized_gain(self, store):
        store.set_cost_basis_method(method="LIFO", account="default", symbol="AAPL")
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="BUY", quantity=10, unit_price=200)
        store.add_transaction(date="2026-03-01", symbol="AAPL", action="SELL", quantity=10, unit_price=250)
        holding = _position(store.get_holdings(), "AAPL")
        assert holding["cost_basis_method"] == "LIFO"
        assert holding["realized_gains"] == pytest.approx(500.0, abs=0.01)
        assert holding["cost_basis"] == pytest.approx(1000.0, abs=0.01)

    def test_average_method_uses_weighted_unit_cost(self, store):
        store.set_cost_basis_method(method="AVERAGE", account="default", symbol="AAPL")
        store.add_transaction(date="2026-01-01", symbol="AAPL", action="BUY", quantity=10, unit_price=100)
        store.add_transaction(date="2026-02-01", symbol="AAPL", action="BUY", quantity=10, unit_price=200)
        store.add_transaction(date="2026-03-01", symbol="AAPL", action="SELL", quantity=10, unit_price=250)
        holding = _position(store.get_holdings(), "AAPL")
        assert holding["cost_basis_method"] == "AVERAGE"
        assert holding["realized_gains"] == pytest.approx(1000.0, abs=0.01)
        assert holding["cost_basis"] == pytest.approx(1500.0, abs=0.01)
        assert holding["lot_count"] == 1


class TestAllocationBreakdowns:
    def test_breakdowns_include_asset_class_sector_region(self, store):
        store.add_transaction(
            date="2026-01-01",
            symbol="AAPL",
            action="BUY",
            quantity=10,
            unit_price=100,
            asset_class="US Stocks",
            sector="Technology",
            region="US",
        )
        store.add_transaction(
            date="2026-01-02",
            symbol="BND",
            action="BUY",
            quantity=20,
            unit_price=50,
            asset_class="US Bonds",
            sector="Fixed Income",
            region="US",
        )
        result = store.update_prices({"AAPL": 120, "BND": 50})

        asset_rows = result["allocation_breakdowns"]["asset_class"]
        sector_rows = result["allocation_breakdowns"]["sector"]
        region_rows = result["allocation_breakdowns"]["region"]

        assert asset_rows[0]["key"] == "US Stocks"
        assert asset_rows[0]["value"] == pytest.approx(1200.0, abs=0.01)
        assert sector_rows[0]["key"] == "Technology"
        assert region_rows[0]["key"] == "US"


class TestSnapshotGeneration:
    def test_build_snapshot(self, store):
        store.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)
        store.add_transaction(date="2026-01-15", symbol="MSFT", action="BUY", quantity=5, unit_price=400)
        store.update_prices({"AAPL": 175.00, "MSFT": 420.00})

        snapshot = build_snapshot_from_holdings(store.get_holdings())
        assert snapshot.total_value_usd == 3850
        assert len(snapshot.holdings) == 2
        assert snapshot.holdings[0].symbol == "MSFT"  # Higher value first
        assert snapshot.twr_return_pct is not None
        assert snapshot.xirr_annualized_return_pct is not None
        assert snapshot.price_return_usd is not None
        assert snapshot.total_return_usd is not None


class TestAccounts:
    def test_default_account_exists(self, store):
        accounts = store.get_accounts()
        assert len(accounts) == 1
        assert accounts[0]["id"] == "default"
        assert accounts[0]["name"] == "Default Brokerage"

    def test_add_account(self, store):
        store.add_account("Roth IRA", "roth_ira")
        accounts = store.get_accounts()
        assert len(accounts) == 2
        assert accounts[1]["id"] == "roth_ira"

    def test_update_account_preserves_id_and_changes_editable_fields(self, store):
        created = store.add_account("Savings", "savings", currency="USD")

        updated = store.update_account(
            created["id"],
            name="Emergency HYSA",
            account_type="savings",
            currency="EUR",
        )

        assert updated["id"] == created["id"]
        assert updated["name"] == "Emergency HYSA"
        assert updated["type"] == "savings"
        assert updated["currency"] == "EUR"
        assert updated["updated_at"]
        assert next(account for account in store.get_accounts() if account["id"] == created["id"]) == updated

    def test_update_account_rejects_unknown_account(self, store):
        with pytest.raises(ValueError, match="Account not found"):
            store.update_account("missing", name="Nope")


class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path):
        dir_ = tmp_path / "portfolio"
        store1 = PortfolioStore(dir_)
        store1.add_transaction(date="2026-01-15", symbol="AAPL", action="BUY", quantity=10, unit_price=150)

        store2 = PortfolioStore(dir_)
        assert len(store2.list_transactions()) == 1
        assert _position_key("AAPL") in store2.get_holdings()["holdings"]

    def test_legacy_holdings_payload_migrates_on_load(self, tmp_path):
        dir_ = tmp_path / "portfolio"
        dir_.mkdir(parents=True)
        (dir_ / "transactions.json").write_text("[]", encoding="utf-8")
        (dir_ / "accounts.json").write_text(json.dumps({"accounts": [{"name": "default", "type": "taxable"}]}), encoding="utf-8")
        (dir_ / "holdings.json").write_text(
            json.dumps(
                {
                    "holdings": {
                        "AAPL": {
                            "symbol": "AAPL",
                            "quantity": 10,
                            "cost_basis": 1500,
                            "avg_cost_per_share": 150,
                            "dividends_received": 0,
                            "current_price": 175,
                            "current_value": 1750,
                        }
                    },
                    "total_value": 1750,
                    "total_cost_basis": 1500,
                    "net_performance": 250,
                    "net_performance_pct": 16.67,
                    "prices_updated_at": "2026-01-31T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        store = PortfolioStore(dir_)
        holdings = store.get_holdings()
        assert holdings["schema_version"] == 8
        assert holdings["performance"]["as_of"] == "2026-01-31T00:00:00+00:00"
        assert holdings["holdings"][_position_key("AAPL")]["realized_gains"] == 0.0
        assert holdings["lot_audit"]["events"] == []
        assert holdings["corporate_actions"]["events"] == []
