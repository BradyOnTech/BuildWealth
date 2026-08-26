"""Versioned review policy for automatically applied connection observations."""

from __future__ import annotations

from typing import Any


CONNECTION_CHANGE_POLICY_VERSION = "2026-08-25.v1"
LARGE_QUANTITY_CHANGE_RATIO = 0.25
LARGE_ACCOUNT_VALUE_CHANGE_RATIO = 0.20
BALANCE_RECONCILIATION_RATIO = 0.02
BALANCE_RECONCILIATION_MINIMUM = 10.0


def evaluate_connection_changes(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if not previous:
        return {
            "policy_version": CONNECTION_CHANGE_POLICY_VERSION,
            "review_required": False,
            "holdings_added": 0,
            "holdings_removed": 0,
            "quantity_changes": 0,
            "large_quantity_changes": 0,
            "large_account_value_changes": 0,
            "accounts_removed": 0,
            "unmapped_securities": _unmapped_security_count(current),
            "balance_mismatches": _balance_mismatch_count(current),
        }

    previous_holdings = _holdings_by_key(previous)
    current_holdings = _holdings_by_key(current)
    added = set(current_holdings) - set(previous_holdings)
    removed = set(previous_holdings) - set(current_holdings)
    quantity_changes = 0
    large_quantity_changes = 0
    for key in set(previous_holdings).intersection(current_holdings):
        before = _number(previous_holdings[key].get("quantity"))
        after = _number(current_holdings[key].get("quantity"))
        if abs(after - before) <= 1e-9:
            continue
        quantity_changes += 1
        baseline = max(abs(before), 1e-9)
        if abs(after - before) / baseline >= LARGE_QUANTITY_CHANGE_RATIO:
            large_quantity_changes += 1

    previous_accounts = _accounts_by_id(previous)
    current_accounts = _accounts_by_id(current)
    accounts_removed = len(set(previous_accounts) - set(current_accounts))
    large_account_value_changes = 0
    for account_id in set(previous_accounts).intersection(current_accounts):
        before = _number(previous_accounts[account_id].get("current_balance"))
        after = _number(current_accounts[account_id].get("current_balance"))
        baseline = max(abs(before), 1e-9)
        if abs(after - before) / baseline >= LARGE_ACCOUNT_VALUE_CHANGE_RATIO:
            large_account_value_changes += 1

    unmapped = _unmapped_security_count(current)
    balance_mismatches = _balance_mismatch_count(current)
    review_required = any(
        (
            added,
            removed,
            large_quantity_changes,
            large_account_value_changes,
            accounts_removed,
            unmapped,
            balance_mismatches,
        )
    )
    return {
        "policy_version": CONNECTION_CHANGE_POLICY_VERSION,
        "review_required": review_required,
        "holdings_added": len(added),
        "holdings_removed": len(removed),
        "quantity_changes": quantity_changes,
        "large_quantity_changes": large_quantity_changes,
        "large_account_value_changes": large_account_value_changes,
        "accounts_removed": accounts_removed,
        "unmapped_securities": unmapped,
        "balance_mismatches": balance_mismatches,
    }


def _holdings_by_key(snapshot: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (
            str(row.get("provider_account_id") or ""),
            str(row.get("provider_security_id") or ""),
        ): row
        for row in snapshot.get("holdings", [])
        if isinstance(row, dict)
    }


def _accounts_by_id(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("provider_account_id") or ""): row
        for row in snapshot.get("accounts", [])
        if isinstance(row, dict) and row.get("provider_account_id")
    }


def _unmapped_security_count(snapshot: dict[str, Any]) -> int:
    return sum(
        1
        for row in snapshot.get("holdings", [])
        if isinstance(row, dict)
        and str(row.get("symbol_or_identifier") or "").startswith("PLAID:")
    )


def _balance_mismatch_count(snapshot: dict[str, Any]) -> int:
    holdings_by_account: dict[str, float] = {}
    evidence_accounts: set[str] = set()
    for row in snapshot.get("holdings", []):
        if not isinstance(row, dict):
            continue
        account_id = str(row.get("provider_account_id") or "")
        if row.get("institution_value") is not None:
            evidence_accounts.add(account_id)
        holdings_by_account[account_id] = holdings_by_account.get(account_id, 0.0) + _number(
            row.get("institution_value")
        )
    mismatches = 0
    for account in snapshot.get("accounts", []):
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("provider_account_id") or "")
        if account.get("cash_balance") is None and account_id not in evidence_accounts:
            continue
        balance = _number(account.get("current_balance"))
        evidence = holdings_by_account.get(account_id, 0.0)
        cash = _number(account.get("cash_balance"))
        difference = abs(balance - (evidence + cash))
        if difference >= BALANCE_RECONCILIATION_MINIMUM and difference / max(abs(balance), 1.0) >= BALANCE_RECONCILIATION_RATIO:
            mismatches += 1
    return mismatches


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
