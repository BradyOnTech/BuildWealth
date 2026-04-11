"""Expense projection helpers for planning workflows.

Projection structure and growth/timeframe behavior are adapted from Ignidash (MIT):
- src/lib/calc/expenses.ts
- src/lib/schemas/inputs/expense-form-schema.ts
- src/lib/schemas/inputs/income-expenses-shared-schemas.ts
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _parse_optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        if "T" in text:
            return datetime.fromisoformat(text).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _active_months_for_year(
    *,
    year: int,
    start_date: date | None,
    end_date: date | None,
) -> int:
    if start_date and start_date.year > year:
        return 0
    if end_date and end_date.year < year:
        return 0

    start_month = 1
    end_month = 12

    if start_date and start_date.year == year:
        start_month = max(1, min(12, start_date.month))
    if end_date and end_date.year == year:
        end_month = max(1, min(12, end_date.month))

    if end_month < start_month:
        return 0
    return end_month - start_month + 1


def project_expense_schedule(
    expense_items: list[dict[str, Any]],
    *,
    start_year: int,
    years: int,
    default_inflation_rate: float = 0.03,
) -> dict[str, Any]:
    resolved_start_year = _safe_int(start_year, datetime.now().year)
    resolved_years = max(1, min(_safe_int(years, 1), 80))
    default_rate = max(-1.0, min(1.0, _safe_float(default_inflation_rate, 0.03)))

    normalized_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, raw in enumerate(expense_items, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped expense row #{index}: expected an object.")
            continue

        label = str(raw.get("label") or raw.get("name") or f"Expense {index}").strip() or f"Expense {index}"
        monthly_amount = max(0.0, _safe_float(raw.get("monthly_amount_usd", raw.get("amount")), 0.0))
        if monthly_amount <= 0:
            continue

        inflation_rate = raw.get("inflation_rate")
        if inflation_rate is None:
            inflation_rate = default_rate
        inflation_rate = max(-1.0, min(1.0, _safe_float(inflation_rate, default_rate)))

        start_date = _parse_optional_date(raw.get("start_date"))
        end_date = _parse_optional_date(raw.get("end_date"))
        if start_date and end_date and start_date > end_date:
            warnings.append(f"Ignored invalid date range for expense '{label}': start_date after end_date.")
            continue

        normalized_items.append(
            {
                "id": str(raw.get("id") or f"expense-{index}"),
                "label": label,
                "monthly_amount_usd": monthly_amount,
                "category": str(raw.get("category") or "general"),
                "is_fixed": bool(raw.get("is_fixed", True)),
                "inflation_rate": inflation_rate,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    yearly_points: list[dict[str, Any]] = []

    for offset in range(resolved_years):
        year = resolved_start_year + offset
        total_expenses = 0.0
        fixed_expenses = 0.0
        variable_expenses = 0.0
        active_items = 0

        for item in normalized_items:
            start_date = item.get("start_date")
            end_date = item.get("end_date")
            months_active = _active_months_for_year(
                year=year,
                start_date=start_date,
                end_date=end_date,
            )
            if months_active <= 0:
                continue

            active_items += 1
            growth_anchor_year = start_date.year if isinstance(start_date, date) else resolved_start_year
            years_since_anchor = max(0, year - growth_anchor_year)
            inflation_rate = _safe_float(item.get("inflation_rate"), default_rate)
            monthly_amount = _safe_float(item.get("monthly_amount_usd"), 0.0)
            monthly_amount = monthly_amount * ((1.0 + inflation_rate) ** years_since_anchor)
            annual_amount = max(0.0, monthly_amount) * months_active

            total_expenses += annual_amount
            if item.get("is_fixed", True):
                fixed_expenses += annual_amount
            else:
                variable_expenses += annual_amount

        yearly_points.append(
            {
                "year": year,
                "total_expenses_usd": round(total_expenses, 2),
                "fixed_expenses_usd": round(fixed_expenses, 2),
                "variable_expenses_usd": round(variable_expenses, 2),
                "active_expense_items": active_items,
            }
        )

    first_year_expenses = yearly_points[0]["total_expenses_usd"] if yearly_points else 0.0
    final_year_expenses = yearly_points[-1]["total_expenses_usd"] if yearly_points else 0.0
    cumulative_expenses = round(sum(_safe_float(point.get("total_expenses_usd")) for point in yearly_points), 2)

    if resolved_years > 1 and first_year_expenses > 0 and final_year_expenses > 0:
        annualized_growth_rate = ((final_year_expenses / first_year_expenses) ** (1 / (resolved_years - 1))) - 1
    else:
        annualized_growth_rate = None

    return {
        "start_year": resolved_start_year,
        "years": resolved_years,
        "default_inflation_rate": round(default_rate, 6),
        "expense_items_count": len(normalized_items),
        "first_year_expenses_usd": round(first_year_expenses, 2),
        "final_year_expenses_usd": round(final_year_expenses, 2),
        "cumulative_expenses_usd": cumulative_expenses,
        "annualized_expense_growth_rate": (
            round(annualized_growth_rate, 6) if annualized_growth_rate is not None else None
        ),
        "yearly_points": yearly_points,
        "warnings": warnings,
    }


__all__ = ["project_expense_schedule"]

