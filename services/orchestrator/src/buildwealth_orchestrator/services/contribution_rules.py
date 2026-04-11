"""Contribution-rule allocation engine for retirement planning.

Core rule/limit behavior is adapted from Ignidash (MIT):
- src/lib/calc/contribution-rules.ts
- src/lib/schemas/inputs/contribution-form-schema.ts
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AmountType = Literal["dollarAmount", "percentRemaining", "unlimited"]
BaseRuleType = Literal["save", "spend"]


ACCOUNT_TYPE_ALIASES: dict[str, str] = {
    "taxable": "taxableBrokerage",
    "taxablebrokerage": "taxableBrokerage",
    "brokerage": "taxableBrokerage",
    "savings": "savings",
    "cash": "savings",
    "checking": "savings",
    "401k": "401k",
    "traditional401k": "401k",
    "roth401k": "roth401k",
    "roth401": "roth401k",
    "403b": "403b",
    "roth403b": "roth403b",
    "roth403": "roth403b",
    "ira": "ira",
    "traditionalira": "ira",
    "rothira": "rothIra",
    "hsa": "hsa",
}

SHARED_LIMIT_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "401k": ("401k", "roth401k", "403b", "roth403b"),
    "403b": ("401k", "roth401k", "403b", "roth403b"),
    "roth401k": ("401k", "roth401k", "403b", "roth403b"),
    "roth403b": ("401k", "roth401k", "403b", "roth403b"),
    "ira": ("ira", "rothIra"),
    "rothIra": ("ira", "rothIra"),
    "hsa": ("hsa",),
}


@dataclass
class AllocationAccount:
    account_id: str
    account_name: str
    account_type: str
    balance_usd: float = 0.0


@dataclass
class AllocationRule:
    rule_id: str
    account_id: str
    rank: int
    contribution_type: AmountType
    dollar_amount_usd: float | None = None
    percent_remaining: float | None = None
    max_balance_usd: float | None = None
    employer_match_usd: float | None = None
    disabled: bool = False
    enable_mega_backdoor_roth: bool = False


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_account_type(account_type: Any) -> str:
    raw = str(account_type or "").strip()
    if not raw:
        return "taxableBrokerage"
    cleaned = raw.replace("-", "").replace("_", "").replace(" ", "").lower()
    return ACCOUNT_TYPE_ALIASES.get(cleaned, str(account_type).strip() or "taxableBrokerage")


def tax_treatment_for_account_type(account_type: Any) -> Literal["taxable", "tax_deferred", "tax_free"]:
    normalized = normalize_account_type(account_type)
    if normalized in {"roth401k", "roth403b", "rothIra"}:
        return "tax_free"
    if normalized in {"401k", "403b", "ira", "hsa"}:
        return "tax_deferred"
    return "taxable"


def _get_account_type_limit_key(account_type: str) -> str:
    if account_type in {"401k", "403b", "roth401k", "roth403b"}:
        return "401kCombined"
    if account_type in {"ira", "rothIra"}:
        return "iraCombined"
    return account_type


def get_annual_contribution_limit(limit_key: str, age: int) -> float:
    # Mirrors Ignidash current IRS-limit table assumptions.
    if limit_key == "401kCombined":
        if 60 <= age <= 63:
            return 35_750.0
        if age >= 50:
            return 32_500.0
        return 24_500.0
    if limit_key == "iraCombined":
        return 8_600.0 if age >= 50 else 7_500.0
    if limit_key == "hsa":
        return 5_400.0 if age >= 55 else 4_400.0
    return float("inf")


def _get_annual_section_415c_limit(age: int) -> float:
    if 60 <= age <= 63:
        return 83_250.0
    if age >= 50:
        return 80_000.0
    return 72_000.0


def _supports_mega_backdoor_roth(account_type: str) -> bool:
    return account_type in {"roth401k", "roth403b"}


def _parse_accounts(raw_accounts: list[dict[str, Any]]) -> list[AllocationAccount]:
    parsed: list[AllocationAccount] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_accounts, start=1):
        account_id = str(raw.get("account_id") or raw.get("id") or "").strip()
        if not account_id:
            account_id = f"account-{index}"
        if account_id in seen:
            continue
        seen.add(account_id)

        parsed.append(
            AllocationAccount(
                account_id=account_id,
                account_name=str(raw.get("account_name") or raw.get("name") or account_id).strip() or account_id,
                account_type=normalize_account_type(raw.get("account_type") or raw.get("type")),
                balance_usd=max(
                    0.0,
                    _safe_float(
                        raw.get("balance_usd", raw.get("balance", raw.get("total_value", 0.0))),
                        0.0,
                    ),
                ),
            )
        )
    return parsed


def _parse_rules(raw_rules: list[dict[str, Any]]) -> list[AllocationRule]:
    parsed: list[AllocationRule] = []
    for index, raw in enumerate(raw_rules, start=1):
        nested_amount = raw.get("amount")
        amount_payload = nested_amount if isinstance(nested_amount, dict) else {}

        contribution_type_raw = (
            raw.get("contribution_type")
            or raw.get("contributionType")
            or amount_payload.get("type")
            or "unlimited"
        )
        contribution_type_text = str(contribution_type_raw).strip()
        contribution_type: AmountType
        if contribution_type_text == "dollarAmount":
            contribution_type = "dollarAmount"
        elif contribution_type_text == "percentRemaining":
            contribution_type = "percentRemaining"
        else:
            contribution_type = "unlimited"

        account_id = str(raw.get("account_id") or raw.get("accountId") or "").strip()
        if not account_id:
            continue

        parsed.append(
            AllocationRule(
                rule_id=str(raw.get("rule_id") or raw.get("id") or f"rule-{index}").strip() or f"rule-{index}",
                account_id=account_id,
                rank=int(_safe_float(raw.get("rank"), 0.0)),
                contribution_type=contribution_type,
                dollar_amount_usd=max(
                    0.0,
                    _safe_float(
                        raw.get("dollar_amount_usd", raw.get("dollarAmount", amount_payload.get("dollarAmount"))),
                        0.0,
                    ),
                )
                if contribution_type == "dollarAmount"
                else None,
                percent_remaining=min(
                    100.0,
                    max(
                        0.0,
                        _safe_float(
                            raw.get(
                                "percent_remaining",
                                raw.get("percentRemaining", amount_payload.get("percentRemaining")),
                            ),
                            0.0,
                        ),
                    ),
                )
                if contribution_type == "percentRemaining"
                else None,
                max_balance_usd=max(
                    0.0,
                    _safe_float(raw.get("max_balance_usd", raw.get("maxBalance")), 0.0),
                )
                if raw.get("max_balance_usd") is not None or raw.get("maxBalance") is not None
                else None,
                employer_match_usd=max(
                    0.0,
                    _safe_float(raw.get("employer_match_usd", raw.get("employerMatch")), 0.0),
                )
                if raw.get("employer_match_usd") is not None or raw.get("employerMatch") is not None
                else None,
                disabled=_safe_bool(raw.get("disabled"), False),
                enable_mega_backdoor_roth=_safe_bool(
                    raw.get("enable_mega_backdoor_roth", raw.get("enableMegaBackdoorRoth")),
                    False,
                ),
            )
        )
    parsed.sort(key=lambda item: (item.rank, item.rule_id))
    return parsed


def _sum_by_types(values: dict[str, float], types: tuple[str, ...]) -> float:
    return sum(values.get(account_type, 0.0) for account_type in types)


def _remaining_account_type_limit(
    *,
    account_type: str,
    age: int,
    employee_by_type: dict[str, float],
    employer_by_type: dict[str, float],
    enable_mega_backdoor_roth: bool,
) -> float:
    shared_types = SHARED_LIMIT_ACCOUNTS.get(account_type)
    if shared_types is None:
        return float("inf")

    if enable_mega_backdoor_roth and _supports_mega_backdoor_roth(account_type):
        employee_total = _sum_by_types(employee_by_type, shared_types)
        employer_total = _sum_by_types(employer_by_type, shared_types)
        return max(0.0, _get_annual_section_415c_limit(age) - (employee_total + employer_total))

    limit = get_annual_contribution_limit(_get_account_type_limit_key(account_type), age)
    if not limit or limit == float("inf"):
        return float("inf")
    employee_total = _sum_by_types(employee_by_type, shared_types)
    return max(0.0, limit - employee_total)


def build_tax_optimized_high_earner_rules(
    accounts: list[dict[str, Any]],
    *,
    employer_match_target_usd: float = 6_000.0,
) -> dict[str, Any]:
    parsed_accounts = _parse_accounts(accounts)
    by_type: dict[str, list[AllocationAccount]] = {}
    for account in parsed_accounts:
        by_type.setdefault(account.account_type, []).append(account)

    employer_account = next(
        (
            account
            for account_type in ("401k", "roth401k", "403b", "roth403b")
            for account in by_type.get(account_type, [])
        ),
        None,
    )
    hsa_account = next(iter(by_type.get("hsa", [])), None)
    roth_ira_account = next(iter(by_type.get("rothIra", [])), None)
    traditional_ira_account = next(iter(by_type.get("ira", [])), None)
    ira_account = roth_ira_account or traditional_ira_account
    taxable_account = next(
        (
            account
            for account_type in ("taxableBrokerage", "savings")
            for account in by_type.get(account_type, [])
        ),
        None,
    )

    rules: list[dict[str, Any]] = []
    next_rank = 1
    match_target = max(0.0, _safe_float(employer_match_target_usd, 0.0))

    if employer_account and match_target > 0:
        rules.append(
            {
                "id": "rule-401k-match",
                "accountId": employer_account.account_id,
                "rank": next_rank,
                "amount": {
                    "type": "dollarAmount",
                    "dollarAmount": round(match_target, 2),
                },
                "employerMatch": round(match_target, 2),
                "disabled": False,
            }
        )
        next_rank += 1

    if hsa_account:
        rules.append(
            {
                "id": "rule-hsa",
                "accountId": hsa_account.account_id,
                "rank": next_rank,
                "amount": {"type": "unlimited"},
                "disabled": False,
            }
        )
        next_rank += 1

    if ira_account:
        rules.append(
            {
                "id": "rule-roth-ira",
                "accountId": ira_account.account_id,
                "rank": next_rank,
                "amount": {"type": "unlimited"},
                "disabled": False,
            }
        )
        next_rank += 1

    if employer_account:
        rules.append(
            {
                "id": "rule-401k-remaining",
                "accountId": employer_account.account_id,
                "rank": next_rank,
                "amount": {"type": "unlimited"},
                "disabled": False,
            }
        )
        next_rank += 1

    if taxable_account:
        rules.append(
            {
                "id": "rule-taxable",
                "accountId": taxable_account.account_id,
                "rank": next_rank,
                "amount": {"type": "unlimited"},
                "disabled": False,
            }
        )
        next_rank += 1

    if not rules and parsed_accounts:
        rules.append(
            {
                "id": "rule-fallback",
                "accountId": parsed_accounts[0].account_id,
                "rank": 1,
                "amount": {"type": "unlimited"},
                "disabled": False,
            }
        )

    return {
        "profile_id": "tax_optimized_high_earner",
        "profile_name": "Tax Optimized (High Earner)",
        "base_rule": {"type": "save"},
        "rules": rules,
    }


def allocate_contributions(
    *,
    annual_contribution_usd: float,
    accounts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    base_rule: dict[str, Any] | None = None,
    age: int = 35,
    profile_id: str | None = None,
) -> dict[str, Any]:
    contribution_target = max(0.0, _safe_float(annual_contribution_usd, 0.0))
    parsed_accounts = _parse_accounts(accounts)
    parsed_rules = [rule for rule in _parse_rules(rules) if not rule.disabled]
    base_rule_type = str((base_rule or {}).get("type") or "save").strip().lower()
    if base_rule_type not in {"save", "spend"}:
        base_rule_type = "save"

    account_lookup: dict[str, AllocationAccount] = {account.account_id: account for account in parsed_accounts}
    account_contributions: dict[str, dict[str, Any]] = {
        account.account_id: {
            "account_id": account.account_id,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "balance_usd": round(account.balance_usd, 2),
            "employee_contribution_usd": 0.0,
            "employer_match_usd": 0.0,
            "total_contribution_usd": 0.0,
            "applied_rule_ids": [],
        }
        for account in parsed_accounts
    }

    employee_by_type: dict[str, float] = {}
    employer_by_type: dict[str, float] = {}
    employee_by_rule: dict[str, float] = {}
    employer_by_rule: dict[str, float] = {}
    warnings: list[str] = []
    rule_results: list[dict[str, Any]] = []

    remaining_budget = contribution_target

    def apply_contribution(
        *,
        account: AllocationAccount,
        rule_id: str,
        employee_contribution_usd: float,
        employer_match_usd: float,
    ) -> None:
        employee_amount = max(0.0, employee_contribution_usd)
        employer_amount = max(0.0, employer_match_usd)
        if employee_amount <= 0 and employer_amount <= 0:
            return

        bucket = account_contributions[account.account_id]
        bucket["employee_contribution_usd"] = round(bucket["employee_contribution_usd"] + employee_amount, 2)
        bucket["employer_match_usd"] = round(bucket["employer_match_usd"] + employer_amount, 2)
        bucket["total_contribution_usd"] = round(
            bucket["employee_contribution_usd"] + bucket["employer_match_usd"],
            2,
        )
        if rule_id not in bucket["applied_rule_ids"]:
            bucket["applied_rule_ids"].append(rule_id)

        employee_by_type[account.account_type] = employee_by_type.get(account.account_type, 0.0) + employee_amount
        employer_by_type[account.account_type] = employer_by_type.get(account.account_type, 0.0) + employer_amount
        employee_by_rule[rule_id] = employee_by_rule.get(rule_id, 0.0) + employee_amount
        employer_by_rule[rule_id] = employer_by_rule.get(rule_id, 0.0) + employer_amount

    for rule in parsed_rules:
        if remaining_budget <= 1e-9:
            break

        account = account_lookup.get(rule.account_id)
        if account is None:
            warnings.append(f"Skipped contribution rule '{rule.rule_id}' because account '{rule.account_id}' was not found.")
            continue

        if rule.contribution_type == "dollarAmount":
            desired = max(0.0, (rule.dollar_amount_usd or 0.0) - employee_by_rule.get(rule.rule_id, 0.0))
        elif rule.contribution_type == "percentRemaining":
            desired = remaining_budget * ((rule.percent_remaining or 0.0) / 100.0)
        else:
            desired = float("inf")

        account_bucket = account_contributions[account.account_id]
        current_account_total = _safe_float(account_bucket.get("total_contribution_usd"), 0.0)
        if rule.max_balance_usd is None:
            remaining_to_max_balance = float("inf")
        else:
            remaining_to_max_balance = max(0.0, rule.max_balance_usd - (account.balance_usd + current_account_total))

        remaining_type_limit = _remaining_account_type_limit(
            account_type=account.account_type,
            age=int(max(0, age)),
            employee_by_type=employee_by_type,
            employer_by_type=employer_by_type,
            enable_mega_backdoor_roth=rule.enable_mega_backdoor_roth,
        )
        max_allowed = min(remaining_budget, remaining_to_max_balance, remaining_type_limit)
        employee_amount = max(0.0, min(desired, max_allowed))

        employer_cap_remaining = max(0.0, (rule.employer_match_usd or 0.0) - employer_by_rule.get(rule.rule_id, 0.0))
        employer_amount = min(employee_amount, employer_cap_remaining)

        limited_by: list[str] = []
        if employee_amount + 1e-9 < desired:
            if remaining_budget <= employee_amount + 1e-9:
                limited_by.append("annual_budget")
            if remaining_to_max_balance <= employee_amount + 1e-9 and remaining_to_max_balance != float("inf"):
                limited_by.append("max_balance")
            if remaining_type_limit <= employee_amount + 1e-9 and remaining_type_limit != float("inf"):
                limited_by.append("irs_limit")
            if not limited_by:
                limited_by.append("rule_cap")

        apply_contribution(
            account=account,
            rule_id=rule.rule_id,
            employee_contribution_usd=employee_amount,
            employer_match_usd=employer_amount,
        )
        remaining_budget = max(0.0, remaining_budget - employee_amount)

        rule_results.append(
            {
                "rule_id": rule.rule_id,
                "account_id": account.account_id,
                "account_type": account.account_type,
                "rank": rule.rank,
                "contribution_type": rule.contribution_type,
                "requested_employee_contribution_usd": None if desired == float("inf") else round(desired, 2),
                "employee_contribution_usd": round(employee_amount, 2),
                "employer_match_usd": round(employer_amount, 2),
                "limited_by": limited_by,
            }
        )

    if remaining_budget > 1e-9 and base_rule_type == "save":
        save_candidates = [
            account
            for account in parsed_accounts
            if account.account_type in {"taxableBrokerage", "savings"}
        ]
        if not save_candidates:
            save_candidates = list(parsed_accounts)

        fallback_account = save_candidates[0] if save_candidates else None
        if fallback_account is None:
            warnings.append("No accounts available for base save rule; some annual contribution remains unallocated.")
        else:
            remaining_type_limit = _remaining_account_type_limit(
                account_type=fallback_account.account_type,
                age=int(max(0, age)),
                employee_by_type=employee_by_type,
                employer_by_type=employer_by_type,
                enable_mega_backdoor_roth=False,
            )
            fallback_amount = max(0.0, min(remaining_budget, remaining_type_limit))
            if fallback_amount > 0:
                apply_contribution(
                    account=fallback_account,
                    rule_id="base-save",
                    employee_contribution_usd=fallback_amount,
                    employer_match_usd=0.0,
                )
                remaining_budget = max(0.0, remaining_budget - fallback_amount)
                rule_results.append(
                    {
                        "rule_id": "base-save",
                        "account_id": fallback_account.account_id,
                        "account_type": fallback_account.account_type,
                        "rank": 9_999,
                        "contribution_type": "unlimited",
                        "requested_employee_contribution_usd": round(fallback_amount, 2),
                        "employee_contribution_usd": round(fallback_amount, 2),
                        "employer_match_usd": 0.0,
                        "limited_by": [],
                    }
                )

    if remaining_budget > 1e-9 and base_rule_type == "save":
        warnings.append(
            "Contribution rules could not allocate the full annual contribution target under account/balance limits."
        )

    allocations = []
    for account in parsed_accounts:
        bucket = account_contributions[account.account_id]
        allocations.append(
            {
                **bucket,
                "employee_contribution_usd": round(_safe_float(bucket.get("employee_contribution_usd"), 0.0), 2),
                "employer_match_usd": round(_safe_float(bucket.get("employer_match_usd"), 0.0), 2),
                "total_contribution_usd": round(_safe_float(bucket.get("total_contribution_usd"), 0.0), 2),
            }
        )

    total_employee = round(sum(_safe_float(item["employee_contribution_usd"]) for item in allocations), 2)
    total_employer = round(sum(_safe_float(item["employer_match_usd"]) for item in allocations), 2)

    return {
        "profile_id": profile_id,
        "base_rule_type": base_rule_type,
        "annual_contribution_target_usd": round(contribution_target, 2),
        "employee_contributions_usd": total_employee,
        "employer_match_usd": total_employer,
        "total_contributions_usd": round(total_employee + total_employer, 2),
        "unallocated_contribution_usd": round(remaining_budget, 2),
        "allocations": allocations,
        "rule_results": rule_results,
        "warnings": warnings,
    }


__all__ = [
    "allocate_contributions",
    "build_tax_optimized_high_earner_rules",
    "get_annual_contribution_limit",
    "normalize_account_type",
    "tax_treatment_for_account_type",
]

