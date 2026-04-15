"""Debt payoff projection helpers for planning workflows.

Debt processing and strategy behavior are adapted from Ignidash (MIT):
- src/lib/calc/debts.ts
- src/lib/schemas/inputs/debt-form-schema.ts
- src/lib/calc/debts.test.ts
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from buildwealth_orchestrator.services.service_utils import safe_float, safe_int

PayoffStrategy = Literal["minimum", "snowball", "avalanche", "custom"]


def _add_months(base: date, months: int) -> date:
    total_month = base.month - 1 + months
    year = base.year + total_month // 12
    month = total_month % 12 + 1
    return date(year, month, 1)


def _resolve_strategy(value: Any) -> PayoffStrategy:
    text = str(value or "").strip().lower()
    if text in {"minimum", "snowball", "avalanche", "custom"}:
        return text  # type: ignore[return-value]
    return "minimum"


@dataclass
class _DebtState:
    id: str
    label: str
    balance: float
    original_balance: float
    annual_rate: float
    minimum_payment: float
    payoff_strategy: PayoffStrategy
    custom_monthly_payment: float
    interest_paid: float = 0.0
    principal_paid: float = 0.0

    @property
    def is_paid_off(self) -> bool:
        return self.balance <= 0.0


def _build_debt_states(
    debt_items: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> list[_DebtState]:
    debts: list[_DebtState] = []
    for index, raw in enumerate(debt_items, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped debt row #{index}: expected an object.")
            continue

        label = str(raw.get("label") or f"Debt {index}").strip() or f"Debt {index}"
        balance = max(0.0, safe_float(raw.get("balance_usd", raw.get("balance")), 0.0))
        if balance <= 0:
            continue

        raw_rate = safe_float(raw.get("interest_rate", raw.get("apr")), 0.0)
        if raw_rate > 1.0:
            raw_rate = raw_rate / 100.0
        annual_rate = max(0.0, min(1.0, raw_rate))
        minimum_payment = max(0.0, safe_float(raw.get("minimum_payment_usd", raw.get("monthlyPayment")), 0.0))
        if minimum_payment <= 0:
            warnings.append(f"Skipped debt '{label}': minimum payment must be greater than zero.")
            continue

        custom_monthly = max(0.0, safe_float(raw.get("custom_monthly_payment_usd"), 0.0))
        debts.append(
            _DebtState(
                id=str(raw.get("id") or f"debt-{index}"),
                label=label,
                balance=balance,
                original_balance=balance,
                annual_rate=annual_rate,
                minimum_payment=minimum_payment,
                payoff_strategy=_resolve_strategy(raw.get("payoff_strategy")),
                custom_monthly_payment=custom_monthly,
            )
        )
    return debts


def _ranked_targets(
    debts: list[_DebtState],
    strategy: PayoffStrategy,
) -> list[_DebtState]:
    active = [debt for debt in debts if not debt.is_paid_off]
    if strategy == "avalanche":
        return sorted(active, key=lambda item: (-item.annual_rate, item.balance, item.id))
    return sorted(active, key=lambda item: (item.balance, -item.annual_rate, item.id))


def _run_projection_scenario(
    debt_items: list[dict[str, Any]],
    *,
    strategy: PayoffStrategy,
    start_date: date,
    max_months: int,
    monthly_accelerated_payment_usd: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    debts = _build_debt_states(debt_items, warnings=warnings)
    if not debts:
        return {
            "strategy": strategy,
            "months_to_payoff": 0,
            "payoff_date": start_date.isoformat(),
            "paid_off": True,
            "remaining_balance_usd": 0.0,
            "total_interest_paid_usd": 0.0,
            "total_principal_paid_usd": 0.0,
            "total_paid_usd": 0.0,
            "first_year_payments_usd": 0.0,
            "month_points": [],
            "debt_summaries": [],
            "warnings": warnings,
        }

    monthly_extra = max(0.0, float(monthly_accelerated_payment_usd))
    month_points: list[dict[str, Any]] = []
    first_year_payments = 0.0

    for month_index in range(1, max_months + 1):
        active = [debt for debt in debts if not debt.is_paid_off]
        if not active:
            break

        month_interest = 0.0
        month_principal = 0.0
        month_payments = 0.0

        # First pass: accrue interest + pay minimums.
        for debt in active:
            interest = max(0.0, debt.balance * (debt.annual_rate / 12.0))
            debt.balance += interest

            payment = min(debt.minimum_payment, debt.balance)
            principal = max(0.0, payment - interest)
            debt.balance = max(0.0, debt.balance - payment)

            debt.interest_paid += interest
            debt.principal_paid += principal
            month_interest += interest
            month_principal += principal
            month_payments += payment

        # Strategy-based accelerated payments.
        if strategy in {"snowball", "avalanche"} and monthly_extra > 0:
            remaining_extra = monthly_extra
            for target in _ranked_targets(debts, strategy):
                if remaining_extra <= 0:
                    break
                if target.is_paid_off:
                    continue
                extra_payment = min(remaining_extra, target.balance)
                target.balance = max(0.0, target.balance - extra_payment)
                target.principal_paid += extra_payment
                month_principal += extra_payment
                month_payments += extra_payment
                remaining_extra -= extra_payment

        if strategy == "custom":
            for debt in _ranked_targets(debts, "snowball"):
                if debt.is_paid_off:
                    continue
                custom_extra = debt.custom_monthly_payment
                if custom_extra <= 0:
                    continue
                extra_payment = min(custom_extra, debt.balance)
                debt.balance = max(0.0, debt.balance - extra_payment)
                debt.principal_paid += extra_payment
                month_principal += extra_payment
                month_payments += extra_payment

            # Optional global extra still applies after per-debt custom.
            remaining_extra = monthly_extra
            for target in _ranked_targets(debts, "snowball"):
                if remaining_extra <= 0:
                    break
                if target.is_paid_off:
                    continue
                extra_payment = min(remaining_extra, target.balance)
                target.balance = max(0.0, target.balance - extra_payment)
                target.principal_paid += extra_payment
                month_principal += extra_payment
                month_payments += extra_payment
                remaining_extra -= extra_payment

        if month_index <= 12:
            first_year_payments += month_payments

        total_balance = sum(max(0.0, debt.balance) for debt in debts)
        month_points.append(
            {
                "month_index": month_index,
                "as_of": _add_months(start_date, month_index - 1).isoformat(),
                "total_balance_usd": round(total_balance, 2),
                "payment_usd": round(month_payments, 2),
                "interest_paid_usd": round(month_interest, 2),
                "principal_paid_usd": round(month_principal, 2),
                "active_debts": len([item for item in debts if not item.is_paid_off]),
            }
        )

    remaining_balance = sum(max(0.0, debt.balance) for debt in debts)
    paid_off = remaining_balance <= 0.01
    months_to_payoff = len(month_points) if paid_off else max_months
    payoff_date = _add_months(start_date, max(0, months_to_payoff - 1)).isoformat()

    debt_summaries = [
        {
            "id": debt.id,
            "label": debt.label,
            "original_balance_usd": round(debt.original_balance, 2),
            "remaining_balance_usd": round(max(0.0, debt.balance), 2),
            "interest_paid_usd": round(debt.interest_paid, 2),
            "principal_paid_usd": round(debt.principal_paid, 2),
            "paid_off": debt.is_paid_off,
        }
        for debt in debts
    ]

    total_interest = sum(debt.interest_paid for debt in debts)
    total_principal = sum(debt.principal_paid for debt in debts)
    total_paid = total_interest + total_principal

    if not paid_off:
        warnings.append("Projection horizon ended before all debts were paid off.")

    return {
        "strategy": strategy,
        "months_to_payoff": months_to_payoff,
        "payoff_date": payoff_date,
        "paid_off": paid_off,
        "remaining_balance_usd": round(remaining_balance, 2),
        "total_interest_paid_usd": round(total_interest, 2),
        "total_principal_paid_usd": round(total_principal, 2),
        "total_paid_usd": round(total_paid, 2),
        "first_year_payments_usd": round(first_year_payments, 2),
        "month_points": month_points,
        "debt_summaries": debt_summaries,
        "warnings": warnings,
    }


def project_debt_payoff(
    debt_items: list[dict[str, Any]],
    *,
    start_date: date | None = None,
    max_years: int = 40,
    strategy: PayoffStrategy = "minimum",
    monthly_accelerated_payment_usd: float = 0.0,
) -> dict[str, Any]:
    resolved_start = start_date or datetime.now().date().replace(day=1)
    resolved_years = max(1, min(safe_int(max_years, 40), 80))
    max_months = resolved_years * 12
    resolved_strategy = _resolve_strategy(strategy)
    resolved_monthly_extra = max(0.0, safe_float(monthly_accelerated_payment_usd, 0.0))

    minimum = _run_projection_scenario(
        debt_items,
        strategy="minimum",
        start_date=resolved_start,
        max_months=max_months,
        monthly_accelerated_payment_usd=0.0,
    )
    selected = _run_projection_scenario(
        debt_items,
        strategy=resolved_strategy,
        start_date=resolved_start,
        max_months=max_months,
        monthly_accelerated_payment_usd=resolved_monthly_extra,
    )

    months_saved = (
        int(minimum["months_to_payoff"]) - int(selected["months_to_payoff"])
        if bool(minimum["paid_off"]) and bool(selected["paid_off"])
        else None
    )
    interest_saved = float(minimum["total_interest_paid_usd"]) - float(selected["total_interest_paid_usd"])

    warnings: list[str] = []
    warnings.extend(minimum.get("warnings", []))
    warnings.extend(selected.get("warnings", []))

    return {
        "start_date": resolved_start.isoformat(),
        "max_years": resolved_years,
        "debt_items_count": len([item for item in debt_items if isinstance(item, dict)]),
        "strategy": resolved_strategy,
        "monthly_accelerated_payment_usd": round(resolved_monthly_extra, 2),
        "minimum_scenario": minimum,
        "selected_scenario": selected,
        "payoff_months_saved_vs_minimum": months_saved,
        "interest_saved_vs_minimum_usd": round(interest_saved, 2),
        "warnings": warnings,
    }


__all__ = ["project_debt_payoff"]
