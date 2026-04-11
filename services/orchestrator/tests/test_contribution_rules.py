from buildwealth_orchestrator.services.contribution_rules import (
    allocate_contributions,
    build_tax_optimized_high_earner_rules,
)


def _allocations_by_account(result: dict) -> dict[str, dict]:
    return {row["account_id"]: row for row in result.get("allocations", [])}


def test_allocate_contributions_enforces_ranked_limits_and_match() -> None:
    accounts = [
        {"account_id": "acct-401k", "account_name": "Employer 401k", "account_type": "401k", "balance_usd": 100000},
        {"account_id": "acct-hsa", "account_name": "HSA", "account_type": "hsa", "balance_usd": 15000},
        {"account_id": "acct-roth", "account_name": "Roth IRA", "account_type": "rothIra", "balance_usd": 30000},
        {"account_id": "acct-taxable", "account_name": "Taxable", "account_type": "taxableBrokerage", "balance_usd": 90000},
    ]
    profile = build_tax_optimized_high_earner_rules(accounts, employer_match_target_usd=6000)

    result = allocate_contributions(
        annual_contribution_usd=50000,
        age=35,
        accounts=accounts,
        rules=profile["rules"],
        base_rule=profile["base_rule"],
        profile_id=profile["profile_id"],
    )
    allocations = _allocations_by_account(result)

    assert result["employee_contributions_usd"] == 50000.0
    assert result["employer_match_usd"] == 6000.0
    assert result["total_contributions_usd"] == 56000.0
    assert result["unallocated_contribution_usd"] == 0.0
    assert allocations["acct-401k"]["employee_contribution_usd"] == 24500.0
    assert allocations["acct-401k"]["employer_match_usd"] == 6000.0
    assert allocations["acct-hsa"]["employee_contribution_usd"] == 4400.0
    assert allocations["acct-roth"]["employee_contribution_usd"] == 7500.0
    assert allocations["acct-taxable"]["employee_contribution_usd"] == 13600.0


def test_allocate_contributions_shares_ira_limit_between_ira_types() -> None:
    accounts = [
        {"account_id": "acct-ira", "account_name": "Traditional IRA", "account_type": "ira", "balance_usd": 20000},
        {"account_id": "acct-roth", "account_name": "Roth IRA", "account_type": "rothIra", "balance_usd": 25000},
    ]
    rules = [
        {"id": "rule-ira", "accountId": "acct-ira", "rank": 1, "amount": {"type": "unlimited"}},
        {"id": "rule-roth", "accountId": "acct-roth", "rank": 2, "amount": {"type": "unlimited"}},
    ]

    result = allocate_contributions(
        annual_contribution_usd=12000,
        age=35,
        accounts=accounts,
        rules=rules,
        base_rule={"type": "spend"},
    )
    allocations = _allocations_by_account(result)

    assert allocations["acct-ira"]["employee_contribution_usd"] == 7500.0
    assert allocations["acct-roth"]["employee_contribution_usd"] == 0.0
    assert result["unallocated_contribution_usd"] == 4500.0


def test_allocate_contributions_spend_base_rule_preserves_unallocated_amount() -> None:
    accounts = [
        {"account_id": "acct-401k", "account_name": "Employer 401k", "account_type": "401k", "balance_usd": 100000},
    ]
    rules = [
        {"id": "rule-401k", "accountId": "acct-401k", "rank": 1, "amount": {"type": "unlimited"}},
    ]

    result = allocate_contributions(
        annual_contribution_usd=50000,
        age=35,
        accounts=accounts,
        rules=rules,
        base_rule={"type": "spend"},
    )
    allocations = _allocations_by_account(result)

    assert allocations["acct-401k"]["employee_contribution_usd"] == 24500.0
    assert result["employee_contributions_usd"] == 24500.0
    assert result["unallocated_contribution_usd"] == 25500.0


def test_build_tax_optimized_high_earner_rules_generates_expected_priority_order() -> None:
    accounts = [
        {"account_id": "acct-taxable", "account_name": "Taxable", "account_type": "taxable"},
        {"account_id": "acct-401k", "account_name": "401k", "account_type": "401k"},
        {"account_id": "acct-hsa", "account_name": "HSA", "account_type": "hsa"},
        {"account_id": "acct-roth", "account_name": "Roth IRA", "account_type": "rothIra"},
    ]

    profile = build_tax_optimized_high_earner_rules(accounts, employer_match_target_usd=5000)
    rules = profile["rules"]

    assert profile["profile_id"] == "tax_optimized_high_earner"
    assert profile["base_rule"]["type"] == "save"
    assert [rule["rank"] for rule in rules] == [1, 2, 3, 4, 5]
    assert rules[0]["id"] == "rule-401k-match"
    assert rules[0]["accountId"] == "acct-401k"
    assert rules[1]["id"] == "rule-hsa"
    assert rules[2]["id"] == "rule-roth-ira"
    assert rules[3]["id"] == "rule-401k-remaining"
    assert rules[4]["id"] == "rule-taxable"

