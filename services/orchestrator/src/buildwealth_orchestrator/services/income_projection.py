"""Income projection helpers for planning workflows.

Projection structure and growth/timeframe behavior are adapted from Ignidash (MIT):
- src/lib/calc/incomes.ts
- src/lib/schemas/inputs/income-form-schema.ts
- src/lib/schemas/inputs/income-expenses-shared-schemas.ts
"""

from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.service_utils import (
    RecurringProjectionConfig,
    project_recurring_schedule,
)

_INCOME_SCHEDULE_CONFIG = RecurringProjectionConfig(
    item_kind="income",
    label_prefix="Income",
    id_prefix="income",
    rate_field="annual_growth_rate",
    grouping_field="is_pre_tax",
    grouping_default=False,
    yearly_total_key="gross_income_usd",
    yearly_group_true_key="pre_tax_income_usd",
    yearly_group_false_key="post_tax_income_usd",
    yearly_active_key="active_income_items",
    item_count_key="income_items_count",
    first_year_key="first_year_gross_income_usd",
    final_year_key="final_year_gross_income_usd",
    cumulative_key="cumulative_gross_income_usd",
    annualized_growth_key="annualized_income_growth_rate",
    default_rate_key="default_annual_growth_rate",
)


def _build_income_extra_fields(raw: dict[str, Any], _: int, __: str) -> dict[str, Any]:
    return {
        "is_pre_tax": bool(raw.get("is_pre_tax", False)),
    }


def project_income_schedule(
    income_items: list[dict[str, Any]],
    *,
    start_year: int,
    years: int,
    default_annual_growth_rate: float = 0.03,
) -> dict[str, Any]:
    return project_recurring_schedule(
        income_items,
        start_year=start_year,
        years=years,
        default_rate=default_annual_growth_rate,
        config=_INCOME_SCHEDULE_CONFIG,
        extra_fields_builder=_build_income_extra_fields,
    )


__all__ = ["project_income_schedule"]
