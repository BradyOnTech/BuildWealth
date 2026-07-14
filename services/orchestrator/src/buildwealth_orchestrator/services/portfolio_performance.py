"""Transaction-aware portfolio performance calculations for standalone BuildWealth.

This module implements pragmatic portfolio return calculations using the local
transaction ledger plus the latest marked holdings values available in the app.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any


ONBOARDING_FUNDING_NOTE = "funding offset for existing position added through portfolio onboarding"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" not in text:
        text = f"{text}T00:00:00+00:00"
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _days_between(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds() / 86400.0, 0.0)


def _annualize(total_return: float, period_days: float) -> float | None:
    if period_days <= 0:
        return None
    if total_return <= -1.0:
        return -1.0
    growth = 1.0 + total_return
    if growth <= 0:
        return None
    return growth ** (365.0 / period_days) - 1.0


def _portfolio_value(positions: dict[str, float], prices: dict[str, float]) -> float:
    total = 0.0
    for symbol, quantity in positions.items():
        price = prices.get(symbol)
        if price is None:
            continue
        total += quantity * price
    return total


def _transaction_cash_flow(transaction: dict[str, Any]) -> float:
    action = str(transaction.get("action", "")).upper().strip()
    quantity = float(transaction.get("quantity", 0) or 0)
    unit_price = float(transaction.get("unit_price", 0) or 0)
    fee = float(transaction.get("fee", 0) or 0)
    gross = quantity * unit_price

    if action == "BUY":
        return -(gross + fee)
    if action == "SELL":
        return gross - fee
    if action in {"DIVIDEND", "INTEREST"}:
        return gross - fee
    if action == "FEE":
        return -abs(fee or gross)
    if action in {"TRANSFER_IN", "CASH_DEPOSIT"}:
        return -(gross + fee)
    if action in {"TRANSFER_OUT", "CASH_WITHDRAW"}:
        return gross - fee
    if action == "MERGER":
        return gross - fee
    return 0.0


def _normalized_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for transaction in transactions:
        parsed = _parse_datetime(transaction.get("date"))
        if parsed is None:
            continue
        normalized.append(
            {
                **transaction,
                "_parsed_date": parsed,
                "_cash_flow": _transaction_cash_flow(transaction),
            }
        )
    normalized.sort(key=lambda item: item["_parsed_date"])
    # The plain-language onboarding flow records an external cash deposit and
    # the matching BUY together. The deposit is the contribution; treating the
    # BUY as another contribution would double the user's invested amount.
    # Preserve legacy BUY-as-contribution behavior for every other ledger path.
    funding_offsets: dict[tuple[datetime, str, str, float], int] = {}
    for transaction in normalized:
        if (
            str(transaction.get("action") or "").upper().strip() == "CASH_DEPOSIT"
            and ONBOARDING_FUNDING_NOTE in str(transaction.get("note") or "")
        ):
            key = _funding_match_key(transaction)
            funding_offsets[key] = funding_offsets.get(key, 0) + 1
    for transaction in normalized:
        if str(transaction.get("action") or "").upper().strip() != "BUY":
            continue
        key = _funding_match_key(transaction)
        if funding_offsets.get(key, 0) <= 0:
            continue
        transaction["_cash_flow"] = 0.0
        funding_offsets[key] -= 1
    return normalized


def _funding_match_key(transaction: dict[str, Any]) -> tuple[datetime, str, str, float]:
    return (
        transaction["_parsed_date"],
        str(transaction.get("account") or "default"),
        str(transaction.get("currency") or "USD").upper().strip(),
        round(abs(float(transaction.get("_cash_flow") or 0.0)), 2),
    )


def calculate_portfolio_performance(
    *,
    transactions: list[dict[str, Any]],
    holdings: dict[str, dict[str, Any]],
    as_of: str | None = None,
    return_components_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    normalized = _normalized_transactions(transactions)
    if not normalized:
        return {
            "start_date": None,
            "as_of": as_of,
            "period_days": 0,
            "gross_contributions": 0.0,
            "net_contributions": 0.0,
            "ending_value": round(
                sum(float(item.get("current_value") or 0.0) for item in holdings.values()),
                2,
            ),
            "twr_return_pct": None,
            "twr_annualized_return_pct": None,
            "xirr_annualized_return_pct": None,
            "realized_gains_usd": 0.0,
            "unrealized_gains_usd": 0.0,
            "income_received_usd": 0.0,
            "fees_paid_usd": 0.0,
            "price_return_usd": 0.0,
            "income_return_usd": 0.0,
            "total_return_usd": 0.0,
            "price_return_pct": None,
            "income_return_pct": None,
            "total_return_pct": None,
            "return_denominator_usd": 0.0,
            "calculation_basis": "transaction_price_estimate",
        }

    resolved_as_of = _parse_datetime(as_of) or datetime.now(timezone.utc)
    prices: dict[str, float] = {}
    positions: dict[str, float] = {}
    cash_flows: list[tuple[datetime, float]] = []
    twr_factor = 1.0
    start_value: float | None = None

    for transaction in normalized:
        symbol = str(transaction.get("symbol", "")).upper().strip()
        quantity = float(transaction.get("quantity", 0) or 0)
        unit_price = float(transaction.get("unit_price", 0) or 0)
        action = str(transaction.get("action", "")).upper().strip()

        if symbol and unit_price > 0:
            prices[symbol] = unit_price

        value_before_flow = _portfolio_value(positions, prices)
        if start_value is not None and start_value > 0:
            twr_factor *= 1.0 + ((value_before_flow - start_value) / start_value)

        if action == "BUY":
            positions[symbol] = positions.get(symbol, 0.0) + quantity
        elif action == "SELL":
            positions[symbol] = positions.get(symbol, 0.0) - quantity
            if abs(positions[symbol]) < 1e-9:
                positions.pop(symbol, None)

        cash_flow = float(transaction["_cash_flow"])
        if cash_flow != 0:
            cash_flows.append((transaction["_parsed_date"], cash_flow))

        start_value = _portfolio_value(positions, prices)

    for key, holding in holdings.items():
        symbol = str(holding.get("symbol") or key).upper().strip()
        if not symbol:
            continue
        current_price = holding.get("current_price")
        if current_price is not None:
            prices[symbol] = float(current_price)
        elif symbol not in prices:
            fallback_price = holding.get("avg_cost_per_share")
            if fallback_price is not None:
                prices[symbol] = float(fallback_price)

    final_value = _portfolio_value(positions, prices)
    if start_value is not None and start_value > 0:
        twr_factor *= 1.0 + ((final_value - start_value) / start_value)

    period_days = int(round(_days_between(normalized[0]["_parsed_date"], resolved_as_of)))
    twr_return = twr_factor - 1.0
    twr_annualized = _annualize(twr_return, max(period_days, 1))

    net_contributions = 0.0
    gross_contributions = 0.0
    for _, amount in cash_flows:
        if amount < 0:
            net_contributions += -amount
            gross_contributions += -amount
        else:
            net_contributions -= amount

    xirr_return = _calculate_xirr(cash_flows=cash_flows, ending_value=final_value, as_of=resolved_as_of)

    holdings_cost_basis = 0.0
    for item in holdings.values():
        explicit_cost_basis = item.get("cost_basis")
        if explicit_cost_basis is not None:
            holdings_cost_basis += float(explicit_cost_basis or 0.0)
            continue
        quantity = float(item.get("quantity") or 0.0)
        avg_cost = float(item.get("avg_cost_per_share") or 0.0)
        holdings_cost_basis += quantity * avg_cost
    holdings_realized = sum(float(item.get("realized_gains") or 0.0) for item in holdings.values())
    holdings_income = sum(float(item.get("dividends_received") or 0.0) for item in holdings.values())
    holdings_fees = sum(float(item.get("fees_paid") or 0.0) for item in holdings.values())

    override = return_components_override or {}
    realized_gains = float(override.get("realized_gains_usd", holdings_realized))
    income_received = float(override.get("income_received_usd", holdings_income))
    fees_paid = float(override.get("fees_paid_usd", holdings_fees))
    unrealized_gains = final_value - holdings_cost_basis
    price_return = realized_gains + unrealized_gains
    total_return = price_return + income_received

    denominator = gross_contributions if gross_contributions > 0 else holdings_cost_basis
    if denominator <= 1e-9:
        denominator = 0.0

    price_return_pct = (price_return / denominator * 100.0) if denominator > 0 else None
    income_return_pct = (income_received / denominator * 100.0) if denominator > 0 else None
    total_return_pct = (total_return / denominator * 100.0) if denominator > 0 else None

    return {
        "start_date": normalized[0]["_parsed_date"].isoformat(),
        "as_of": resolved_as_of.isoformat(),
        "period_days": period_days,
        "gross_contributions": round(gross_contributions, 2),
        "net_contributions": round(net_contributions, 2),
        "ending_value": round(final_value, 2),
        "twr_return_pct": round(twr_return * 100, 2) if isfinite(twr_return) else None,
        "twr_annualized_return_pct": round(twr_annualized * 100, 2) if twr_annualized is not None else None,
        "xirr_annualized_return_pct": round(xirr_return * 100, 2) if xirr_return is not None else None,
        "realized_gains_usd": round(realized_gains, 2),
        "unrealized_gains_usd": round(unrealized_gains, 2),
        "income_received_usd": round(income_received, 2),
        "fees_paid_usd": round(fees_paid, 2),
        "price_return_usd": round(price_return, 2),
        "income_return_usd": round(income_received, 2),
        "total_return_usd": round(total_return, 2),
        "price_return_pct": round(price_return_pct, 2) if price_return_pct is not None else None,
        "income_return_pct": round(income_return_pct, 2) if income_return_pct is not None else None,
        "total_return_pct": round(total_return_pct, 2) if total_return_pct is not None else None,
        "return_denominator_usd": round(denominator, 2),
        "calculation_basis": "transaction_price_estimate",
    }


def _calculate_xirr(
    *,
    cash_flows: list[tuple[datetime, float]],
    ending_value: float,
    as_of: datetime,
) -> float | None:
    flows = list(cash_flows)
    if ending_value != 0:
        flows.append((as_of, ending_value))

    if not flows:
        return None

    has_positive = any(amount > 0 for _, amount in flows)
    has_negative = any(amount < 0 for _, amount in flows)
    if not (has_positive and has_negative):
        return None

    start_date = min(date for date, _ in flows)
    year_fractions = [(_days_between(start_date, date) / 365.0, amount) for date, amount in flows]

    def f(rate: float) -> float:
        return sum(amount / ((1.0 + rate) ** years) for years, amount in year_fractions)

    def df(rate: float) -> float:
        return sum((-years * amount) / ((1.0 + rate) ** (years + 1.0)) for years, amount in year_fractions)

    rate = 0.1
    for _ in range(50):
        if rate <= -0.999999:
            rate = -0.999999
        value = f(rate)
        deriv = df(rate)
        if abs(deriv) < 1e-12:
            break
        next_rate = rate - (value / deriv)
        if not isfinite(next_rate):
            break
        if abs(next_rate - rate) < 1e-10:
            return next_rate
        rate = next_rate

    if rate <= -0.999999 or not isfinite(rate):
        return None

    residual = f(rate)
    if abs(residual) > 1e-5:
        return None
    return rate


def calculate_modified_dietz_return(
    *,
    start_value: float,
    end_value: float,
    start_date: datetime,
    end_date: datetime,
    cash_flows: list[tuple[datetime, float]],
) -> tuple[float | None, float | None]:
    total_days = _days_between(start_date, end_date)
    if total_days <= 0 or start_value < 0:
        return None, None

    net_flows = sum(amount for _, amount in cash_flows)
    weighted_flows = 0.0
    for flow_date, amount in cash_flows:
        days_from_start = _days_between(start_date, flow_date)
        weight = max(total_days - days_from_start, 0.0) / total_days
        weighted_flows += amount * weight

    denominator = start_value + weighted_flows
    if abs(denominator) < 1e-9:
        return None, None

    period_return = (end_value - start_value - net_flows) / denominator
    annualized = _annualize(period_return, total_days)
    return period_return, annualized


def filter_transaction_cash_flows(
    *,
    transactions: list[dict[str, Any]],
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[datetime, float]]:
    flows: list[tuple[datetime, float]] = []
    for transaction in _normalized_transactions(transactions):
        parsed = transaction["_parsed_date"]
        if parsed < start_date or parsed > end_date:
            continue
        cash_flow = float(transaction["_cash_flow"])
        if cash_flow != 0:
            flows.append((parsed, -cash_flow))
    return flows
