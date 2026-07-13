"""One front door for getting money into the portfolio.

Translates three plain-language flows — "I own an investment", "cash
balance", and "property or other asset" — into the ledger primitives the
portfolio store already understands (BUY/SELL/TRANSFER_IN transactions,
CASH_DEPOSIT, custom asset + manual price). Anything the store shouldn't
be asked to guess raises AddFlowError with a human sentence; routes map
that to a 400.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .portfolio_store import PortfolioStore

INVESTMENT_ACTIONS = {"BUY", "SELL"}

# UI type -> (store asset_type, allocation asset_class)
PROPERTY_TYPES = {
    "real_estate": ("real_estate", "Real Estate"),
    "vehicle": ("vehicle", "Vehicles"),
    "other": ("custom_asset", "Alternatives"),
}

ESTIMATED_BASIS_NOTE = "basis estimated at entry"


class AddFlowError(ValueError):
    """Validation failure carrying a human-readable message."""


def execute_add_flow(store: PortfolioStore, body: dict[str, Any]) -> dict[str, Any]:
    flow = str(body.get("flow") or "").strip().lower()
    if flow == "investment":
        return _add_investment(store, body)
    if flow == "cash":
        return _add_cash(store, body)
    if flow == "property":
        return _add_property(store, body)
    raise AddFlowError("Choose what you're adding: an investment, cash, or a property.")


# ---- Flows ----


def _add_investment(store: PortfolioStore, body: dict[str, Any]) -> dict[str, Any]:
    symbol = str(body.get("symbol") or "").strip().upper()
    if not symbol:
        raise AddFlowError("Enter the ticker symbol for this investment.")

    action = str(body.get("action") or "BUY").strip().upper() or "BUY"
    # No TRANSFER_IN here: the ledger treats it as a cash inflow, so a share
    # transfer recorded that way would silently become cash. Recording the
    # acquisition as a BUY at its basis is the honest representation until
    # the store supports position transfers.
    if body.get("transfer"):
        action = "BUY"
    if action not in INVESTMENT_ACTIONS:
        raise AddFlowError("This flow records a buy or a sell.")

    account = _resolve_account(store, body)
    quantity = _parse_amount(body.get("quantity"), "Shares")
    value_usd = _parse_amount(body.get("value_usd"), "Current value")
    unit_cost = _parse_amount(body.get("unit_cost"), "Cost per share")
    acquired_date = str(body.get("acquired_date") or "").strip() or date.today().isoformat()

    known_price = _known_price(store, symbol)
    if quantity is None:
        if value_usd is None:
            raise AddFlowError("Enter either the number of shares or their current dollar value.")
        if known_price is None:
            raise AddFlowError(
                f"BuildWealth has no current price for {symbol} yet — "
                "enter the number of shares and what you paid per share instead."
            )
        quantity = round(value_usd / known_price, 8)

    estimated_basis = False
    note = str(body.get("note") or "").strip()
    if unit_cost is None:
        if known_price is None:
            raise AddFlowError(
                f"BuildWealth has no current price for {symbol} yet — "
                "add what you paid per share so this position has a cost basis."
            )
        unit_cost = known_price
        estimated_basis = True
        note = f"{note}; {ESTIMATED_BASIS_NOTE}" if note else ESTIMATED_BASIS_NOTE

    txn = store.add_transaction(
        date=acquired_date,
        symbol=symbol,
        action=action,
        quantity=quantity,
        unit_price=unit_cost,
        fee=0.0,
        account=str(account.get("id") or "default"),
        currency=str(account.get("currency") or "USD"),
        note=note,
    )

    verb = {"BUY": "a buy of", "SELL": "a sale of"}[action]
    detail = (
        f"Recorded {verb} {_fmt_qty(quantity)} {symbol} "
        f"at {_fmt_usd(unit_cost)} per share in {_account_name(account)}."
    )
    return {
        "created": txn,
        "account_id": account.get("id"),
        "estimated_basis": estimated_basis,
        "detail": detail,
    }


def _add_cash(store: PortfolioStore, body: dict[str, Any]) -> dict[str, Any]:
    amount = _parse_amount(body.get("amount_usd"), "Amount")
    if amount is None:
        raise AddFlowError("Enter how much cash to add.")
    account = _resolve_account(store, body)

    txn = store.add_transaction(
        date=date.today().isoformat(),
        symbol="CASH",
        action="CASH_DEPOSIT",
        quantity=1.0,
        unit_price=amount,
        fee=0.0,
        account=str(account.get("id") or "default"),
        currency=str(account.get("currency") or "USD"),
        note=str(body.get("note") or ""),
    )
    return {
        "created": txn,
        "account_id": account.get("id"),
        "detail": f"Added {_fmt_usd(amount)} cash to {_account_name(account)}.",
    }


def _add_property(store: PortfolioStore, body: dict[str, Any]) -> dict[str, Any]:
    label = str(body.get("label") or "").strip()
    if not label:
        raise AddFlowError('Give this asset a short name, like "Home" or "2021 Subaru".')
    value = _parse_amount(body.get("value_usd"), "Value")
    if value is None:
        raise AddFlowError("Enter what this asset is worth today.")

    type_key = str(body.get("asset_type") or "other").strip().lower()
    if type_key not in PROPERTY_TYPES:
        raise AddFlowError("Pick a type: real estate, a vehicle, or something else.")
    asset_type, asset_class = PROPERTY_TYPES[type_key]

    account = _resolve_account(store, body)
    created = store.create_custom_asset(
        name=label,
        value=value,
        account=str(account.get("id") or "default"),
        asset_type=asset_type,
        asset_class=asset_class,
        note=str(body.get("note") or ""),
    )
    return {
        "created": created,
        "account_id": account.get("id"),
        "detail": (
            f"Added {label} at {_fmt_usd(value)}. "
            "Its value stays where you set it until you update it."
        ),
    }


# ---- Shared pieces ----


def _resolve_account(store: PortfolioStore, body: dict[str, Any]) -> dict[str, Any]:
    """Existing account by id or name, an inline-created one, or the default."""
    new_account = body.get("new_account")
    if isinstance(new_account, dict):
        name = str(new_account.get("name") or "").strip()
        if not name:
            raise AddFlowError("Give the new account a name.")
        return store.add_account(
            name=name,
            account_type=str(new_account.get("type") or "taxable"),
            currency=str(new_account.get("currency") or "USD"),
        )

    ref = str(body.get("account_id") or "").strip()
    if not ref:
        return store.ensure_account("default")

    lowered = ref.lower()
    for account in store.get_accounts():
        if not isinstance(account, dict):
            continue
        if str(account.get("id") or "").strip().lower() == lowered:
            return account
        if str(account.get("name") or "").strip().lower() == lowered:
            return account
    raise AddFlowError(
        f'No account called "{ref}" is set up yet — pick one from the list or create it inline.'
    )


def _known_price(store: PortfolioStore, symbol: str) -> float | None:
    """Latest usable price: manual override first, then the holdings payload."""
    manual = store.get_manual_prices().get("by_symbol")
    if isinstance(manual, dict):
        entry = manual.get(symbol)
        if isinstance(entry, dict):
            price = _positive_or_none(entry.get("price"))
            if price is not None:
                return price

    by_symbol = store.get_holdings().get("holdings_by_symbol")
    if isinstance(by_symbol, dict):
        row = by_symbol.get(symbol)
        if isinstance(row, dict):
            price = _positive_or_none(row.get("current_price"))
            if price is not None:
                return price
    return None


def _parse_amount(value: Any, field_label: str) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AddFlowError(f"{field_label} must be a number.") from exc
    if number <= 0:
        raise AddFlowError(f"{field_label} must be greater than zero.")
    return number


def _positive_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _account_name(account: dict[str, Any]) -> str:
    return str(account.get("name") or account.get("id") or "your account")


def _fmt_usd(amount: float) -> str:
    return f"${amount:,.2f}"


def _fmt_qty(quantity: float) -> str:
    text = f"{quantity:,.4f}".rstrip("0").rstrip(".")
    return text or "0"
