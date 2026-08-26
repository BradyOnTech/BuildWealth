"""Fund look-through route: constituent-level exposure and overlap.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_portfolio_look_through",
]


@router.get("/api/portfolio/look-through")
def get_portfolio_look_through(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Estimated company / sector / region exposure once covered funds are opened up."""
    from buildwealth_orchestrator.services.fund_composition import FundCompositionService

    resolved_services = m.route_workspace_services(services, permission="portfolio.read")
    return FundCompositionService().look_through_report(
        (
            resolved_services.current_portfolio()
            if isinstance(resolved_services, m.WorkspaceServices)
            else resolved_services.portfolio_store.get_holdings()
        )
    )
