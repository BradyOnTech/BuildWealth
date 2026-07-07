"""Trim plans — a concentration breach becomes trades a person can execute.

"Review your risk" is homework; "sell ~$5,200 of NVDA from the 401k — no tax
due now" is an instruction. This service turns a breach alert into ranked,
tax-aware sell suggestions:

  - tax-advantaged accounts first (sales there are tax-neutral today),
    traditional before Roth (Roth growth is the most precious to preserve),
    taxable last, with the realized-gain split estimated from lots
  - untradable positions (property, custom-valued assets) are named, not
    pretended away — the honest advice is offsetting future contributions

The app never executes trades. These are instructions for the human, and the
numbers say exactly what each one costs.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from buildwealth_orchestrator.services.contribution_rules import (
    tax_treatment_for_account_type,
)

# Sell-preference by tax treatment: lower sells first.
_SELL_RANK = {"tax_deferred": 0, "tax_free": 1, "taxable": 2}
_LONG_TERM = timedelta(days=365)
_UNTRADABLE_ASSET_TYPES = {"property", "real_estate", "collectible", "private"}  # asset TYPES, not classes


def build_trim_plan(
    *,
    alert: dict[str, Any],
    holdings: dict[str, Any],
    accounts: list[dict[str, Any]] | None = None,
    total_market_value: float,
    as_of: datetime | None = None,
) -> dict[str, Any] | None:
    """Concrete sell plan for a single-symbol concentration breach.

    Returns None for alerts this engine does not understand (v1 handles
    single-holding concentration only).
    """
    if str(alert.get("metric") or "").strip() != "single_holding":
        return None
    context = alert.get("context") if isinstance(alert.get("context"), dict) else {}
    symbol = str(context.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    observed = _safe(alert.get("observed"))
    threshold = _safe(alert.get("threshold"))
    reduce_by = max(0.0, (observed - threshold) / 100.0 * total_market_value)
    if reduce_by <= 0:
        return None

    resolved_as_of = as_of or datetime.now(timezone.utc)
    treatment_by_account = _treatments(accounts)

    positions = []
    notes: list[str] = []
    for entry in holdings.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("symbol") or "").strip().upper() != symbol:
            continue
        value = _safe(entry.get("current_value"))
        if value <= 0:
            continue
        if is_untradable_position(entry):
            notes.append(
                f"{symbol} in {entry.get('account')} is not a market-tradable position; "
                "reduce its weight by directing future contributions elsewhere."
            )
            continue
        account_id = str(entry.get("account") or "").strip()
        treatment = treatment_by_account.get(account_id, "taxable")
        positions.append((entry, account_id, treatment, value))

    if not positions:
        return {
            "status": "no_tradable_position",
            "symbol": symbol,
            "reduce_by_usd": round(reduce_by, 2),
            "trades": [],
            "residual_usd": round(reduce_by, 2),
            "notes": notes or [f"No tradable {symbol} position was found to trim."],
        }

    positions.sort(key=lambda item: (_SELL_RANK.get(item[2], 3), -item[3]))

    trades: list[dict[str, Any]] = []
    remaining = reduce_by
    for entry, account_id, treatment, value in positions:
        if remaining <= 1.0:
            break
        sell_value = min(value, remaining)
        price = _safe(entry.get("current_price"))
        quantity = round(sell_value / price, 4) if price > 0 else None
        long_gain, short_gain = _gain_split(entry, sell_value, resolved_as_of)
        trades.append(
            {
                "symbol": symbol,
                "account_id": account_id,
                "tax_treatment": treatment,
                "sell_value_usd": round(sell_value, 2),
                "quantity": quantity,
                "estimated_long_term_gain_usd": round(long_gain, 2) if treatment == "taxable" else 0.0,
                "estimated_short_term_gain_usd": round(short_gain, 2) if treatment == "taxable" else 0.0,
                "tax_due_now": treatment == "taxable" and (long_gain > 0 or short_gain > 0),
                "note": (
                    "No tax due now — sale stays inside the account."
                    if treatment in ("tax_deferred", "tax_free")
                    else "Taxable account — gains estimated from recorded lots (FIFO)."
                ),
            }
        )
        remaining -= sell_value

    return {
        "status": "ready",
        "symbol": symbol,
        "reduce_by_usd": round(reduce_by, 2),
        "trades": trades,
        "residual_usd": round(max(0.0, remaining), 2),
        "notes": notes,
    }


def trim_plan_summary(plan: dict[str, Any]) -> str:
    """One plain sentence for the recommendation detail."""
    trades = plan.get("trades") if isinstance(plan.get("trades"), list) else []
    if not trades:
        notes = plan.get("notes") or []
        return str(notes[0]) if notes else ""
    parts = []
    for trade in trades[:3]:
        piece = f"sell ~${trade['sell_value_usd']:,.0f} of {trade['symbol']} from {trade['account_id']}"
        if trade["tax_treatment"] in ("tax_deferred", "tax_free"):
            piece += " (no tax due now)"
        else:
            gains = trade["estimated_long_term_gain_usd"] + trade["estimated_short_term_gain_usd"]
            piece += f" (≈${gains:,.0f} in realized gains)" if gains > 0 else " (no gain at current basis)"
        parts.append(piece)
    sentence = "; then ".join(parts)
    return sentence[0].upper() + sentence[1:] + "."


def _gain_split(entry: dict[str, Any], sell_value: float, as_of: datetime) -> tuple[float, float]:
    """Estimated (long_term, short_term) realized gains for a FIFO sale."""
    price = _safe(entry.get("current_price"))
    if price <= 0 or sell_value <= 0:
        return 0.0, 0.0
    quantity_to_sell = sell_value / price
    lots = entry.get("lots") if isinstance(entry.get("lots"), list) else []
    lots = sorted(
        (lot for lot in lots if isinstance(lot, dict)),
        key=lambda lot: str(lot.get("acquired_date") or "9999"),
    )
    long_gain = short_gain = 0.0
    for lot in lots:
        if quantity_to_sell <= 0:
            break
        available = _safe(lot.get("remaining_quantity") or lot.get("quantity"))
        if available <= 0:
            continue
        take = min(available, quantity_to_sell)
        gain = (price - _safe(lot.get("unit_cost"))) * take
        if _is_long_term(lot.get("acquired_date"), as_of):
            long_gain += gain
        else:
            short_gain += gain
        quantity_to_sell -= take
    if quantity_to_sell > 0:
        # No lot coverage for part of the sale: fall back to average cost.
        avg_cost = _safe(entry.get("avg_cost_per_share"))
        if avg_cost > 0:
            long_gain += (price - avg_cost) * quantity_to_sell
    return long_gain, short_gain


def _is_long_term(acquired_date: Any, as_of: datetime) -> bool:
    text = str(acquired_date or "").strip()
    try:
        acquired = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return True  # unknown age: assume long-term, the kinder tax estimate
    if acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=timezone.utc)
    return (as_of - acquired) >= _LONG_TERM


def is_untradable_position(entry: dict[str, Any]) -> bool:
    """Personal, illiquid, or custom-valued — not market-tradable money.

    Shared discriminator: the rebalancing engine skips these for trades and
    the diversification score excludes them from the investable universe.
    """
    if bool(entry.get("is_custom_asset")) and str(entry.get("valuation_method") or "").strip():
        return True
    # asset_TYPE only: direct property is type real_estate/property, while a
    # REIT fund is type etf with asset_class real_estate — and fully tradable.
    asset_type = str(entry.get("asset_type") or "").strip().lower()
    return asset_type in _UNTRADABLE_ASSET_TYPES


def _treatments(accounts: list[dict[str, Any]] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for account in accounts or []:
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            continue
        result[account_id] = tax_treatment_for_account_type(str(account.get("type") or ""))
    return result


def _safe(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result else 0.0


# ─── Allocation drift ───────────────────────────────────────────────────────
# Targets say where the household wants to be; drift guidance says how far
# off it is and where the next dollar (or the next trim) should go. Research
# framing only — the app never trades.

DRIFT_TOLERANCE_PCT = 5.0


def build_allocation_drift_plan(
    *,
    holdings: dict[str, Any],
    targets_pct: dict[str, Any],
    total_market_value: float,
    tolerance_pct: float = DRIFT_TOLERANCE_PCT,
) -> dict[str, Any]:
    targets = _normalized_targets(targets_pct)
    if not targets or total_market_value <= 0:
        return {"status": "no_targets", "rows": [], "tolerance_pct": tolerance_pct}

    # Allocation targets govern INVESTABLE money. A home is housing — counting
    # it here turns "you live in a house" into a fake 60-point real-estate
    # overweight with a dollar figure nobody can act on.
    value_by_class: dict[str, float] = {}
    largest_tradable: dict[str, list[tuple[float, str]]] = {}
    investable_total = 0.0
    for entry in holdings.values():
        if not isinstance(entry, dict):
            continue
        value = _safe(entry.get("current_value"))
        if value <= 0:
            continue
        if is_untradable_position(entry):
            continue
        klass = _class_key(entry.get("asset_class"))
        value_by_class[klass] = value_by_class.get(klass, 0.0) + value
        investable_total += value
        largest_tradable.setdefault(klass, []).append((value, str(entry.get("symbol") or "")))

    base_value = investable_total if investable_total > 0 else total_market_value
    if base_value <= 0:
        return {"status": "no_targets", "rows": [], "tolerance_pct": tolerance_pct}

    rows: list[dict[str, Any]] = []
    for klass, target in targets.items():
        current = round(value_by_class.get(klass, 0.0) / base_value * 100.0, 2)
        drift = round(current - target, 2)
        if abs(drift) <= tolerance_pct:  # at tolerance is close enough — no nagging
            continue
        gap_usd = round(abs(drift) / 100.0 * base_value, 2)
        direction = "overweight" if drift > 0 else "underweight"
        candidates = [
            symbol
            for _, symbol in sorted(largest_tradable.get(klass, []), reverse=True)[:2]
            if symbol
        ]
        rows.append(
            {
                "asset_class": klass,
                "target_pct": target,
                "current_pct": current,
                "drift_pct": drift,
                "gap_usd": gap_usd,
                "direction": direction,
                "trim_candidates": candidates if direction == "overweight" else [],
                # For underweights the same largest-holdings list answers the
                # opposite question: which of the household's OWN funds new
                # money could go to.
                "add_candidates": candidates if direction == "underweight" else [],
            }
        )

    rows.sort(key=lambda row: abs(row["drift_pct"]), reverse=True)
    return {
        "status": "ready" if rows else "on_target",
        "rows": rows,
        "tolerance_pct": tolerance_pct,
        "targets_pct": targets,
        "investable_value_usd": round(base_value, 2),
    }


def build_excess_cash_deployment(
    *,
    excess_cash_usd: float,
    holdings: dict[str, Any],
    targets_pct: dict[str, Any],
    total_market_value: float,
) -> dict[str, Any]:
    """One honest way to deploy spare cash against the saved targets.

    Underweight gaps are filled first (largest first), and whatever remains
    follows the target weights — naming the household's OWN largest fund in
    each class so "add to fixed income" reads as "add to BND". The cash class
    itself never receives a deployment (the money is already cash).

    Static approximation on purpose: gaps are measured before any deployment,
    not re-solved after each dollar — this is a review-only suggestion, not
    an order ticket, and false precision would overstate what it is.
    """
    excess = round(max(_safe(excess_cash_usd), 0.0), 2)
    if excess <= 0:
        return {"status": "no_excess", "rows": [], "sentence": ""}
    plan = build_allocation_drift_plan(
        holdings=holdings,
        targets_pct=targets_pct,
        total_market_value=total_market_value,
    )
    if plan.get("status") == "no_targets":
        return {"status": "no_targets", "rows": [], "sentence": ""}

    rows: list[dict[str, Any]] = []
    remaining = excess

    underweights = [
        row
        for row in plan.get("rows") or []
        if row.get("direction") == "underweight" and str(row.get("asset_class")) != "cash"
    ]
    for row in sorted(underweights, key=lambda item: -_safe(item.get("gap_usd"))):
        if remaining <= 0:
            break
        amount = round(min(_safe(row.get("gap_usd")), remaining), 2)
        if amount <= 0:
            continue
        rows.append(
            {
                "asset_class": row.get("asset_class"),
                "amount_usd": amount,
                "reason": "closes_gap",
                "add_candidates": row.get("add_candidates") or [],
            }
        )
        remaining = round(remaining - amount, 2)

    if remaining > 0:
        targets = {
            klass: pct
            for klass, pct in (plan.get("targets_pct") or {}).items()
            if klass != "cash"
        }
        total_weight = sum(targets.values())
        if total_weight > 0:
            largest_by_class: dict[str, list[str]] = {}
            for entry in holdings.values():
                if not isinstance(entry, dict) or is_untradable_position(entry):
                    continue
                klass = _class_key(entry.get("asset_class"))
                symbol = str(entry.get("symbol") or "").strip()
                if symbol and klass in targets:
                    largest_by_class.setdefault(klass, []).append(symbol)
            for klass, pct in sorted(targets.items(), key=lambda item: -item[1]):
                amount = round(remaining * pct / total_weight, 2)
                if amount <= 0:
                    continue
                rows.append(
                    {
                        "asset_class": klass,
                        "amount_usd": amount,
                        "reason": "target_weight",
                        "add_candidates": (largest_by_class.get(klass) or [])[:2],
                    }
                )

    if not rows:
        return {"status": "no_targets", "rows": [], "sentence": ""}

    # A class can receive money twice (gap fill + remainder); one line per
    # class is what a person can actually read.
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        klass = str(row["asset_class"])
        if klass in merged:
            merged[klass]["amount_usd"] = round(merged[klass]["amount_usd"] + _safe(row["amount_usd"]), 2)
            if not merged[klass]["add_candidates"]:
                merged[klass]["add_candidates"] = row["add_candidates"]
        else:
            merged[klass] = dict(row)
    merged_rows = sorted(merged.values(), key=lambda row: -_safe(row["amount_usd"]))

    parts: list[str] = []
    for row in merged_rows:
        klass = str(row["asset_class"]).replace("_", " ")
        candidates = ", ".join(row["add_candidates"][:2])
        suffix = f" (add to {candidates})" if candidates else ""
        parts.append(f"${_safe(row['amount_usd']):,.0f} to {klass}{suffix}")
    sentence = (
        "One way to deploy it against your saved targets: "
        + "; ".join(parts)
        + ". A suggestion to review, not an order."
    )
    return {"status": "ready", "rows": merged_rows, "sentence": sentence}


def allocation_drift_sentence(row: dict[str, Any]) -> str:
    klass = str(row.get("asset_class") or "").replace("_", " ")
    gap = _safe(row.get("gap_usd"))
    if row.get("direction") == "underweight":
        return (
            f"{klass.title()} is {abs(_safe(row.get('drift_pct'))):.1f} points under your "
            f"{_safe(row.get('target_pct')):.0f}% target — directing roughly ${gap:,.0f} of future "
            "contributions there closes the gap without selling anything."
        )
    candidates = ", ".join(row.get("trim_candidates") or [])
    tail = f" Largest positions there: {candidates}." if candidates else ""
    return (
        f"{klass.title()} is {abs(_safe(row.get('drift_pct'))):.1f} points over your "
        f"{_safe(row.get('target_pct')):.0f}% target (≈${gap:,.0f}).{tail}"
    )


def _normalized_targets(targets_pct: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in (targets_pct or {}).items():
        pct = _safe(value)
        klass = _class_key(key)
        if klass and 0 < pct <= 100:
            result[klass] = pct
    return result


def _class_key(value: Any) -> str:
    return str(value or "unclassified").strip().lower().replace(" ", "_")
