"""Historical snapshot backfill using transaction replay and daily pricing.

Adapted from Ghostfolio (MIT):
- apps/api/src/app/portfolio/calculator/portfolio-calculator.ts
- apps/api/src/helper/portfolio.helper.ts
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.research import OpenBBResearchService
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _parse_txn_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    base = text[:10]
    try:
        return datetime.fromisoformat(base).date()
    except ValueError:
        return None


def _daily_range(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _history_period(start_date: date, end_date: date) -> str:
    days = max((end_date - start_date).days, 1)
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


def _extract_price_row(row: dict[str, Any]) -> tuple[str | None, float | None]:
    date_value = row.get("date") or row.get("datetime") or row.get("timestamp")
    if date_value is None:
        return None, None
    date_text = str(date_value).strip()
    if not date_text:
        return None, None
    date_key = date_text[:10]

    for key in ("close", "adj_close", "last", "market_price", "price"):
        value = row.get(key)
        if value is None:
            continue
        parsed = _safe_float(value, None)
        if parsed is None or parsed <= 0:
            continue
        return date_key, parsed

    return date_key, None


def _extract_quote_price(quote: dict[str, Any]) -> float | None:
    for key in ("market_price", "regular_market_price", "last_price", "price", "close", "prev_close"):
        value = quote.get(key)
        parsed = _safe_float(value, None)
        if parsed is None or parsed <= 0:
            continue
        return parsed
    return None


def _fill_daily_series(
    *,
    sparse_by_date: dict[str, float],
    start_date: date,
    end_date: date,
    fallback_price: float | None = None,
) -> dict[str, float]:
    if not sparse_by_date and fallback_price is None:
        return {}

    date_keys = [d.isoformat() for d in _daily_range(start_date, end_date)]
    if sparse_by_date:
        latest_date = max(sparse_by_date.keys())
        previous = sparse_by_date[latest_date]
    else:
        previous = fallback_price

    filled: dict[str, float] = {}
    for key in reversed(date_keys):
        if key in sparse_by_date and sparse_by_date[key] > 0:
            previous = sparse_by_date[key]
            filled[key] = previous
        elif previous is not None and previous > 0:
            filled[key] = previous

    return {key: filled[key] for key in date_keys if key in filled}


def _fx_rate_to_base_on_date(
    *,
    currency: str,
    date_key: str,
    base_currency: str,
    rates: dict[str, float],
    history_pairs: dict[str, dict[str, float]],
) -> float:
    normalized = _normalize_symbol(currency) or base_currency
    if normalized == base_currency:
        return 1.0

    pair = f"{normalized}{base_currency}"
    daily = history_pairs.get(pair)
    if isinstance(daily, dict) and daily:
        if date_key in daily and daily[date_key] > 0:
            return float(daily[date_key])
        prior_dates = [item for item in daily.keys() if item <= date_key]
        if prior_dates:
            return float(daily[max(prior_dates)])
        return float(daily[min(daily.keys())])

    reverse_pair = f"{base_currency}{normalized}"
    reverse_daily = history_pairs.get(reverse_pair)
    if isinstance(reverse_daily, dict) and reverse_daily:
        if date_key in reverse_daily and reverse_daily[date_key] > 0:
            return 1.0 / float(reverse_daily[date_key])
        prior_dates = [item for item in reverse_daily.keys() if item <= date_key]
        if prior_dates:
            value = float(reverse_daily[max(prior_dates)])
            if value > 0:
                return 1.0 / value
        value = float(reverse_daily[min(reverse_daily.keys())])
        if value > 0:
            return 1.0 / value

    fallback = _safe_float(rates.get(normalized), None)
    if fallback is None or fallback <= 0:
        return 1.0
    return fallback


def _snapshot_path(snapshot_dir: Path, as_of: datetime) -> Path:
    return snapshot_dir / as_of.strftime("snapshot-%Y%m%dT%H%M%SZ.json")


def backfill_snapshot_history(
    *,
    portfolio_store: PortfolioStore,
    snapshot_store: SnapshotStore,
    research: OpenBBResearchService,
    start_date: date | None = None,
    end_date: date | None = None,
    days: int | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    transactions = portfolio_store.list_transactions(limit=50_000)
    if not transactions:
        return {
            "days_written": 0,
            "days_skipped": 0,
            "symbols": 0,
            "start_date": None,
            "end_date": None,
            "period": None,
        }

    sorted_txns = sorted(
        transactions,
        key=lambda row: (str(row.get("date", "")), str(row.get("created_at", "")), str(row.get("id", ""))),
    )
    txn_dates = [_parse_txn_date(row.get("date")) for row in sorted_txns]
    txn_dates = [value for value in txn_dates if value is not None]
    if not txn_dates:
        return {
            "days_written": 0,
            "days_skipped": 0,
            "symbols": 0,
            "start_date": None,
            "end_date": None,
            "period": None,
        }

    first_txn_date = min(txn_dates)
    last_day = end_date or datetime.now(timezone.utc).date()

    if days is not None and days > 0:
        range_start = max(first_txn_date, last_day - timedelta(days=max(days - 1, 0)))
    else:
        range_start = first_txn_date

    if start_date is not None:
        range_start = max(range_start, start_date)
    if range_start > last_day:
        return {
            "days_written": 0,
            "days_skipped": 0,
            "symbols": 0,
            "start_date": range_start.isoformat(),
            "end_date": last_day.isoformat(),
            "period": None,
        }

    holdings_payload = portfolio_store.get_holdings()
    accounts = holdings_payload.get("accounts", [])
    metadata_map = portfolio_store.get_asset_metadata_map()
    manual_prices = holdings_payload.get("manual_prices", {}) if isinstance(holdings_payload.get("manual_prices"), dict) else {}

    base_currency = _normalize_symbol(holdings_payload.get("base_currency")) or "USD"
    fx_rates_payload = portfolio_store.get_fx_rates()
    fx_history_payload = portfolio_store.get_fx_rates_history()
    rates = fx_rates_payload.get("rates", {}) if isinstance(fx_rates_payload.get("rates"), dict) else {}
    rates = {(_normalize_symbol(currency) or base_currency): _safe_float(rate, 1.0) for currency, rate in rates.items()}
    rates[base_currency] = 1.0

    history_pairs_raw = fx_history_payload.get("pairs", {}) if isinstance(fx_history_payload.get("pairs"), dict) else {}
    history_pairs: dict[str, dict[str, float]] = {}
    for pair, date_map in history_pairs_raw.items():
        normalized_pair = _normalize_symbol(pair)
        if len(normalized_pair) != 6 or not isinstance(date_map, dict):
            continue
        history_pairs[normalized_pair] = {
            str(key): _safe_float(value, 0.0)
            for key, value in date_map.items()
            if _safe_float(value, 0.0) > 0
        }

    symbols: set[str] = set()
    fallback_price_by_symbol: dict[str, float] = {}
    for row in sorted_txns:
        symbol = _normalize_symbol(row.get("symbol"))
        action = _normalize_symbol(row.get("action"))
        if not symbol or symbol == "CASH":
            continue
        if action in {"TRANSFER_IN", "TRANSFER_OUT", "CASH_DEPOSIT", "CASH_WITHDRAW"}:
            continue
        symbols.add(symbol)
        fallback_price = _safe_float(row.get("unit_price"), 0.0)
        if fallback_price > 0:
            fallback_price_by_symbol[symbol] = fallback_price

    period = _history_period(range_start, last_day)
    price_series_by_symbol: dict[str, dict[str, float]] = {}
    for symbol in sorted(symbols):
        history_rows = research.get_price_history(symbol, period=period, interval="1d")
        sparse: dict[str, float] = {}
        for row in history_rows:
            if not isinstance(row, dict):
                continue
            date_key, price = _extract_price_row(row)
            if date_key is None or price is None or price <= 0:
                continue
            sparse[date_key] = price

        quote = research.get_quote(symbol)
        quote_price = _extract_quote_price(quote) if isinstance(quote, dict) else None
        if quote_price is not None and quote_price > 0:
            sparse[last_day.isoformat()] = quote_price

        manual_entry = manual_prices.get(symbol) if isinstance(manual_prices.get(symbol), dict) else None
        manual_price = _safe_float(manual_entry.get("price"), None) if manual_entry else None
        fallback = manual_price or fallback_price_by_symbol.get(symbol)

        price_series_by_symbol[symbol] = _fill_daily_series(
            sparse_by_date=sparse,
            start_date=range_start,
            end_date=last_day,
            fallback_price=fallback,
        )

    txns_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in sorted_txns:
        txn_date = _parse_txn_date(row.get("date"))
        if txn_date is None:
            continue
        key = txn_date.isoformat()
        txns_by_date.setdefault(key, []).append(row)

    positions: dict[str, dict[str, Any]] = {}
    account_cash_base: dict[str, float] = {}

    days_written = 0
    days_skipped = 0
    for day in _daily_range(range_start, last_day):
        day_key = day.isoformat()
        day_txns = txns_by_date.get(day_key, [])
        for txn in day_txns:
            action = _normalize_symbol(txn.get("action"))
            symbol = _normalize_symbol(txn.get("symbol"))
            account_id = str(txn.get("account") or "default")
            quantity = abs(_safe_float(txn.get("quantity"), 0.0))
            unit_price_native = abs(_safe_float(txn.get("unit_price"), 0.0))
            fee_native = abs(_safe_float(txn.get("fee"), 0.0))
            currency = _normalize_symbol(txn.get("currency")) or base_currency
            fx_rate = _fx_rate_to_base_on_date(
                currency=currency,
                date_key=day_key,
                base_currency=base_currency,
                rates=rates,
                history_pairs=history_pairs,
            )

            gross_base = quantity * unit_price_native * fx_rate
            fee_base = fee_native * fx_rate

            if action in {"TRANSFER_IN", "CASH_DEPOSIT"}:
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) + gross_base
                continue
            if action in {"TRANSFER_OUT", "CASH_WITHDRAW"}:
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) - gross_base
                continue

            if not symbol or symbol == "CASH":
                continue

            position_key = f"{account_id}:{symbol}"
            if position_key not in positions:
                metadata = metadata_map.get(symbol, {}) if isinstance(metadata_map, dict) else {}
                positions[position_key] = {
                    "account": account_id,
                    "symbol": symbol,
                    "currency": currency,
                    "quantity": 0.0,
                    "investment_base": 0.0,
                    "name": metadata.get("name") if isinstance(metadata, dict) else None,
                    "asset_type": metadata.get("asset_type") if isinstance(metadata, dict) else None,
                    "asset_class": metadata.get("asset_class") if isinstance(metadata, dict) else None,
                    "sector": metadata.get("sector") if isinstance(metadata, dict) else None,
                    "region": metadata.get("region") if isinstance(metadata, dict) else None,
                    "data_source": metadata.get("data_source") if isinstance(metadata, dict) else None,
                }

            position = positions[position_key]

            if action == "BUY":
                if quantity <= 0:
                    continue
                position["quantity"] = _safe_float(position.get("quantity"), 0.0) + quantity
                position["investment_base"] = _safe_float(position.get("investment_base"), 0.0) + gross_base + fee_base
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) - (gross_base + fee_base)
            elif action == "SELL":
                available_qty = _safe_float(position.get("quantity"), 0.0)
                sell_qty = min(quantity, available_qty)
                if sell_qty <= 0:
                    continue
                avg_cost = (_safe_float(position.get("investment_base"), 0.0) / available_qty) if available_qty > 0 else 0.0
                position["quantity"] = max(available_qty - sell_qty, 0.0)
                position["investment_base"] = max(_safe_float(position.get("investment_base"), 0.0) - (sell_qty * avg_cost), 0.0)
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) + (gross_base - fee_base)
                if position["quantity"] <= 1e-9:
                    position["quantity"] = 0.0
                    position["investment_base"] = 0.0
            elif action == "STOCK_SPLIT":
                split_factor = quantity
                if split_factor > 0:
                    position["quantity"] = _safe_float(position.get("quantity"), 0.0) * split_factor
            elif action == "MERGER":
                available_qty = _safe_float(position.get("quantity"), 0.0)
                merge_qty = min(quantity if quantity > 0 else available_qty, available_qty)
                if merge_qty <= 0:
                    continue
                avg_cost = (_safe_float(position.get("investment_base"), 0.0) / available_qty) if available_qty > 0 else 0.0
                position["quantity"] = max(available_qty - merge_qty, 0.0)
                position["investment_base"] = max(_safe_float(position.get("investment_base"), 0.0) - (merge_qty * avg_cost), 0.0)
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) + (gross_base - fee_base)
                if position["quantity"] <= 1e-9:
                    position["quantity"] = 0.0
                    position["investment_base"] = 0.0
            elif action in {"DIVIDEND", "INTEREST"}:
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) + (gross_base - fee_base)
            elif action == "FEE":
                charge = fee_base if fee_base > 0 else gross_base
                account_cash_base[account_id] = account_cash_base.get(account_id, 0.0) - charge

        aggregated_by_symbol: dict[str, dict[str, Any]] = {}
        total_value = 0.0
        total_investment = 0.0
        for position in positions.values():
            quantity = _safe_float(position.get("quantity"), 0.0)
            if quantity <= 1e-9:
                continue
            symbol = str(position.get("symbol"))
            currency = _normalize_symbol(position.get("currency")) or base_currency

            native_price = price_series_by_symbol.get(symbol, {}).get(day_key)
            if native_price is None:
                investment_base = _safe_float(position.get("investment_base"), 0.0)
                fx_rate = _fx_rate_to_base_on_date(
                    currency=currency,
                    date_key=day_key,
                    base_currency=base_currency,
                    rates=rates,
                    history_pairs=history_pairs,
                )
                native_price = (investment_base / quantity / fx_rate) if quantity > 0 and fx_rate > 0 else 0.0

            fx_rate = _fx_rate_to_base_on_date(
                currency=currency,
                date_key=day_key,
                base_currency=base_currency,
                rates=rates,
                history_pairs=history_pairs,
            )
            market_price_base = native_price * fx_rate
            value_base = quantity * market_price_base
            investment_base = _safe_float(position.get("investment_base"), 0.0)

            bucket = aggregated_by_symbol.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "name": position.get("name") or symbol,
                    "data_source": position.get("data_source"),
                    "asset_type": position.get("asset_type"),
                    "asset_class": position.get("asset_class"),
                    "sector": position.get("sector"),
                    "region": position.get("region"),
                    "quantity": 0.0,
                    "value_base": 0.0,
                    "investment_base": 0.0,
                },
            )
            bucket["quantity"] += quantity
            bucket["value_base"] += value_base
            bucket["investment_base"] += investment_base
            total_value += value_base
            total_investment += investment_base

        holdings: list[Holding] = []
        for bucket in sorted(aggregated_by_symbol.values(), key=lambda row: float(row.get("value_base", 0.0)), reverse=True):
            quantity = _safe_float(bucket.get("quantity"), 0.0)
            value_base = _safe_float(bucket.get("value_base"), 0.0)
            investment_base = _safe_float(bucket.get("investment_base"), 0.0)
            allocation_pct = (value_base / total_value * 100.0) if total_value > 0 else 0.0
            net_performance = value_base - investment_base
            net_performance_pct = (net_performance / investment_base * 100.0) if investment_base > 0 else None
            market_price = (value_base / quantity) if quantity > 0 else None

            holdings.append(
                Holding(
                    symbol=str(bucket.get("symbol") or "UNKNOWN"),
                    name=str(bucket.get("name") or bucket.get("symbol") or "UNKNOWN"),
                    data_source=bucket.get("data_source"),
                    asset_type=bucket.get("asset_type"),
                    asset_class=bucket.get("asset_class"),
                    sector=bucket.get("sector"),
                    region=bucket.get("region"),
                    allocation_percent=round(allocation_pct, 2),
                    value_usd=round(value_base, 2),
                    quantity=round(quantity, 8),
                    market_price=(round(market_price, 4) if market_price is not None else None),
                    net_performance_usd=round(net_performance, 2),
                    net_performance_percent=(round(net_performance_pct, 2) if net_performance_pct is not None else None),
                )
            )

        snapshot = PortfolioSnapshot(
            as_of=datetime.combine(day, time(hour=0, minute=0, second=0, tzinfo=timezone.utc)),
            base_currency=base_currency,
            total_value_usd=round(total_value, 2),
            total_investment_usd=round(total_investment, 2),
            net_performance_usd=round(total_value - total_investment, 2),
            net_performance_percent=(
                round(((total_value - total_investment) / total_investment) * 100.0, 2)
                if total_investment > 0
                else 0.0
            ),
            holdings=holdings,
            accounts=accounts if isinstance(accounts, list) else [],
            raw={
                "historical_backfill": {
                    "date": day_key,
                    "positions": len(holdings),
                    "symbols_requested": len(symbols),
                    "period": period,
                }
            },
        )

        path = _snapshot_path(snapshot_store.snapshot_dir, snapshot.as_of)
        if not overwrite and path.exists():
            days_skipped += 1
            continue
        snapshot_store.write(snapshot)
        days_written += 1

    return {
        "days_written": days_written,
        "days_skipped": days_skipped,
        "symbols": len(symbols),
        "start_date": range_start.isoformat(),
        "end_date": last_day.isoformat(),
        "period": period,
        "overwrite": overwrite,
    }
