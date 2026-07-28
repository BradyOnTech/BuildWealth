"""Compute a financial health summary from profile data and portfolio snapshot."""

from __future__ import annotations

from datetime import datetime, timezone

from buildwealth_orchestrator.schemas import (
    DebtItem,
    ExpenseItem,
    FinancialHealthResponse,
    IncomeItem,
    GoalItem,
    PhysicalAssetItem,
    PortfolioSnapshot,
    TaxProfile,
)
from buildwealth_orchestrator.services.household_assets import reconcile_household_assets

# Thresholds for health assessment
SAVINGS_RATE_HEALTHY = 20.0      # >= 20% savings rate is healthy
SAVINGS_RATE_ATTENTION = 10.0    # >= 10% is needs_attention, below is critical
DTI_HEALTHY = 20.0               # <= 20% DTI is healthy
DTI_ATTENTION = 36.0             # <= 36% is needs_attention, above is critical
EMERGENCY_HEALTHY = 6.0          # >= 6 months is healthy
EMERGENCY_ATTENTION = 3.0        # >= 3 months is needs_attention

LIQUID_ACCOUNT_TYPES = {"depository", "checking", "savings", "cash", "money_market", "taxable", "brokerage"}
ILLIQUID_ACCOUNT_TYPES = {"401k", "ira", "roth_ira", "traditional_ira", "hsa", "real_estate"}


def estimate_liquid_cash_value(snapshot: PortfolioSnapshot | None) -> float:
    if snapshot is None:
        return 0.0

    account_totals = snapshot.raw.get("account_totals") if isinstance(snapshot.raw, dict) else None
    if isinstance(account_totals, dict) and account_totals:
        liquid_cash = 0.0
        saw_cash_detail = False
        for account in account_totals.values():
            if not isinstance(account, dict):
                continue
            account_type = str(account.get("type") or "").strip().lower()
            if account_type in ILLIQUID_ACCOUNT_TYPES:
                continue
            cash_balance = float(account.get("cash_balance") or 0.0)
            if cash_balance > 0:
                saw_cash_detail = True
                if not account_type or account_type in LIQUID_ACCOUNT_TYPES:
                    liquid_cash += cash_balance
        if saw_cash_detail:
            return liquid_cash

    cash_like_holdings = 0.0
    for holding in snapshot.holdings:
        asset_class = str(holding.asset_class or "").strip().lower()
        asset_type = str(holding.asset_type or "").strip().lower()
        if asset_class in {"cash", "cash_equivalent"} or asset_type in {"cash", "money_market"}:
            cash_like_holdings += float(holding.value_usd or 0.0)
    if cash_like_holdings > 0:
        return cash_like_holdings

    # Older snapshots did not separate cash from invested assets. Preserve the
    # legacy behavior only when no liquidity detail is available.
    return float(snapshot.total_value_usd or 0.0)


def portfolio_value_with_cash(snapshot: PortfolioSnapshot | None) -> float:
    """Return the canonical account value, including account cash.

    Some importers keep invested holdings in ``total_value_usd`` and put the
    uninvested account balance only in ``raw.account_totals``. Prefer an
    explicit sum of account totals when it is larger, without double-counting
    snapshots whose headline total already includes that cash.
    """
    if snapshot is None:
        return 0.0
    headline = float(snapshot.total_value_usd or 0.0)
    account_totals = snapshot.raw.get("account_totals") if isinstance(snapshot.raw, dict) else None
    if not isinstance(account_totals, dict) or not account_totals:
        return headline
    explicit_total = 0.0
    saw_explicit_total = False
    reconstructed_total = 0.0
    saw_reconstructable = False
    for account in account_totals.values():
        if not isinstance(account, dict):
            continue
        if account.get("total_value") is not None:
            explicit_total += float(account.get("total_value") or 0.0)
            saw_explicit_total = True
        market_value = account.get("market_value")
        cash_balance = account.get("cash_balance")
        if market_value is not None or cash_balance is not None:
            reconstructed_total += float(market_value or 0.0) + float(cash_balance or 0.0)
            saw_reconstructable = True
    account_value = explicit_total if saw_explicit_total else reconstructed_total if saw_reconstructable else 0.0
    return max(headline, account_value)


def compute_monthly_cash_flow(
    *,
    income_items: list[IncomeItem],
    expense_items: list[ExpenseItem],
    debt_items: list[DebtItem],
    tax_profile: TaxProfile | None = None,
) -> dict[str, float]:
    """Compute the shared cash-flow basis used by Today and decision tools."""
    gross_income = sum(float(item.monthly_amount_usd or 0.0) for item in income_items)
    pre_tax_income = sum(
        float(item.monthly_amount_usd or 0.0) for item in income_items if item.is_pre_tax
    )
    federal_rate = float(tax_profile.effective_tax_rate or 0.0) if tax_profile else 0.0
    state_rate = float(tax_profile.state_tax_rate or 0.0) if tax_profile else 0.0
    combined_rate = min(max(federal_rate + state_rate, 0.0), 1.0)
    estimated_taxes = pre_tax_income * combined_rate
    net_income = gross_income - estimated_taxes
    # A debt-linked expense is descriptive context for the obligation, not a
    # second cash-flow charge. Debt.minimum_payment_usd owns that outflow.
    total_expenses = sum(
        float(item.monthly_amount_usd or 0.0)
        for item in expense_items
        if not str(item.linked_debt_id or "").strip()
    )
    total_debt_payments = sum(float(item.minimum_payment_usd or 0.0) for item in debt_items)
    monthly_surplus = net_income - total_expenses - total_debt_payments
    return {
        "gross_income": gross_income,
        "net_income": net_income,
        "estimated_taxes": estimated_taxes,
        "total_expenses": total_expenses,
        "total_debt_payments": total_debt_payments,
        "monthly_surplus": monthly_surplus,
        "savings_rate": (monthly_surplus / gross_income * 100.0) if gross_income > 0 else 0.0,
        "dti": (total_debt_payments / gross_income * 100.0) if gross_income > 0 else 0.0,
    }


def _investable_assets_value(snapshot: PortfolioSnapshot | None) -> float:
    """Market-tradable portfolio value: the home, collectibles, and other
    custom-valued positions are housing/personal property, not money that can
    fund retirement without selling the roof."""
    from buildwealth_orchestrator.services.portfolio_rebalancing import is_untradable_position

    if snapshot is None:
        return 0.0
    if not snapshot.holdings:
        return float(snapshot.total_value_usd or 0.0)
    total = 0.0
    for holding in snapshot.holdings:
        entry = {"asset_type": holding.asset_type, "asset_class": holding.asset_class}
        if is_untradable_position(entry):
            continue
        total += float(holding.value_usd or 0.0)
    cash_in_holdings = sum(
        float(holding.value_usd or 0.0)
        for holding in snapshot.holdings
        if str(holding.asset_class or "").strip().lower() in {"cash", "cash_equivalent"}
        or str(holding.asset_type or "").strip().lower() in {"cash", "money_market"}
    )
    detailed_cash = estimate_liquid_cash_value(snapshot)
    return total + max(0.0, detailed_cash - cash_in_holdings)


def compute_financial_health(
    *,
    income_items: list[IncomeItem],
    expense_items: list[ExpenseItem],
    debt_items: list[DebtItem],
    goal_items: list[GoalItem],
    physical_assets: list[PhysicalAssetItem],
    snapshot: PortfolioSnapshot | None,
    tax_profile: TaxProfile | None = None,
) -> FinancialHealthResponse:
    now = datetime.now(timezone.utc)

    # --- Portfolio & Debt ---
    portfolio_value = portfolio_value_with_cash(snapshot)
    reconciled_assets = reconcile_household_assets(
        portfolio_assets=(holding.model_dump(mode="python") for holding in snapshot.holdings)
        if snapshot is not None
        else (),
        profile_assets=(asset.model_dump(mode="python") for asset in physical_assets),
    )
    # Portfolio total already includes custom-valued property and other
    # physical holdings. Add only Profile assets that do not resolve to one of
    # those positions.
    physical_assets_value = reconciled_assets.profile_only_value_usd
    total_assets = (
        portfolio_value
        + reconciled_assets.portfolio_value_adjustment_usd
        + physical_assets_value
    )
    total_debt = sum(d.balance_usd for d in debt_items)
    net_worth = total_assets - total_debt
    investable_assets = _investable_assets_value(snapshot)
    plan_funding_profile_ids = {
        asset.id for asset in physical_assets if asset.include_in_plan_funding
    }
    plan_funding_assets = sum(
        asset.value_usd
        for asset in reconciled_assets.assets
        if asset.profile_id in plan_funding_profile_ids
    )

    # --- Cash Flow ---
    cash_flow = compute_monthly_cash_flow(
        income_items=income_items,
        expense_items=expense_items,
        debt_items=debt_items,
        tax_profile=tax_profile,
    )
    gross_income = cash_flow["gross_income"]
    net_income = cash_flow["net_income"]
    estimated_taxes = cash_flow["estimated_taxes"]
    total_expenses = cash_flow["total_expenses"]
    total_debt_payments = cash_flow["total_debt_payments"]
    monthly_surplus = cash_flow["monthly_surplus"]

    # --- Ratios ---
    savings_rate = cash_flow["savings_rate"]
    dti = cash_flow["dti"]
    monthly_burn = total_expenses + total_debt_payments
    emergency_fund_value = estimate_liquid_cash_value(snapshot)
    emergency_months = (emergency_fund_value / monthly_burn) if monthly_burn > 0 else 0.0

    # --- Highlights ---
    highlights: list[str] = []
    has_data = gross_income > 0 or total_assets > 0 or total_debt > 0

    if not has_data:
        return FinancialHealthResponse(
            generated_at=now,
            portfolio_value_usd=0.0,
            physical_assets_value_usd=0.0,
            total_assets_usd=0.0,
            total_debt_usd=0.0,
            net_worth_usd=0.0,
            investable_assets_usd=0.0,
            plan_funding_assets_usd=0.0,
            gross_monthly_income_usd=0.0,
            net_monthly_income_usd=0.0,
            estimated_monthly_taxes_usd=0.0,
            total_monthly_expenses_usd=0.0,
            total_monthly_debt_payments_usd=0.0,
            monthly_surplus_usd=0.0,
            savings_rate_pct=0.0,
            debt_to_income_ratio_pct=0.0,
            emergency_fund_months=0.0,
            status="insufficient_data",
            status_detail="Add income, expenses, or sync your portfolio to generate a financial health summary.",
            highlights=["Complete your financial profile to get started."],
            income_item_count=0,
            expense_item_count=0,
            debt_item_count=0,
            goal_item_count=len(goal_items),
            physical_asset_item_count=0,
        )

    if physical_assets_value > 0:
        highlights.append(
            f"Physical assets contribute ${physical_assets_value:,.0f} to net worth."
        )
    if plan_funding_assets > 0:
        highlights.append(
            f"${plan_funding_assets:,.0f} of property is explicitly available for a future plan."
        )

    # Cash flow highlights
    if monthly_surplus > 0:
        highlights.append(f"Monthly surplus of ${monthly_surplus:,.0f} available for saving and investing.")
    elif monthly_surplus < 0:
        highlights.append(f"Monthly deficit of ${abs(monthly_surplus):,.0f} — spending exceeds income.")

    # Savings rate highlights
    if gross_income > 0:
        if savings_rate >= SAVINGS_RATE_HEALTHY:
            highlights.append(f"Savings rate of {savings_rate:.1f}% is strong (target: {SAVINGS_RATE_HEALTHY:.0f}%+).")
        elif savings_rate >= SAVINGS_RATE_ATTENTION:
            highlights.append(f"Savings rate of {savings_rate:.1f}% is moderate — consider targeting {SAVINGS_RATE_HEALTHY:.0f}%+.")
        elif savings_rate > 0:
            highlights.append(f"Savings rate of {savings_rate:.1f}% is low — look for ways to reduce expenses or increase income.")
        else:
            highlights.append("Negative savings rate — outflows exceed income.")

    # Debt highlights
    if total_debt > 0:
        if dti <= DTI_HEALTHY:
            highlights.append(f"Debt-to-income ratio of {dti:.1f}% is manageable.")
        elif dti <= DTI_ATTENTION:
            highlights.append(f"Debt-to-income ratio of {dti:.1f}% is elevated — prioritize debt reduction.")
        else:
            highlights.append(f"Debt-to-income ratio of {dti:.1f}% is high — debt payments are a significant burden.")
    elif len(debt_items) == 0:
        highlights.append("No debt recorded — strong foundation.")

    # Emergency fund highlights
    if portfolio_value > 0 and monthly_burn > 0:
        if emergency_months >= EMERGENCY_HEALTHY:
            highlights.append(f"Liquid cash covers {emergency_months:.1f} months of expenses — solid emergency buffer.")
        elif emergency_months >= EMERGENCY_ATTENTION:
            highlights.append(f"Liquid cash covers {emergency_months:.1f} months of expenses — consider building to {EMERGENCY_HEALTHY:.0f}+ months.")
        else:
            highlights.append(f"Liquid cash covers only {emergency_months:.1f} months of expenses — emergency fund is thin.")

    # --- Overall Status ---
    scores: list[int] = []

    if gross_income > 0:
        if savings_rate >= SAVINGS_RATE_HEALTHY:
            scores.append(2)
        elif savings_rate >= SAVINGS_RATE_ATTENTION:
            scores.append(1)
        else:
            scores.append(0)

        if dti <= DTI_HEALTHY:
            scores.append(2)
        elif dti <= DTI_ATTENTION:
            scores.append(1)
        else:
            scores.append(0)

    if monthly_burn > 0:
        if emergency_months >= EMERGENCY_HEALTHY:
            scores.append(2)
        elif emergency_months >= EMERGENCY_ATTENTION:
            scores.append(1)
        else:
            scores.append(0)

    if not scores:
        status = "insufficient_data"
        status_detail = "Not enough data to assess financial health. Add income and expense information."
    else:
        avg = sum(scores) / len(scores)
        if avg >= 1.5:
            status = "healthy"
            status_detail = "Your financial indicators are in good shape. Keep up the current trajectory."
        elif avg >= 0.8:
            status = "needs_attention"
            status_detail = "Some financial indicators need improvement. Review the highlights for areas to focus on."
        else:
            status = "critical"
            status_detail = "Multiple financial indicators are concerning. Consider reducing expenses or addressing debt."

    return FinancialHealthResponse(
        generated_at=now,
        portfolio_value_usd=round(portfolio_value, 2),
        physical_assets_value_usd=round(physical_assets_value, 2),
        total_assets_usd=round(total_assets, 2),
        total_debt_usd=round(total_debt, 2),
        net_worth_usd=round(net_worth, 2),
        investable_assets_usd=round(investable_assets, 2),
        plan_funding_assets_usd=round(plan_funding_assets, 2),
        gross_monthly_income_usd=round(gross_income, 2),
        net_monthly_income_usd=round(net_income, 2),
        estimated_monthly_taxes_usd=round(estimated_taxes, 2),
        total_monthly_expenses_usd=round(total_expenses, 2),
        total_monthly_debt_payments_usd=round(total_debt_payments, 2),
        monthly_surplus_usd=round(monthly_surplus, 2),
        savings_rate_pct=round(savings_rate, 1),
        debt_to_income_ratio_pct=round(dti, 1),
        emergency_fund_months=round(emergency_months, 1),
        status=status,
        status_detail=status_detail,
        highlights=highlights,
        income_item_count=len(income_items),
        expense_item_count=len(expense_items),
        debt_item_count=len(debt_items),
        goal_item_count=len(goal_items),
        physical_asset_item_count=len(physical_assets),
    )
