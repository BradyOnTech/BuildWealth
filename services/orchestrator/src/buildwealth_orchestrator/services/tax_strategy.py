"""Tax strategy tools: tax-loss harvesting candidates and Roth conversion ladders.

Both tools compose existing engines — lot-level cost basis from the portfolio
store and bracket math from tax_engine — into decision-support reports. They
describe tradeoffs; they never execute anything.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from buildwealth_orchestrator.services.tax_engine import estimate_federal_tax

WASH_SALE_WINDOW_DAYS = 30
LONG_TERM_HOLDING_DAYS = 365
MIN_HARVEST_LOSS_USD = 50.0
ORDINARY_LOSS_OFFSET_LIMIT_USD = 3000.0

# Account types where realized losses have tax meaning.
TAXABLE_ACCOUNT_TYPES = {"taxable", "brokerage", "individual", "joint"}


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _taxable_account_ids(accounts: Any) -> set[str]:
    if isinstance(accounts, dict):  # tolerate the raw accounts.json shape
        accounts = accounts.get("accounts")
    ids = set()
    for account in accounts if isinstance(accounts, list) else []:
        if not isinstance(account, dict):
            continue
        if str(account.get("type") or "").strip().lower() in TAXABLE_ACCOUNT_TYPES:
            ids.add(str(account.get("id") or ""))
    return ids


def _recent_buys_by_symbol(
    transactions: list[dict[str, Any]], *, since: date
) -> dict[str, list[str]]:
    """Symbols bought on/after `since`, mapped to the buy dates (wash-sale
    lookback across ALL accounts — IRS rules don't care which account
    repurchases)."""
    buys: dict[str, list[str]] = {}
    for txn in transactions or []:
        if not isinstance(txn, dict):
            continue
        if str(txn.get("action") or "").strip().upper() != "BUY":
            continue
        when = _parse_date(txn.get("date"))
        if when is None or when < since:
            continue
        symbol = str(txn.get("symbol") or "").strip().upper()
        if symbol:
            buys.setdefault(symbol, []).append(when.isoformat())
    return buys


def build_tax_loss_harvest_report(
    *,
    holdings_payload: dict[str, Any],
    transactions: list[dict[str, Any]],
    profile_payload: dict[str, Any],
    now: date | None = None,
) -> dict[str, Any]:
    today = now or _today()
    tax_profile = profile_payload.get("tax_profile") if isinstance(profile_payload, dict) else {}
    tax_profile = tax_profile if isinstance(tax_profile, dict) else {}
    marginal_rate = float(tax_profile.get("marginal_tax_rate") or 0.24)
    state_rate = float(tax_profile.get("state_tax_rate") or 0.0)
    # LTCG estimate: households under the top ordinary brackets mostly sit in
    # the 15% band; refined per-household math happens in the Roth/`what-if`
    # tools that run the full engine.
    long_term_rate = 0.15 + state_rate
    short_term_rate = marginal_rate + state_rate

    accounts = holdings_payload.get("accounts")
    taxable_ids = _taxable_account_ids(accounts if isinstance(accounts, list) else [])
    wash_window_start = today - timedelta(days=WASH_SALE_WINDOW_DAYS)
    recent_buys = _recent_buys_by_symbol(transactions, since=wash_window_start)

    holdings = holdings_payload.get("holdings")
    holdings = holdings if isinstance(holdings, dict) else {}

    candidates: list[dict[str, Any]] = []
    skipped_non_taxable = 0
    for key, holding in holdings.items():
        if not isinstance(holding, dict):
            continue
        account = str(holding.get("account") or "").strip()
        symbol = str(holding.get("symbol") or key).strip().upper()
        if account not in taxable_ids:
            skipped_non_taxable += 1
            continue
        current_price = float(holding.get("current_price") or 0.0)
        if current_price <= 0:
            continue
        for lot in holding.get("lots") or []:
            if not isinstance(lot, dict):
                continue
            quantity = float(lot.get("remaining_quantity") or 0.0)
            unit_cost = float(lot.get("unit_cost") or 0.0)
            if quantity <= 0 or unit_cost <= 0:
                continue
            loss = (current_price - unit_cost) * quantity
            if loss > -MIN_HARVEST_LOSS_USD:
                continue
            acquired = _parse_date(lot.get("acquired_date"))
            held_days = (today - acquired).days if acquired else None
            is_long_term = bool(held_days is not None and held_days > LONG_TERM_HOLDING_DAYS)
            rate = long_term_rate if is_long_term else short_term_rate
            buy_dates = recent_buys.get(symbol, [])
            candidates.append(
                {
                    "symbol": symbol,
                    "account": account,
                    "lot_id": lot.get("lot_id"),
                    "acquired_date": acquired.isoformat() if acquired else None,
                    "held_days": held_days,
                    "term": "long" if is_long_term else "short",
                    "quantity": round(quantity, 6),
                    "unit_cost": round(unit_cost, 4),
                    "current_price": round(current_price, 4),
                    "unrealized_loss_usd": round(loss, 2),
                    "estimated_tax_benefit_usd": round(-loss * rate, 2),
                    "wash_sale_risk": bool(buy_dates),
                    "recent_buy_dates": buy_dates,
                }
            )

    candidates.sort(key=lambda row: row["unrealized_loss_usd"])
    total_loss = round(sum(row["unrealized_loss_usd"] for row in candidates), 2)
    total_benefit = round(sum(row["estimated_tax_benefit_usd"] for row in candidates), 2)

    notes = [
        "Estimates use your profile's marginal rate for short-term lots and a 15% "
        "federal long-term rate plus state; actual benefit depends on realized "
        "gains this year.",
        f"Realized losses first offset capital gains; up to ${ORDINARY_LOSS_OFFSET_LIMIT_USD:,.0f} "
        "of net losses can offset ordinary income per year, the rest carries forward.",
        "Wash-sale rule: buying the same (or substantially identical) security within "
        f"{WASH_SALE_WINDOW_DAYS} days before or after the sale disallows the loss — "
        "flagged lots had purchases inside the lookback window; avoid repurchasing for "
        f"{WASH_SALE_WINDOW_DAYS} days after selling.",
    ]
    if skipped_non_taxable:
        notes.append(
            f"{skipped_non_taxable} holding(s) in non-taxable accounts were skipped — "
            "losses there have no harvesting value."
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "candidate_count": len(candidates),
        "total_harvestable_loss_usd": total_loss,
        "total_estimated_tax_benefit_usd": total_benefit,
        "assumptions": {
            "short_term_rate": round(short_term_rate, 4),
            "long_term_rate": round(long_term_rate, 4),
            "min_loss_usd": MIN_HARVEST_LOSS_USD,
        },
        "candidates": candidates,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Roth conversion ladder
# ---------------------------------------------------------------------------

BRACKET_CEILING_CHOICES = (0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37)
MAX_LADDER_YEARS = 30


def build_roth_conversion_ladder(
    *,
    traditional_balance_usd: float,
    filing_status: str,
    annual_ordinary_income_usd: float,
    target_bracket_rate: float = 0.24,
    years: int = 10,
    annual_growth_rate: float = 0.05,
    state_tax_rate: float = 0.0,
    age: int | None = None,
    tax_year: int | None = None,
) -> dict[str, Any]:
    """Fill-the-bracket conversion schedule.

    Each year converts just enough to reach the top of the target federal
    bracket (given expected ordinary income), pricing the conversion as the
    federal+state delta from the full tax engine — so IRMAA and deduction
    effects are included rather than approximated.
    """
    from buildwealth_orchestrator.services.tax_engine import TAX_CONFIG_BY_YEAR, TAX_YEAR_2026

    balance = max(0.0, float(traditional_balance_usd or 0.0))
    income = max(0.0, float(annual_ordinary_income_usd or 0.0))
    growth = max(-0.5, min(0.5, float(annual_growth_rate or 0.0)))
    state_rate = max(0.0, min(1.0, float(state_tax_rate or 0.0)))
    horizon = max(1, min(MAX_LADDER_YEARS, int(years or 10)))
    start_year = int(tax_year or datetime.now(timezone.utc).year)

    config = TAX_CONFIG_BY_YEAR.get(start_year, TAX_YEAR_2026)
    filing = filing_status if filing_status in config.standard_deduction else "single"
    brackets = config.federal_income_brackets[filing]
    standard_deduction = config.standard_deduction[filing]

    target_rate = float(target_bracket_rate or 0.24)
    ceiling = None
    for bracket in brackets:
        if abs(bracket.rate - target_rate) < 1e-9:
            ceiling = bracket.max_income
            break
    if ceiling is None:
        # Unknown target: default to the 24% bracket ceiling.
        ceiling = next(b.max_income for b in brackets if abs(b.rate - 0.24) < 1e-9)
        target_rate = 0.24

    rows: list[dict[str, Any]] = []
    warnings: set[str] = set()
    total_converted = 0.0
    total_tax = 0.0

    for offset in range(horizon):
        if balance <= 0.5:
            break
        year = start_year + offset
        taxable_income_before = max(0.0, income - standard_deduction)
        headroom = max(0.0, ceiling - taxable_income_before)
        conversion = min(balance, headroom)
        if conversion <= 0.5:
            rows.append(
                {
                    "year": year,
                    "starting_balance_usd": round(balance, 2),
                    "conversion_usd": 0.0,
                    "estimated_tax_usd": 0.0,
                    "effective_rate_on_conversion": None,
                    "ending_balance_usd": round(balance * (1 + growth), 2),
                    "note": "No headroom below the target bracket this year.",
                }
            )
            balance *= 1 + growth
            continue

        base = estimate_federal_tax(
            tax_year=year if year in TAX_CONFIG_BY_YEAR else start_year,
            filing_status=filing,
            ordinary_income_usd=income,
            state_tax_rate=state_rate,
            age=age,
        )
        with_conversion = estimate_federal_tax(
            tax_year=year if year in TAX_CONFIG_BY_YEAR else start_year,
            filing_status=filing,
            ordinary_income_usd=income + conversion,
            state_tax_rate=state_rate,
            age=age,
        )
        for payload in (base, with_conversion):
            for warning in payload.get("warnings") or []:
                warnings.add(str(warning))
        tax_delta = float(with_conversion.get("total_estimated_tax_usd") or 0.0) - float(
            base.get("total_estimated_tax_usd") or 0.0
        )
        irmaa_delta = float(with_conversion.get("irmaa_annual_surcharge_usd") or 0.0) - float(
            base.get("irmaa_annual_surcharge_usd") or 0.0
        )
        if irmaa_delta > 0:
            warnings.add(
                "Conversions push income across an IRMAA threshold in at least one year — "
                "Medicare premiums rise two years later."
            )

        balance_after = (balance - conversion) * (1 + growth)
        rows.append(
            {
                "year": year,
                "starting_balance_usd": round(balance, 2),
                "conversion_usd": round(conversion, 2),
                "estimated_tax_usd": round(tax_delta, 2),
                "effective_rate_on_conversion": round(tax_delta / conversion, 4) if conversion else None,
                "irmaa_delta_usd": round(irmaa_delta, 2),
                "ending_balance_usd": round(balance_after, 2),
            }
        )
        total_converted += conversion
        total_tax += tax_delta
        balance = balance_after

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "traditional_balance_usd": round(float(traditional_balance_usd or 0.0), 2),
            "filing_status": filing,
            "annual_ordinary_income_usd": round(income, 2),
            "target_bracket_rate": target_rate,
            "years": horizon,
            "annual_growth_rate": growth,
            "state_tax_rate": state_rate,
            "tax_year": start_year,
        },
        "schedule": rows,
        "total_converted_usd": round(total_converted, 2),
        "total_estimated_tax_usd": round(total_tax, 2),
        "average_rate_on_conversions": round(total_tax / total_converted, 4) if total_converted else None,
        "remaining_balance_usd": round(balance, 2),
        "warnings": sorted(warnings),
        "notes": [
            "Fill-the-bracket schedule: each year converts up to the top of the "
            "target federal bracket given expected ordinary income.",
            "Taxes are the full-engine delta (federal + state + IRMAA) between "
            "converting and not converting in that year.",
            "This is planning support, not advice — coordinate with RMD timing, "
            "ACA subsidies, and state rules before acting.",
        ],
    }
