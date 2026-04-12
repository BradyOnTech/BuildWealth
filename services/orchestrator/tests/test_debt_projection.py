from datetime import date

import pytest

from buildwealth_orchestrator.services.debt_projection import project_debt_payoff


def test_project_debt_payoff_minimum_strategy_pays_down_debt() -> None:
    result = project_debt_payoff(
        [
            {
                "id": "debt-1",
                "label": "Card",
                "balance_usd": 6000,
                "interest_rate": 0.18,
                "minimum_payment_usd": 300,
            }
        ],
        start_date=date(2026, 1, 1),
        max_years=10,
        strategy="minimum",
    )

    selected = result["selected_scenario"]
    assert selected["strategy"] == "minimum"
    assert selected["paid_off"] is True
    assert selected["months_to_payoff"] > 0
    assert selected["remaining_balance_usd"] == pytest.approx(0.0, abs=0.01)
    assert selected["total_interest_paid_usd"] > 0


def test_project_debt_payoff_snowball_accelerates_vs_minimum() -> None:
    debts = [
        {
            "id": "debt-1",
            "label": "Card A",
            "balance_usd": 3000,
            "interest_rate": 0.19,
            "minimum_payment_usd": 100,
        },
        {
            "id": "debt-2",
            "label": "Card B",
            "balance_usd": 7000,
            "interest_rate": 0.15,
            "minimum_payment_usd": 150,
        },
    ]
    result = project_debt_payoff(
        debts,
        start_date=date(2026, 1, 1),
        max_years=20,
        strategy="snowball",
        monthly_accelerated_payment_usd=300,
    )

    minimum = result["minimum_scenario"]
    selected = result["selected_scenario"]
    assert selected["strategy"] == "snowball"
    assert selected["months_to_payoff"] < minimum["months_to_payoff"]
    assert selected["total_interest_paid_usd"] < minimum["total_interest_paid_usd"]
    assert result["payoff_months_saved_vs_minimum"] is not None
    assert result["interest_saved_vs_minimum_usd"] > 0


def test_project_debt_payoff_custom_uses_custom_monthly_payment() -> None:
    result = project_debt_payoff(
        [
            {
                "id": "debt-1",
                "label": "Loan",
                "balance_usd": 10000,
                "interest_rate": 0.08,
                "minimum_payment_usd": 250,
                "payoff_strategy": "custom",
                "custom_monthly_payment_usd": 300,
            }
        ],
        start_date=date(2026, 1, 1),
        max_years=20,
        strategy="custom",
        monthly_accelerated_payment_usd=0,
    )

    minimum = result["minimum_scenario"]
    selected = result["selected_scenario"]
    assert selected["strategy"] == "custom"
    assert selected["months_to_payoff"] < minimum["months_to_payoff"]
    assert selected["first_year_payments_usd"] > minimum["first_year_payments_usd"]


def test_project_debt_payoff_warns_when_horizon_ends_before_payoff() -> None:
    result = project_debt_payoff(
        [
            {
                "id": "debt-1",
                "label": "Slow Loan",
                "balance_usd": 50000,
                "interest_rate": 0.12,
                "minimum_payment_usd": 100,
            }
        ],
        start_date=date(2026, 1, 1),
        max_years=1,
        strategy="minimum",
    )

    selected = result["selected_scenario"]
    assert selected["paid_off"] is False
    assert selected["remaining_balance_usd"] > 0
    assert selected["warnings"]
    assert result["warnings"]


def test_project_debt_payoff_skips_invalid_rows() -> None:
    result = project_debt_payoff(
        [
            {
                "id": "debt-1",
                "label": "Invalid",
                "balance_usd": 5000,
                "interest_rate": 0.1,
                "minimum_payment_usd": 0,
            }
        ],
        start_date=date(2026, 1, 1),
        max_years=5,
        strategy="minimum",
    )

    selected = result["selected_scenario"]
    assert result["debt_items_count"] == 1
    assert selected["paid_off"] is True
    assert selected["months_to_payoff"] == 0
    assert selected["warnings"]

