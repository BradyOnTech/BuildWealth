"""Simulate a buy/sell trade against current holdings and show portfolio impact."""

from __future__ import annotations

from typing import Literal

from buildwealth_orchestrator.schemas import (
    Holding,
    PortfolioSnapshot,
    SimulatedHolding,
    SimulateTradeResponse,
)


def _concentration_risk(top_pct: float) -> Literal["low", "medium", "high"]:
    if top_pct >= 35:
        return "high"
    if top_pct >= 20:
        return "medium"
    return "low"


def simulate_trade(
    *,
    snapshot: PortfolioSnapshot,
    symbol: str,
    action: Literal["buy", "sell"],
    amount_usd: float,
    name: str | None = None,
) -> SimulateTradeResponse:
    symbol = symbol.upper().strip()
    holdings = list(snapshot.holdings)
    current_total = snapshot.total_value_usd

    # Find existing holding
    existing = next((h for h in holdings if h.symbol.upper() == symbol), None)
    resolved_name = name or (existing.name if existing else symbol)

    highlights: list[str] = []

    if action == "buy":
        new_total = current_total + amount_usd
        if existing:
            new_value = existing.value_usd + amount_usd
            new_holdings = [
                Holding(
                    symbol=h.symbol,
                    name=h.name,
                    value_usd=h.value_usd + amount_usd if h.symbol.upper() == symbol else h.value_usd,
                    allocation_percent=(
                        (h.value_usd + amount_usd) / new_total * 100 if h.symbol.upper() == symbol
                        else h.value_usd / new_total * 100
                    ),
                    quantity=h.quantity,
                )
                for h in holdings
            ]
            highlights.append(f"Adding ${amount_usd:,.0f} to existing {symbol} position (${existing.value_usd:,.0f} → ${new_value:,.0f}).")
        else:
            new_holdings = [
                Holding(
                    symbol=h.symbol,
                    name=h.name,
                    value_usd=h.value_usd,
                    allocation_percent=h.value_usd / new_total * 100,
                    quantity=h.quantity,
                )
                for h in holdings
            ]
            new_holdings.append(Holding(
                symbol=symbol,
                name=resolved_name,
                value_usd=amount_usd,
                allocation_percent=amount_usd / new_total * 100,
            ))
            highlights.append(f"New position: ${amount_usd:,.0f} in {symbol}.")

    elif action == "sell":
        if not existing:
            highlights.append(f"{symbol} is not in your current portfolio — nothing to sell.")
            return _unchanged_response(
                snapshot=snapshot, symbol=symbol, action=action, amount_usd=amount_usd,
                name=resolved_name, highlights=highlights,
            )

        sell_amount = min(amount_usd, existing.value_usd)
        remaining = existing.value_usd - sell_amount
        new_total = current_total - sell_amount

        if new_total <= 0:
            new_total = 0.01  # avoid division by zero

        new_holdings = []
        for h in holdings:
            if h.symbol.upper() == symbol:
                if remaining > 0:
                    new_holdings.append(Holding(
                        symbol=h.symbol, name=h.name,
                        value_usd=remaining,
                        allocation_percent=remaining / new_total * 100,
                        quantity=0,
                    ))
                # else: fully sold, omit from list
            else:
                new_holdings.append(Holding(
                    symbol=h.symbol, name=h.name,
                    value_usd=h.value_usd,
                    allocation_percent=h.value_usd / new_total * 100,
                    quantity=h.quantity,
                ))

        if remaining <= 0:
            highlights.append(f"Fully selling {symbol} position (${existing.value_usd:,.0f}).")
        else:
            highlights.append(f"Selling ${sell_amount:,.0f} of {symbol} (${existing.value_usd:,.0f} → ${remaining:,.0f}).")
    else:
        raise ValueError(f"Unknown action: {action}")

    # Sort by value descending
    new_holdings.sort(key=lambda h: h.value_usd, reverse=True)

    # Current top holding
    current_sorted = sorted(holdings, key=lambda h: h.value_usd, reverse=True)
    current_top = current_sorted[0] if current_sorted else None
    current_top_symbol = current_top.symbol if current_top else None
    current_top_pct = (current_top.value_usd / current_total * 100) if current_top and current_total > 0 else 0.0

    # New top holding
    new_top = new_holdings[0] if new_holdings else None
    new_top_symbol = new_top.symbol if new_top else None
    new_top_pct = (new_top.value_usd / new_total * 100) if new_top and new_total > 0 else 0.0

    current_risk = _concentration_risk(current_top_pct)
    new_risk = _concentration_risk(new_top_pct)

    if new_risk == current_risk:
        conc_change: Literal["improved", "unchanged", "worsened"] = "unchanged"
    elif (new_risk == "low" and current_risk != "low") or (new_risk == "medium" and current_risk == "high"):
        conc_change = "improved"
    else:
        conc_change = "worsened"

    # Concentration highlights
    if conc_change == "worsened":
        highlights.append(f"Concentration risk increases from {current_risk} to {new_risk} (top holding: {new_top_symbol} at {new_top_pct:.1f}%).")
    elif conc_change == "improved":
        highlights.append(f"Concentration risk improves from {current_risk} to {new_risk} (top holding: {new_top_symbol} at {new_top_pct:.1f}%).")
    else:
        highlights.append(f"Concentration risk stays {new_risk} (top holding: {new_top_symbol} at {new_top_pct:.1f}%).")

    # Holdings count change
    if len(new_holdings) > len(holdings):
        highlights.append(f"Portfolio diversifies from {len(holdings)} to {len(new_holdings)} positions.")
    elif len(new_holdings) < len(holdings):
        highlights.append(f"Portfolio consolidates from {len(holdings)} to {len(new_holdings)} positions.")

    # Build top holdings comparison (top 10)
    top_holdings: list[SimulatedHolding] = []
    all_symbols = {h.symbol.upper() for h in holdings} | {h.symbol.upper() for h in new_holdings}
    for sym in all_symbols:
        curr_h = next((h for h in holdings if h.symbol.upper() == sym), None)
        new_h = next((h for h in new_holdings if h.symbol.upper() == sym), None)
        curr_val = curr_h.value_usd if curr_h else 0.0
        new_val = new_h.value_usd if new_h else 0.0
        curr_alloc = (curr_val / current_total * 100) if current_total > 0 else 0.0
        new_alloc = (new_val / new_total * 100) if new_total > 0 else 0.0
        top_holdings.append(SimulatedHolding(
            symbol=sym,
            name=(new_h or curr_h).name if (new_h or curr_h) else sym,
            current_value_usd=round(curr_val, 2),
            new_value_usd=round(new_val, 2),
            current_allocation_pct=round(curr_alloc, 2),
            new_allocation_pct=round(new_alloc, 2),
            allocation_change_pct=round(new_alloc - curr_alloc, 2),
        ))
    top_holdings.sort(key=lambda h: h.new_value_usd, reverse=True)
    top_holdings = top_holdings[:10]

    return SimulateTradeResponse(
        symbol=symbol,
        action=action,
        amount_usd=amount_usd,
        name=resolved_name,
        current_total_value_usd=round(current_total, 2),
        new_total_value_usd=round(new_total, 2),
        current_top_holding_symbol=current_top_symbol,
        current_top_holding_pct=round(current_top_pct, 2),
        new_top_holding_symbol=new_top_symbol,
        new_top_holding_pct=round(new_top_pct, 2),
        current_concentration_risk=current_risk,
        new_concentration_risk=new_risk,
        concentration_change=conc_change,
        current_holdings_count=len(holdings),
        new_holdings_count=len(new_holdings),
        top_holdings=top_holdings,
        highlights=highlights,
    )


def _unchanged_response(
    *, snapshot: PortfolioSnapshot, symbol: str, action: str,
    amount_usd: float, name: str, highlights: list[str],
) -> SimulateTradeResponse:
    holdings = snapshot.holdings
    total = snapshot.total_value_usd
    top = sorted(holdings, key=lambda h: h.value_usd, reverse=True)
    top_h = top[0] if top else None
    top_pct = (top_h.value_usd / total * 100) if top_h and total > 0 else 0.0
    risk = _concentration_risk(top_pct)
    return SimulateTradeResponse(
        symbol=symbol, action=action, amount_usd=amount_usd, name=name,
        current_total_value_usd=round(total, 2), new_total_value_usd=round(total, 2),
        current_top_holding_symbol=top_h.symbol if top_h else None,
        current_top_holding_pct=round(top_pct, 2),
        new_top_holding_symbol=top_h.symbol if top_h else None,
        new_top_holding_pct=round(top_pct, 2),
        current_concentration_risk=risk, new_concentration_risk=risk,
        concentration_change="unchanged",
        current_holdings_count=len(holdings), new_holdings_count=len(holdings),
        top_holdings=[], highlights=highlights,
    )
