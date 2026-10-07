"""Timeline event impact helpers for planning workflows.

Retirement-timeline schema and persistence patterns are written independently; design reference: Ignidash (see ATTRIBUTIONS.md):
- src/lib/schemas/inputs/timeline-form-schema.ts
- convex/timeline.ts
- convex/validators/timeline_validator.ts
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from buildwealth_orchestrator.services.timeline_defaults import (
    TIMELINE_DEFAULT_IMPACT_BY_EVENT as DEFAULT_IMPACT_BY_EVENT,
    TIMELINE_EVENT_TYPES,
    TIMELINE_FREQUENCIES,
    TIMELINE_IMPACT_TYPES,
)


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
    start_date: date,
    end_date: date | None,
) -> int:
    if start_date.year > year:
        return 0
    if end_date and end_date.year < year:
        return 0

    start_month = 1
    end_month = 12

    if start_date.year == year:
        start_month = max(1, min(12, start_date.month))
    if end_date and end_date.year == year:
        end_month = max(1, min(12, end_date.month))

    if end_month < start_month:
        return 0
    return end_month - start_month + 1


def project_timeline_impacts(
    timeline_events: list[dict[str, Any]],
    *,
    start_year: int,
    years: int,
) -> dict[str, Any]:
    resolved_start_year = _safe_int(start_year, datetime.now().year)
    resolved_years = max(1, min(_safe_int(years, 1), 80))
    warnings: list[str] = []
    normalized_events: list[dict[str, Any]] = []

    for index, raw in enumerate(timeline_events, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped timeline event #{index}: expected an object.")
            continue

        label = str(raw.get("label") or f"Event {index}").strip() or f"Event {index}"
        event_type = str(raw.get("event_type") or "milestone").strip().lower()
        if event_type not in TIMELINE_EVENT_TYPES:
            warnings.append(f"Skipped timeline event '{label}': unsupported event_type '{event_type}'.")
            continue

        event_date = _parse_optional_date(raw.get("date"))
        if event_date is None:
            warnings.append(f"Skipped timeline event '{label}': missing/invalid date.")
            continue

        impact_type = str(raw.get("impact_type") or DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")).strip().lower()
        if impact_type not in TIMELINE_IMPACT_TYPES:
            warnings.append(f"Skipped timeline event '{label}': unsupported impact_type '{impact_type}'.")
            continue

        frequency = str(raw.get("recurring_frequency") or "one_time").strip().lower()
        if frequency not in TIMELINE_FREQUENCIES:
            warnings.append(f"Skipped timeline event '{label}': unsupported recurring_frequency '{frequency}'.")
            continue

        amount = _safe_float(raw.get("amount_usd"), 0.0)
        end_date = _parse_optional_date(raw.get("end_date"))
        if end_date and event_date > end_date:
            warnings.append(f"Skipped timeline event '{label}': date is after end_date.")
            continue

        normalized_events.append(
            {
                "id": str(raw.get("id") or f"event-{index}"),
                "label": label,
                "event_type": event_type,
                "date": event_date,
                "impact_type": impact_type,
                "amount_usd": amount,
                "recurring_frequency": frequency,
                "end_date": end_date,
                "account_id": str(raw.get("account_id") or "").strip() or None,
                "notes": str(raw.get("notes") or "").strip(),
            }
        )

    yearly_points: list[dict[str, Any]] = []
    cumulative_net_cashflow = 0.0

    for offset in range(resolved_years):
        year = resolved_start_year + offset
        income = 0.0
        expense = 0.0
        portfolio = 0.0
        contribution = 0.0
        debt_payment = 0.0
        events_applied = 0

        for event in normalized_events:
            event_date = event["date"]
            frequency = event["recurring_frequency"]
            amount = _safe_float(event.get("amount_usd"), 0.0)
            if amount == 0:
                continue

            year_amount = 0.0
            if frequency == "one_time":
                if event_date.year == year:
                    year_amount = amount
            elif frequency == "yearly":
                if event_date.year <= year and (event.get("end_date") is None or event["end_date"].year >= year):
                    year_amount = amount
            elif frequency == "monthly":
                months_active = _active_months_for_year(
                    year=year,
                    start_date=event_date,
                    end_date=event.get("end_date"),
                )
                if months_active > 0:
                    year_amount = amount * months_active

            if year_amount == 0:
                continue

            impact_type = event["impact_type"]
            if impact_type == "income":
                income += year_amount
            elif impact_type == "expense":
                expense += year_amount
            elif impact_type == "portfolio":
                portfolio += year_amount
            elif impact_type == "contribution":
                contribution += year_amount
            elif impact_type == "debt_payment":
                debt_payment += year_amount
            events_applied += 1

        net_cashflow = income - expense - debt_payment - contribution + portfolio
        cumulative_net_cashflow += net_cashflow
        yearly_points.append(
            {
                "year": year,
                "income_impact_usd": round(income, 2),
                "expense_impact_usd": round(expense, 2),
                "portfolio_impact_usd": round(portfolio, 2),
                "contribution_impact_usd": round(contribution, 2),
                "debt_payment_impact_usd": round(debt_payment, 2),
                "net_cashflow_impact_usd": round(net_cashflow, 2),
                "events_applied": events_applied,
            }
        )

    first_year = yearly_points[0] if yearly_points else {}
    return {
        "start_year": resolved_start_year,
        "years": resolved_years,
        "events_count": len(normalized_events),
        "first_year_income_impact_usd": round(_safe_float(first_year.get("income_impact_usd")), 2),
        "first_year_expense_impact_usd": round(_safe_float(first_year.get("expense_impact_usd")), 2),
        "first_year_portfolio_impact_usd": round(_safe_float(first_year.get("portfolio_impact_usd")), 2),
        "first_year_contribution_impact_usd": round(_safe_float(first_year.get("contribution_impact_usd")), 2),
        "first_year_debt_payment_impact_usd": round(_safe_float(first_year.get("debt_payment_impact_usd")), 2),
        "cumulative_net_cashflow_impact_usd": round(cumulative_net_cashflow, 2),
        "yearly_points": yearly_points,
        "warnings": warnings,
    }


__all__ = ["project_timeline_impacts"]
