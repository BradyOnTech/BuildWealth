"""Tax-aware planning scenario engine.

Projection structure and account/phase processing patterns are adapted from
Ignidash (MIT):
- src/lib/calc/simulation-engine.ts
- src/lib/calc/portfolio.ts
- src/lib/calc/account.ts
- src/lib/calc/phase.ts
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Any, Literal

from buildwealth_orchestrator.schemas import (
    PlanningResponse,
    ScenarioAccountBalancePoint,
    ScenarioResult,
    ScenarioTimelinePoint,
)
from buildwealth_orchestrator.services.contribution_rules import (
    normalize_account_type,
    tax_treatment_for_account_type,
)
from buildwealth_orchestrator.services.tax_engine import estimate_federal_tax


FilingStatus = Literal[
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
]

VALID_FILING_STATUSES: set[str] = {
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
}


@dataclass
class ScenarioAssumptions:
    years: int
    annual_contribution_usd: float
    expected_return: float
    inflation: float


@dataclass
class ProjectionAccount:
    account_id: str
    account_type: str
    tax_treatment: Literal["taxable", "tax_deferred", "tax_free"]
    balance_usd: float
    contribution_hint_usd: float = 0.0


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


def _normalize_filing_status(value: Any) -> FilingStatus:
    text = str(value or "").strip().lower()
    if text in VALID_FILING_STATUSES:
        return text  # type: ignore[return-value]
    return "single"


def _projection_point_for_year(
    projection: dict[str, Any] | None,
    *,
    year: int,
) -> dict[str, Any] | None:
    if not isinstance(projection, dict):
        return None
    yearly_points = projection.get("yearly_points")
    if not isinstance(yearly_points, list):
        return None
    for item in yearly_points:
        if not isinstance(item, dict):
            continue
        if _safe_int(item.get("year"), -1) == year:
            return item
    return None


def _income_for_year(
    income_projection: dict[str, Any] | None,
    *,
    year: int,
) -> float:
    point = _projection_point_for_year(income_projection, year=year)
    if point is not None:
        return max(0.0, _safe_float(point.get("gross_income_usd"), 0.0))
    if not isinstance(income_projection, dict):
        return 0.0
    return max(0.0, _safe_float(income_projection.get("first_year_gross_income_usd"), 0.0))


def _expenses_for_year(
    expense_projection: dict[str, Any] | None,
    *,
    year: int,
) -> float:
    point = _projection_point_for_year(expense_projection, year=year)
    if point is not None:
        return max(0.0, _safe_float(point.get("total_expenses_usd"), 0.0))
    if not isinstance(expense_projection, dict):
        return 0.0
    return max(0.0, _safe_float(expense_projection.get("first_year_expenses_usd"), 0.0))


def _debt_payments_for_year(
    debt_projection: dict[str, Any] | None,
    *,
    year: int,
    start_year: int,
) -> float:
    if not isinstance(debt_projection, dict):
        return 0.0

    selected = debt_projection.get("selected_scenario")
    if isinstance(selected, dict):
        month_points = selected.get("month_points")
        if isinstance(month_points, list) and month_points:
            total = 0.0
            for item in month_points:
                if not isinstance(item, dict):
                    continue
                as_of = _parse_optional_date(item.get("as_of"))
                if as_of is None:
                    continue
                if as_of.year != year:
                    continue
                total += max(0.0, _safe_float(item.get("payment_usd"), 0.0))
            if total > 0:
                return total

        if year == start_year:
            return max(0.0, _safe_float(selected.get("first_year_payments_usd"), 0.0))

    if year == start_year:
        return max(0.0, _safe_float(debt_projection.get("first_year_payments_usd"), 0.0))
    return 0.0


def _timeline_impacts_for_year(
    timeline_projection: dict[str, Any] | None,
    *,
    year: int,
) -> dict[str, float]:
    defaults = {
        "income": 0.0,
        "expense": 0.0,
        "debt_payment": 0.0,
    }
    point = _projection_point_for_year(timeline_projection, year=year)
    if point is None:
        return defaults
    return {
        "income": _safe_float(point.get("income_impact_usd"), 0.0),
        "expense": _safe_float(point.get("expense_impact_usd"), 0.0),
        "debt_payment": _safe_float(point.get("debt_payment_impact_usd"), 0.0),
    }


class ScenarioEngine:
    def __init__(
        self,
        years_to_retirement: int,
        annual_contribution_usd: float,
        baseline_return: float,
        optimistic_return: float,
        conservative_return: float,
        return_volatility: float,
        inflation: float,
        monte_carlo_runs: int,
        hsa_delta_default: float,
        marginal_tax_rate: float,
    ):
        self.years_to_retirement = years_to_retirement
        self.annual_contribution_usd = annual_contribution_usd
        self.baseline_return = baseline_return
        self.optimistic_return = optimistic_return
        self.conservative_return = conservative_return
        self.return_volatility = return_volatility
        self.inflation = inflation
        self.monte_carlo_runs = monte_carlo_runs
        self.hsa_delta_default = hsa_delta_default
        self.marginal_tax_rate = marginal_tax_rate

    @staticmethod
    def _real_value(nominal_future_value: float, years: int, inflation: float) -> float:
        if years <= 0:
            return nominal_future_value
        return nominal_future_value / ((1 + inflation) ** years)

    @staticmethod
    def _copy_accounts(accounts: list[ProjectionAccount]) -> list[ProjectionAccount]:
        return [
            ProjectionAccount(
                account_id=item.account_id,
                account_type=item.account_type,
                tax_treatment=item.tax_treatment,
                balance_usd=float(item.balance_usd),
                contribution_hint_usd=float(item.contribution_hint_usd),
            )
            for item in accounts
        ]

    def _build_projection_accounts(
        self,
        *,
        accounts: list[dict[str, Any]] | None,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float,
        contribution_allocation: dict[str, Any] | None,
    ) -> list[ProjectionAccount]:
        parsed: list[ProjectionAccount] = []
        seen: set[str] = set()

        for index, raw in enumerate(accounts or [], start=1):
            if not isinstance(raw, dict):
                continue
            account_id = str(raw.get("account_id") or raw.get("id") or "").strip() or f"account-{index}"
            if account_id in seen:
                continue
            seen.add(account_id)

            account_type = normalize_account_type(raw.get("account_type") or raw.get("type"))
            tax_treatment_raw = str(raw.get("tax_treatment") or "").strip().lower()
            if tax_treatment_raw in {"taxable", "tax_deferred", "tax_free"}:
                tax_treatment: Literal["taxable", "tax_deferred", "tax_free"] = tax_treatment_raw  # type: ignore[assignment]
            else:
                tax_treatment = tax_treatment_for_account_type(account_type)

            balance_usd = max(0.0, _safe_float(raw.get("balance_usd", raw.get("balance")), 0.0))
            contribution_hint = max(
                0.0,
                _safe_float(
                    raw.get(
                        "annual_contribution_usd",
                        raw.get("annual_contribution", raw.get("total_contribution_usd", 0.0)),
                    ),
                    0.0,
                ),
            )

            parsed.append(
                ProjectionAccount(
                    account_id=account_id,
                    account_type=account_type,
                    tax_treatment=tax_treatment,
                    balance_usd=balance_usd,
                    contribution_hint_usd=contribution_hint,
                )
            )

        if not parsed:
            parsed.append(
                ProjectionAccount(
                    account_id="primary",
                    account_type="portfolio",
                    tax_treatment="taxable",
                    balance_usd=max(0.0, float(current_portfolio_value_usd)),
                    contribution_hint_usd=max(0.0, float(annual_contribution_usd)),
                )
            )

        if isinstance(contribution_allocation, dict):
            allocations = contribution_allocation.get("allocations")
            if isinstance(allocations, list):
                by_id: dict[str, float] = {}
                for item in allocations:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("account_id") or "").strip()
                    if not key:
                        continue
                    by_id[key] = max(
                        0.0,
                        _safe_float(
                            item.get(
                                "total_contribution_usd",
                                item.get("employee_contribution_usd"),
                            ),
                            0.0,
                        ),
                    )
                for account in parsed:
                    if account.account_id in by_id:
                        account.contribution_hint_usd = by_id[account.account_id]

        total_balance = sum(max(0.0, account.balance_usd) for account in parsed)
        target_total = max(0.0, float(current_portfolio_value_usd))
        if target_total <= 0:
            for account in parsed:
                account.balance_usd = 0.0
        elif total_balance <= 0:
            parsed[0].balance_usd = target_total
            for account in parsed[1:]:
                account.balance_usd = 0.0
        else:
            scale = target_total / total_balance
            for account in parsed:
                account.balance_usd = max(0.0, account.balance_usd * scale)

        return parsed

    @staticmethod
    def _preferred_contribution_account(accounts: list[ProjectionAccount]) -> ProjectionAccount:
        for account in accounts:
            if account.tax_treatment == "tax_deferred":
                return account
        for account in accounts:
            if account.tax_treatment == "taxable":
                return account
        return accounts[0]

    def _allocate_planned_contributions(
        self,
        *,
        accounts: list[ProjectionAccount],
        annual_contribution_target_usd: float,
    ) -> dict[str, float]:
        target = max(0.0, float(annual_contribution_target_usd))
        if target <= 0 or not accounts:
            return {}

        total_hints = sum(max(0.0, account.contribution_hint_usd) for account in accounts)
        if total_hints <= 0:
            preferred = self._preferred_contribution_account(accounts)
            return {preferred.account_id: target}

        allocations: dict[str, float] = {}
        running = 0.0
        for index, account in enumerate(accounts, start=1):
            weight = max(0.0, account.contribution_hint_usd) / total_hints
            if index == len(accounts):
                amount = max(0.0, target - running)
            else:
                amount = target * weight
                running += amount
            allocations[account.account_id] = max(0.0, amount)
        return allocations

    @staticmethod
    def _add_extra_savings(
        *,
        accounts: list[ProjectionAccount],
        contributions_by_account: dict[str, float],
        extra_savings_usd: float,
    ) -> None:
        amount = max(0.0, float(extra_savings_usd))
        if amount <= 0 or not accounts:
            return
        for account in accounts:
            if account.tax_treatment == "taxable":
                contributions_by_account[account.account_id] = contributions_by_account.get(account.account_id, 0.0) + amount
                return
        contributions_by_account[accounts[0].account_id] = contributions_by_account.get(accounts[0].account_id, 0.0) + amount

    @staticmethod
    def _apply_contributions(
        *,
        accounts: list[ProjectionAccount],
        contributions_by_account: dict[str, float],
    ) -> float:
        total = 0.0
        by_id: dict[str, ProjectionAccount] = {account.account_id: account for account in accounts}
        for account_id, amount in contributions_by_account.items():
            contribution = max(0.0, float(amount))
            account = by_id.get(account_id)
            if account is None or contribution <= 0:
                continue
            account.balance_usd += contribution
            total += contribution
        return total

    @staticmethod
    def _withdraw_from_accounts(
        *,
        accounts: list[ProjectionAccount],
        amount_usd: float,
    ) -> dict[str, Any]:
        requested = max(0.0, float(amount_usd))
        if requested <= 0:
            return {
                "total_withdrawn_usd": 0.0,
                "shortfall_usd": 0.0,
                "by_account": {},
                "by_tax_treatment": {
                    "taxable": 0.0,
                    "tax_deferred": 0.0,
                    "tax_free": 0.0,
                },
            }

        buckets: dict[str, list[ProjectionAccount]] = {
            "taxable": [],
            "tax_deferred": [],
            "tax_free": [],
        }
        for account in accounts:
            buckets[account.tax_treatment].append(account)

        ordered_accounts = [
            *buckets["taxable"],
            *buckets["tax_deferred"],
            *buckets["tax_free"],
        ]

        remaining = requested
        by_account: dict[str, float] = {}
        by_tax_treatment = {"taxable": 0.0, "tax_deferred": 0.0, "tax_free": 0.0}

        for account in ordered_accounts:
            if remaining <= 1e-9:
                break
            available = max(0.0, account.balance_usd)
            if available <= 0:
                continue
            withdrawn = min(available, remaining)
            account.balance_usd -= withdrawn
            remaining -= withdrawn
            by_account[account.account_id] = by_account.get(account.account_id, 0.0) + withdrawn
            by_tax_treatment[account.tax_treatment] += withdrawn

        return {
            "total_withdrawn_usd": requested - remaining,
            "shortfall_usd": max(0.0, remaining),
            "by_account": by_account,
            "by_tax_treatment": by_tax_treatment,
        }

    @staticmethod
    def _apply_growth(
        *,
        account: ProjectionAccount,
        expected_return: float,
        effective_tax_rate: float,
    ) -> float:
        rate = max(-0.95, float(expected_return))
        if rate > 0 and account.tax_treatment == "taxable":
            drag = min(max(float(effective_tax_rate), 0.0), 0.55)
            rate *= 1.0 - drag
        growth = account.balance_usd * rate
        account.balance_usd = max(0.0, account.balance_usd + growth)
        return growth

    def _scenario(
        self,
        *,
        label: str,
        current_value: float,
        assumptions: ScenarioAssumptions,
        projection_accounts: list[ProjectionAccount],
        income_projection: dict[str, Any] | None,
        expense_projection: dict[str, Any] | None,
        debt_projection: dict[str, Any] | None,
        timeline_projection: dict[str, Any] | None,
        filing_status: FilingStatus,
        start_year: int,
        start_age: int,
    ) -> ScenarioResult:
        accounts = self._copy_accounts(projection_accounts)
        timeline_points: list[ScenarioTimelinePoint] = []
        account_points: list[ScenarioAccountBalancePoint] = []

        total_taxes_paid = 0.0
        total_contributions = 0.0
        total_withdrawals = 0.0
        tax_rates: list[float] = []

        for offset in range(max(0, assumptions.years)):
            year = start_year + offset
            age = start_age + offset

            starting_by_account = {
                account.account_id: max(0.0, float(account.balance_usd))
                for account in accounts
            }
            starting_balance = sum(starting_by_account.values())

            annual_income = _income_for_year(income_projection, year=year)
            annual_expenses = _expenses_for_year(expense_projection, year=year)
            annual_debt = _debt_payments_for_year(
                debt_projection,
                year=year,
                start_year=start_year,
            )
            timeline_impact = _timeline_impacts_for_year(timeline_projection, year=year)

            annual_income += timeline_impact["income"]
            annual_expenses += timeline_impact["expense"]
            annual_debt += timeline_impact["debt_payment"]
            annual_income = max(0.0, annual_income)
            annual_expenses = max(0.0, annual_expenses)
            annual_debt = max(0.0, annual_debt)

            contributions_by_account = self._allocate_planned_contributions(
                accounts=accounts,
                annual_contribution_target_usd=assumptions.annual_contribution_usd,
            )
            planned_contributions = sum(contributions_by_account.values())
            pre_tax_contributions = sum(
                amount
                for account in accounts
                for account_id, amount in contributions_by_account.items()
                if account.account_id == account_id and account.tax_treatment == "tax_deferred"
            )

            initial_tax = estimate_federal_tax(
                tax_year=year,
                filing_status=filing_status,
                earned_income_usd=annual_income,
                ordinary_income_usd=0.0,
                short_term_capital_gains_usd=0.0,
                long_term_capital_gains_usd=0.0,
                qualified_dividends_usd=0.0,
                interest_income_usd=0.0,
                social_security_income_usd=0.0,
                pre_tax_contributions_usd=pre_tax_contributions,
                tax_withholding_usd=0.0,
            )
            taxes = max(0.0, _safe_float(initial_tax.get("total_estimated_tax_usd"), 0.0))

            net_cash_after_planned = annual_income - annual_expenses - annual_debt - taxes - planned_contributions
            discretionary_savings = max(0.0, net_cash_after_planned)
            required_withdrawals = max(0.0, -net_cash_after_planned)

            self._add_extra_savings(
                accounts=accounts,
                contributions_by_account=contributions_by_account,
                extra_savings_usd=discretionary_savings,
            )
            total_contribution_this_year = self._apply_contributions(
                accounts=accounts,
                contributions_by_account=contributions_by_account,
            )

            withdrawals_result = self._withdraw_from_accounts(
                accounts=accounts,
                amount_usd=required_withdrawals,
            )
            total_withdrawn = _safe_float(withdrawals_result.get("total_withdrawn_usd"), 0.0)
            by_account_withdrawals: dict[str, float] = dict(withdrawals_result.get("by_account") or {})
            by_treatment = withdrawals_result.get("by_tax_treatment") or {}
            tax_deferred_withdrawals = _safe_float(by_treatment.get("tax_deferred"), 0.0)

            if tax_deferred_withdrawals > 0:
                revised_tax_payload = estimate_federal_tax(
                    tax_year=year,
                    filing_status=filing_status,
                    earned_income_usd=annual_income,
                    ordinary_income_usd=tax_deferred_withdrawals,
                    short_term_capital_gains_usd=0.0,
                    long_term_capital_gains_usd=0.0,
                    qualified_dividends_usd=0.0,
                    interest_income_usd=0.0,
                    social_security_income_usd=0.0,
                    pre_tax_contributions_usd=pre_tax_contributions,
                    tax_withholding_usd=0.0,
                )
                revised_taxes = max(0.0, _safe_float(revised_tax_payload.get("total_estimated_tax_usd"), 0.0))
                additional_tax_due = max(0.0, revised_taxes - taxes)
                taxes = revised_taxes

                if additional_tax_due > 0:
                    extra_withdrawals = self._withdraw_from_accounts(
                        accounts=accounts,
                        amount_usd=additional_tax_due,
                    )
                    total_withdrawn += _safe_float(extra_withdrawals.get("total_withdrawn_usd"), 0.0)
                    extra_by_account = extra_withdrawals.get("by_account") or {}
                    for account_id, amount in extra_by_account.items():
                        by_account_withdrawals[account_id] = by_account_withdrawals.get(account_id, 0.0) + float(amount)
                    extra_by_treatment = extra_withdrawals.get("by_tax_treatment") or {}
                    tax_deferred_withdrawals += _safe_float(extra_by_treatment.get("tax_deferred"), 0.0)

                    final_tax_payload = estimate_federal_tax(
                        tax_year=year,
                        filing_status=filing_status,
                        earned_income_usd=annual_income,
                        ordinary_income_usd=tax_deferred_withdrawals,
                        short_term_capital_gains_usd=0.0,
                        long_term_capital_gains_usd=0.0,
                        qualified_dividends_usd=0.0,
                        interest_income_usd=0.0,
                        social_security_income_usd=0.0,
                        pre_tax_contributions_usd=pre_tax_contributions,
                        tax_withholding_usd=0.0,
                    )
                    taxes = max(0.0, _safe_float(final_tax_payload.get("total_estimated_tax_usd"), 0.0))

            effective_tax_rate = 0.0
            if annual_income > 0:
                effective_tax_rate = max(0.0, min(1.0, taxes / annual_income))
            else:
                effective_tax_rate = max(
                    0.0,
                    min(1.0, _safe_float(initial_tax.get("effective_tax_rate"), 0.0)),
                )

            total_growth = 0.0
            ending_by_account: dict[str, float] = {}
            for account in accounts:
                account_id = account.account_id
                contribution = _safe_float(contributions_by_account.get(account_id), 0.0)
                withdrawal = _safe_float(by_account_withdrawals.get(account_id), 0.0)
                growth = self._apply_growth(
                    account=account,
                    expected_return=assumptions.expected_return,
                    effective_tax_rate=effective_tax_rate,
                )
                total_growth += growth
                ending_by_account[account_id] = account.balance_usd
                account_points.append(
                    ScenarioAccountBalancePoint(
                        year=year,
                        account_id=account_id,
                        account_type=account.account_type,
                        tax_treatment=account.tax_treatment,
                        starting_balance_usd=round(_safe_float(starting_by_account.get(account_id)), 2),
                        contribution_usd=round(contribution, 2),
                        withdrawal_usd=round(withdrawal, 2),
                        growth_usd=round(growth, 2),
                        ending_balance_usd=round(account.balance_usd, 2),
                    )
                )

            ending_balance = sum(ending_by_account.values())
            ending_balance_real = self._real_value(
                nominal_future_value=ending_balance,
                years=offset + 1,
                inflation=assumptions.inflation,
            )

            timeline_points.append(
                ScenarioTimelinePoint(
                    year=year,
                    age=age,
                    starting_balance_usd=round(starting_balance, 2),
                    ending_balance_usd=round(ending_balance, 2),
                    contributions_usd=round(total_contribution_this_year, 2),
                    income_usd=round(annual_income, 2),
                    expenses_usd=round(annual_expenses + annual_debt, 2),
                    taxes_usd=round(taxes, 2),
                    growth_usd=round(total_growth, 2),
                    withdrawals_usd=round(total_withdrawn, 2),
                    ending_balance_real_usd=round(ending_balance_real, 2),
                )
            )

            total_taxes_paid += taxes
            total_contributions += total_contribution_this_year
            total_withdrawals += total_withdrawn
            tax_rates.append(effective_tax_rate)

        ending_nominal = sum(max(0.0, account.balance_usd) for account in accounts)
        average_tax_rate = (sum(tax_rates) / len(tax_rates)) if tax_rates else 0.0

        return ScenarioResult(
            label=label,  # type: ignore[arg-type]
            future_value_usd=round(ending_nominal, 2),
            real_value_usd=round(
                self._real_value(
                    ending_nominal,
                    assumptions.years,
                    assumptions.inflation,
                ),
                2,
            ),
            assumptions={
                "years": assumptions.years,
                "annual_contribution_usd": round(assumptions.annual_contribution_usd, 2),
                "expected_return": assumptions.expected_return,
                "inflation": assumptions.inflation,
                "account_count": len(accounts),
                "total_taxes_paid_usd": round(total_taxes_paid, 2),
                "total_contributions_usd": round(total_contributions, 2),
                "total_withdrawals_usd": round(total_withdrawals, 2),
                "average_effective_tax_rate": round(average_tax_rate, 6),
            },
            timeline_points=timeline_points,
            account_balance_points=account_points,
        )

    def _monte_carlo(
        self,
        *,
        current_value: float,
        annual_contribution: float,
        years: int,
        effective_tax_rate: float,
    ) -> dict[str, float | int]:
        outcomes: list[float] = []
        drag = min(max(float(effective_tax_rate), 0.0), 0.5)

        for _ in range(self.monte_carlo_runs):
            value = max(0.0, float(current_value))
            for _ in range(max(0, years)):
                yearly_return = random.gauss(self.baseline_return, self.return_volatility)
                yearly_return = max(-0.95, yearly_return)
                if yearly_return > 0:
                    yearly_return *= 1.0 - drag * 0.5
                value = max(0.0, (value * (1 + yearly_return)) + annual_contribution)
            outcomes.append(value)

        outcomes.sort()
        p10 = outcomes[max(0, math.floor(len(outcomes) * 0.10) - 1)] if outcomes else 0.0
        p50 = median(outcomes) if outcomes else 0.0
        p90 = outcomes[min(len(outcomes) - 1, math.ceil(len(outcomes) * 0.90) - 1)] if outcomes else 0.0

        return {
            "runs": self.monte_carlo_runs,
            "p10_future_value_usd": round(float(p10), 2),
            "p50_future_value_usd": round(float(p50), 2),
            "p90_future_value_usd": round(float(p90), 2),
        }

    def run(
        self,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float | None = None,
        years: int | None = None,
        hsa_extra_contribution_usd: float | None = None,
        *,
        accounts: list[dict[str, Any]] | None = None,
        income_projection: dict[str, Any] | None = None,
        expense_projection: dict[str, Any] | None = None,
        debt_projection: dict[str, Any] | None = None,
        timeline_projection: dict[str, Any] | None = None,
        contribution_allocation: dict[str, Any] | None = None,
        filing_status: str | None = None,
        start_year: int | None = None,
        start_age: int = 35,
    ) -> PlanningResponse:
        resolved_years = max(1, _safe_int(years, self.years_to_retirement))
        resolved_contribution = max(
            0.0,
            _safe_float(annual_contribution_usd, self.annual_contribution_usd),
        )
        resolved_hsa_delta = max(
            0.0,
            _safe_float(hsa_extra_contribution_usd, self.hsa_delta_default),
        )
        resolved_start_year = _safe_int(start_year, datetime.now().year)
        resolved_start_age = max(0, _safe_int(start_age, 35))
        resolved_filing_status = _normalize_filing_status(filing_status)

        base_accounts = self._build_projection_accounts(
            accounts=accounts,
            current_portfolio_value_usd=current_portfolio_value_usd,
            annual_contribution_usd=resolved_contribution,
            contribution_allocation=contribution_allocation,
        )

        baseline = self._scenario(
            label="baseline",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution,
                expected_return=self.baseline_return,
                inflation=self.inflation,
            ),
            projection_accounts=base_accounts,
            income_projection=income_projection,
            expense_projection=expense_projection,
            debt_projection=debt_projection,
            timeline_projection=timeline_projection,
            filing_status=resolved_filing_status,
            start_year=resolved_start_year,
            start_age=resolved_start_age,
        )
        optimistic = self._scenario(
            label="optimistic",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution,
                expected_return=self.optimistic_return,
                inflation=self.inflation,
            ),
            projection_accounts=base_accounts,
            income_projection=income_projection,
            expense_projection=expense_projection,
            debt_projection=debt_projection,
            timeline_projection=timeline_projection,
            filing_status=resolved_filing_status,
            start_year=resolved_start_year,
            start_age=resolved_start_age,
        )
        conservative = self._scenario(
            label="conservative",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution,
                expected_return=self.conservative_return,
                inflation=self.inflation,
            ),
            projection_accounts=base_accounts,
            income_projection=income_projection,
            expense_projection=expense_projection,
            debt_projection=debt_projection,
            timeline_projection=timeline_projection,
            filing_status=resolved_filing_status,
            start_year=resolved_start_year,
            start_age=resolved_start_age,
        )
        hsa_delta = self._scenario(
            label="hsa_delta",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution + resolved_hsa_delta,
                expected_return=self.baseline_return,
                inflation=self.inflation,
            ),
            projection_accounts=base_accounts,
            income_projection=income_projection,
            expense_projection=expense_projection,
            debt_projection=debt_projection,
            timeline_projection=timeline_projection,
            filing_status=resolved_filing_status,
            start_year=resolved_start_year,
            start_age=resolved_start_age,
        )

        monte_carlo = self._monte_carlo(
            current_value=current_portfolio_value_usd,
            annual_contribution=resolved_contribution,
            years=resolved_years,
            effective_tax_rate=_safe_float(
                baseline.assumptions.get("average_effective_tax_rate"),
                self.marginal_tax_rate,
            ),
        )

        return PlanningResponse(
            scenarios=[baseline, optimistic, conservative, hsa_delta],
            monte_carlo=monte_carlo,
        )
