"""Service-level tests for the 'Add to portfolio' front door.

Runs against a real PortfolioStore on tmp_path — every flow must land as the
ledger primitives the store already understands.
"""

import pytest

from buildwealth_orchestrator.services.portfolio_add_flow import (
    ESTIMATED_BASIS_NOTE,
    AddFlowError,
    execute_add_flow,
)
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


@pytest.fixture
def store(tmp_path):
    return PortfolioStore(tmp_path / "portfolio")


class TestInvestmentFlow:
    def test_quantity_and_unit_cost_writes_a_buy(self, store):
        result = execute_add_flow(
            store,
            {
                "flow": "investment",
                "symbol": "vti",
                "account_id": "default",
                "quantity": 4,
                "unit_cost": 250,
                "acquired_date": "2026-06-01",
            },
        )

        created = result["created"]
        assert created["symbol"] == "VTI"
        assert created["action"] == "BUY"
        assert created["quantity"] == 4
        assert created["unit_price"] == 250
        assert created["date"] == "2026-06-01"
        assert result["account_id"] == "default"
        assert result["estimated_basis"] is False
        assert "VTI" in result["detail"]

        holding = store.get_holdings()["holdings"]["default:VTI"]
        assert holding["quantity"] == 4
        assert holding["cost_basis"] == 1000

    def test_value_usd_resolves_quantity_from_known_price(self, store):
        store.set_manual_price(symbol="VTI", price=250)
        result = execute_add_flow(
            store,
            {"flow": "investment", "symbol": "VTI", "account_id": "default", "value_usd": 1000, "unit_cost": 200},
        )
        assert result["created"]["quantity"] == 4  # 1000 / 250
        assert result["created"]["unit_price"] == 200
        assert result["estimated_basis"] is False

    def test_missing_unit_cost_estimates_basis_from_current_price(self, store):
        store.set_manual_price(symbol="VTI", price=250)
        result = execute_add_flow(
            store,
            {"flow": "investment", "symbol": "VTI", "account_id": "default", "quantity": 2},
        )
        assert result["estimated_basis"] is True
        assert result["created"]["unit_price"] == 250
        assert ESTIMATED_BASIS_NOTE in result["created"]["note"]

    def test_defaults_acquired_date_to_today(self, store):
        store.set_manual_price(symbol="VTI", price=100)
        result = execute_add_flow(
            store,
            {"flow": "investment", "symbol": "VTI", "quantity": 1, "unit_cost": 90},
        )
        assert len(result["created"]["date"]) == 10  # YYYY-MM-DD

    def test_sell_action_passes_through(self, store):
        execute_add_flow(
            store,
            {"flow": "investment", "symbol": "VTI", "quantity": 4, "unit_cost": 200, "account_id": "default"},
        )
        result = execute_add_flow(
            store,
            {
                "flow": "investment",
                "symbol": "VTI",
                "action": "SELL",
                "quantity": 1,
                "unit_cost": 260,
                "account_id": "default",
            },
        )
        assert result["created"]["action"] == "SELL"
        holding = store.get_holdings()["holdings"]["default:VTI"]
        assert holding["quantity"] == 3

    def test_transfer_flag_records_an_honest_buy(self, store):
        # TRANSFER_IN is a cash inflow in the ledger, so a share transfer is
        # recorded as a BUY at its basis until position transfers exist.
        result = execute_add_flow(
            store,
            {"flow": "investment", "symbol": "VTI", "quantity": 2, "unit_cost": 250, "transfer": True},
        )
        assert result["created"]["action"] == "BUY"
        holding = store.get_holdings()["holdings"]["default:VTI"]
        assert holding["quantity"] == 2

    def test_inline_account_creation(self, store):
        result = execute_add_flow(
            store,
            {
                "flow": "investment",
                "symbol": "VOO",
                "quantity": 1,
                "unit_cost": 400,
                "new_account": {"name": "Fidelity Roth IRA", "type": "roth"},
            },
        )
        account_id = result["account_id"]
        accounts = {a["id"]: a for a in store.get_accounts()}
        assert account_id in accounts
        assert accounts[account_id]["name"] == "Fidelity Roth IRA"
        assert accounts[account_id]["type"] == "roth"
        assert result["created"]["account"] == account_id


class TestCashFlow:
    def test_cash_deposit_lands_in_account_cash(self, store):
        result = execute_add_flow(store, {"flow": "cash", "account_id": "default", "amount_usd": 5000})
        assert result["created"]["action"] == "CASH_DEPOSIT"
        assert "$5,000.00" in result["detail"]
        assert store.get_holdings()["total_cash"] == 5000

    def test_cash_with_new_account(self, store):
        result = execute_add_flow(
            store,
            {"flow": "cash", "amount_usd": 100, "new_account": {"name": "Ally Savings", "type": "cash"}},
        )
        accounts = {a["id"]: a for a in store.get_accounts()}
        assert accounts[result["account_id"]]["name"] == "Ally Savings"


class TestPropertyFlow:
    def test_property_creates_custom_asset_and_manual_price(self, store):
        result = execute_add_flow(
            store,
            {"flow": "property", "label": "Home", "value_usd": 450000, "asset_type": "real_estate"},
        )
        symbol = result["created"]["symbol"]
        assert symbol.startswith("MANUAL_")
        assert result["created"]["asset_type"] == "real_estate"
        assert result["created"]["asset_class"] == "Real Estate"

        manual = store.get_manual_prices()["by_symbol"]
        assert manual[symbol]["price"] == 450000

        holdings = store.get_holdings()
        holding = holdings["holdings_by_symbol"][symbol]
        assert holding["current_value"] == 450000
        assert holding["is_custom_asset"] is True

    def test_vehicle_type_maps_to_vehicles_class(self, store):
        result = execute_add_flow(
            store,
            {"flow": "property", "label": "2021 Subaru", "value_usd": 18000, "asset_type": "vehicle"},
        )
        assert result["created"]["asset_type"] == "vehicle"
        assert result["created"]["asset_class"] == "Vehicles"


class TestValidation:
    def test_unknown_flow(self, store):
        with pytest.raises(AddFlowError, match="an investment, cash, or a property"):
            execute_add_flow(store, {"flow": "mystery"})

    def test_investment_requires_symbol(self, store):
        with pytest.raises(AddFlowError, match="ticker symbol"):
            execute_add_flow(store, {"flow": "investment", "quantity": 1, "unit_cost": 10})

    def test_investment_requires_quantity_or_value(self, store):
        with pytest.raises(AddFlowError, match="number of shares or their current dollar value"):
            execute_add_flow(store, {"flow": "investment", "symbol": "VTI"})

    def test_value_without_known_price_is_rejected(self, store):
        with pytest.raises(AddFlowError, match="no current price for ZZTOP"):
            execute_add_flow(store, {"flow": "investment", "symbol": "ZZTOP", "value_usd": 1000})

    def test_quantity_without_cost_or_price_is_rejected(self, store):
        with pytest.raises(AddFlowError, match="no current price for ZZTOP"):
            execute_add_flow(store, {"flow": "investment", "symbol": "ZZTOP", "quantity": 3})

    def test_unknown_account_id_is_rejected(self, store):
        with pytest.raises(AddFlowError, match='No account called "nope"'):
            execute_add_flow(
                store,
                {"flow": "investment", "symbol": "VTI", "quantity": 1, "unit_cost": 10, "account_id": "nope"},
            )

    def test_new_account_requires_a_name(self, store):
        with pytest.raises(AddFlowError, match="name"):
            execute_add_flow(
                store,
                {"flow": "cash", "amount_usd": 100, "new_account": {"type": "cash"}},
            )

    def test_invalid_action_is_rejected(self, store):
        with pytest.raises(AddFlowError, match="buy or a sell"):
            execute_add_flow(
                store,
                {"flow": "investment", "symbol": "VTI", "action": "SHORT", "quantity": 1, "unit_cost": 10},
            )

    def test_non_numeric_amount_is_rejected(self, store):
        with pytest.raises(AddFlowError, match="Amount must be a number"):
            execute_add_flow(store, {"flow": "cash", "amount_usd": "lots"})

    def test_negative_amount_is_rejected(self, store):
        with pytest.raises(AddFlowError, match="greater than zero"):
            execute_add_flow(store, {"flow": "cash", "amount_usd": -5})

    def test_cash_requires_amount(self, store):
        with pytest.raises(AddFlowError, match="how much cash"):
            execute_add_flow(store, {"flow": "cash", "account_id": "default"})

    def test_property_requires_label_and_value(self, store):
        with pytest.raises(AddFlowError, match="short name"):
            execute_add_flow(store, {"flow": "property", "value_usd": 100})
        with pytest.raises(AddFlowError, match="worth today"):
            execute_add_flow(store, {"flow": "property", "label": "Home"})

    def test_property_rejects_unknown_type(self, store):
        with pytest.raises(AddFlowError, match="Pick a type"):
            execute_add_flow(
                store,
                {"flow": "property", "label": "Boat", "value_usd": 100, "asset_type": "yacht"},
            )
