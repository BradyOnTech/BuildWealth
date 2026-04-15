"""Shared recurring projection helpers for `income_projection` and `expense_projection`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from buildwealth_orchestrator.services.value_coercion import (
    clamp,
    parse_optional_date,
    safe_float,
    safe_int,
)


def active_months_for_year(
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


@dataclass(frozen=True)
class RecurringProjectionConfig:
    item_kind: str
    label_prefix: str
    id_prefix: str
    rate_field: str
    grouping_field: str
    grouping_default: bool
    yearly_total_key: str
    yearly_group_true_key: str
    yearly_group_false_key: str
    yearly_active_key: str
    item_count_key: str
    first_year_key: str
    final_year_key: str
    cumulative_key: str
    annualized_growth_key: str
    default_rate_key: str


def project_recurring_schedule(
    items: list[dict[str, Any]],
    *,
    start_year: int,
    years: int,
    default_rate: float,
    config: RecurringProjectionConfig,
    extra_fields_builder: Callable[[dict[str, Any], int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_start_year = safe_int(start_year, datetime.now().year)
    resolved_years = max(1, min(safe_int(years, 1), 80))
    resolved_default_rate = clamp(safe_float(default_rate, 0.03), -1.0, 1.0)

    normalized_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped {config.item_kind} row #{index}: expected an object.")
            continue

        label = str(raw.get("label") or raw.get("name") or f"{config.label_prefix} {index}").strip()
        if not label:
            label = f"{config.label_prefix} {index}"

        monthly_amount = max(0.0, safe_float(raw.get("monthly_amount_usd", raw.get("amount")), 0.0))
        if monthly_amount <= 0:
            continue

        rate_value = raw.get(config.rate_field)
        if rate_value is None:
            rate_value = resolved_default_rate
        rate_value = clamp(safe_float(rate_value, resolved_default_rate), -1.0, 1.0)

        start_date = parse_optional_date(raw.get("start_date"))
        end_date = parse_optional_date(raw.get("end_date"))
        if start_date and end_date and start_date > end_date:
            warnings.append(
                f"Ignored invalid date range for {config.item_kind} '{label}': start_date after end_date."
            )
            continue

        normalized_item = {
            "id": str(raw.get("id") or f"{config.id_prefix}-{index}"),
            "label": label,
            "monthly_amount_usd": monthly_amount,
            config.grouping_field: bool(raw.get(config.grouping_field, config.grouping_default)),
            config.rate_field: rate_value,
            "start_date": start_date,
            "end_date": end_date,
        }
        if extra_fields_builder is not None:
            normalized_item.update(extra_fields_builder(raw, index, label))
        normalized_items.append(normalized_item)

    yearly_points: list[dict[str, Any]] = []

    for offset in range(resolved_years):
        year = resolved_start_year + offset
        yearly_total = 0.0
        grouped_true = 0.0
        grouped_false = 0.0
        active_items = 0

        for item in normalized_items:
            start_date = item.get("start_date")
            end_date = item.get("end_date")
            months_active = active_months_for_year(
                year=year,
                start_date=start_date,
                end_date=end_date,
            )
            if months_active <= 0:
                continue

            active_items += 1
            growth_anchor_year = start_date.year if isinstance(start_date, date) else resolved_start_year
            years_since_anchor = max(0, year - growth_anchor_year)
            rate_value = safe_float(item.get(config.rate_field), resolved_default_rate)
            monthly_amount = safe_float(item.get("monthly_amount_usd"), 0.0)
            monthly_amount = monthly_amount * ((1.0 + rate_value) ** years_since_anchor)
            annual_amount = max(0.0, monthly_amount) * months_active

            yearly_total += annual_amount
            if item.get(config.grouping_field):
                grouped_true += annual_amount
            else:
                grouped_false += annual_amount

        yearly_points.append(
            {
                "year": year,
                config.yearly_total_key: round(yearly_total, 2),
                config.yearly_group_true_key: round(grouped_true, 2),
                config.yearly_group_false_key: round(grouped_false, 2),
                config.yearly_active_key: active_items,
            }
        )

    first_year_total = yearly_points[0][config.yearly_total_key] if yearly_points else 0.0
    final_year_total = yearly_points[-1][config.yearly_total_key] if yearly_points else 0.0
    cumulative_total = round(
        sum(safe_float(point.get(config.yearly_total_key)) for point in yearly_points),
        2,
    )

    if resolved_years > 1 and first_year_total > 0 and final_year_total > 0:
        annualized_growth_rate = ((final_year_total / first_year_total) ** (1 / (resolved_years - 1))) - 1
    else:
        annualized_growth_rate = None

    return {
        "start_year": resolved_start_year,
        "years": resolved_years,
        config.default_rate_key: round(resolved_default_rate, 6),
        config.item_count_key: len(normalized_items),
        config.first_year_key: round(first_year_total, 2),
        config.final_year_key: round(final_year_total, 2),
        config.cumulative_key: cumulative_total,
        config.annualized_growth_key: (
            round(annualized_growth_rate, 6) if annualized_growth_rate is not None else None
        ),
        "yearly_points": yearly_points,
        "warnings": warnings,
    }


__all__ = [
    "RecurringProjectionConfig",
    "active_months_for_year",
    "project_recurring_schedule",
]
