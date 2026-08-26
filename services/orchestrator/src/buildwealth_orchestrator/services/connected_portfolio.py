"""Resolve provider observations into Portfolio's current-state read model.

The transaction ledger remains untouched. Connected observations replace only
the current quantity, balance, and cash view for explicitly mapped accounts.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.services.portfolio_risk_alerts import (
    calculate_portfolio_risk_alerts,
)


def resolve_connected_portfolio(
    payload: dict[str, Any],
    *,
    connection_store: Any,
    portfolio_store: Any,
) -> dict[str, Any]:
    result = deepcopy(payload)
    connected_snapshots: list[tuple[dict[str, Any], dict[str, Any]]] = []
    authoritative_account_ids: set[str] = set()
    for connection in connection_store.list_connections():
        if connection.get("status") not in {
            "active",
            "needs_attention",
            "error",
            "disconnected",
        }:
            continue
        state = connection_store.get_observation_state(connection["connection_id"])
        current = state.get("current")
        if not isinstance(current, dict):
            continue
        connected_snapshots.append((connection, current))
        authoritative_account_ids.update(
            str(row.get("buildwealth_account_id") or "")
            for row in current.get("accounts", [])
            if isinstance(row, dict) and row.get("buildwealth_account_id")
        )

    if not connected_snapshots:
        return result

    base_holdings = result.get("holdings") if isinstance(result.get("holdings"), dict) else {}
    holdings = {
        key: dict(row)
        for key, row in base_holdings.items()
        if isinstance(row, dict)
        and str(row.get("account") or "") not in authoritative_account_ids
    }
    account_cash = {
        str(account_id): float(value or 0.0)
        for account_id, value in (
            result.get("account_cash")
            if isinstance(result.get("account_cash"), dict)
            else {}
        ).items()
        if str(account_id) not in authoritative_account_ids
    }
    account_observations: dict[str, dict[str, Any]] = {}
    metadata_map = portfolio_store.get_asset_metadata_map()
    base_currency = str(result.get("base_currency") or "USD").upper()
    fx_rates = result.get("fx_rates") if isinstance(result.get("fx_rates"), dict) else {}
    market_prices: dict[str, tuple[float, str]] = {}
    for row in base_holdings.values():
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        price = row.get("current_price_native") or row.get("current_price")
        if symbol and price is not None and float(price or 0) > 0:
            market_prices[symbol] = (float(price), str(row.get("price_source") or "market_data"))

    for connection, snapshot in connected_snapshots:
        stale = _connection_is_stale(connection)
        observed_at = snapshot.get("observed_at")
        for account in snapshot.get("accounts", []):
            if not isinstance(account, dict):
                continue
            account_id = str(account.get("buildwealth_account_id") or "")
            if not account_id:
                continue
            account_observations[account_id] = account
            cash = account.get("cash_balance")
            if cash is None:
                account_value = float(account.get("current_balance") or 0.0)
                holding_value = sum(
                    float(row.get("institution_value") or 0.0)
                    for row in snapshot.get("holdings", [])
                    if isinstance(row, dict)
                    and str(row.get("buildwealth_account_id") or "") == account_id
                )
                cash = account_value - holding_value
            account_currency = str(account.get("currency") or base_currency).upper()
            fx_rate = float(fx_rates.get(account_currency) or 1.0)
            account_cash[account_id] = round(float(cash or 0.0) * fx_rate, 2)

        for observed in snapshot.get("holdings", []):
            if not isinstance(observed, dict):
                continue
            account_id = str(observed.get("buildwealth_account_id") or "")
            symbol = str(observed.get("symbol_or_identifier") or "").strip().upper()
            if not account_id or not symbol:
                continue
            quantity = float(observed.get("quantity") or 0.0)
            institution_price = float(observed.get("institution_price") or 0.0)
            institution_value = float(observed.get("institution_value") or 0.0)
            cost_basis = float(observed.get("cost_basis") or 0.0)
            metadata = metadata_map.get(symbol) if isinstance(metadata_map, dict) else None
            metadata = metadata if isinstance(metadata, dict) else {}
            currency = str(observed.get("currency") or base_currency).upper()
            fx_rate = float(fx_rates.get(currency) or 1.0)
            market_evidence = market_prices.get(symbol)
            if market_evidence is not None:
                current_price_native, price_source = market_evidence
                current_value_native = quantity * current_price_native
            else:
                current_price_native = institution_price if institution_price > 0 else None
                current_value_native = institution_value
                price_source = "institution_observation_fallback"
            current_price = (
                current_price_native * fx_rate if current_price_native is not None else None
            )
            current_value = current_value_native * fx_rate
            provider_security_id = str(observed.get("provider_security_id") or "")
            position_key = f"{account_id}:{symbol}"
            if position_key in holdings:
                position_key = f"{position_key}:{provider_security_id}"
            holdings[position_key] = {
                "symbol": symbol,
                "account": account_id,
                "provider_security_id": provider_security_id,
                "currency": currency,
                "base_currency": base_currency,
                "fx_rate_to_base": fx_rate,
                "quantity": quantity,
                "cost_basis_native": cost_basis,
                "cost_basis": cost_basis * fx_rate,
                "avg_cost_per_share_native": (
                    cost_basis / quantity if quantity else 0.0
                ),
                "avg_cost_per_share": (cost_basis * fx_rate) / quantity if quantity else 0.0,
                "cost_basis_method": "PROVIDER_REPORTED",
                "lots": [],
                "lot_count": 0,
                "current_price_native": current_price_native,
                "current_price": current_price,
                "current_value_native": current_value_native,
                "current_value": current_value,
                "price_source": price_source,
                "institution_price": institution_price or None,
                "institution_value": institution_value,
                "institution_value_base": institution_value * fx_rate,
                "institution_market_delta": current_value - (institution_value * fx_rate),
                "name": observed.get("name") or metadata.get("name") or symbol,
                "asset_type": metadata.get("asset_type") or "connected_security",
                "asset_class": metadata.get("asset_class") or "Needs Review",
                "sector": metadata.get("sector"),
                "region": metadata.get("region"),
                "data_source": metadata.get("data_source") or "PLAID",
                "source": "connected",
                "provider_owned": True,
                "connection_id": connection["connection_id"],
                "institution_name": connection.get("institution_name"),
                "observed_at": observed.get("observed_at") or observed_at,
                "stale": stale,
                "connection_health": connection.get("status"),
            }

    result["holdings"] = holdings
    result["account_cash"] = account_cash
    result["holdings_by_symbol"] = _aggregate_by_symbol(holdings)
    result["account_totals"] = _account_totals(
        holdings,
        account_cash,
        portfolio_store.get_accounts(),
        account_observations,
    )
    result["total_cash"] = round(sum(account_cash.values()), 2)
    result["total_value"] = round(
        sum(float(row.get("current_value") or 0.0) for row in holdings.values()),
        2,
    )
    result["total_cost_basis"] = round(
        sum(float(row.get("cost_basis") or 0.0) for row in holdings.values()),
        2,
    )
    result["total_portfolio_value"] = round(
        result["total_value"] + result["total_cash"], 2
    )
    result["priced_holdings_count"] = sum(
        1 for row in holdings.values() if row.get("current_value") is not None
    )
    result["unpriced_holdings_count"] = len(holdings) - int(
        result["priced_holdings_count"]
    )
    result["valuation_status"] = (
        "complete" if result["unpriced_holdings_count"] == 0 else "partial"
    )
    result["connected_observations_applied"] = True
    result["connected_account_ids"] = sorted(authoritative_account_ids)
    result["allocation_breakdowns"] = _allocation_breakdowns(
        holdings,
        total_market_value=result["total_value"],
        total_cash=result["total_cash"],
    )
    risk_policy = result.get("risk_policy") if isinstance(result.get("risk_policy"), dict) else {}
    result["risk_alerts"] = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals=result["account_totals"],
        allocation_breakdowns=result.get("allocation_breakdowns"),
        thresholds=risk_policy.get("thresholds"),
        generated_at=str(result.get("updated_at") or ""),
    )
    return result


def _connection_is_stale(connection: dict[str, Any]) -> bool:
    if connection.get("status") != "active":
        return True
    timestamp = connection.get("last_successful_sync_at")
    if not timestamp:
        return True
    try:
        observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - observed).total_seconds() > 36 * 3600


def _allocation_breakdowns(
    holdings: dict[str, dict[str, Any]],
    *,
    total_market_value: float,
    total_cash: float,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, dict[str, float]] = {
        "asset_class": {},
        "sector": {},
        "region": {},
    }
    fallbacks = {"asset_class": "Unclassified", "sector": "Unknown", "region": "Unknown"}
    for holding in holdings.values():
        value = float(holding.get("current_value") or 0.0)
        if value <= 0:
            continue
        for dimension in buckets:
            label = str(holding.get(dimension) or fallbacks[dimension])
            buckets[dimension][label] = buckets[dimension].get(label, 0.0) + value
    if total_cash > 0:
        buckets["asset_class"]["Cash"] = buckets["asset_class"].get("Cash", 0.0) + total_cash
    output: dict[str, list[dict[str, Any]]] = {}
    for dimension, values in buckets.items():
        denominator = total_market_value + total_cash if dimension == "asset_class" else total_market_value
        denominator = denominator or 1.0
        output[dimension] = [
            {
                "key": key,
                "value": round(value, 2),
                "allocation_pct": round((value / denominator) * 100, 2),
            }
            for key, value in sorted(values.items(), key=lambda item: item[1], reverse=True)
        ]
    return output


def _aggregate_by_symbol(holdings: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    for row in holdings.values():
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        item = aggregated.setdefault(
            symbol,
            {
                "symbol": symbol,
                "quantity": 0.0,
                "cost_basis": 0.0,
                "current_value": 0.0,
                "accounts": [],
                "position_count": 0,
                "name": row.get("name") or symbol,
                "asset_type": row.get("asset_type"),
                "asset_class": row.get("asset_class"),
                "sector": row.get("sector"),
                "region": row.get("region"),
            },
        )
        item["quantity"] += float(row.get("quantity") or 0.0)
        item["cost_basis"] += float(row.get("cost_basis") or 0.0)
        item["current_value"] += float(row.get("current_value") or 0.0)
        item["position_count"] += 1
        account = str(row.get("account") or "")
        if account and account not in item["accounts"]:
            item["accounts"].append(account)
        if row.get("source") == "connected":
            item["has_connected_observation"] = True
    for item in aggregated.values():
        quantity = float(item["quantity"] or 0.0)
        item["avg_cost_per_share"] = (
            float(item["cost_basis"] or 0.0) / quantity if quantity else 0.0
        )
        item["current_price"] = (
            float(item["current_value"] or 0.0) / quantity if quantity else None
        )
    return aggregated


def _account_totals(
    holdings: dict[str, dict[str, Any]],
    account_cash: dict[str, float],
    accounts: list[dict[str, Any]],
    observations: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    account_by_id = {str(row.get("id") or ""): row for row in accounts if isinstance(row, dict)}
    account_ids = set(account_cash)
    account_ids.update(str(row.get("account") or "") for row in holdings.values())
    totals: dict[str, dict[str, Any]] = {}
    for account_id in sorted(value for value in account_ids if value):
        positions = [row for row in holdings.values() if str(row.get("account") or "") == account_id]
        market_value = sum(float(row.get("current_value") or 0.0) for row in positions)
        cost_basis = sum(float(row.get("cost_basis") or 0.0) for row in positions)
        cash = float(account_cash.get(account_id, 0.0))
        account = account_by_id.get(account_id) or {}
        observation = observations.get(account_id) or {}
        totals[account_id] = {
            "account_id": account_id,
            "name": account.get("name") or observation.get("name") or account_id,
            "type": account.get("type") or "taxable",
            "currency": account.get("currency") or observation.get("currency") or "USD",
            "market_value": round(market_value, 2),
            "cash_balance": round(cash, 2),
            "cost_basis": round(cost_basis, 2),
            "holdings_count": len(positions),
            "total_value": round(market_value + cash, 2),
            "net_performance": round(market_value - cost_basis, 2),
            "net_performance_pct": (
                round(((market_value - cost_basis) / cost_basis) * 100, 2)
                if cost_basis
                else None
            ),
            "source": "connected" if account_id in observations else "manual",
            "provider_owned": account_id in observations,
        }
    return totals
