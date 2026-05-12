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
    diagnostics = _diagnostics(rows)
    contribution_ordering = _contribution_ordering_notes(rows)
    review_level = _review_level(warnings, tradeoffs, diagnostics)

    return {
        "summary": summary,
        "recommended_strategy": recommended,
        "drivers": drivers,
        "tradeoffs": tradeoffs,
        "diagnostics": diagnostics,
        "contribution_ordering": contribution_ordering,
        "review_level": review_level,
        "warnings": warnings,
        "trace": {
            "comparison_count": len(rows),
            "strategy_order": [_strategy(row) for row in rows],
            "best_future_value": _strategy(best_future),
            "lowest_tax": _strategy(lowest_tax),
            "diagnostic_count": len(diagnostics),
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


def _diagnostics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    tax_values = [_number(row.get("total_taxes_usd")) for row in rows]
    tax_values = [value for value in tax_values if value is not None]
    withdrawal_values = [_number(row.get("total_withdrawals_usd")) for row in rows]
    withdrawal_values = [value for value in withdrawal_values if value is not None]
    terminal_values = [_number(row.get("terminal_balance_usd")) for row in rows]
    terminal_values = [value for value in terminal_values if value is not None]
    p10_values = [_number(row.get("monte_carlo_p10_future_value_usd")) for row in rows]
    p10_values = [value for value in p10_values if value is not None]

    if tax_values:
        diagnostics.append(
            {
                "key": "tax_drag",
                "label": "Tax drag",
                "summary": f"Projected taxes range from {_money(min(tax_values))} to {_money(max(tax_values))}.",
                "level": _spread_level(tax_values),
            }
        )
    if terminal_values:
        diagnostics.append(
            {
                "key": "ending_value",
                "label": "Ending value",
                "summary": f"Ending balances range from {_money(min(terminal_values))} to {_money(max(terminal_values))}.",
                "level": "high" if min(terminal_values) <= 0 else _spread_level(terminal_values),
            }
        )
    if p10_values:
        diagnostics.append(
            {
                "key": "depletion_risk",
                "label": "Downside risk",
                "summary": f"The lower-end simulation range bottoms at {_money(min(p10_values))}.",
                "level": "high" if min(p10_values) <= 0 else "medium",
            }
        )
    if withdrawal_values:
        diagnostics.append(
            {
                "key": "cash_flow_stability",
                "label": "Cash-flow stability",
                "summary": f"Total planned withdrawals range from {_money(min(withdrawal_values))} to {_money(max(withdrawal_values))}.",
                "level": _spread_level(withdrawal_values),
            }
        )

    exhausted = [
        _label(_strategy(row))
        for row in rows
        if (_number(row.get("terminal_balance_usd")) or 0.0) <= 0
    ]
    if exhausted:
        diagnostics.append(
            {
                "key": "account_exhaustion",
                "label": "Account exhaustion",
                "summary": f"{', '.join(exhausted)} reaches a zero ending balance in this projection.",
                "level": "high",
            }
        )
    return diagnostics


def _contribution_ordering_notes(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    notes = [
        "Before choosing a drawdown strategy, keep contributions ordered around free employer match, tax-advantaged room, and needed cash reserves.",
        "If a strategy relies on large taxable withdrawals later, review whether more pre-retirement taxable savings would make the plan easier to fund.",
    ]
    if any((_number(row.get("total_rmds_usd")) or 0.0) > 0 for row in rows):
        notes.append("RMDs show up in this comparison, so tax-deferred contribution priority should be checked against future forced withdrawals.")
    if any((_number(row.get("total_roth_conversions_usd")) or 0.0) > 0 for row in rows):
        notes.append("Roth conversions are part of at least one result, so Roth contribution and conversion ordering should be reviewed together.")
    return notes


def _review_level(
    warnings: list[str],
    tradeoffs: list[str],
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    high_reasons = [
        item["summary"]
        for item in diagnostics
        if item.get("level") == "high"
    ]
    if warnings:
        high_reasons.append("Warnings need review before this supports a plan decision.")
    if any("runs out of money" in item.lower() for item in tradeoffs):
        high_reasons.append("At least one strategy runs out of money.")
    if high_reasons:
        return {
            "level": "high",
            "summary": "High review: read the diagnostics and save a rationale before changing the active withdrawal strategy.",
            "reasons": _dedupe(high_reasons)[:5],
        }
    return {
        "level": "low",
        "summary": "Normal review is enough before saving this as a decision note.",
        "reasons": ["No depletion, warning, or high-spread diagnostic was found."],
    }


def _spread_level(values: list[float]) -> str:
    if len(values) < 2:
        return "low"
    low = min(values)
    high = max(values)
    if high <= 0:
        return "low"
    spread = (high - low) / high
    if spread >= 0.25:
        return "high"
    if spread >= 0.1:
        return "medium"
    return "low"


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
