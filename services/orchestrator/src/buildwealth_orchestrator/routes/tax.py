"""Tax strategy routes: loss-harvesting candidates and Roth conversion ladders.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_tax_loss_harvest_report",
    "build_roth_ladder",
]


@router.get("/api/tax/loss-harvest")
def get_tax_loss_harvest_report(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Taxable lots below basis, with wash-sale flags and estimated benefit."""
    from buildwealth_orchestrator.services.tax_strategy import build_tax_loss_harvest_report

    resolved_services = m.route_workspace_services(services, permission="portfolio.read")
    return build_tax_loss_harvest_report(
        holdings_payload=(
            resolved_services.current_portfolio()
            if isinstance(resolved_services, m.WorkspaceServices)
            else resolved_services.portfolio_store.get_holdings()
        ),
        transactions=resolved_services.portfolio_store.list_transactions(limit=2000),
        profile_payload=resolved_services.financial_profile_store.load(),
    )


@router.post("/api/tax/roth-ladder")
def build_roth_ladder(
    request: dict[str, m.Any],
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Fill-the-bracket Roth conversion schedule priced with the tax engine.

    Filing status, state rate, and income default from the financial profile;
    every input can be overridden in the request body.
    """
    from datetime import datetime, timezone

    from buildwealth_orchestrator.services.peer_benchmark import _age_from_profile
    from buildwealth_orchestrator.services.tax_strategy import build_roth_conversion_ladder

    resolved_services = m.route_workspace_services(services, permission="profile.read")
    profile = resolved_services.financial_profile_store.load()
    tax_profile = profile.get("tax_profile") if isinstance(profile.get("tax_profile"), dict) else {}

    income_default = 0.0
    for item in profile.get("income_items") or []:
        if isinstance(item, dict):
            income_default += float(item.get("annual_amount_usd") or 0.0) or (
                float(item.get("monthly_amount_usd") or 0.0) * 12.0
            )

    def _num(key: str, fallback: float) -> float:
        try:
            return float(request.get(key)) if request.get(key) is not None else fallback
        except (TypeError, ValueError):
            return fallback

    return build_roth_conversion_ladder(
        traditional_balance_usd=_num("traditional_balance_usd", 0.0),
        filing_status=str(
            request.get("filing_status") or tax_profile.get("filing_status") or "single"
        ),
        annual_ordinary_income_usd=_num("annual_ordinary_income_usd", income_default),
        target_bracket_rate=_num("target_bracket_rate", 0.24),
        years=int(_num("years", 10)),
        annual_growth_rate=_num("annual_growth_rate", 0.05),
        state_tax_rate=_num("state_tax_rate", float(tax_profile.get("state_tax_rate") or 0.0)),
        age=int(_num("age", 0))
        or _age_from_profile(profile, current_year=datetime.now(timezone.utc).year),
    )
