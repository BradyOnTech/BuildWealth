"""One mutation seam for reviewed financial-profile changes.

All assisted onboarding sources (context candidates, document vision, and
statement imports) pass through the normalization and de-duplication helpers
in this module.  Cross-store context-candidate applies also use the
compensating transaction below so Profile and review lifecycle state cannot
silently diverge.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping

FILING_STATUSES = {
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
}
TAX_RATE_FIELDS = ("marginal_tax_rate", "effective_tax_rate", "state_tax_rate")

_INCOME_ITEM_DEFAULTS = {"source_type": "other", "is_pre_tax": False}
_EXPENSE_ITEM_DEFAULTS = {"category": "general", "is_fixed": True}


def numeric_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", "").replace("$", "").rstrip("%").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_monthly_item(raw: Mapping[str, Any], *, section: str) -> dict[str, Any] | None:
    label = str(raw.get("label") or "").strip()
    amount = numeric_or_none(raw.get("monthly_amount_usd"))
    if not label or amount is None:
        return None
    item: dict[str, Any] = {"label": label, "monthly_amount_usd": round(amount, 2)}
    item_id = str(raw.get("id") or "").strip()
    if item_id:
        item["id"] = item_id
    defaults = _INCOME_ITEM_DEFAULTS if section == "income_items" else _EXPENSE_ITEM_DEFAULTS
    for key, fallback in defaults.items():
        value = raw.get(key)
        item[key] = fallback if value is None else value
    return item


def profile_item_dedupe_key(item: Mapping[str, Any]) -> tuple[str, float | None]:
    label = str(item.get("label") or "").strip().lower()
    amount = numeric_or_none(item.get("monthly_amount_usd"))
    return (label, round(amount, 2) if amount is not None else None)


def normalize_debt_item(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    label = str(raw.get("label") or "").strip()
    balance = numeric_or_none(raw.get("balance_usd"))
    if not label or balance is None:
        return None
    item: dict[str, Any] = {"label": label, "balance_usd": round(balance, 2)}
    item_id = str(raw.get("id") or "").strip()
    if item_id:
        item["id"] = item_id
    rate = numeric_or_none(raw.get("interest_rate"))
    if rate is not None:
        item["interest_rate"] = round(rate / 100.0 if rate > 1 else rate, 6)
    minimum = numeric_or_none(raw.get("minimum_payment_usd"))
    if minimum is not None:
        item["minimum_payment_usd"] = round(minimum, 2)
    return item


def debt_dedupe_key(item: Mapping[str, Any]) -> tuple[str, float | None]:
    label = str(item.get("label") or "").strip().lower()
    balance = numeric_or_none(item.get("balance_usd"))
    return (label, round(balance, 2) if balance is not None else None)


def normalize_tax_profile(raw: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    filing = str(raw.get("filing_status") or "").strip().lower()
    if filing in FILING_STATUSES:
        cleaned["filing_status"] = filing
    state = str(raw.get("state") or "").strip()
    if state:
        cleaned["state"] = state
    for key in TAX_RATE_FIELDS:
        value = numeric_or_none(raw.get(key))
        if value is None:
            continue
        if value > 1:
            value /= 100.0
        if 0 <= value <= 1:
            cleaned[key] = round(value, 4)
    return cleaned


def merge_reviewed_profile_patch(
    profile: Mapping[str, Any],
    patch: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build one normalized, de-duplicated patch without writing it."""
    patch = patch if isinstance(patch, Mapping) else {}
    updates: dict[str, Any] = {}
    applied_sections: list[str] = []
    counts: dict[str, int] = {}
    skipped = 0

    for section in ("income_items", "expense_items"):
        incoming = patch.get(section)
        if not isinstance(incoming, list):
            continue
        current = [item for item in (profile.get(section) or []) if isinstance(item, Mapping)]
        seen = {profile_item_dedupe_key(item) for item in current}
        added: list[dict[str, Any]] = []
        for raw_item in incoming:
            if not isinstance(raw_item, Mapping):
                continue
            item = normalize_monthly_item(raw_item, section=section)
            if item is None:
                continue
            key = profile_item_dedupe_key(item)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            added.append(item)
        if added:
            updates[section] = [dict(item) for item in current] + added
            applied_sections.append(section)
            counts[section] = len(added)

    incoming_debts = patch.get("debt_items")
    if isinstance(incoming_debts, list):
        current = [item for item in (profile.get("debt_items") or []) if isinstance(item, Mapping)]
        seen = {debt_dedupe_key(item) for item in current}
        added: list[dict[str, Any]] = []
        for raw_item in incoming_debts:
            if not isinstance(raw_item, Mapping):
                continue
            item = normalize_debt_item(raw_item)
            if item is None:
                continue
            key = debt_dedupe_key(item)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            added.append(item)
        if added:
            updates["debt_items"] = [dict(item) for item in current] + added
            applied_sections.append("debt_items")
            counts["debt_items"] = len(added)

    tax_patch = patch.get("tax_profile")
    if isinstance(tax_patch, Mapping):
        cleaned = normalize_tax_profile(tax_patch)
        if cleaned:
            current_tax = profile.get("tax_profile")
            merged_tax = dict(current_tax) if isinstance(current_tax, Mapping) else {}
            merged_tax.update(cleaned)
            updates["tax_profile"] = merged_tax
            applied_sections.append("tax_profile")
            counts["tax_profile"] = len(cleaned)

    return {
        "updates": updates,
        "applied_sections": applied_sections,
        "counts": counts,
        "skipped_duplicates": skipped,
    }


def apply_reviewed_profile_patch(
    patch: Mapping[str, Any] | None,
    profile_store: Any,
    *,
    metadata_source: str,
) -> dict[str, Any]:
    merged = merge_reviewed_profile_patch(profile_store.get(), patch)
    updates = merged.pop("updates")
    if updates:
        profile_store.save(
            updates,
            metadata_source=metadata_source,
            metadata_status="user_confirmed",
        )
    return merged


def apply_candidate_profile_mutation(
    *,
    candidate: Mapping[str, Any],
    profile_store: Any,
    context_service: Any,
    apply_profile: Callable[[Mapping[str, Any], Any], dict[str, Any]],
) -> dict[str, Any]:
    """Apply one candidate and finalize its lifecycle as a single unit.

    The backing stores are heterogeneous (JSON plus SQLite), so this uses
    deterministic compensation rather than pretending there is a distributed
    transaction.  Both snapshots are restored if finalization fails.
    """
    profile_before = profile_store.get()
    candidate_before = dict(candidate)
    apply_result = apply_profile(candidate, profile_store)
    if not apply_result.get("applied"):
        return {"candidate": candidate_before, "apply_result": apply_result}

    try:
        updated = context_service.update_context_candidate_lifecycle(
            str(candidate_before.get("id") or ""),
            lifecycle_state="applied",
            prompt_influence="authoritative",
            metadata_patch={
                "review_action": "applied_to_profile",
                "resolution_state": "resolved_by_apply",
                "applied_sections": list(apply_result.get("sections") or []),
            },
        )
    except Exception:
        profile_store.replace(profile_before)
        context_service.restore_context_candidate_lifecycle(candidate_before)
        raise
    return {"candidate": updated, "apply_result": apply_result}
