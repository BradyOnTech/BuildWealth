"""Housing exposure — the home gets its own honest lens.

The diversification score deliberately excludes the primary residence: a home
is housing first, and you cannot rebalance a kitchen. But the exposure is
real — value, mortgage, equity, and the fact that it all sits in one property
in one local market. This payload names that plainly, separate from invested
money, for research and understanding only.
"""

from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.household_assets import reconcile_household_assets

_MORTGAGE_HINTS = ("mortgage", "home", "house", "heloc", "property")


def _safe(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result else 0.0


def _looks_like_mortgage(label: str) -> bool:
    lowered = label.strip().lower()
    return any(hint in lowered for hint in _MORTGAGE_HINTS)


def build_housing_exposure_payload(
    holdings: dict[str, Any],
    *,
    debt_items: list[dict[str, Any]] | None = None,
    physical_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reconciliation = reconcile_household_assets(
        portfolio_assets=(entry for entry in holdings.values() if isinstance(entry, dict)),
        profile_assets=physical_assets,
    )
    properties = [
        {"label": asset.label, "value_usd": round(asset.value_usd, 2)}
        for asset in reconciliation.assets
        if asset.is_housing
    ]
    other_assets_total = sum(asset.value_usd for asset in reconciliation.assets if not asset.is_housing)

    if not properties:
        return {
            "status": "none",
            "properties": [],
            "home_value_usd": 0.0,
            "mortgage_balance_usd": 0.0,
            "equity_usd": None,
            "loan_to_value_pct": None,
            "share_of_total_assets_pct": None,
            "notes": [],
        }

    home_value = sum(_safe(row["value_usd"]) for row in properties)

    mortgage_balance = 0.0
    mortgage_rate: float | None = None
    saw_mortgage = False
    for debt in debt_items or []:
        if not isinstance(debt, dict):
            continue
        if not _looks_like_mortgage(str(debt.get("label") or "")):
            continue
        saw_mortgage = True
        mortgage_balance += _safe(debt.get("balance_usd"))
        rate = debt.get("interest_rate")
        if mortgage_rate is None and rate is not None:
            mortgage_rate = _safe(rate)

    equity = home_value - mortgage_balance if saw_mortgage else None
    total_assets = home_value + other_assets_total
    share_pct = (home_value / total_assets * 100.0) if total_assets > 0 else None
    ltv_pct = (mortgage_balance / home_value * 100.0) if saw_mortgage and home_value > 0 else None

    notes: list[str] = []
    if len(properties) == 1:
        notes.append(
            "This is one property in one place — its value moves with one local market, "
            "and it can't be trimmed or rebalanced like invested money."
        )
    else:
        notes.append(
            f"{len(properties)} properties. Each moves with its own local market and "
            "can't be trimmed or rebalanced like invested money."
        )
    if share_pct is not None and share_pct >= 50:
        notes.append(
            f"Housing is {share_pct:.0f}% of everything you own. That's common for homeowners — "
            "worth knowing when reading the portfolio numbers, which cover invested money only."
        )
    if saw_mortgage and equity is not None and home_value > 0:
        notes.append(
            f"Equity is what's yours after the loan: ${equity:,.0f} of the ${home_value:,.0f} value."
        )
    if not saw_mortgage:
        notes.append(
            "No mortgage recorded. If there is one, add it under Profile → Debts and "
            "this becomes an equity picture instead of just a value."
        )
    notes.append("For understanding only — nothing here is a recommendation to buy or sell a home.")

    return {
        "status": "ready",
        "properties": sorted(properties, key=lambda row: -_safe(row["value_usd"])),
        "home_value_usd": round(home_value, 2),
        "mortgage_balance_usd": round(mortgage_balance, 2),
        "equity_usd": round(equity, 2) if equity is not None else None,
        "loan_to_value_pct": round(ltv_pct, 1) if ltv_pct is not None else None,
        "share_of_total_assets_pct": round(share_pct, 1) if share_pct is not None else None,
        "mortgage_interest_rate": mortgage_rate,
        "notes": notes,
    }
