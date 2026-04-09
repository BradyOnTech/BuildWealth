"""Assess whether a proposed expense or purchase is affordable given current finances."""

from __future__ import annotations

from buildwealth_orchestrator.schemas import (
    AffordabilityResponse,
    DebtItem,
    ExpenseItem,
    IncomeItem,
)

# Assessment thresholds
MIN_SURPLUS_AFTER_USD = 200.0     # Must keep at least $200/month surplus
MIN_SAVINGS_RATE_AFTER = 5.0      # Must keep at least 5% savings rate
MAX_DTI_AFTER = 43.0              # FHA-style max DTI limit
STRETCH_SAVINGS_RATE = 15.0       # Below 15% savings rate = "stretch"
DEFAULT_MORTGAGE_RATE = 6.5       # Default mortgage rate if not specified
DEFAULT_MORTGAGE_TERM = 30        # Default 30-year mortgage
DEFAULT_DOWN_PAYMENT_PCT = 20.0   # Default 20% down


def _monthly_loan_payment(principal: float, annual_rate_pct: float, term_years: int) -> float:
    """Calculate monthly payment using standard amortization formula."""
    if principal <= 0:
        return 0.0
    if annual_rate_pct <= 0:
        return principal / (term_years * 12)
    r = annual_rate_pct / 100.0 / 12.0
    n = term_years * 12
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def assess_affordability(
    *,
    description: str,
    monthly_amount_usd: float | None,
    purchase_price_usd: float | None,
    loan_rate_pct: float | None,
    loan_term_years: int | None,
    down_payment_pct: float | None,
    income_items: list[IncomeItem],
    expense_items: list[ExpenseItem],
    debt_items: list[DebtItem],
) -> AffordabilityResponse:
    gross_income = sum(i.monthly_amount_usd for i in income_items)
    total_expenses = sum(e.monthly_amount_usd for e in expense_items)
    total_debt_payments = sum(d.minimum_payment_usd or 0.0 for d in debt_items)
    current_surplus = gross_income - total_expenses - total_debt_payments
    current_savings_rate = (current_surplus / gross_income * 100.0) if gross_income > 0 else 0.0
    current_dti = (total_debt_payments / gross_income * 100.0) if gross_income > 0 else 0.0

    if gross_income <= 0:
        return AffordabilityResponse(
            description=description or "Proposed expense",
            assessment="insufficient_data",
            assessment_detail="No income data available. Add income to your financial profile to assess affordability.",
            proposed_monthly_usd=0.0,
            is_loan_estimate=False,
            current_monthly_surplus_usd=0.0,
            current_savings_rate_pct=0.0,
            current_dti_pct=0.0,
            new_monthly_surplus_usd=0.0,
            new_savings_rate_pct=0.0,
            new_dti_pct=0.0,
            surplus_change_usd=0.0,
            savings_rate_change_pct=0.0,
            dti_change_pct=0.0,
            current_annual_savings_usd=0.0,
            new_annual_savings_usd=0.0,
            annual_savings_reduction_usd=0.0,
            highlights=["Add income information to your financial profile."],
        )

    # Determine the proposed monthly cost
    is_loan = False
    loan_principal = None
    down_payment = None
    est_monthly_payment = None
    rate = loan_rate_pct
    term = loan_term_years

    if purchase_price_usd is not None and purchase_price_usd > 0:
        # Loan/mortgage calculation
        is_loan = True
        dp_pct = down_payment_pct if down_payment_pct is not None else DEFAULT_DOWN_PAYMENT_PCT
        rate = rate if rate is not None else DEFAULT_MORTGAGE_RATE
        term = term if term is not None else DEFAULT_MORTGAGE_TERM
        down_payment = purchase_price_usd * (dp_pct / 100.0)
        loan_principal = purchase_price_usd - down_payment
        est_monthly_payment = _monthly_loan_payment(loan_principal, rate, term)
        proposed_monthly = est_monthly_payment
    elif monthly_amount_usd is not None and monthly_amount_usd > 0:
        proposed_monthly = monthly_amount_usd
    else:
        return AffordabilityResponse(
            description=description or "Proposed expense",
            assessment="insufficient_data",
            assessment_detail="Provide either a monthly amount or purchase price to assess affordability.",
            proposed_monthly_usd=0.0,
            is_loan_estimate=False,
            current_monthly_surplus_usd=round(current_surplus, 2),
            current_savings_rate_pct=round(current_savings_rate, 1),
            current_dti_pct=round(current_dti, 1),
            new_monthly_surplus_usd=round(current_surplus, 2),
            new_savings_rate_pct=round(current_savings_rate, 1),
            new_dti_pct=round(current_dti, 1),
            surplus_change_usd=0.0,
            savings_rate_change_pct=0.0,
            dti_change_pct=0.0,
            current_annual_savings_usd=round(current_surplus * 12, 2),
            new_annual_savings_usd=round(current_surplus * 12, 2),
            annual_savings_reduction_usd=0.0,
            highlights=["Provide a monthly amount or purchase price."],
        )

    # Compute new state
    new_surplus = current_surplus - proposed_monthly
    new_savings_rate = (new_surplus / gross_income * 100.0) if gross_income > 0 else 0.0
    # Only loan payments affect DTI — regular expenses don't count as debt obligations
    new_debt_payments = total_debt_payments + (proposed_monthly if is_loan else 0.0)
    new_dti = (new_debt_payments / gross_income * 100.0) if gross_income > 0 else 0.0

    current_annual_savings = current_surplus * 12
    new_annual_savings = new_surplus * 12
    annual_reduction = current_annual_savings - new_annual_savings

    # Assessment
    highlights: list[str] = []

    if new_surplus < 0:
        assessment = "not_affordable"
        highlights.append(f"This expense would create a monthly deficit of ${abs(new_surplus):,.0f}.")
    elif new_surplus < MIN_SURPLUS_AFTER_USD:
        assessment = "not_affordable"
        highlights.append(f"This would leave only ${new_surplus:,.0f}/month surplus — below the ${MIN_SURPLUS_AFTER_USD:,.0f} safety minimum.")
    elif new_dti > MAX_DTI_AFTER:
        assessment = "not_affordable"
        highlights.append(f"New debt-to-income ratio of {new_dti:.1f}% exceeds the {MAX_DTI_AFTER:.0f}% guideline.")
    elif new_savings_rate < MIN_SAVINGS_RATE_AFTER:
        assessment = "stretch"
        highlights.append(f"Savings rate would drop to {new_savings_rate:.1f}% — below the {MIN_SAVINGS_RATE_AFTER:.0f}% minimum for long-term growth.")
    elif new_savings_rate < STRETCH_SAVINGS_RATE:
        assessment = "stretch"
        highlights.append(f"Savings rate would drop to {new_savings_rate:.1f}% — affordable but leaves less room for investing.")
    else:
        assessment = "affordable"
        highlights.append(f"Savings rate would remain at {new_savings_rate:.1f}% after this expense.")

    # Cash flow impact
    highlights.append(f"Monthly surplus changes from ${current_surplus:,.0f} to ${new_surplus:,.0f} (−${proposed_monthly:,.0f}/month).")

    # Plan trajectory impact
    if annual_reduction > 0:
        highlights.append(f"Annual investment capacity reduces by ${annual_reduction:,.0f}/year, from ${current_annual_savings:,.0f} to ${new_annual_savings:,.0f}.")

    # Loan-specific highlights
    if is_loan and loan_principal is not None:
        highlights.append(f"Estimated loan: ${loan_principal:,.0f} at {rate}% for {term} years = ${est_monthly_payment:,.0f}/month.")
        if down_payment and down_payment > 0:
            highlights.append(f"Down payment: ${down_payment:,.0f} ({down_payment_pct or DEFAULT_DOWN_PAYMENT_PCT:.0f}% of ${purchase_price_usd:,.0f}).")

    # DTI warning
    if new_dti > 36:
        highlights.append(f"New DTI of {new_dti:.1f}% is above conventional lending guidelines (36%).")
    elif new_dti > 28 and is_loan:
        highlights.append(f"New DTI of {new_dti:.1f}% is above the front-end housing guideline (28%) but within back-end limits.")

    assessment_detail = {
        "affordable": f"This expense fits within your current cash flow. You'd still save {new_savings_rate:.1f}% of income.",
        "stretch": f"This is technically affordable but would significantly reduce your savings capacity.",
        "not_affordable": f"This expense would strain your finances beyond sustainable limits.",
        "insufficient_data": "Not enough data to assess.",
    }[assessment]

    plan_impact = None
    if annual_reduction > 0:
        plan_impact = (
            f"Reducing annual savings by ${annual_reduction:,.0f} would slow portfolio growth. "
            f"Run a scenario diff with reduced contributions to see the long-term impact."
        )

    return AffordabilityResponse(
        description=description or "Proposed expense",
        assessment=assessment,
        assessment_detail=assessment_detail,
        proposed_monthly_usd=round(proposed_monthly, 2),
        is_loan_estimate=is_loan,
        loan_principal_usd=round(loan_principal, 2) if loan_principal is not None else None,
        down_payment_usd=round(down_payment, 2) if down_payment is not None else None,
        estimated_monthly_payment_usd=round(est_monthly_payment, 2) if est_monthly_payment is not None else None,
        loan_rate_pct=rate if is_loan else None,
        loan_term_years=term if is_loan else None,
        current_monthly_surplus_usd=round(current_surplus, 2),
        current_savings_rate_pct=round(current_savings_rate, 1),
        current_dti_pct=round(current_dti, 1),
        new_monthly_surplus_usd=round(new_surplus, 2),
        new_savings_rate_pct=round(new_savings_rate, 1),
        new_dti_pct=round(new_dti, 1),
        surplus_change_usd=round(-proposed_monthly, 2),
        savings_rate_change_pct=round(new_savings_rate - current_savings_rate, 1),
        dti_change_pct=round(new_dti - current_dti, 1),
        current_annual_savings_usd=round(current_annual_savings, 2),
        new_annual_savings_usd=round(new_annual_savings, 2),
        annual_savings_reduction_usd=round(annual_reduction, 2),
        plan_impact_detail=plan_impact,
        highlights=highlights,
    )
