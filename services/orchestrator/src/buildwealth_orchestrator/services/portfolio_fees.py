"""Fee drag — expense ratios converted into felt dollars.

Sharpe's arithmetic, rendered: before costs the average dollar earns the
market; after costs it must earn less. Funds express costs as innocuous
percentages; people feel dollars per year. This service does the unit
conversion and nothing else.

Expense-ratio convention: canonical storage is a FRACTION (0.0003 = 3 bps).
Values above 0.02 are treated as percent-style entry (0.75 -> 0.75%) because
no retail fund charges more than 2% — this forgives the natural way a human
types "0.75" while keeping provider-fed fractions exact.
"""

from typing import Any

INDEX_ALTERNATIVE_EXPENSE_RATIO = 0.0005  # a broad-market index fund, ~5 bps
_PERCENT_ENTRY_THRESHOLD = 0.02


def normalize_expense_ratio(value: Any) -> float | None:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    if ratio <= 0:
        return None
    if ratio > _PERCENT_ENTRY_THRESHOLD:
        ratio = ratio / 100.0
    return ratio if ratio <= 0.05 else None  # >5%/yr is a data error, not a fee


def build_portfolio_fee_payload(
    holdings: list[dict[str, Any]],
    *,
    registry_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ratio_by_symbol: dict[str, float] = {}
    for row in registry_rows or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        ratio = normalize_expense_ratio(row.get("expense_ratio"))
        if symbol and ratio is not None:
            ratio_by_symbol[symbol] = ratio

    # Holdings arrive one row per account; a fund held in three accounts is
    # still one fund to the user — aggregate by symbol before pricing.
    value_by_symbol: dict[str, float] = {}
    name_by_symbol: dict[str, str] = {}
    holding_ratio_by_symbol: dict[str, float] = {}
    fund_symbols: set[str] = set()
    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        value = _safe_float(holding.get("value_usd") or holding.get("current_value"))
        if value <= 0:
            continue
        symbol = str(holding.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        value_by_symbol[symbol] = value_by_symbol.get(symbol, 0.0) + value
        name_by_symbol.setdefault(symbol, str(holding.get("name") or symbol))
        asset_type = str(holding.get("asset_type") or "").strip().lower()
        if asset_type in ("etf", "fund", "mutual_fund", "index_fund"):
            fund_symbols.add(symbol)
        ratio = normalize_expense_ratio(holding.get("expense_ratio"))
        if ratio is not None:
            holding_ratio_by_symbol.setdefault(symbol, ratio)

    rows: list[dict[str, Any]] = []
    covered_value = 0.0
    uncovered: list[str] = []
    for symbol, value in value_by_symbol.items():
        ratio = holding_ratio_by_symbol.get(symbol) or ratio_by_symbol.get(symbol)
        if ratio is None:
            # Only funds carry expense ratios; individual stocks, cash, and
            # property are free to hold and should not count as "unknown".
            if symbol in fund_symbols:
                uncovered.append(symbol)
            continue
        annual_fee = value * ratio
        index_fee = value * INDEX_ALTERNATIVE_EXPENSE_RATIO
        rows.append(
            {
                "symbol": symbol,
                "name": name_by_symbol.get(symbol, symbol),
                "value_usd": round(value, 2),
                "expense_ratio": ratio,
                "expense_ratio_pct": round(ratio * 100, 4),
                "annual_fee_usd": round(annual_fee, 2),
                "index_alternative_fee_usd": round(index_fee, 2),
                "excess_fee_usd": round(max(0.0, annual_fee - index_fee), 2),
            }
        )
        covered_value += value

    rows.sort(key=lambda row: row["annual_fee_usd"], reverse=True)
    total_fee = round(sum(row["annual_fee_usd"] for row in rows), 2)
    total_excess = round(sum(row["excess_fee_usd"] for row in rows), 2)
    weighted_ratio = (total_fee / covered_value) if covered_value > 0 else None

    return {
        "status": "ready" if rows else "no_data",
        "rows": rows,
        "total_annual_fee_usd": total_fee,
        "total_excess_vs_index_usd": total_excess,
        "ten_year_excess_usd": round(total_excess * 10, 2),
        "weighted_expense_ratio_pct": round(weighted_ratio * 100, 4) if weighted_ratio is not None else None,
        "covered_value_usd": round(covered_value, 2),
        "uncovered_symbols": sorted(set(uncovered))[:10],
        "index_alternative_expense_ratio_pct": INDEX_ALTERNATIVE_EXPENSE_RATIO * 100,
    }


def _safe_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result else 0.0  # NaN guard
