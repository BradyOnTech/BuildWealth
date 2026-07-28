import pytest

from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, IncomeItem, TaxProfile
from buildwealth_orchestrator.services.affordability import assess_affordability, _monthly_loan_payment


INCOME = [IncomeItem(id="i1", label="Salary", monthly_amount_usd=8000)]
EXPENSES = [ExpenseItem(id="e1", label="Rent", monthly_amount_usd=2000)]


def _assess(**kwargs):
    defaults = dict(
        description="Test expense",
        monthly_amount_usd=None,
        purchase_price_usd=None,
        loan_rate_pct=None,
        loan_term_years=None,
        down_payment_pct=None,
        financing_mode=None,
        available_cash_usd=0,
        tax_profile=None,
        income_items=INCOME,
        expense_items=EXPENSES,
        debt_items=[],
    )
    defaults.update(kwargs)
    return assess_affordability(**defaults)


class TestMonthlyExpense:
    def test_affordable_small_expense(self):
        r = _assess(monthly_amount_usd=500)
        assert r.assessment == "affordable"
        assert r.proposed_monthly_usd == 500
        assert r.new_monthly_surplus_usd == 5500
        assert r.is_loan_estimate is False

    def test_affordable_moderate_expense(self):
        r = _assess(monthly_amount_usd=3000)
        assert r.assessment == "affordable"
        assert r.new_monthly_surplus_usd == 3000
        assert r.new_savings_rate_pct == pytest.approx(37.5, abs=0.1)

    def test_stretch_expense(self):
        # 5200/month leaves 800 surplus = 10% savings rate
        r = _assess(monthly_amount_usd=5200)
        assert r.assessment == "stretch"
        assert r.new_savings_rate_pct == pytest.approx(10.0, abs=0.1)

    def test_not_affordable_deficit(self):
        r = _assess(monthly_amount_usd=7000)
        assert r.assessment == "not_affordable"
        assert r.new_monthly_surplus_usd < 0

    def test_not_affordable_low_surplus(self):
        # Leaves only $100 surplus
        r = _assess(monthly_amount_usd=5900)
        assert r.assessment == "not_affordable"


class TestMortgageEstimate:
    def test_basic_mortgage(self):
        r = _assess(purchase_price_usd=300000, financing_mode="loan")
        assert r.is_loan_estimate is True
        assert r.loan_principal_usd == 240000  # 80% of 300k
        assert r.down_payment_usd == 60000
        assert r.estimated_monthly_payment_usd > 0
        assert r.loan_rate_pct == 6.5  # default
        assert r.loan_term_years == 30  # default

    def test_custom_mortgage_terms(self):
        r = _assess(
            purchase_price_usd=400000,
            financing_mode="loan",
            loan_rate_pct=5.5,
            loan_term_years=15,
            down_payment_pct=10,
        )
        assert r.loan_principal_usd == 360000
        assert r.down_payment_usd == 40000
        assert r.loan_rate_pct == 5.5
        assert r.loan_term_years == 15
        # 15-year at 5.5% on 360k should be ~$2,941
        assert 2900 < r.estimated_monthly_payment_usd < 3000

    def test_expensive_house_not_affordable(self):
        r = _assess(purchase_price_usd=1000000, financing_mode="loan")
        # 800k loan at 6.5% for 30 years = ~$5,056/month
        assert r.assessment in ("stretch", "not_affordable")

    def test_mortgage_shows_in_highlights(self):
        r = _assess(purchase_price_usd=300000, financing_mode="loan")
        assert any("loan" in h.lower() or "estimated" in h.lower() for h in r.highlights)


class TestDTI:
    def test_high_dti_with_loan(self):
        debts = [DebtItem(id="d1", label="Car", balance_usd=25000, minimum_payment_usd=500)]
        # Current DTI = 500/8000 = 6.25%
        # Adding a $300k purchase (loan ~$1,517/month at 6.5%) pushes DTI up
        r = _assess(purchase_price_usd=300000, financing_mode="loan", debt_items=debts)
        assert r.current_dti_pct == pytest.approx(6.25, abs=0.1)
        assert r.new_dti_pct > r.current_dti_pct
        assert r.is_loan_estimate is True

    def test_regular_expense_does_not_affect_dti(self):
        # A monthly expense (not a loan) should NOT increase DTI
        r = _assess(monthly_amount_usd=1000)
        assert r.new_dti_pct == r.current_dti_pct

    def test_dti_warning_in_highlights_for_mortgage(self):
        debts = [DebtItem(id="d1", label="Car", balance_usd=25000, minimum_payment_usd=1500)]
        r = _assess(purchase_price_usd=400000, financing_mode="loan", debt_items=debts)
        assert any("dti" in h.lower() or "debt-to-income" in h.lower() for h in r.highlights)


class TestPlanImpact:
    def test_annual_savings_reduction(self):
        r = _assess(monthly_amount_usd=1000)
        assert r.annual_savings_reduction_usd == 12000
        assert r.current_annual_savings_usd == 72000
        assert r.new_annual_savings_usd == 60000

    def test_plan_impact_detail_present(self):
        r = _assess(monthly_amount_usd=1000)
        assert r.plan_impact_detail is not None
        assert "simulation" in r.plan_impact_detail.lower()


class TestCashPurchase:
    def test_cash_purchase_does_not_invent_a_loan_or_reduce_annual_savings(self):
        r = _assess(
            purchase_price_usd=3000,
            financing_mode="cash",
            available_cash_usd=10000,
        )

        assert r.is_loan_estimate is False
        assert r.proposed_monthly_usd == 0
        assert r.one_time_cash_required_usd == 3000
        assert r.cash_after_purchase_usd == 7000
        assert r.annual_savings_reduction_usd == 0

    def test_cash_purchase_is_not_affordable_when_cash_is_insufficient(self):
        r = _assess(
            purchase_price_usd=5000,
            financing_mode="cash",
            available_cash_usd=4300,
        )

        assert r.assessment == "not_affordable"
        assert r.cash_after_purchase_usd == -700

    def test_cash_purchase_is_a_stretch_when_it_breaks_three_month_runway(self):
        r = _assess(
            purchase_price_usd=5000,
            financing_mode="cash",
            available_cash_usd=10000,
        )

        assert r.assessment == "stretch"
        assert r.runway_after_purchase_months == pytest.approx(2.5)


class TestTaxes:
    def test_saved_tax_rates_reduce_affordable_monthly_surplus(self):
        r = _assess(
            monthly_amount_usd=1000,
            income_items=[IncomeItem(id="i1", label="Salary", monthly_amount_usd=8000, is_pre_tax=True)],
            tax_profile=TaxProfile(effective_tax_rate=0.12, state_tax_rate=0.05),
        )

        assert r.current_monthly_surplus_usd == 4640
        assert r.new_monthly_surplus_usd == 3640


class TestEdgeCases:
    def test_no_income(self):
        r = _assess(monthly_amount_usd=500, income_items=[])
        assert r.assessment == "insufficient_data"

    def test_no_amount_or_price(self):
        r = _assess()
        assert r.assessment == "insufficient_data"

    def test_zero_monthly(self):
        r = _assess(monthly_amount_usd=0)
        assert r.assessment == "insufficient_data"

    def test_zero_purchase_price(self):
        r = _assess(purchase_price_usd=0)
        assert r.assessment == "insufficient_data"


class TestLoanPaymentMath:
    def test_known_mortgage(self):
        # $200k at 6% for 30 years = $1,199.10
        payment = _monthly_loan_payment(200000, 6.0, 30)
        assert payment == pytest.approx(1199.10, abs=1.0)

    def test_zero_rate(self):
        payment = _monthly_loan_payment(120000, 0.0, 10)
        assert payment == pytest.approx(1000.0, abs=0.01)

    def test_zero_principal(self):
        assert _monthly_loan_payment(0, 6.0, 30) == 0.0


class TestHighlights:
    def test_surplus_change_highlighted(self):
        r = _assess(monthly_amount_usd=1000)
        assert any("surplus" in h.lower() for h in r.highlights)

    def test_savings_rate_highlighted(self):
        r = _assess(monthly_amount_usd=1000)
        assert any("savings rate" in h.lower() or "saving" in h.lower() for h in r.highlights)
