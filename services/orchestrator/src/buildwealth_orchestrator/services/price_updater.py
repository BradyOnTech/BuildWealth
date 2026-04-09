"""Fetch current prices for portfolio holdings and build snapshots.

Uses the OpenBB research service for market data, replacing Ghostfolio
as the price source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.research import OpenBBResearchService


async def fetch_prices(
    symbols: list[str],
    research: OpenBBResearchService,
) -> dict[str, float]:
    """Fetch current prices for a list of symbols via OpenBB."""
    prices: dict[str, float] = {}
    for symbol in symbols:
        try:
            result = research.get_quote(symbol)
            if isinstance(result, dict):
                # Try common quote fields
                price = (
                    result.get("last_price")
                    or result.get("price")
                    or result.get("regular_market_price")
                    or result.get("close")
                    or result.get("prev_close")
                )
                if price is not None:
                    prices[symbol] = float(price)
        except Exception:
            pass  # Skip symbols that fail — prices dict just won't have them
    return prices


async def refresh_portfolio(
    portfolio_store: PortfolioStore,
    research: OpenBBResearchService,
) -> dict[str, Any]:
    """Fetch prices for all holdings and update the portfolio store."""
    holdings_data = portfolio_store.get_holdings()
    symbols = list(holdings_data.get("holdings", {}).keys())

    if not symbols:
        return holdings_data

    prices = await fetch_prices(symbols, research)
    return portfolio_store.update_prices(prices)


def build_snapshot_from_holdings(holdings_data: dict[str, Any]) -> PortfolioSnapshot:
    """Convert portfolio store holdings into a PortfolioSnapshot for compatibility."""
    holdings_map = holdings_data.get("holdings", {})
    total_value = holdings_data.get("total_value", 0.0)
    total_cost = holdings_data.get("total_cost_basis", 0.0)

    holdings: list[Holding] = []
    for sym, h in holdings_map.items():
        value = h.get("current_value") or 0.0
        alloc = (value / total_value * 100) if total_value > 0 else 0.0
        cost = h.get("cost_basis", 0.0)
        perf = value - cost if value else None
        perf_pct = (perf / cost * 100) if cost > 0 and perf is not None else None

        holdings.append(Holding(
            symbol=sym,
            name=sym,  # We don't store names; UI can look up via research_quote
            value_usd=value,
            allocation_percent=round(alloc, 2),
            quantity=h.get("quantity", 0),
            market_price=h.get("current_price"),
            net_performance_usd=round(perf, 2) if perf is not None else None,
            net_performance_percent=round(perf_pct, 2) if perf_pct is not None else None,
        ))

    holdings.sort(key=lambda x: x.value_usd, reverse=True)

    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        total_value_usd=total_value,
        total_investment_usd=total_cost,
        net_performance_usd=round(total_value - total_cost, 2),
        net_performance_percent=round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0.0,
        holdings=holdings,
    )
