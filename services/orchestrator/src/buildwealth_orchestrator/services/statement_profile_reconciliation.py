"""Reconcile statement-derived expenses against the canonical profile.

Statement rows describe cash movement, while Profile debt and expense rows
describe recurring obligations.  Treating both as independent expenses can
double-count the same payment.  This module keeps the decision deterministic:

* exact profile expense duplicates and clear debt-payment matches are held out;
* plausible but uncertain matches become a clarification candidate;
* only suggestions with no credible existing match are safe to add.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from buildwealth_orchestrator.services.profile_mutation import (
    apply_reviewed_profile_patch,
    normalize_monthly_item,
    numeric_or_none,
    profile_item_dedupe_key,
)

CLARIFICATION_KIND = "statement_payment_conflict"
RESOLUTION_OPTIONS = {"same_as_existing", "separate_expense", "ignore"}

_GENERIC_TOKENS = {
    "ach",
    "automatic",
    "autopay",
    "bank",
    "bill",
    "debit",
    "debt",
    "financial",
    "loan",
    "monthly",
    "online",
    "pay",
    "payment",
    "payments",
    "pmt",
    "pymt",
    "recurring",
    "the",
}
_NON_SPENDING_PATTERNS = (
    r"\bpayment\s+thank\s+you\b",
    r"\bcardmember\s+payment\b",
    r"\bcredit\s+card\s+payment\b",
    r"\bpayment\s+received\b",
    r"\bautopay\s+pymt\b",
    r"\binternal\s+transfer\b",
    r"\btransfer\s+(?:to|from)\b",
)
_DEBT_KIND_TERMS: dict[str, set[str]] = {
    "mortgage": {"home", "house", "mortgage"},
    "auto": {"auto", "car", "truck", "vehicle"},
    "auto_loan": {"auto", "car", "truck", "vehicle"},
    "vehicle": {"auto", "boat", "car", "rv", "trailer", "truck", "utv", "vehicle"},
    "recreational_vehicle_loan": {
        "boat",
        "motorcycle",
        "rv",
        "trailer",
        "utv",
        "vehicle",
    },
    "student": {"college", "education", "student", "university"},
    "student_loan": {"college", "education", "student", "university"},
    "credit_card": {"amex", "card", "discover", "mastercard", "visa"},
    "personal": {"personal"},
    "personal_loan": {"personal"},
    "heloc": {"heloc", "home"},
    "business": {"business"},
}


def reconcile_statement_expenses(
    profile: Mapping[str, Any],
    expenses: list[Any] | None,
) -> dict[str, Any]:
    """Classify statement suggestions without mutating Profile."""
    current_expenses = [
        item for item in (profile.get("expense_items") or []) if isinstance(item, Mapping)
    ]
    debts = [item for item in (profile.get("debt_items") or []) if isinstance(item, Mapping)]
    assets = {
        str(item.get("id") or ""): item
        for item in (profile.get("physical_assets") or [])
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    }
    exact_expenses = {profile_item_dedupe_key(item): item for item in current_expenses}

    safe: list[dict[str, Any]] = []
    already_counted: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    invalid_count = 0

    for raw in expenses or []:
        if not isinstance(raw, Mapping):
            invalid_count += 1
            continue
        item = normalize_monthly_item(raw, section="expense_items")
        if item is None:
            invalid_count += 1
            continue
        # Retain review evidence used by the matcher and later clarification.
        for key in ("sample_descriptions", "transaction_count"):
            if raw.get(key) is not None:
                item[key] = raw.get(key)

        if _is_non_spending_transfer(item):
            already_counted.append(
                _automatic_match(item, kind="statement_transfer", match=None)
            )
            continue

        exact = exact_expenses.get(profile_item_dedupe_key(item))
        if exact is not None:
            already_counted.append(
                _automatic_match(item, kind="expense", match=exact)
            )
            continue

        debt_matches = _debt_matches(item, debts, assets)
        expense_matches = _expense_matches(item, current_expenses)
        credible_matches = [*debt_matches, *expense_matches]
        exact_amount_debts = [match for match in debt_matches if match["amount_match"] == "exact"]
        clear_debt_matches = [
            match
            for match in exact_amount_debts
            if match["semantic_match"] and match["kind"] == "debt"
        ]

        # Auto-hold only when one debt is the sole exact payment candidate and
        # the merchant/asset/debt language points to it.
        if len(exact_amount_debts) == 1 and len(clear_debt_matches) == 1:
            already_counted.append(
                _automatic_match(item, kind="debt", match=clear_debt_matches[0])
            )
            continue

        if credible_matches:
            conflicts.append(_build_conflict(item, credible_matches))
            continue
        safe.append(item)

    return {
        "safe_expenses": safe,
        "already_counted": already_counted,
        "conflicts": conflicts,
        "invalid_count": invalid_count,
    }


def draft_statement_conflict_candidate(
    context_service: Any,
    conflict: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one unresolved payment question for Copilot and Inbox."""
    fingerprint = str(conflict.get("fingerprint") or "").strip()
    suggestion = conflict.get("suggestion")
    suggestion = dict(suggestion) if isinstance(suggestion, Mapping) else {}
    return context_service.draft_context_candidate(
        source_domain="statement_import",
        source_ref=f"statement_import/payment_conflict/{fingerprint}",
        extracted_claim=str(conflict.get("question") or ""),
        # The owning question lives in Copilot. The affected profile expense is
        # carried in metadata/target_value but remains suppressed until the
        # dedicated resolution endpoint records the user's answer.
        target_domain="conversation",
        target_area="statement_payment_reconciliation",
        target_field=CLARIFICATION_KIND,
        target_value={"expense_items": [suggestion]},
        confidence="medium",
        prompt_influence="suppressed",
        dedupe_key=f"{CLARIFICATION_KIND}:{fingerprint}",
        metadata={
            "clarification_kind": CLARIFICATION_KIND,
            "question": str(conflict.get("question") or ""),
            "statement_suggestion": suggestion,
            "profile_matches": list(conflict.get("matches") or []),
            "resolution_options": [
                "same_as_existing",
                "separate_expense",
                "ignore",
            ],
            "resolution_state": "needs_user_answer",
        },
    )


def resolve_statement_payment_conflict(
    *,
    candidate: Mapping[str, Any],
    resolution: str,
    profile_store: Any,
    context_service: Any,
) -> dict[str, Any]:
    """Resolve one held suggestion, compensating if lifecycle finalization fails."""
    choice = str(resolution or "").strip().lower()
    if choice not in RESOLUTION_OPTIONS:
        raise ValueError(f"Unsupported statement conflict resolution: {choice or 'blank'}")
    metadata = candidate.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    if str(metadata.get("clarification_kind") or "") != CLARIFICATION_KIND:
        raise ValueError("This context candidate is not a statement payment conflict")
    state = str(candidate.get("lifecycle_state") or "")
    if state not in {"pending_review", "deferred"}:
        raise ValueError(f"This statement payment conflict is already {state or 'resolved'}")

    suggestion = metadata.get("statement_suggestion")
    suggestion = dict(suggestion) if isinstance(suggestion, Mapping) else {}
    profile_before = profile_store.get()
    apply_result: dict[str, Any] = {
        "applied_sections": [],
        "counts": {},
        "skipped_duplicates": 0,
    }
    lifecycle_state = "rejected" if choice == "ignore" else "applied"

    if choice == "separate_expense":
        apply_result = apply_reviewed_profile_patch(
            {"expense_items": [suggestion]},
            profile_store,
            metadata_source="statement_conflict_resolution",
        )

    try:
        updated = context_service.update_context_candidate_lifecycle(
            str(candidate.get("id") or ""),
            lifecycle_state=lifecycle_state,
            prompt_influence="suppressed",
            metadata_patch={
                "resolution_state": "resolved",
                "resolution": choice,
                "profile_mutated": bool(apply_result.get("applied_sections")),
                "applied_sections": list(apply_result.get("applied_sections") or []),
            },
        )
    except Exception:
        if choice == "separate_expense":
            profile_store.replace(profile_before)
        context_service.restore_context_candidate_lifecycle(candidate)
        raise

    return {
        "candidate": updated,
        "resolution": choice,
        "added_expenses": int((apply_result.get("counts") or {}).get("expense_items") or 0),
        "skipped_duplicates": int(apply_result.get("skipped_duplicates") or 0),
        "profile_changed": bool(apply_result.get("applied_sections")),
    }


def _automatic_match(
    suggestion: Mapping[str, Any],
    *,
    kind: str,
    match: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "suggestion": dict(suggestion),
        "match_kind": kind,
        "match_id": str((match or {}).get("id") or "") or None,
        "match_label": str((match or {}).get("label") or "") or None,
        "reason": (
            "This is a statement payment or transfer, not new spending."
            if kind == "statement_transfer"
            else "This payment is already represented in Profile."
        ),
    }


def _debt_matches(
    suggestion: Mapping[str, Any],
    debts: list[Mapping[str, Any]],
    assets: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    amount = numeric_or_none(suggestion.get("monthly_amount_usd"))
    if amount is None:
        return []
    source_text = _suggestion_text(suggestion)
    source_tokens = _tokens(source_text)
    matches: list[dict[str, Any]] = []
    for debt in debts:
        payment = numeric_or_none(debt.get("minimum_payment_usd"))
        if payment is None or payment <= 0:
            continue
        amount_match = _amount_match(amount, payment)
        if amount_match is None:
            continue
        linked_asset = assets.get(str(debt.get("linked_asset_id") or ""))
        match_text = " ".join(
            value
            for value in (
                str(debt.get("label") or ""),
                str(debt.get("debt_type") or ""),
                str((linked_asset or {}).get("label") or ""),
                str(
                    (linked_asset or {}).get("asset_subtype")
                    or (linked_asset or {}).get("subtype")
                    or ""
                ),
            )
            if value
        )
        semantic = bool(source_tokens & _tokens(match_text)) or _debt_kind_matches(
            source_text,
            debt,
            linked_asset,
        )
        matches.append(
            {
                "kind": "debt",
                "id": str(debt.get("id") or "") or None,
                "label": str(debt.get("label") or "Debt payment"),
                "monthly_amount_usd": round(payment, 2),
                "amount_match": amount_match,
                "semantic_match": semantic,
                "linked_asset_id": str(debt.get("linked_asset_id") or "") or None,
            }
        )
    return sorted(
        matches,
        key=lambda row: (
            row["amount_match"] != "exact",
            not row["semantic_match"],
            str(row["label"]),
        ),
    )


def _expense_matches(
    suggestion: Mapping[str, Any],
    current: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    amount = numeric_or_none(suggestion.get("monthly_amount_usd"))
    if amount is None:
        return []
    source_tokens = _tokens(_suggestion_text(suggestion))
    matches: list[dict[str, Any]] = []
    for expense in current:
        existing_amount = numeric_or_none(expense.get("monthly_amount_usd"))
        if existing_amount is None:
            continue
        amount_match = _amount_match(amount, existing_amount)
        if amount_match is None:
            continue
        semantic = bool(source_tokens & _tokens(str(expense.get("label") or "")))
        if not semantic and amount_match != "exact":
            continue
        matches.append(
            {
                "kind": "expense",
                "id": str(expense.get("id") or "") or None,
                "label": str(expense.get("label") or "Existing expense"),
                "monthly_amount_usd": round(existing_amount, 2),
                "amount_match": amount_match,
                "semantic_match": semantic,
                "linked_debt_id": str(expense.get("linked_debt_id") or "") or None,
                "linked_asset_id": str(expense.get("linked_asset_id") or "") or None,
            }
        )
    return matches


def _build_conflict(
    suggestion: Mapping[str, Any],
    matches: list[Mapping[str, Any]],
) -> dict[str, Any]:
    label = str(suggestion.get("label") or "This statement payment")
    amount = float(numeric_or_none(suggestion.get("monthly_amount_usd")) or 0.0)
    match_labels = [str(match.get("label") or "an existing Profile item") for match in matches[:3]]
    if len(match_labels) == 1:
        target = f'"{match_labels[0]}"'
    else:
        target = ", ".join(f'"{value}"' for value in match_labels)
    question = (
        f'Is "{label}" at ${amount:,.2f} per month the same payment as {target} '
        "already in your Profile, or is it a separate expense?"
    )
    fingerprint_payload = {
        "suggestion": {
            "label": label.lower(),
            "monthly_amount_usd": round(amount, 2),
        },
        "matches": [
            {
                "kind": match.get("kind"),
                "id": match.get("id"),
                "label": str(match.get("label") or "").lower(),
                "monthly_amount_usd": match.get("monthly_amount_usd"),
            }
            for match in matches
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "fingerprint": fingerprint,
        "suggestion": dict(suggestion),
        "matches": [dict(match) for match in matches],
        "question": question,
    }


def _suggestion_text(suggestion: Mapping[str, Any]) -> str:
    samples = suggestion.get("sample_descriptions")
    sample_text = " ".join(str(value) for value in samples) if isinstance(samples, list) else ""
    return f"{suggestion.get('label') or ''} {sample_text}".strip().lower()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 2 and token not in _GENERIC_TOKENS
    }


def _amount_match(left: float, right: float) -> str | None:
    difference = abs(left - right)
    exact_tolerance = max(1.0, max(abs(left), abs(right)) * 0.01)
    if difference <= exact_tolerance:
        return "exact"
    near_tolerance = max(25.0, max(abs(left), abs(right)) * 0.05)
    return "near" if difference <= near_tolerance else None


def _debt_kind_matches(
    source_text: str,
    debt: Mapping[str, Any],
    linked_asset: Mapping[str, Any] | None,
) -> bool:
    debt_type = str(debt.get("debt_type") or "").strip().lower()
    asset_subtype = str(
        (linked_asset or {}).get("asset_subtype")
        or (linked_asset or {}).get("subtype")
        or ""
    ).strip().lower()
    terms = set(_DEBT_KIND_TERMS.get(debt_type, set()))
    terms.update(_DEBT_KIND_TERMS.get(asset_subtype, set()))
    source_tokens = set(re.findall(r"[a-z0-9]+", source_text.lower()))
    return bool(terms & source_tokens)


def _is_non_spending_transfer(suggestion: Mapping[str, Any]) -> bool:
    text = _suggestion_text(suggestion)
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _NON_SPENDING_PATTERNS)


__all__ = [
    "CLARIFICATION_KIND",
    "RESOLUTION_OPTIONS",
    "draft_statement_conflict_candidate",
    "reconcile_statement_expenses",
    "resolve_statement_payment_conflict",
]
