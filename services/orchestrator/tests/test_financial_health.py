from datetime import datetime, timezone

import pytest

from buildwealth_orchestrator.schemas import (
    DebtItem,
    ExpenseItem,
    IncomeItem,
    GoalItem,
    PhysicalAssetItem,
    PortfolioSnapshot,
)
from buildwealth_orchestrator.services.financial_health import compute_financial_health


def _snap(total_value: float = 100000, total_investment: float = 80000) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime(2026, 4, 8, tzinfo=timezone.utc),
        total_value_usd=total_value,
        total_investment_usd=total_investment,
    )


def _health(**kwargs):
    defaults = dict(
        income_items=[IncomeItem(id="i1", label="Salary", monthly_amount_usd=8000)],
        expense_items=[ExpenseItem(id="e1", label="Rent", monthly_amount_usd=2000)],
        debt_items=[],
        goal_items=[],
        physical_assets=[],
        snapshot=_snap(),
    )
    defaults.update(kwargs)
    return compute_financial_health(**defaults)


class TestNetWorth:
    def test_net_worth_no_debt(self):
        r = _health()
        assert r.portfolio_value_usd == 100000
        assert r.total_debt_usd == 0
        assert r.net_worth_usd == 100000

    def test_net_worth_with_debt(self):
        r = _health(debt_items=[DebtItem(id="d1", label="Loan", balance_usd=30000, minimum_payment_usd=500)])
        assert r.net_worth_usd == 70000
        assert r.total_debt_usd == 30000

    def test_net_worth_includes_physical_assets(self):
        r = _health(
            physical_assets=[
                PhysicalAssetItem(
                    id="asset-1",
                    label="House",
                    current_value_usd=450000,
                    asset_type="real_estate",
                )
            ],
        )
        assert r.portfolio_value_usd == 100000
        assert r.physical_assets_value_usd == 450000
        assert r.total_assets_usd == 550000
        assert r.net_worth_usd == 550000

    def test_net_worth_no_portfolio(self):
        r = _health(snapshot=None)
        assert r.portfolio_value_usd == 0
        assert r.net_worth_usd == 0


class TestCashFlow:
    def test_basic_surplus(self):
        r = _health()
        assert r.gross_monthly_income_usd == 8000
        assert r.total_monthly_expenses_usd == 2000
        assert r.monthly_surplus_usd == 6000

    def test_surplus_with_debt_payments(self):
        r = _health(debt_items=[DebtItem(id="d1", label="Car", balance_usd=20000, minimum_payment_usd=400)])
        assert r.monthly_surplus_usd == 5600

    def test_deficit(self):
        r = _health(expense_items=[ExpenseItem(id="e1", label="Life", monthly_amount_usd=9000)])
        assert r.monthly_surplus_usd < 0

    def test_multiple_income_sources(self):
        items = [
            IncomeItem(id="i1", label="Salary", monthly_amount_usd=7000),
            IncomeItem(id="i2", label="Side gig", monthly_amount_usd=1500),
        ]
        r = _health(income_items=items)
        assert r.gross_monthly_income_usd == 8500


class TestSavingsRate:
    def test_healthy_savings_rate(self):
        # 8000 income, 2000 expenses, 0 debt = 75% savings rate
        r = _health()
        assert r.savings_rate_pct == 75.0
        assert r.status == "healthy"

    def test_low_savings_rate(self):
        r = _health(expense_items=[ExpenseItem(id="e1", label="Life", monthly_amount_usd=7500)])
        assert r.savings_rate_pct == pytest.approx(6.25, abs=0.1)

    def test_zero_income(self):
        r = _health(income_items=[])
        assert r.savings_rate_pct == 0.0


class TestDebtToIncome:
    def test_no_debt(self):
        r = _health()
        assert r.debt_to_income_ratio_pct == 0.0

    def test_manageable_dti(self):
        r = _health(debt_items=[DebtItem(id="d1", label="Car", balance_usd=15000, minimum_payment_usd=300)])
        assert r.debt_to_income_ratio_pct == pytest.approx(3.75, abs=0.1)

    def test_high_dti(self):
        debts = [
            DebtItem(id="d1", label="Mortgage", balance_usd=300000, minimum_payment_usd=2000),
            DebtItem(id="d2", label="Car", balance_usd=25000, minimum_payment_usd=500),
            DebtItem(id="d3", label="Student", balance_usd=40000, minimum_payment_usd=600),
        ]
        r = _health(debt_items=debts)
        # 3100 / 8000 = 38.75%
        assert r.debt_to_income_ratio_pct == pytest.approx(38.75, abs=0.1)
        assert r.status in ("needs_attention", "critical")


class TestEmergencyFund:
    def test_strong_emergency_fund(self):
        # 100k portfolio, 2000 expenses = 50 months
        r = _health()
        assert r.emergency_fund_months == 50.0

    def test_thin_emergency_fund(self):
        r = _health(
            snapshot=_snap(total_value=5000),
            expense_items=[ExpenseItem(id="e1", label="Life", monthly_amount_usd=3000)],
        )
        assert r.emergency_fund_months == pytest.approx(1.7, abs=0.1)

    def test_no_expenses(self):
        r = _health(expense_items=[])
        assert r.emergency_fund_months == 0.0


class TestStatusAssessment:
    def test_healthy(self):
        r = _health()
        assert r.status == "healthy"

    def test_critical_deficit(self):
        r = _health(
            income_items=[IncomeItem(id="i1", label="Part-time", monthly_amount_usd=2000)],
            expense_items=[ExpenseItem(id="e1", label="Life", monthly_amount_usd=3000)],
            debt_items=[DebtItem(id="d1", label="CC", balance_usd=15000, minimum_payment_usd=500)],
            snapshot=_snap(total_value=2000),
        )
        assert r.status == "critical"

    def test_insufficient_data(self):
        r = _health(income_items=[], expense_items=[], snapshot=None)
        assert r.status == "insufficient_data"

    def test_physical_assets_count_as_data(self):
        r = _health(
            income_items=[],
            expense_items=[],
            snapshot=None,
            physical_assets=[PhysicalAssetItem(id="asset-1", label="Car", current_value_usd=25000, asset_type="vehicle")],
        )
        assert r.status == "insufficient_data"
        assert r.net_worth_usd == 25000


class TestHighlights:
    def test_surplus_highlight(self):
        r = _health()
        assert any("surplus" in h.lower() for h in r.highlights)

    def test_deficit_highlight(self):
        r = _health(expense_items=[ExpenseItem(id="e1", label="Life", monthly_amount_usd=9000)])
        assert any("deficit" in h.lower() for h in r.highlights)

    def test_no_debt_highlight(self):
        r = _health()
        assert any("no debt" in h.lower() for h in r.highlights)

    def test_high_dti_highlight(self):
        r = _health(debt_items=[DebtItem(id="d1", label="Mortgage", balance_usd=300000, minimum_payment_usd=3500)])
        assert any("high" in h.lower() and "debt" in h.lower() for h in r.highlights)


class TestCounts:
    def test_item_counts(self):
        r = _health(
            goal_items=[GoalItem(id="g1", label="House", target_amount_usd=80000)],
            physical_assets=[PhysicalAssetItem(id="asset-1", label="House", current_value_usd=400000, asset_type="real_estate")],
        )
        assert r.income_item_count == 1
        assert r.expense_item_count == 1
        assert r.debt_item_count == 0
        assert r.goal_item_count == 1
        assert r.physical_asset_item_count == 1
