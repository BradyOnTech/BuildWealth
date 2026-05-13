"""Required Minimum Distribution projection helpers for planning workflows.

RMD table and start-age policy are implemented for BuildWealth simulation workflows:
- src/lib/calc/historical-data/rmd-table.ts
- src/lib/calc/simulation-engine.ts
- src/lib/calc/portfolio.ts
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from buildwealth_orchestrator.services.contribution_rules import normalize_account_type
from buildwealth_orchestrator.services.value_coercion import safe_float, safe_int


UNIFORM_LIFETIME_FACTORS: dict[int, float] = {
    72: 27.4,
    73: 26.5,
    74: 25.5,
    75: 24.6,
    76: 23.7,
    77: 22.9,
    78: 22.0,
    79: 21.1,
    80: 20.2,
    81: 19.4,
    82: 18.5,
    83: 17.7,
    84: 16.8,
    85: 16.0,
    86: 15.2,
    87: 14.4,
    88: 13.7,
    89: 12.9,
    90: 12.2,
    91: 11.5,
    92: 10.8,
    93: 10.1,
    94: 9.5,
    95: 8.9,
    96: 8.4,
    97: 7.8,
    98: 7.3,
    99: 6.8,
    100: 6.4,
    101: 6.0,
    102: 5.6,
    103: 5.2,
    104: 4.9,
    105: 4.6,
    106: 4.3,
    107: 4.1,
    108: 3.9,
    109: 3.7,
    110: 3.5,
    111: 3.4,
    112: 3.3,
    113: 3.1,
    114: 3.0,
    115: 2.9,
    116: 2.8,
    117: 2.7,
    118: 2.5,
    119: 2.3,
    120: 2.0,
}

RMD_ELIGIBLE_ACCOUNT_TYPES = {"401k", "403b", "ira"}


def determine_rmd_start_age(
    *,
    birth_year: int | None,
    override_start_age: int | None = None,
) -> int:
    if override_start_age is not None:
        return max(72, min(int(override_start_age), 120))
    if birth_year is not None and int(birth_year) >= 1960:
        return 75
    return 73


def _lookup_factor_for_age(age: float) -> tuple[int, float | None]:
    lookup_age = max(72, min(int(math.floor(age)), 120))
    return lookup_age, UNIFORM_LIFETIME_FACTORS.get(lookup_age)


def _is_rmd_eligible_account(account_type: Any) -> bool:
    normalized = normalize_account_type(account_type)
    return normalized in RMD_ELIGIBLE_ACCOUNT_TYPES


def estimate_year_rmd_for_accounts(
    *,
    accounts: list[dict[str, Any]],
    age: float,
    rmd_start_age: int,
) -> dict[str, Any]:
    rounded_age = float(age)
    if rounded_age < rmd_start_age:
        return {
            "age": rounded_age,
            "rmd_start_age": int(rmd_start_age),
            "lookup_age": None,
            "life_expectancy_factor": None,
            "total_rmd_usd": 0.0,
            "account_rmds": [],
            "warnings": [],
        }

    lookup_age, factor = _lookup_factor_for_age(rounded_age)
    if factor is None or factor <= 0:
        return {
            "age": rounded_age,
            "rmd_start_age": int(rmd_start_age),
            "lookup_age": lookup_age,
            "life_expectancy_factor": None,
            "total_rmd_usd": 0.0,
            "account_rmds": [],
            "warnings": [f"No IRS Uniform Lifetime factor found for age {lookup_age}."],
        }

    account_rows: list[dict[str, Any]] = []
    total = 0.0
    for raw in accounts:
        if not isinstance(raw, dict):
            continue
        account_type = normalize_account_type(raw.get("account_type"))
        if not _is_rmd_eligible_account(account_type):
            continue

        account_id = str(raw.get("account_id") or "").strip()
        if not account_id:
            continue

        starting_balance = max(
            0.0,
            safe_float(raw.get("balance_usd", raw.get("balance")), 0.0),
        )
        if starting_balance <= 0:
            continue

        rmd_amount = starting_balance / factor
        rmd_amount = max(0.0, min(rmd_amount, starting_balance))
        total += rmd_amount
        account_rows.append(
            {
                "account_id": account_id,
                "account_type": account_type,
                "starting_balance_usd": round(starting_balance, 2),
                "rmd_usd": round(rmd_amount, 2),
            }
        )

    return {
        "age": rounded_age,
        "rmd_start_age": int(rmd_start_age),
        "lookup_age": lookup_age,
        "life_expectancy_factor": factor,
        "total_rmd_usd": round(total, 2),
        "account_rmds": account_rows,
        "warnings": [],
    }


def project_rmd_schedule(
    *,
    accounts: list[dict[str, Any]],
    start_year: int,
    years: int,
    current_age: int = 35,
    birth_year: int | None = None,
    expected_return: float = 0.04,
    start_age_override: int | None = None,
) -> dict[str, Any]:
    resolved_start_year = safe_int(start_year, datetime.now().year)
    resolved_years = max(1, min(safe_int(years, 1), 80))
    resolved_current_age = max(0, min(safe_int(current_age, 35), 120))
    resolved_birth_year = None if birth_year is None else max(1900, min(safe_int(birth_year, 0), 2500))
    resolved_expected_return = max(-0.95, min(safe_float(expected_return, 0.04), 1.0))
    resolved_start_age = (
        None if start_age_override is None else max(72, min(safe_int(start_age_override, 73), 120))
    )
    rmd_start_age = determine_rmd_start_age(
        birth_year=resolved_birth_year,
        override_start_age=resolved_start_age,
    )

    warnings: list[str] = []
    working_accounts: list[dict[str, Any]] = []
    for raw in accounts:
        if not isinstance(raw, dict):
            continue
        account_id = str(raw.get("account_id") or "").strip()
        account_type = normalize_account_type(raw.get("account_type"))
        balance = max(0.0, safe_float(raw.get("balance_usd", raw.get("balance")), 0.0))
        if not account_id:
            continue
        working_accounts.append(
            {
                "account_id": account_id,
                "account_type": account_type,
                "balance_usd": balance,
            }
        )

    eligible_accounts = [
        account
        for account in working_accounts
        if _is_rmd_eligible_account(account.get("account_type"))
    ]
    if not eligible_accounts:
        warnings.append("No eligible RMD accounts found (eligible: 401k, 403b, ira).")

    total_initial_eligible_balance = round(
        sum(max(0.0, safe_float(item.get("balance_usd"), 0.0)) for item in eligible_accounts),
        2,
    )

    yearly_points: list[dict[str, Any]] = []
    cumulative_rmds = 0.0
    for offset in range(resolved_years):
        year = resolved_start_year + offset
        age = resolved_current_age + offset
        before_total = round(
            sum(max(0.0, safe_float(item.get("balance_usd"), 0.0)) for item in eligible_accounts),
            2,
        )
        year_rmd = estimate_year_rmd_for_accounts(
            accounts=eligible_accounts,
            age=float(age),
            rmd_start_age=rmd_start_age,
        )
        total_rmd = safe_float(year_rmd.get("total_rmd_usd"), 0.0)
        cumulative_rmds += total_rmd

        by_account = {row.get("account_id"): safe_float(row.get("rmd_usd"), 0.0) for row in year_rmd.get("account_rmds", [])}
        for account in eligible_accounts:
            account_id = str(account.get("account_id") or "")
            balance = max(0.0, safe_float(account.get("balance_usd"), 0.0))
            withdrawal = max(0.0, by_account.get(account_id, 0.0))
            post_withdrawal = max(0.0, balance - withdrawal)
            account["balance_usd"] = post_withdrawal * (1.0 + resolved_expected_return)

        yearly_points.append(
            {
                "year": year,
                "age": age,
                "lookup_age": year_rmd.get("lookup_age"),
                "life_expectancy_factor": year_rmd.get("life_expectancy_factor"),
                "total_eligible_balance_start_usd": before_total,
                "total_rmd_usd": round(total_rmd, 2),
                "cumulative_rmds_usd": round(cumulative_rmds, 2),
                "account_rmds": year_rmd.get("account_rmds", []),
            }
        )
        for warning in year_rmd.get("warnings", []):
            if warning not in warnings:
                warnings.append(str(warning))

    return {
        "start_year": resolved_start_year,
        "years": resolved_years,
        "current_age": resolved_current_age,
        "birth_year": resolved_birth_year,
        "rmd_start_age": rmd_start_age,
        "expected_return": round(resolved_expected_return, 6),
        "eligible_account_count": len(eligible_accounts),
        "total_initial_eligible_balance_usd": total_initial_eligible_balance,
        "total_projected_rmds_usd": round(cumulative_rmds, 2),
        "yearly_points": yearly_points,
        "warnings": warnings,
    }


__all__ = [
    "UNIFORM_LIFETIME_FACTORS",
    "determine_rmd_start_age",
    "estimate_year_rmd_for_accounts",
    "project_rmd_schedule",
]
