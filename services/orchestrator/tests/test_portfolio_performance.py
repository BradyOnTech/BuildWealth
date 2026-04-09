from datetime import datetime, timezone

import pytest

from buildwealth_orchestrator.services.portfolio_performance import (
    calculate_modified_dietz_return,
    calculate_portfolio_performance,
    filter_transaction_cash_flows,
)


def test_calculate_portfolio_performance_single_position_gain():
    result = calculate_portfolio_performance(
        transactions=[
            {
                "date": "2026-01-01",
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 10,
                "unit_price": 100,
                "fee": 0,
            }
        ],
        holdings={
            "AAPL": {
                "symbol": "AAPL",
                "quantity": 10,
                "avg_cost_per_share": 100,
                "current_price": 110,
                "current_value": 1100,
            }
        },
        as_of="2026-01-31T00:00:00+00:00",
    )

    assert result["ending_value"] == 1100.0
    assert result["net_contributions"] == 1000.0
    assert result["twr_return_pct"] == pytest.approx(10.0, abs=0.01)
    assert result["twr_annualized_return_pct"] is not None
    assert result["xirr_annualized_return_pct"] is not None


def test_calculate_portfolio_performance_handles_mid_period_buy():
    result = calculate_portfolio_performance(
        transactions=[
            {
                "date": "2026-01-01",
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 10,
                "unit_price": 100,
            },
            {
                "date": "2026-02-01",
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 5,
                "unit_price": 120,
            },
        ],
        holdings={
            "AAPL": {
                "symbol": "AAPL",
                "quantity": 15,
                "avg_cost_per_share": 106.6667,
                "current_price": 120,
                "current_value": 1800,
            }
        },
        as_of="2026-03-01T00:00:00+00:00",
    )

    assert result["ending_value"] == 1800.0
    assert result["net_contributions"] == 1600.0
    assert result["twr_return_pct"] == pytest.approx(20.0, abs=0.01)


def test_filter_transaction_cash_flows_uses_portfolio_contribution_signs():
    flows = filter_transaction_cash_flows(
        transactions=[
            {"date": "2026-01-10", "symbol": "AAPL", "action": "BUY", "quantity": 10, "unit_price": 100},
            {"date": "2026-01-20", "symbol": "AAPL", "action": "SELL", "quantity": 2, "unit_price": 120},
            {"date": "2026-01-25", "symbol": "AAPL", "action": "DIVIDEND", "quantity": 10, "unit_price": 0.5},
        ],
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert flows == [
        (datetime(2026, 1, 10, tzinfo=timezone.utc), 1000.0),
        (datetime(2026, 1, 20, tzinfo=timezone.utc), -240.0),
        (datetime(2026, 1, 25, tzinfo=timezone.utc), -5.0),
    ]


def test_calculate_modified_dietz_return():
    period_return, annualized_return = calculate_modified_dietz_return(
        start_value=100000,
        end_value=110000,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
        cash_flows=[(datetime(2026, 2, 15, tzinfo=timezone.utc), 5000)],
    )

    assert period_return == pytest.approx(0.04878, abs=0.001)
    assert annualized_return is not None
    assert annualized_return > period_return
