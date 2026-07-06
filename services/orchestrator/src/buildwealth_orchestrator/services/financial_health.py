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
)

# Thresholds for health assessment
SAVINGS_RATE_HEALTHY = 20.0      # >= 20% savings rate is healthy
SAVINGS_RATE_ATTENTION = 10.0    # >= 10% is needs_attention, below is critical
DTI_HEALTHY = 20.0               # <= 20% DTI is healthy
DTI_ATTENTION = 36.0             # <= 36% is needs_attention, above is critical
EMERGENCY_HEALTHY = 6.0          # >= 6 months is healthy
EMERGENCY_ATTENTION = 3.0        # >= 3 months is needs_attention

LIQUID_ACCOUNT_TYPES = {"depository", "checking", "savings", "cash", "money_market", "taxable", "brokerage"}
ILLIQUID_ACCOUNT_TYPES = {"401k", "ira", "roth_ira", "traditional_ira", "hsa", "real_estate"}


def _estimate_emergency_fund_value(snapshot: PortfolioSnapshot | None) -> float:
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
    return total


def compute_financial_health(
    *,
    income_items: list[IncomeItem],
    expense_items: list[ExpenseItem],
    debt_items: list[DebtItem],
    goal_items: list[GoalItem],
    physical_assets: list[PhysicalAssetItem],
    snapshot: PortfolioSnapshot | None,
) -> FinancialHealthResponse:
    now = datetime.now(timezone.utc)

    # --- Portfolio & Debt ---
    portfolio_value = snapshot.total_value_usd if snapshot else 0.0
    physical_assets_value = sum(asset.current_value_usd for asset in physical_assets)
    total_assets = portfolio_value + physical_assets_value
    total_debt = sum(d.balance_usd for d in debt_items)
    net_worth = total_assets - total_debt
    investable_assets = _investable_assets_value(snapshot)

    # --- Cash Flow ---
    gross_income = sum(i.monthly_amount_usd for i in income_items)
    total_expenses = sum(e.monthly_amount_usd for e in expense_items)
    total_debt_payments = sum(d.minimum_payment_usd or 0.0 for d in debt_items)
    monthly_surplus = gross_income - total_expenses - total_debt_payments

    # --- Ratios ---
    savings_rate = (monthly_surplus / gross_income * 100.0) if gross_income > 0 else 0.0
    dti = (total_debt_payments / gross_income * 100.0) if gross_income > 0 else 0.0
    monthly_burn = total_expenses + total_debt_payments
    emergency_fund_value = _estimate_emergency_fund_value(snapshot)
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
            gross_monthly_income_usd=0.0,
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
        gross_monthly_income_usd=round(gross_income, 2),
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
