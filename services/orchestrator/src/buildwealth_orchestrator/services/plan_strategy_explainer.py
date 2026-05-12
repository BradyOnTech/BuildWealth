from __future__ import annotations

from typing import Any


STRATEGY_LABELS = {
    "cashflow_only": "Cashflow Only",
    "four_percent_rule": "4% Rule",
    "dynamic_guardrails": "Dynamic Guardrails",
    "bond_tent": "Bond Tent",
    "bucket_strategy": "Bucket Strategy",
}


def explain_withdrawal_strategy_comparison(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate withdrawal comparison rows into plain-language decision guidance."""

    rows = [row for row in payload.get("comparisons", []) if isinstance(row, dict)]
    warnings = _warning_list(payload, rows)
    if not rows:
        return {
            "summary": "No withdrawal strategy results were available to explain.",
            "recommended_strategy": None,
            "drivers": [],
            "tradeoffs": [],
            "warnings": warnings,
            "trace": {"comparison_count": 0},
        }

    best_future = _best_row(rows, "baseline_future_value_usd")
    best_real = _best_row(rows, "baseline_real_value_usd")
    best_p50 = _best_row(rows, "monte_carlo_p50_future_value_usd")
    lowest_tax = _best_row(rows, "total_taxes_usd", lowest=True)
    highest_withdrawals = _best_row(rows, "total_withdrawals_usd")
    safest_p10 = _best_row(rows, "monte_carlo_p10_future_value_usd")

    recommended = _recommended_strategy(
        [
            _strategy(best_future),
            _strategy(best_real),
            _strategy(best_p50),
            _strategy(safest_p10),
        ]
    )

    summary = _summary(recommended, best_future, lowest_tax, warnings)
    drivers = _drivers(
        best_future=best_future,
        best_real=best_real,
        best_p50=best_p50,
        safest_p10=safest_p10,
        lowest_tax=lowest_tax,
        highest_withdrawals=highest_withdrawals,
    )
    tradeoffs = _tradeoffs(rows, best_future, lowest_tax)

    return {
        "summary": summary,
        "recommended_strategy": recommended,
        "drivers": drivers,
        "tradeoffs": tradeoffs,
        "warnings": warnings,
        "trace": {
            "comparison_count": len(rows),
            "strategy_order": [_strategy(row) for row in rows],
            "best_future_value": _strategy(best_future),
            "lowest_tax": _strategy(lowest_tax),
        },
    }


def _summary(
    recommended: str | None,
    best_future: dict[str, Any] | None,
    lowest_tax: dict[str, Any] | None,
    warnings: list[str],
) -> str:
    if recommended:
        lead = f"{_label(recommended)} has the strongest overall result in this comparison."
    elif best_future:
        lead = f"{_label(_strategy(best_future))} has the highest projected ending value."
    else:
        lead = "The comparison shows trade-offs, but no clear winner."

    parts = [lead]
    if lowest_tax and _strategy(lowest_tax) and _strategy(lowest_tax) != recommended:
        parts.append(f"{_label(_strategy(lowest_tax))} has the lowest projected taxes.")
    if warnings:
        parts.append("Review the warnings before using this for a plan decision.")
    return " ".join(parts)


def _drivers(
    *,
    best_future: dict[str, Any] | None,
    best_real: dict[str, Any] | None,
    best_p50: dict[str, Any] | None,
    safest_p10: dict[str, Any] | None,
    lowest_tax: dict[str, Any] | None,
    highest_withdrawals: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows = [
        _driver("Highest ending value", best_future, "baseline_future_value_usd", "ending value"),
        _driver("Highest inflation-adjusted value", best_real, "baseline_real_value_usd", "inflation-adjusted value"),
        _driver("Best middle simulation result", best_p50, "monte_carlo_p50_future_value_usd", "middle simulation value"),
        _driver("Best rough downside result", safest_p10, "monte_carlo_p10_future_value_usd", "lower-end simulation value"),
        _driver("Lowest taxes", lowest_tax, "total_taxes_usd", "projected taxes", lower_is_better=True),
        _driver("Most cash withdrawn", highest_withdrawals, "total_withdrawals_usd", "projected withdrawals"),
    ]
    return [row for row in rows if row is not None]


def _driver(
    label: str,
    row: dict[str, Any] | None,
    key: str,
    metric_label: str,
    *,
    lower_is_better: bool = False,
) -> dict[str, Any] | None:
    if not row:
        return None
    value = _number(row.get(key))
    strategy = _strategy(row)
    if value is None or not strategy:
        return None
    direction = "positive" if not lower_is_better else "neutral"
    return {
        "label": label,
        "strategy": strategy,
        "strategy_label": _label(strategy),
        "direction": direction,
        "detail": f"{_label(strategy)} has the {'lowest' if lower_is_better else 'highest'} {metric_label}: {_money(value)}.",
        "amount_usd": value,
    }


def _tradeoffs(
    rows: list[dict[str, Any]],
    best_future: dict[str, Any] | None,
    lowest_tax: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    if best_future and lowest_tax and _strategy(best_future) != _strategy(lowest_tax):
        future_tax = _number(best_future.get("total_taxes_usd"))
        low_tax = _number(lowest_tax.get("total_taxes_usd"))
        if future_tax is not None and low_tax is not None:
            notes.append(
                f"{_label(_strategy(best_future))} has the highest ending value, but "
                f"{_label(_strategy(lowest_tax))} projects {_money(abs(future_tax - low_tax))} less in taxes."
            )

    balances = [_number(row.get("terminal_balance_usd")) for row in rows]
    balances = [value for value in balances if value is not None]
    if balances and min(balances) <= 0:
        notes.append("At least one strategy runs out of money before the end of the projection.")

    degraded = [_label(_strategy(row)) for row in rows if str(row.get("engine_status") or "").lower() == "degraded"]
    if degraded:
        notes.append(f"{', '.join(degraded)} used a lower-confidence model result.")

    return notes


def _recommended_strategy(strategies: list[str | None]) -> str | None:
    counts: dict[str, int] = {}
    for strategy in strategies:
        if not strategy:
            continue
        counts[strategy] = counts.get(strategy, 0) + 1
    if not counts:
        return None
    strategy, count = max(counts.items(), key=lambda item: (item[1], item[0]))
    return strategy if count >= 2 else None


def _best_row(rows: list[dict[str, Any]], key: str, *, lowest: bool = False) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for row in rows:
        value = _number(row.get(key))
        if value is None:
            continue
        if best is None:
            best = row
            continue
        best_value = _number(best.get(key))
        if best_value is None or (value < best_value if lowest else value > best_value):
            best = row
    return best


def _warning_list(payload: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if isinstance(payload.get("warnings"), list):
        warnings.extend(str(item).strip() for item in payload["warnings"] if str(item).strip())
    for row in rows:
        row_warnings = row.get("warnings")
        if isinstance(row_warnings, list):
            warnings.extend(str(item).strip() for item in row_warnings if str(item).strip())
    return _dedupe(warnings)


def _strategy(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    value = str(row.get("strategy") or "").strip()
    return value or None


def _label(strategy: str | None) -> str:
    return STRATEGY_LABELS.get(str(strategy or ""), _human_text(str(strategy or "")))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _human_text(value: str) -> str:
    text = str(value or "").replace("_", " ").strip()
    return text.title() if text else "Strategy"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        rows.append(value)
    return rows
