"""Fetch current prices for portfolio holdings and build snapshots.

Uses the OpenBB research service for BuildWealth market data.
as the price source.
"""

from __future__ import annotations

# FX pair fallback and historical-rate lookup flow implemented for BuildWealth portfolio workflows:
# apps/api/src/services/exchange-rate-data/exchange-rate-data.service.ts

from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.research import OpenBBResearchService


def _extract_quote_price(quote: dict[str, Any]) -> float | None:
    for key in ("market_price", "regular_market_price", "last_price", "price", "close", "prev_close"):
        value = quote.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def _extract_history_row_rate(row: dict[str, Any]) -> tuple[str | None, float | None]:
    date_value = row.get("date") or row.get("datetime") or row.get("timestamp")
    if date_value is None:
        return None, None
    date_text = str(date_value).strip()
    if not date_text:
        return None, None
    date_string = date_text[:10]

    for key in ("close", "adj_close", "last", "market_price", "price"):
        value = row.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return date_string, parsed
    return date_string, None


def _fx_symbol_candidates(currency_from: str, currency_to: str) -> list[tuple[str, bool]]:
    direct = f"{currency_from}{currency_to}"
    inverse = f"{currency_to}{currency_from}"
    return [
        (f"{direct}=X", False),
        (f"{inverse}=X", True),
        (direct, False),
        (inverse, True),
    ]


def _fx_history_period(start_date: datetime | None) -> str:
    if start_date is None:
        return "1y"
    days = max((datetime.now(timezone.utc) - start_date).days, 1)
    if days <= 31:
        return "1mo"
    if days <= 93:
        return "3mo"
    if days <= 186:
        return "6mo"
    if days <= 370:
        return "1y"
    if days <= 730:
        return "2y"
    if days <= 1825:
        return "5y"
    return "max"


def _parse_start_date(transactions: list[dict[str, Any]]) -> datetime | None:
    earliest: datetime | None = None
    for transaction in transactions:
        raw_date = str(transaction.get("date") or "").strip()
        if not raw_date:
            continue
        normalized = raw_date if "T" in raw_date else f"{raw_date}T00:00:00+00:00"
        normalized = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        if earliest is None or parsed < earliest:
            earliest = parsed
    return earliest


def _collect_portfolio_currencies(holdings_data: dict[str, Any]) -> tuple[str, set[str]]:
    base_currency = str(holdings_data.get("base_currency") or "USD").upper()
    currencies: set[str] = set()
    accounts = holdings_data.get("accounts", [])
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            currency = str(account.get("currency") or "").strip().upper()
            if currency:
                currencies.add(currency)
    holdings = holdings_data.get("holdings", {})
    if isinstance(holdings, dict):
        for row in holdings.values():
            if not isinstance(row, dict):
                continue
            currency = str(row.get("currency") or "").strip().upper()
            if currency:
                currencies.add(currency)
    currencies.discard(base_currency)
    return base_currency, currencies


def _fetch_latest_fx_rate(currency: str, base_currency: str, research: OpenBBResearchService) -> float | None:
    for symbol, invert in _fx_symbol_candidates(currency, base_currency):
        quote = research.get_quote(symbol)
        if not isinstance(quote, dict) or not quote:
            continue
        price = _extract_quote_price(quote)
        if price is None or price <= 0:
            continue
        return (1.0 / price) if invert else price
    return None


def _fetch_historical_fx_rates(
    *,
    currency: str,
    base_currency: str,
    period: str,
    research: OpenBBResearchService,
) -> dict[str, float]:
    for symbol, invert in _fx_symbol_candidates(currency, base_currency):
        rows = research.get_price_history(symbol, period=period, interval="1d")
        if not rows:
            continue
        rates_by_date: dict[str, float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            date_string, price = _extract_history_row_rate(row)
            if date_string is None or price is None or price <= 0:
                continue
            rate = (1.0 / price) if invert else price
            if rate <= 0:
                continue
            rates_by_date[date_string] = round(float(rate), 8)
        if rates_by_date:
            return dict(sorted(rates_by_date.items()))
    return {}


def refresh_fx_for_portfolio(
    *,
    portfolio_store: PortfolioStore,
    research: OpenBBResearchService,
    holdings_data: dict[str, Any],
) -> dict[str, Any]:
    base_currency, currencies = _collect_portfolio_currencies(holdings_data)
    if not currencies:
        return {
            "base_currency": base_currency,
            "rates_updated": 0,
            "history_updated": 0,
        }

    transactions = portfolio_store.list_transactions(limit=5000)
    start_date = _parse_start_date(transactions)
    period = _fx_history_period(start_date)

    rates_by_currency: dict[str, float] = {}
    history_by_currency: dict[str, dict[str, float]] = {}

    for currency in sorted(currencies):
        latest = _fetch_latest_fx_rate(currency, base_currency, research)
        if latest is not None and latest > 0:
            rates_by_currency[currency] = round(latest, 8)
        history = _fetch_historical_fx_rates(
            currency=currency,
            base_currency=base_currency,
            period=period,
            research=research,
        )
        if history:
            history_by_currency[currency] = history

    if rates_by_currency or history_by_currency:
        portfolio_store.update_fx_market_data(
            rates_by_currency=rates_by_currency,
            history_by_currency=history_by_currency,
            base_currency=base_currency,
        )

    return {
        "base_currency": base_currency,
        "rates_updated": len(rates_by_currency),
        "history_updated": len(history_by_currency),
        "history_period": period,
    }


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
    refresh_fx_for_portfolio(
        portfolio_store=portfolio_store,
        research=research,
        holdings_data=holdings_data,
    )
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
                    "metadata_source": holding.get("metadata_source"),
                    "expense_ratio": holding.get("expense_ratio"),
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
            for field in ("name", "asset_type", "asset_class", "sector", "region", "metadata_source", "expense_ratio"):
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
                metadata_source=holding.get("metadata_source"),
                expense_ratio=holding.get("expense_ratio"),
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
