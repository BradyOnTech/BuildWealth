"""Tax-aware planning scenario engine.

Projection structure and account/phase processing patterns are adapted from
BuildWealth simulation workflows:
- src/lib/calc/simulation-engine.ts
- src/lib/calc/returns-providers/stochastic-returns-provider.ts
- src/lib/calc/returns-providers/lcg-historical-backtest-returns-provider.ts
- src/lib/calc/historical-data/nyu-returns.ts
- src/lib/calc/portfolio.ts
- src/lib/calc/account.ts
- src/lib/calc/phase.ts
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime
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
from buildwealth_orchestrator.services.value_coercion import (
    clamp as _clamp,
    parse_optional_date as _parse_optional_date,
    safe_float as _safe_float,
    safe_int as _safe_int,
)
from buildwealth_orchestrator.services.rmd_projection import (
    determine_rmd_start_age,
    estimate_year_rmd_for_accounts,
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

WithdrawalStrategy = Literal[
    "cashflow_only",
    "four_percent_rule",
    "dynamic_guardrails",
    "bond_tent",
    "bucket_strategy",
]

STRATEGY_ALIASES: dict[str, WithdrawalStrategy] = {
    "": "cashflow_only",
    "cashflow_only": "cashflow_only",
    "none": "cashflow_only",
    "default": "cashflow_only",
    "4_percent_rule": "four_percent_rule",
    "4percent_rule": "four_percent_rule",
    "four_percent_rule": "four_percent_rule",
    "4_percent": "four_percent_rule",
    "dynamic_withdrawal": "dynamic_guardrails",
    "dynamic_guardrails": "dynamic_guardrails",
    "guyton_klinger": "dynamic_guardrails",
    "guyton_klinger_guardrails": "dynamic_guardrails",
    "bond_tent": "bond_tent",
    "bucket_strategy": "bucket_strategy",
    "bucket": "bucket_strategy",
}

DrawdownBucket = Literal["cash", "taxable", "tax_deferred", "tax_free"]
DRAWDOWN_BUCKETS: tuple[DrawdownBucket, ...] = ("cash", "taxable", "tax_deferred", "tax_free")

DRAWDOWN_ALIASES: dict[str, DrawdownBucket] = {
    "cash": "cash",
    "cash_first": "cash",
    "cash_reserve": "cash",
    "savings": "cash",
    "taxable": "taxable",
    "brokerage": "taxable",
    "tax_deferred": "tax_deferred",
    "taxdeferred": "tax_deferred",
    "deferred": "tax_deferred",
    "traditional": "tax_deferred",
    "tax_free": "tax_free",
    "taxfree": "tax_free",
    "roth": "tax_free",
}

DRAWDOWN_PRESETS: dict[str, tuple[DrawdownBucket, ...] | None] = {
    "age_aware": None,
    "taxable_first": ("cash", "taxable", "tax_deferred", "tax_free"),
    "tax_efficient": ("cash", "taxable", "tax_deferred", "tax_free"),
    "tax_deferred_first": ("cash", "tax_deferred", "taxable", "tax_free"),
    "tax_free_first": ("cash", "tax_free", "taxable", "tax_deferred"),
}

SimulationMode = Literal["fixed", "stochastic", "historical", "monte_carlo"]
SIMULATION_MODE_ALIASES: dict[str, SimulationMode] = {
    "": "fixed",
    "fixed": "fixed",
    "fixed_returns": "fixed",
    "fixedreturns": "fixed",
    "stochastic": "stochastic",
    "stochastic_returns": "stochastic",
    "stochasticreturns": "stochastic",
    "historical": "historical",
    "historical_backtest": "historical",
    "historicalbacktest": "historical",
    "lcg_historical_backtest": "historical",
    "lcghistoricalbacktest": "historical",
    "monte_carlo": "monte_carlo",
    "montecarlo": "monte_carlo",
    "monte_carlo_p10": "monte_carlo",
    "monte_carlo_p50": "monte_carlo",
    "monte_carlo_p90": "monte_carlo",
}

MonteCarloVariant = Literal["p10", "p50", "p90"]
MONTE_CARLO_VARIANT_ALIASES: dict[str, MonteCarloVariant] = {
    "": "p50",
    "p50": "p50",
    "median": "p50",
    "p10": "p10",
    "p90": "p90",
}

DEFAULT_SIMULATION_SEED = 9521

# Historical market dataset used by BuildWealth simulation paths:
# src/lib/calc/historical-data/nyu-returns.ts
HISTORICAL_STOCK_RETURNS: tuple[tuple[int, float, float], ...] = (
    (1928, 0.4549, -0.0116),
    (1929, -0.0883, 0.0058),
    (1930, -0.2001, -0.064),
    (1931, -0.3807, -0.0932),
    (1932, 0.0182, -0.1027),
    (1933, 0.4885, 0.0076),
    (1934, -0.0266, 0.0152),
    (1935, 0.4249, 0.0299),
    (1936, 0.3006, 0.0145),
    (1937, -0.3713, 0.0286),
    (1938, 0.3298, -0.0278),
    (1939, -0.011, 0.0),
    (1940, -0.1131, 0.0071),
    (1941, -0.2065, 0.0993),
    (1942, 0.093, 0.0903),
    (1943, 0.2147, 0.0296),
    (1944, 0.1636, 0.023),
    (1945, 0.3284, 0.0225),
    (1946, -0.2248, 0.1813),
    (1947, -0.0334, 0.0884),
    (1948, 0.0263, 0.0299),
    (1949, 0.2081, -0.0207),
    (1950, 0.2348, 0.0593),
    (1951, 0.1668, 0.06),
    (1952, 0.1727, 0.0075),
    (1953, -0.0194, 0.0075),
    (1954, 0.5371, -0.0074),
    (1955, 0.321, 0.0037),
    (1956, 0.0433, 0.0299),
    (1957, -0.1298, 0.029),
    (1958, 0.4123, 0.0176),
    (1959, 0.1015, 0.0173),
    (1960, -0.0101, 0.0136),
    (1961, 0.2579, 0.0067),
    (1962, -0.1001, 0.0133),
    (1963, 0.2063, 0.0164),
    (1964, 0.153, 0.0097),
    (1965, 0.1028, 0.0192),
    (1966, -0.1298, 0.0346),
    (1967, 0.2015, 0.0304),
    (1968, 0.0582, 0.0472),
    (1969, -0.136, 0.062),
    (1970, -0.019, 0.0557),
    (1971, 0.1061, 0.0327),
    (1972, 0.1484, 0.0341),
    (1973, -0.2117, 0.0871),
    (1974, -0.3404, 0.1234),
    (1975, 0.2811, 0.0694),
    (1976, 0.1809, 0.0486),
    (1977, -0.1282, 0.067),
    (1978, -0.023, 0.0902),
    (1979, 0.0461, 0.1329),
    (1980, 0.1708, 0.1252),
    (1981, -0.1251, 0.0892),
    (1982, 0.1598, 0.0383),
    (1983, 0.1787, 0.0379),
    (1984, 0.0211, 0.0395),
    (1985, 0.2643, 0.038),
    (1986, 0.1721, 0.011),
    (1987, 0.0132, 0.0443),
    (1988, 0.116, 0.0442),
    (1989, 0.2564, 0.0465),
    (1990, -0.0864, 0.0611),
    (1991, 0.2636, 0.0306),
    (1992, 0.0446, 0.029),
    (1993, 0.0703, 0.0275),
    (1994, -0.0131, 0.0267),
    (1995, 0.338, 0.0254),
    (1996, 0.1874, 0.0332),
    (1997, 0.3088, 0.017),
    (1998, 0.263, 0.0161),
    (1999, 0.1772, 0.0268),
    (2000, -0.1201, 0.0339),
    (2001, -0.132, 0.0155),
    (2002, -0.2378, 0.0238),
    (2003, 0.2599, 0.0188),
    (2004, 0.0725, 0.0326),
    (2005, 0.0137, 0.0342),
    (2006, 0.1275, 0.0254),
    (2007, 0.0135, 0.0408),
    (2008, -0.3661, 0.0009),
    (2009, 0.226, 0.0272),
    (2010, 0.1313, 0.015),
    (2011, -0.0084, 0.0296),
    (2012, 0.1391, 0.0174),
    (2013, 0.3019, 0.015),
    (2014, 0.1267, 0.0076),
    (2015, 0.0064, 0.0073),
    (2016, 0.095, 0.0207),
    (2017, 0.1909, 0.0211),
    (2018, -0.0602, 0.0191),
    (2019, 0.2828, 0.0229),
    (2020, 0.1644, 0.0136),
    (2021, 0.2002, 0.0704),
    (2022, -0.2301, 0.0645),
    (2023, 0.2197, 0.0335),
    (2024, 0.2154, 0.0275),
)

HISTORICAL_YEARS: tuple[int, ...] = tuple(row[0] for row in HISTORICAL_STOCK_RETURNS)
HISTORICAL_YEAR_TO_INDEX: dict[int, int] = {year: index for index, year in enumerate(HISTORICAL_YEARS)}
HISTORICAL_RETURN_VALUES: tuple[float, ...] = tuple(row[1] for row in HISTORICAL_STOCK_RETURNS)
HISTORICAL_INFLATION_VALUES: tuple[float, ...] = tuple(row[2] for row in HISTORICAL_STOCK_RETURNS)


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


@dataclass
class WithdrawalStrategyState:
    previous_withdrawal_target_usd: float | None = None
    previous_growth_rate: float | None = None
    retirement_years_elapsed: int = 0


def _normalize_filing_status(value: Any) -> FilingStatus:
    text = str(value or "").strip().lower()
    if text in VALID_FILING_STATUSES:
        return text  # type: ignore[return-value]
    return "single"


def _normalize_withdrawal_strategy(value: Any) -> WithdrawalStrategy:
    text = str(value or "").strip().lower()
    return STRATEGY_ALIASES.get(text, "cashflow_only")


def _normalize_retirement_age(value: Any) -> int:
    age = _safe_int(value, 65)
    return int(_clamp(float(age), 35, 100))


def _normalize_drawdown_order(value: Any) -> tuple[DrawdownBucket, ...] | None:
    if value is None:
        return None

    raw_items: list[str]
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text in DRAWDOWN_PRESETS:
            return DRAWDOWN_PRESETS[text]
        raw_items = [item.strip().lower() for item in text.split(",") if item.strip()]
    elif isinstance(value, list):
        raw_items = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        return None

    resolved: list[DrawdownBucket] = []
    for item in raw_items:
        canonical = DRAWDOWN_ALIASES.get(item)
        if canonical is None or canonical in resolved:
            continue
        resolved.append(canonical)

    if not resolved:
        return None

    for bucket in DRAWDOWN_BUCKETS:
        if bucket not in resolved:
            resolved.append(bucket)
    return tuple(resolved)


def _normalize_optional_age(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return int(_clamp(float(parsed), 0, 120))


def _normalize_simulation_mode(value: Any) -> SimulationMode:
    text = str(value or "").strip().lower()
    return SIMULATION_MODE_ALIASES.get(text, "fixed")


def _normalize_monte_carlo_variant(value: Any) -> MonteCarloVariant:
    text = str(value or "").strip().lower()
    return MONTE_CARLO_VARIANT_ALIASES.get(text, "p50")


def _normalize_simulation_seed(value: Any) -> int:
    seed = _safe_int(value, DEFAULT_SIMULATION_SEED)
    return max(0, min(seed, 2_147_483_647))


def _normalize_historical_start_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    year = _safe_int(value, 0)
    if year in HISTORICAL_YEAR_TO_INDEX:
        return year
    return None


def _resolve_roth_conversion_window(
    *,
    start_age: int | None,
    end_age: int | None,
) -> tuple[int | None, int | None]:
    resolved_start = _normalize_optional_age(start_age)
    resolved_end = _normalize_optional_age(end_age)
    if resolved_start is not None and resolved_end is not None and resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start
    return resolved_start, resolved_end


def _is_roth_account_type(account_type: str) -> bool:
    return account_type in {"roth401k", "roth403b", "rothIra"}


def _is_cash_account_type(account_type: str) -> bool:
    return account_type in {"savings"}


def _drawdown_bucket_for_account(account: ProjectionAccount) -> DrawdownBucket:
    if _is_cash_account_type(account.account_type):
        return "cash"
    if account.tax_treatment == "taxable":
        return "taxable"
    if account.tax_treatment == "tax_deferred":
        return "tax_deferred"
    return "tax_free"


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


def _social_security_income_for_year(
    social_security_projection: dict[str, Any] | None,
    *,
    year: int,
) -> float:
    point = _projection_point_for_year(social_security_projection, year=year)
    if point is not None:
        return max(0.0, _safe_float(point.get("annual_benefit_usd"), 0.0))
    if not isinstance(social_security_projection, dict):
        return 0.0
    return max(0.0, _safe_float(social_security_projection.get("selected_annual_benefit_usd"), 0.0))


def _resolve_rmd_start_age(rmd_projection: dict[str, Any] | None) -> int:
    if not isinstance(rmd_projection, dict):
        return determine_rmd_start_age(birth_year=None)

    birth_year_raw = rmd_projection.get("birth_year")
    birth_year = None
    if birth_year_raw is not None:
        birth_year = max(1900, min(_safe_int(birth_year_raw, 0), 2500))

    override_raw = rmd_projection.get("rmd_start_age")
    override_start_age = None
    if override_raw is not None:
        override_start_age = max(72, min(_safe_int(override_raw, 73), 120))

    return determine_rmd_start_age(
        birth_year=birth_year,
        override_start_age=override_start_age,
    )


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

    def _resolve_historical_start_index(
        self,
        *,
        simulation_seed: int,
        requested_start_year: int | None,
    ) -> tuple[int, int]:
        if requested_start_year is not None and requested_start_year in HISTORICAL_YEAR_TO_INDEX:
            index = HISTORICAL_YEAR_TO_INDEX[requested_start_year]
            return index, requested_start_year
        rng = random.Random(simulation_seed)
        index = rng.randrange(len(HISTORICAL_RETURN_VALUES))
        return index, HISTORICAL_YEARS[index]

    def _historical_average_inflation(
        self,
        *,
        start_index: int,
        years: int,
    ) -> float:
        bounded_years = max(1, years)
        values: list[float] = []
        for offset in range(bounded_years):
            index = (start_index + offset) % len(HISTORICAL_INFLATION_VALUES)
            values.append(float(HISTORICAL_INFLATION_VALUES[index]))
        return sum(values) / len(values)

    def _build_annual_return_series(
        self,
        *,
        mode: SimulationMode,
        years: int,
        expected_return: float,
        simulation_seed: int,
        historical_start_year: int | None,
    ) -> tuple[list[float], dict[str, float | int]]:
        bounded_years = max(1, years)
        metadata: dict[str, float | int] = {}
        if mode == "fixed":
            return [float(expected_return)] * bounded_years, metadata

        if mode == "stochastic":
            rng = random.Random(simulation_seed)
            series: list[float] = []
            for _ in range(bounded_years):
                draw = rng.gauss(float(expected_return), float(self.return_volatility))
                series.append(max(-0.95, float(draw)))
            return series, metadata

        start_index, resolved_start_year = self._resolve_historical_start_index(
            simulation_seed=simulation_seed,
            requested_start_year=historical_start_year,
        )
        baseline_delta = float(expected_return) - float(self.baseline_return)
        series = []
        for offset in range(bounded_years):
            index = (start_index + offset) % len(HISTORICAL_RETURN_VALUES)
            adjusted = float(HISTORICAL_RETURN_VALUES[index]) + baseline_delta
            series.append(max(-0.95, min(1.5, adjusted)))
        metadata["historical_start_year"] = int(resolved_start_year)
        metadata["historical_average_inflation"] = self._historical_average_inflation(
            start_index=start_index,
            years=bounded_years,
        )
        return series, metadata

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
    def _account_withdrawal_priority(
        account: ProjectionAccount,
        *,
        age: float,
        strategy: WithdrawalStrategy,
        drawdown_order: tuple[DrawdownBucket, ...] | None,
    ) -> tuple[int, str]:
        if drawdown_order:
            order_index = {bucket: index for index, bucket in enumerate(drawdown_order, start=1)}
            bucket = _drawdown_bucket_for_account(account)
            return (order_index.get(bucket, len(drawdown_order) + 1), account.account_id)

        account_type = account.account_type

        # Bucket strategy approximation:
        # cash bucket -> bond-like/tax-deferred bucket -> equity-like/taxable -> tax-free.
        if strategy == "bucket_strategy":
            if _is_cash_account_type(account_type):
                return (1, account.account_id)
            if account.tax_treatment == "tax_deferred":
                return (2, account.account_id)
            if account.tax_treatment == "taxable":
                return (3, account.account_id)
            return (4, account.account_id)

        # simulation age-aware withdrawal ordering.
        if age < 59.5:
            if _is_cash_account_type(account_type):
                return (1, account.account_id)
            if account_type == "taxableBrokerage":
                return (2, account.account_id)
            if _is_roth_account_type(account_type):
                return (3, account.account_id)
            if account_type in {"401k", "403b", "ira"}:
                return (4, account.account_id)
            if account_type == "hsa":
                return (5, account.account_id)
        else:
            if _is_cash_account_type(account_type):
                return (1, account.account_id)
            if account_type in {"401k", "403b", "ira"}:
                return (2, account.account_id)
            if account_type == "taxableBrokerage":
                return (3, account.account_id)
            if _is_roth_account_type(account_type):
                return (4, account.account_id)
            if account_type == "hsa":
                return (5, account.account_id)

        # Fallback to tax-treatment ordering if the account type is unknown.
        if account.tax_treatment == "taxable":
            return (10, account.account_id)
        if account.tax_treatment == "tax_deferred":
            return (11, account.account_id)
        return (12, account.account_id)

    @staticmethod
    def _strategy_withdrawal_target(
        *,
        strategy: WithdrawalStrategy,
        state: WithdrawalStrategyState,
        age: int,
        retirement_age: int,
        starting_balance: float,
        base_required_withdrawals: float,
        inflation: float,
    ) -> float:
        if age < retirement_age:
            return 0.0
        if base_required_withdrawals <= 0:
            return 0.0

        safe_starting_balance = max(0.0, starting_balance)
        if safe_starting_balance <= 0:
            return 0.0

        if strategy == "cashflow_only":
            return 0.0

        inflation_factor = 1.0 + max(-1.0, inflation)

        if strategy == "four_percent_rule":
            if state.previous_withdrawal_target_usd is None:
                target = safe_starting_balance * 0.04
            else:
                target = state.previous_withdrawal_target_usd * inflation_factor
            return max(0.0, target)

        if strategy == "dynamic_guardrails":
            if state.previous_withdrawal_target_usd is None:
                target = safe_starting_balance * 0.04
            else:
                prior_growth = state.previous_growth_rate
                # Guyton-Klinger-inspired inflation adjustment:
                # skip inflation step-up after down years.
                if prior_growth is not None and prior_growth < 0:
                    target = state.previous_withdrawal_target_usd
                else:
                    target = state.previous_withdrawal_target_usd * inflation_factor

            current_rate = target / safe_starting_balance if safe_starting_balance > 0 else 0.0
            lower_guardrail = 0.032  # 4% * 0.8
            upper_guardrail = 0.048  # 4% * 1.2
            if current_rate > upper_guardrail:
                target *= 0.90
            elif current_rate < lower_guardrail:
                target *= 1.10
            return max(0.0, target)

        if strategy == "bond_tent":
            # Glide from a conservative early-retirement withdrawal rate
            # toward a higher long-run rate as the tent unwinds.
            start_rate = 0.0325
            end_rate = 0.045
            tent_years = 15
            progress = min(1.0, max(0.0, state.retirement_years_elapsed / max(1, tent_years - 1)))
            rate = start_rate + ((end_rate - start_rate) * progress)
            return max(0.0, safe_starting_balance * rate)

        if strategy == "bucket_strategy":
            if state.previous_withdrawal_target_usd is None:
                target = max(base_required_withdrawals, safe_starting_balance * 0.035)
            else:
                target = state.previous_withdrawal_target_usd * inflation_factor
            return max(0.0, target)

        return 0.0

    @staticmethod
    def _resolve_roth_conversion_target(
        *,
        annual_amount_usd: float,
        age: int,
        start_age: int | None,
        end_age: int | None,
    ) -> float:
        if annual_amount_usd <= 0:
            return 0.0
        if start_age is not None and age < start_age:
            return 0.0
        if end_age is not None and age > end_age:
            return 0.0
        return max(0.0, annual_amount_usd)

    @staticmethod
    def _ensure_roth_destination_account(
        *,
        accounts: list[ProjectionAccount],
    ) -> ProjectionAccount:
        roth_accounts = [
            account for account in accounts
            if account.tax_treatment == "tax_free" and _is_roth_account_type(account.account_type)
        ]
        if roth_accounts:
            return sorted(roth_accounts, key=lambda account: account.account_id)[0]

        generic_tax_free_accounts = [
            account for account in accounts if account.tax_treatment == "tax_free"
        ]
        if generic_tax_free_accounts:
            return sorted(generic_tax_free_accounts, key=lambda account: account.account_id)[0]

        synthetic = ProjectionAccount(
            account_id="synthetic-roth-conversion",
            account_type="rothIra",
            tax_treatment="tax_free",
            balance_usd=0.0,
            contribution_hint_usd=0.0,
        )
        accounts.append(synthetic)
        return synthetic

    @staticmethod
    def _apply_roth_conversion(
        *,
        accounts: list[ProjectionAccount],
        amount_usd: float,
    ) -> dict[str, Any]:
        requested = max(0.0, float(amount_usd))
        if requested <= 0:
            return {
                "requested_usd": 0.0,
                "converted_usd": 0.0,
                "shortfall_usd": 0.0,
                "by_source_account": {},
                "by_target_account": {},
            }

        source_accounts = sorted(
            [
                account for account in accounts
                if account.tax_treatment == "tax_deferred" and account.balance_usd > 0
            ],
            key=lambda account: account.account_id,
        )
        if not source_accounts:
            return {
                "requested_usd": requested,
                "converted_usd": 0.0,
                "shortfall_usd": requested,
                "by_source_account": {},
                "by_target_account": {},
            }

        remaining = requested
        by_source_account: dict[str, float] = {}
        for account in source_accounts:
            if remaining <= 1e-9:
                break
            available = max(0.0, float(account.balance_usd))
            if available <= 0:
                continue
            converted = min(available, remaining)
            account.balance_usd = max(0.0, account.balance_usd - converted)
            remaining -= converted
            by_source_account[account.account_id] = (
                by_source_account.get(account.account_id, 0.0) + converted
            )

        total_converted = max(0.0, requested - remaining)
        by_target_account: dict[str, float] = {}
        if total_converted > 0:
            target_account = ScenarioEngine._ensure_roth_destination_account(accounts=accounts)
            target_account.balance_usd += total_converted
            by_target_account[target_account.account_id] = total_converted

        return {
            "requested_usd": requested,
            "converted_usd": total_converted,
            "shortfall_usd": max(0.0, remaining),
            "by_source_account": by_source_account,
            "by_target_account": by_target_account,
        }

    @staticmethod
    def _withdraw_from_accounts(
        *,
        accounts: list[ProjectionAccount],
        amount_usd: float,
        age: float,
        strategy: WithdrawalStrategy,
        drawdown_order: tuple[DrawdownBucket, ...] | None,
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

        ordered_accounts = sorted(
            accounts,
            key=lambda account: ScenarioEngine._account_withdrawal_priority(
                account,
                age=age,
                strategy=strategy,
                drawdown_order=drawdown_order,
            ),
        )

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
    def _withdraw_from_account_targets(
        *,
        accounts: list[ProjectionAccount],
        target_withdrawals: dict[str, float],
    ) -> dict[str, Any]:
        if not target_withdrawals:
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

        by_id = {account.account_id: account for account in accounts}
        by_account: dict[str, float] = {}
        by_tax_treatment = {"taxable": 0.0, "tax_deferred": 0.0, "tax_free": 0.0}
        total_withdrawn = 0.0
        shortfall = 0.0

        for account_id, requested in target_withdrawals.items():
            amount = max(0.0, _safe_float(requested, 0.0))
            if amount <= 0:
                continue
            account = by_id.get(account_id)
            if account is None:
                shortfall += amount
                continue
            available = max(0.0, account.balance_usd)
            withdrawn = min(available, amount)
            account.balance_usd = max(0.0, account.balance_usd - withdrawn)
            total_withdrawn += withdrawn
            by_account[account_id] = by_account.get(account_id, 0.0) + withdrawn
            by_tax_treatment[account.tax_treatment] += withdrawn
            if withdrawn < amount:
                shortfall += amount - withdrawn

        return {
            "total_withdrawn_usd": total_withdrawn,
            "shortfall_usd": max(0.0, shortfall),
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
        social_security_projection: dict[str, Any] | None,
        rmd_projection: dict[str, Any] | None,
        filing_status: FilingStatus,
        state_tax_rate: float,
        include_irmaa: bool,
        roth_conversion_annual_amount_usd: float,
        roth_conversion_start_age: int | None,
        roth_conversion_end_age: int | None,
        drawdown_order: tuple[DrawdownBucket, ...] | None,
        start_year: int,
        start_age: int,
        withdrawal_strategy: WithdrawalStrategy,
        retirement_age: int,
        annual_return_series: list[float] | None = None,
        simulation_metadata: dict[str, float | int | str | bool | None] | None = None,
        assumption_set_id: str | None = None,
        assumption_set_name: str | None = None,
    ) -> ScenarioResult:
        accounts = self._copy_accounts(projection_accounts)
        timeline_points: list[ScenarioTimelinePoint] = []
        account_points: list[ScenarioAccountBalancePoint] = []
        withdrawal_state = WithdrawalStrategyState()

        total_taxes_paid = 0.0
        total_federal_taxes_paid = 0.0
        total_state_taxes_paid = 0.0
        total_irmaa_surcharges_paid = 0.0
        total_contributions = 0.0
        total_withdrawals = 0.0
        total_rmds = 0.0
        total_social_security_income = 0.0
        total_roth_conversions = 0.0
        tax_rates: list[float] = []
        rmd_start_age = _resolve_rmd_start_age(rmd_projection)

        for offset in range(max(0, assumptions.years)):
            year = start_year + offset
            age = start_age + offset

            starting_by_account = {
                account.account_id: max(0.0, float(account.balance_usd))
                for account in accounts
            }
            starting_balance = sum(starting_by_account.values())

            annual_income = _income_for_year(income_projection, year=year)
            annual_social_security_income = _social_security_income_for_year(
                social_security_projection,
                year=year,
            )
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
                social_security_income_usd=annual_social_security_income,
                pre_tax_contributions_usd=pre_tax_contributions,
                state_tax_rate=state_tax_rate,
                age=age,
                include_irmaa=include_irmaa,
                tax_withholding_usd=0.0,
            )
            active_tax_payload = initial_tax
            taxes = max(0.0, _safe_float(initial_tax.get("total_estimated_tax_usd"), 0.0))

            net_cash_after_planned = (
                annual_income
                + annual_social_security_income
                - annual_expenses
                - annual_debt
                - taxes
                - planned_contributions
            )
            discretionary_savings = max(0.0, net_cash_after_planned)
            base_required_withdrawals = max(0.0, -net_cash_after_planned)
            year_rmd = estimate_year_rmd_for_accounts(
                accounts=[
                    {
                        "account_id": account.account_id,
                        "account_type": account.account_type,
                        "balance_usd": _safe_float(starting_by_account.get(account.account_id), 0.0),
                    }
                    for account in accounts
                ],
                age=float(age),
                rmd_start_age=rmd_start_age,
            )
            rmd_by_account = {
                str(row.get("account_id")): max(0.0, _safe_float(row.get("rmd_usd"), 0.0))
                for row in year_rmd.get("account_rmds", [])
                if isinstance(row, dict) and str(row.get("account_id") or "").strip()
            }

            strategy_withdrawal_target = self._strategy_withdrawal_target(
                strategy=withdrawal_strategy,
                state=withdrawal_state,
                age=age,
                retirement_age=retirement_age,
                starting_balance=starting_balance,
                base_required_withdrawals=base_required_withdrawals,
                inflation=assumptions.inflation,
            )
            required_withdrawals = max(base_required_withdrawals, strategy_withdrawal_target)
            strategy_extra_spending = max(0.0, required_withdrawals - base_required_withdrawals)
            if strategy_extra_spending > 0:
                annual_expenses += strategy_extra_spending
                discretionary_savings = max(0.0, discretionary_savings - strategy_extra_spending)

            self._add_extra_savings(
                accounts=accounts,
                contributions_by_account=contributions_by_account,
                extra_savings_usd=discretionary_savings,
            )
            total_contribution_this_year = self._apply_contributions(
                accounts=accounts,
                contributions_by_account=contributions_by_account,
            )
            roth_conversion_target = self._resolve_roth_conversion_target(
                annual_amount_usd=roth_conversion_annual_amount_usd,
                age=age,
                start_age=roth_conversion_start_age,
                end_age=roth_conversion_end_age,
            )
            roth_conversion_result = self._apply_roth_conversion(
                accounts=accounts,
                amount_usd=roth_conversion_target,
            )
            roth_conversions_this_year = _safe_float(roth_conversion_result.get("converted_usd"), 0.0)
            by_account_roth_conversion_out = {
                str(account_id): _safe_float(amount, 0.0)
                for account_id, amount in (roth_conversion_result.get("by_source_account") or {}).items()
            }
            by_account_roth_conversion_in = {
                str(account_id): _safe_float(amount, 0.0)
                for account_id, amount in (roth_conversion_result.get("by_target_account") or {}).items()
            }

            rmd_withdrawals_result = self._withdraw_from_account_targets(
                accounts=accounts,
                target_withdrawals=rmd_by_account,
            )
            mandatory_rmd_withdrawn = _safe_float(rmd_withdrawals_result.get("total_withdrawn_usd"), 0.0)
            total_rmds += mandatory_rmd_withdrawn

            withdrawals_result = self._withdraw_from_accounts(
                accounts=accounts,
                amount_usd=max(0.0, required_withdrawals - mandatory_rmd_withdrawn),
                age=float(age),
                strategy=withdrawal_strategy,
                drawdown_order=drawdown_order,
            )
            total_withdrawn = mandatory_rmd_withdrawn + _safe_float(withdrawals_result.get("total_withdrawn_usd"), 0.0)
            by_account_withdrawals: dict[str, float] = dict(rmd_withdrawals_result.get("by_account") or {})
            for account_id, amount in (withdrawals_result.get("by_account") or {}).items():
                by_account_withdrawals[account_id] = by_account_withdrawals.get(account_id, 0.0) + float(amount)

            by_treatment = rmd_withdrawals_result.get("by_tax_treatment") or {}
            next_by_treatment = withdrawals_result.get("by_tax_treatment") or {}
            for key in ("taxable", "tax_deferred", "tax_free"):
                by_treatment[key] = _safe_float(by_treatment.get(key), 0.0) + _safe_float(next_by_treatment.get(key), 0.0)
            tax_deferred_withdrawals = _safe_float(by_treatment.get("tax_deferred"), 0.0)
            taxable_ordinary_income = tax_deferred_withdrawals + roth_conversions_this_year
            if taxable_ordinary_income > 0:
                revised_tax_payload = estimate_federal_tax(
                    tax_year=year,
                    filing_status=filing_status,
                    earned_income_usd=annual_income,
                    ordinary_income_usd=taxable_ordinary_income,
                    short_term_capital_gains_usd=0.0,
                    long_term_capital_gains_usd=0.0,
                    qualified_dividends_usd=0.0,
                    interest_income_usd=0.0,
                    social_security_income_usd=annual_social_security_income,
                    pre_tax_contributions_usd=pre_tax_contributions,
                    state_tax_rate=state_tax_rate,
                    age=age,
                    include_irmaa=include_irmaa,
                    tax_withholding_usd=0.0,
                )
                active_tax_payload = revised_tax_payload
                revised_taxes = max(0.0, _safe_float(revised_tax_payload.get("total_estimated_tax_usd"), 0.0))
                additional_tax_due = max(0.0, revised_taxes - taxes)
                taxes = revised_taxes

                if additional_tax_due > 0:
                    extra_withdrawals = self._withdraw_from_accounts(
                        accounts=accounts,
                        amount_usd=additional_tax_due,
                        age=float(age),
                        strategy=withdrawal_strategy,
                        drawdown_order=drawdown_order,
                    )
                    total_withdrawn += _safe_float(extra_withdrawals.get("total_withdrawn_usd"), 0.0)
                    extra_by_account = extra_withdrawals.get("by_account") or {}
                    for account_id, amount in extra_by_account.items():
                        by_account_withdrawals[account_id] = by_account_withdrawals.get(account_id, 0.0) + float(amount)
                    extra_by_treatment = extra_withdrawals.get("by_tax_treatment") or {}
                    tax_deferred_withdrawals += _safe_float(extra_by_treatment.get("tax_deferred"), 0.0)
                    taxable_ordinary_income = tax_deferred_withdrawals + roth_conversions_this_year

                    final_tax_payload = estimate_federal_tax(
                        tax_year=year,
                        filing_status=filing_status,
                        earned_income_usd=annual_income,
                        ordinary_income_usd=taxable_ordinary_income,
                        short_term_capital_gains_usd=0.0,
                        long_term_capital_gains_usd=0.0,
                        qualified_dividends_usd=0.0,
                        interest_income_usd=0.0,
                        social_security_income_usd=annual_social_security_income,
                        pre_tax_contributions_usd=pre_tax_contributions,
                        state_tax_rate=state_tax_rate,
                        age=age,
                        include_irmaa=include_irmaa,
                        tax_withholding_usd=0.0,
                    )
                    active_tax_payload = final_tax_payload
                    taxes = max(0.0, _safe_float(final_tax_payload.get("total_estimated_tax_usd"), 0.0))

            effective_tax_rate = max(
                0.0,
                min(1.0, _safe_float(active_tax_payload.get("effective_tax_rate"), 0.0)),
            )
            federal_taxes = (
                _safe_float(active_tax_payload.get("federal_income_tax_usd"), 0.0)
                + _safe_float(active_tax_payload.get("capital_gains_tax_usd"), 0.0)
                + _safe_float(active_tax_payload.get("niit_tax_usd"), 0.0)
                + _safe_float(active_tax_payload.get("total_fica_tax_usd"), 0.0)
            )
            state_taxes = _safe_float(active_tax_payload.get("state_income_tax_usd"), 0.0)
            irmaa_surcharges = _safe_float(active_tax_payload.get("irmaa_annual_surcharge_usd"), 0.0)

            total_growth = 0.0
            ending_by_account: dict[str, float] = {}
            expected_return_for_year = (
                float(annual_return_series[offset])
                if isinstance(annual_return_series, list) and offset < len(annual_return_series)
                else float(assumptions.expected_return)
            )
            for account in accounts:
                account_id = account.account_id
                contribution = _safe_float(contributions_by_account.get(account_id), 0.0)
                withdrawal = _safe_float(by_account_withdrawals.get(account_id), 0.0)
                rmd_withdrawal = _safe_float(rmd_by_account.get(account_id), 0.0)
                roth_conversion_out = _safe_float(by_account_roth_conversion_out.get(account_id), 0.0)
                roth_conversion_in = _safe_float(by_account_roth_conversion_in.get(account_id), 0.0)
                growth = self._apply_growth(
                    account=account,
                    expected_return=expected_return_for_year,
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
                        rmd_withdrawal_usd=round(rmd_withdrawal, 2),
                        roth_conversion_out_usd=round(roth_conversion_out, 2),
                        roth_conversion_in_usd=round(roth_conversion_in, 2),
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
                    income_usd=round(annual_income + annual_social_security_income, 2),
                    social_security_income_usd=round(annual_social_security_income, 2),
                    expenses_usd=round(annual_expenses + annual_debt, 2),
                    taxes_usd=round(taxes, 2),
                    federal_taxes_usd=round(federal_taxes, 2),
                    state_taxes_usd=round(state_taxes, 2),
                    irmaa_surcharges_usd=round(irmaa_surcharges, 2),
                    growth_usd=round(total_growth, 2),
                    withdrawals_usd=round(total_withdrawn, 2),
                    rmds_usd=round(mandatory_rmd_withdrawn, 2),
                    roth_conversions_usd=round(roth_conversions_this_year, 2),
                    ending_balance_real_usd=round(ending_balance_real, 2),
                )
            )

            total_taxes_paid += taxes
            total_federal_taxes_paid += federal_taxes
            total_state_taxes_paid += state_taxes
            total_irmaa_surcharges_paid += irmaa_surcharges
            total_contributions += total_contribution_this_year
            total_withdrawals += total_withdrawn
            total_social_security_income += annual_social_security_income
            total_roth_conversions += roth_conversions_this_year
            tax_rates.append(effective_tax_rate)

            if starting_balance > 0:
                withdrawal_state.previous_growth_rate = total_growth / starting_balance
            else:
                withdrawal_state.previous_growth_rate = 0.0
            if age >= retirement_age:
                withdrawal_state.retirement_years_elapsed += 1
            withdrawal_state.previous_withdrawal_target_usd = required_withdrawals

        ending_nominal = sum(max(0.0, account.balance_usd) for account in accounts)
        average_tax_rate = (sum(tax_rates) / len(tax_rates)) if tax_rates else 0.0
        social_security_claiming_age: int | None = None
        social_security_optimal_claiming_age: int | None = None
        if isinstance(social_security_projection, dict):
            claiming_age_raw = social_security_projection.get("selected_claiming_age")
            optimal_age_raw = social_security_projection.get("optimal_claiming_age")
            if claiming_age_raw is not None:
                social_security_claiming_age = _safe_int(claiming_age_raw, 0)
            if optimal_age_raw is not None:
                social_security_optimal_claiming_age = _safe_int(optimal_age_raw, 0)

        assumption_payload: dict[str, float | int | str | bool | None] = {
            "years": assumptions.years,
            "annual_contribution_usd": round(assumptions.annual_contribution_usd, 2),
            "expected_return": assumptions.expected_return,
            "inflation": assumptions.inflation,
            "account_count": len(accounts),
            "withdrawal_strategy": withdrawal_strategy,
            "drawdown_order": ",".join(drawdown_order) if drawdown_order else "age_aware",
            "retirement_age": retirement_age,
            "rmd_start_age": rmd_start_age,
            "total_taxes_paid_usd": round(total_taxes_paid, 2),
            "total_federal_taxes_paid_usd": round(total_federal_taxes_paid, 2),
            "total_state_taxes_paid_usd": round(total_state_taxes_paid, 2),
            "total_irmaa_surcharges_paid_usd": round(total_irmaa_surcharges_paid, 2),
            "total_contributions_usd": round(total_contributions, 2),
            "total_withdrawals_usd": round(total_withdrawals, 2),
            "total_rmds_usd": round(total_rmds, 2),
            "total_social_security_income_usd": round(total_social_security_income, 2),
            "total_roth_conversions_usd": round(total_roth_conversions, 2),
            "state_tax_rate": round(float(state_tax_rate), 6),
            "include_irmaa": bool(include_irmaa),
            "roth_conversion_annual_amount_usd": round(float(roth_conversion_annual_amount_usd), 2),
            "roth_conversion_start_age": roth_conversion_start_age,
            "roth_conversion_end_age": roth_conversion_end_age,
            "social_security_claiming_age": social_security_claiming_age,
            "social_security_optimal_claiming_age": social_security_optimal_claiming_age,
            "average_effective_tax_rate": round(average_tax_rate, 6),
            "assumption_set_id": (str(assumption_set_id).strip() or None),
            "assumption_set_name": (str(assumption_set_name).strip() or None),
        }
        if isinstance(simulation_metadata, dict):
            for key, value in simulation_metadata.items():
                if value is None:
                    continue
                assumption_payload[str(key)] = value

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
            assumptions=assumption_payload,
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
        expected_return: float,
        simulation_seed: int,
    ) -> dict[str, float | int]:
        outcomes: list[float] = []
        drag = min(max(float(effective_tax_rate), 0.0), 0.5)
        rng = random.Random(simulation_seed)

        for _ in range(self.monte_carlo_runs):
            value = max(0.0, float(current_value))
            for _ in range(max(0, years)):
                yearly_return = rng.gauss(float(expected_return), float(self.return_volatility))
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
        social_security_projection: dict[str, Any] | None = None,
        rmd_projection: dict[str, Any] | None = None,
        filing_status: str | None = None,
        state_tax_rate: float | None = None,
        include_irmaa: bool = True,
        roth_conversion_annual_amount_usd: float | None = None,
        roth_conversion_start_age: int | None = None,
        roth_conversion_end_age: int | None = None,
        drawdown_order: str | list[str] | None = None,
        start_year: int | None = None,
        start_age: int = 35,
        withdrawal_strategy: str | None = None,
        retirement_age: int | None = None,
        simulation_mode: str | None = None,
        simulation_monte_carlo_variant: str | None = None,
        simulation_historical_start_year: int | None = None,
        simulation_seed: int | None = None,
        assumption_set_id: str | None = None,
        assumption_set_name: str | None = None,
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
        resolved_state_tax_rate = max(0.0, min(1.0, _safe_float(state_tax_rate, 0.0)))
        resolved_include_irmaa = bool(include_irmaa)
        resolved_roth_conversion_annual_amount = max(
            0.0,
            _safe_float(roth_conversion_annual_amount_usd, 0.0),
        )
        (
            resolved_roth_conversion_start_age,
            resolved_roth_conversion_end_age,
        ) = _resolve_roth_conversion_window(
            start_age=roth_conversion_start_age,
            end_age=roth_conversion_end_age,
        )
        resolved_drawdown_order = _normalize_drawdown_order(drawdown_order)
        resolved_withdrawal_strategy = _normalize_withdrawal_strategy(withdrawal_strategy)
        resolved_retirement_age = _normalize_retirement_age(retirement_age)
        resolved_simulation_mode = _normalize_simulation_mode(simulation_mode)
        resolved_simulation_monte_carlo_variant = _normalize_monte_carlo_variant(
            simulation_monte_carlo_variant
        )
        resolved_simulation_seed = _normalize_simulation_seed(simulation_seed)
        resolved_simulation_historical_start_year = _normalize_historical_start_year(
            simulation_historical_start_year
        )
        timeline_simulation_mode: SimulationMode = (
            "fixed" if resolved_simulation_mode == "monte_carlo" else resolved_simulation_mode
        )

        base_accounts = self._build_projection_accounts(
            accounts=accounts,
            current_portfolio_value_usd=current_portfolio_value_usd,
            annual_contribution_usd=resolved_contribution,
            contribution_allocation=contribution_allocation,
        )

        scenario_specs = [
            ("baseline", resolved_contribution, self.baseline_return),
            ("optimistic", resolved_contribution, self.optimistic_return),
            ("conservative", resolved_contribution, self.conservative_return),
            ("hsa_delta", resolved_contribution + resolved_hsa_delta, self.baseline_return),
        ]
        computed_scenarios: list[ScenarioResult] = []
        resolved_historical_start_year_by_label: dict[str, int] = {}
        monte_carlo_by_label: dict[str, dict[str, float | int]] = {}

        for label, annual_contribution_for_label, expected_return_for_label in scenario_specs:
            annual_return_series, return_metadata = self._build_annual_return_series(
                mode=timeline_simulation_mode,
                years=resolved_years,
                expected_return=float(expected_return_for_label),
                simulation_seed=resolved_simulation_seed,
                historical_start_year=resolved_simulation_historical_start_year,
            )
            scenario_inflation = float(self.inflation)
            historical_start_year_for_label = return_metadata.get("historical_start_year")
            if isinstance(historical_start_year_for_label, int):
                resolved_historical_start_year_by_label[label] = historical_start_year_for_label
            historical_average_inflation = return_metadata.get("historical_average_inflation")
            if (
                timeline_simulation_mode == "historical"
                and isinstance(historical_average_inflation, (int, float))
            ):
                scenario_inflation = float(historical_average_inflation)

            simulation_metadata: dict[str, float | int | str | bool | None] = {
                "simulation_mode": resolved_simulation_mode,
                "simulation_timeline_mode": timeline_simulation_mode,
                "simulation_monte_carlo_variant": resolved_simulation_monte_carlo_variant,
                "simulation_seed": resolved_simulation_seed,
            }
            if resolved_simulation_historical_start_year is not None:
                simulation_metadata["simulation_requested_historical_start_year"] = (
                    resolved_simulation_historical_start_year
                )
            if isinstance(historical_start_year_for_label, int):
                simulation_metadata["simulation_historical_start_year"] = (
                    historical_start_year_for_label
                )
            if isinstance(historical_average_inflation, (int, float)):
                simulation_metadata["simulation_historical_average_inflation"] = round(
                    float(historical_average_inflation),
                    6,
                )

            scenario = self._scenario(
                label=label,
                current_value=current_portfolio_value_usd,
                assumptions=ScenarioAssumptions(
                    years=resolved_years,
                    annual_contribution_usd=annual_contribution_for_label,
                    expected_return=float(expected_return_for_label),
                    inflation=scenario_inflation,
                ),
                projection_accounts=base_accounts,
                income_projection=income_projection,
                expense_projection=expense_projection,
                debt_projection=debt_projection,
                timeline_projection=timeline_projection,
                social_security_projection=social_security_projection,
                rmd_projection=rmd_projection,
                filing_status=resolved_filing_status,
                state_tax_rate=resolved_state_tax_rate,
                include_irmaa=resolved_include_irmaa,
                roth_conversion_annual_amount_usd=resolved_roth_conversion_annual_amount,
                roth_conversion_start_age=resolved_roth_conversion_start_age,
                roth_conversion_end_age=resolved_roth_conversion_end_age,
                drawdown_order=resolved_drawdown_order,
                start_year=resolved_start_year,
                start_age=resolved_start_age,
                withdrawal_strategy=resolved_withdrawal_strategy,
                retirement_age=resolved_retirement_age,
                annual_return_series=annual_return_series,
                simulation_metadata=simulation_metadata,
                assumption_set_id=assumption_set_id,
                assumption_set_name=assumption_set_name,
            )

            if resolved_simulation_mode == "monte_carlo":
                monte_carlo_for_scenario = self._monte_carlo(
                    current_value=current_portfolio_value_usd,
                    annual_contribution=annual_contribution_for_label,
                    years=resolved_years,
                    effective_tax_rate=_safe_float(
                        scenario.assumptions.get("average_effective_tax_rate"),
                        self.marginal_tax_rate,
                    ),
                    expected_return=float(expected_return_for_label),
                    simulation_seed=resolved_simulation_seed,
                )
                monte_carlo_by_label[label] = monte_carlo_for_scenario
                selected_future_value = _safe_float(
                    monte_carlo_for_scenario.get(
                        f"{resolved_simulation_monte_carlo_variant}_future_value_usd"
                    ),
                    0.0,
                )
                selected_real_value = self._real_value(
                    nominal_future_value=selected_future_value,
                    years=resolved_years,
                    inflation=float(scenario.assumptions.get("inflation") or self.inflation),
                )
                updated_assumptions = dict(scenario.assumptions)
                updated_assumptions["simulation_mode"] = "monte_carlo"
                updated_assumptions["simulation_monte_carlo_variant"] = (
                    resolved_simulation_monte_carlo_variant
                )
                updated_assumptions["simulation_monte_carlo_runs"] = int(
                    monte_carlo_for_scenario.get("runs") or self.monte_carlo_runs
                )
                updated_assumptions["simulation_monte_carlo_p10_future_value_usd"] = _safe_float(
                    monte_carlo_for_scenario.get("p10_future_value_usd"),
                    0.0,
                )
                updated_assumptions["simulation_monte_carlo_p50_future_value_usd"] = _safe_float(
                    monte_carlo_for_scenario.get("p50_future_value_usd"),
                    0.0,
                )
                updated_assumptions["simulation_monte_carlo_p90_future_value_usd"] = _safe_float(
                    monte_carlo_for_scenario.get("p90_future_value_usd"),
                    0.0,
                )
                updated_assumptions["simulation_selected_future_value_usd"] = round(
                    selected_future_value,
                    2,
                )
                scenario = scenario.model_copy(
                    update={
                        "future_value_usd": round(selected_future_value, 2),
                        "real_value_usd": round(selected_real_value, 2),
                        "assumptions": updated_assumptions,
                    }
                )

            computed_scenarios.append(scenario)

        scenarios_by_label = {item.label: item for item in computed_scenarios}
        ordered_scenarios = [
            scenarios_by_label[label]
            for label in ("baseline", "optimistic", "conservative", "hsa_delta")
            if label in scenarios_by_label
        ]
        baseline = scenarios_by_label.get("baseline")

        if resolved_simulation_mode == "monte_carlo":
            monte_carlo: dict[str, Any] = dict(monte_carlo_by_label.get("baseline", {}))
            if not monte_carlo:
                monte_carlo = self._monte_carlo(
                    current_value=current_portfolio_value_usd,
                    annual_contribution=resolved_contribution,
                    years=resolved_years,
                    effective_tax_rate=_safe_float(
                        baseline.assumptions.get("average_effective_tax_rate")
                        if baseline is not None
                        else self.marginal_tax_rate,
                        self.marginal_tax_rate,
                    ),
                    expected_return=float(self.baseline_return),
                    simulation_seed=resolved_simulation_seed,
                )
        else:
            monte_carlo = self._monte_carlo(
                current_value=current_portfolio_value_usd,
                annual_contribution=resolved_contribution,
                years=resolved_years,
                effective_tax_rate=_safe_float(
                    baseline.assumptions.get("average_effective_tax_rate")
                    if baseline is not None
                    else self.marginal_tax_rate,
                    self.marginal_tax_rate,
                ),
                expected_return=float(self.baseline_return),
                simulation_seed=resolved_simulation_seed,
            )

        monte_carlo["mode"] = resolved_simulation_mode
        monte_carlo["variant"] = resolved_simulation_monte_carlo_variant
        monte_carlo["seed"] = resolved_simulation_seed
        if resolved_simulation_historical_start_year is not None:
            monte_carlo["requested_historical_start_year"] = (
                resolved_simulation_historical_start_year
            )

        simulation_summary: dict[str, Any] = {
            "mode": resolved_simulation_mode,
            "timeline_mode": timeline_simulation_mode,
            "monte_carlo_variant": resolved_simulation_monte_carlo_variant,
            "seed": resolved_simulation_seed,
            "requested_historical_start_year": resolved_simulation_historical_start_year,
        }
        if resolved_historical_start_year_by_label:
            simulation_summary["resolved_historical_start_year_by_scenario"] = (
                resolved_historical_start_year_by_label
            )

        return PlanningResponse(
            scenarios=ordered_scenarios,
            monte_carlo=monte_carlo,
            simulation=simulation_summary,
        )
