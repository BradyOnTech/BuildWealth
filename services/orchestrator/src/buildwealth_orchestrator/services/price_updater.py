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


def _infer_asset_class(symbol: str, quote: dict[str, Any]) -> str | None:
    quote_type = str(quote.get("quote_type") or quote.get("asset_type") or quote.get("type") or "").lower()
    country = str(quote.get("country") or quote.get("region") or "").lower()
    symbol_upper = symbol.upper()

    if "crypto" in quote_type or symbol_upper.endswith("-USD"):
        return "Crypto"
    if "bond" in quote_type:
        return "US Bonds"
    if "money_market" in quote_type or "cash" in quote_type:
        return "Cash"
    if "reit" in quote_type:
        return "REITs"
    if "commodity" in quote_type:
        return "Commodities"

    if "etf" in quote_type:
        if symbol_upper in {"BND", "AGG", "SCHZ", "TLT", "IEF", "VGIT", "BNDX"}:
            return "US Bonds"
        if symbol_upper in {"VXUS", "VEA", "IXUS", "IEFA", "VWO", "IEMG"}:
            return "International Stocks"
        if symbol_upper in {"VNQ", "SCHH", "IYR"}:
            return "REITs"
        if symbol_upper in {"GLD", "IAU", "DBC", "PDBC", "GSG"}:
            return "Commodities"
        return "US Stocks"

    if country and country not in {"us", "usa", "united states"}:
        return "International Stocks"

    if quote_type in {"equity", "stock", "common_stock"}:
        return "US Stocks"

    return None


def _extract_asset_metadata(symbol: str, quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": quote.get("long_name") or quote.get("short_name") or quote.get("name"),
        "asset_type": quote.get("quote_type") or quote.get("asset_type") or quote.get("type"),
        "asset_class": _infer_asset_class(symbol, quote),
        "sector": quote.get("sector"),
        "region": quote.get("country") or quote.get("region"),
    }


async def fetch_prices_and_metadata(
    symbols: list[str],
    research: OpenBBResearchService,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Fetch current prices and basic asset metadata for symbols via OpenBB."""
    prices: dict[str, float] = {}
    metadata_by_symbol: dict[str, dict[str, Any]] = {}

    for symbol in symbols:
        try:
            result = research.get_quote(symbol)
            if isinstance(result, dict):
                price = (
                    result.get("last_price")
                    or result.get("price")
                    or result.get("regular_market_price")
                    or result.get("close")
                    or result.get("prev_close")
                )
                if price is not None:
                    prices[symbol] = float(price)
                metadata = _extract_asset_metadata(symbol, result)
                if any(value for value in metadata.values()):
                    metadata_by_symbol[symbol] = metadata
        except Exception:
            pass

    return prices, metadata_by_symbol


async def refresh_portfolio(
    portfolio_store: PortfolioStore,
    research: OpenBBResearchService,
) -> dict[str, Any]:
    """Fetch prices for all holdings and update the portfolio store."""
    holdings_data = portfolio_store.get_holdings()
    symbols: set[str] = set()
    for key, holding in holdings_data.get("holdings", {}).items():
        symbol = str(holding.get("symbol") or key).upper().strip()
        if symbol:
            symbols.add(symbol)

    if not symbols:
        return holdings_data

    prices, metadata_by_symbol = await fetch_prices_and_metadata(sorted(symbols), research)
    if metadata_by_symbol:
        portfolio_store.upsert_asset_metadata_bulk(metadata_by_symbol)
    return portfolio_store.update_prices(prices)


def build_snapshot_from_holdings(holdings_data: dict[str, Any]) -> PortfolioSnapshot:
    """Convert portfolio store holdings into a PortfolioSnapshot for compatibility."""
    holdings_map = holdings_data.get("holdings", {})
    total_value = holdings_data.get("total_value", 0.0)
    total_cost = holdings_data.get("total_cost_basis", 0.0)
    performance = holdings_data.get("performance", {})

    aggregated = holdings_data.get("holdings_by_symbol", {})
    if not isinstance(aggregated, dict):
        aggregated = {}
    if not aggregated and isinstance(holdings_map, dict):
        for key, holding in holdings_map.items():
            symbol = str(holding.get("symbol") or key).upper().strip()
            if not symbol:
                continue
            bucket = aggregated.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "name": holding.get("name"),
                    "data_source": holding.get("data_source") or holding.get("price_source"),
                    "asset_type": holding.get("asset_type"),
                    "asset_class": holding.get("asset_class"),
                    "sector": holding.get("sector"),
                    "region": holding.get("region"),
                    "quantity": 0.0,
                    "cost_basis": 0.0,
                    "current_value": 0.0,
                    "current_price": None,
                },
            )
            quantity = float(holding.get("quantity") or 0.0)
            bucket["quantity"] += quantity
            bucket["cost_basis"] += float(holding.get("cost_basis") or 0.0)
            bucket["current_value"] += float(holding.get("current_value") or 0.0)
            if bucket.get("current_price") is None and holding.get("current_price") is not None:
                bucket["current_price"] = holding.get("current_price")
            for field in ("name", "asset_type", "asset_class", "sector", "region"):
                if not bucket.get(field) and holding.get(field):
                    bucket[field] = holding.get(field)
            if not bucket.get("data_source"):
                bucket["data_source"] = holding.get("data_source") or holding.get("price_source")

    holdings: list[Holding] = []
    for symbol, holding in aggregated.items():
        value = float(holding.get("current_value") or 0.0)
        alloc = (value / total_value * 100) if total_value > 0 else 0.0
        cost = float(holding.get("cost_basis") or 0.0)
        perf = value - cost if value else None
        perf_pct = (perf / cost * 100) if cost > 0 and perf is not None else None

        holdings.append(
            Holding(
                symbol=symbol,
                name=holding.get("name") or symbol,
                data_source=holding.get("data_source"),
                asset_type=holding.get("asset_type"),
                asset_class=holding.get("asset_class"),
                sector=holding.get("sector"),
                region=holding.get("region"),
                value_usd=value,
                allocation_percent=round(alloc, 2),
                quantity=float(holding.get("quantity") or 0.0),
                market_price=holding.get("current_price"),
                net_performance_usd=round(perf, 2) if perf is not None else None,
                net_performance_percent=round(perf_pct, 2) if perf_pct is not None else None,
            )
        )

    holdings.sort(key=lambda x: x.value_usd, reverse=True)

    as_of = performance.get("as_of") or holdings_data.get("prices_updated_at")

    return PortfolioSnapshot(
        as_of=(
            datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
            if as_of
            else datetime.now(timezone.utc)
        ),
        base_currency=str(holdings_data.get("base_currency") or "USD"),
        total_value_usd=total_value,
        total_investment_usd=total_cost,
        net_performance_usd=round(total_value - total_cost, 2),
        net_performance_percent=round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0.0,
        twr_return_pct=performance.get("twr_return_pct"),
        twr_annualized_return_pct=performance.get("twr_annualized_return_pct"),
        xirr_annualized_return_pct=performance.get("xirr_annualized_return_pct"),
        price_return_usd=performance.get("price_return_usd"),
        income_return_usd=performance.get("income_return_usd"),
        total_return_usd=performance.get("total_return_usd"),
        price_return_pct=performance.get("price_return_pct"),
        income_return_pct=performance.get("income_return_pct"),
        total_return_pct=performance.get("total_return_pct"),
        holdings=holdings,
        accounts=holdings_data.get("accounts", []),
        raw={
            "portfolio_performance": performance,
            "account_totals": holdings_data.get("account_totals", {}),
        },
    )
