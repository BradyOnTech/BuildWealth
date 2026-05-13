"""Expense projection helpers for planning workflows.

Projection structure and growth/timeframe behavior are implemented for BuildWealth simulation workflows:
- src/lib/calc/expenses.ts
- src/lib/schemas/inputs/expense-form-schema.ts
- src/lib/schemas/inputs/income-expenses-shared-schemas.ts
"""

from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.recurring_projection import (
    RecurringProjectionConfig,
    project_recurring_schedule,
)

_EXPENSE_SCHEDULE_CONFIG = RecurringProjectionConfig(
    item_kind="expense",
    label_prefix="Expense",
    id_prefix="expense",
    rate_field="inflation_rate",
    grouping_field="is_fixed",
    grouping_default=True,
    yearly_total_key="total_expenses_usd",
    yearly_group_true_key="fixed_expenses_usd",
    yearly_group_false_key="variable_expenses_usd",
    yearly_active_key="active_expense_items",
    item_count_key="expense_items_count",
    first_year_key="first_year_expenses_usd",
    final_year_key="final_year_expenses_usd",
    cumulative_key="cumulative_expenses_usd",
    annualized_growth_key="annualized_expense_growth_rate",
    default_rate_key="default_inflation_rate",
)


def _build_expense_extra_fields(raw: dict[str, Any], _: int, __: str) -> dict[str, Any]:
    return {
        "category": str(raw.get("category") or "general"),
    }


def project_expense_schedule(
    expense_items: list[dict[str, Any]],
    *,
    start_year: int,
    years: int,
    default_inflation_rate: float = 0.03,
) -> dict[str, Any]:
    return project_recurring_schedule(
        expense_items,
        start_year=start_year,
        years=years,
        default_rate=default_inflation_rate,
        config=_EXPENSE_SCHEDULE_CONFIG,
        extra_fields_builder=_build_expense_extra_fields,
    )


__all__ = ["project_expense_schedule"]
