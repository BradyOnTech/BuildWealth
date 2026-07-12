"""Apply bridge for document-vision suggestions.

Takes the (possibly user-edited) suggestions patch produced by
profile_document_vision and merges it into the financial profile. Only known
sections and fields are honored; list sections append to the current list
with the same label+amount dedupe as the context-candidate bridge; the store
save is a single call carrying document-vision metadata.
"""

from __future__ import annotations

from typing import Any, Mapping

from buildwealth_orchestrator.services.profile_candidate_apply import (
    _item_dedupe_key,
    _normalize_item,
    _numeric_or_none,
)

APPLY_METADATA_SOURCE = "profile_document_vision"

FILING_STATUSES = {"single", "married_filing_jointly", "married_filing_separately", "head_of_household"}
TAX_RATE_FIELDS = ("marginal_tax_rate", "effective_tax_rate", "state_tax_rate")


def apply_document_suggestions(patch: Mapping[str, Any] | None, profile_store: Any) -> dict[str, Any]:
    """Merge a reviewed suggestions patch into the profile.

    Returns {"applied_sections": [...], "counts": {...}, "skipped_duplicates": n}.
    """
    patch = patch if isinstance(patch, Mapping) else {}
    profile = profile_store.get()
    updates: dict[str, Any] = {}
    applied_sections: list[str] = []
    counts: dict[str, int] = {}
    skipped = 0

    for section in ("income_items", "expense_items"):
        incoming = patch.get(section)
        if not isinstance(incoming, list):
            continue
        current = [item for item in (profile.get(section) or []) if isinstance(item, Mapping)]
        seen = {_item_dedupe_key(item) for item in current}
        added: list[dict[str, Any]] = []
        for raw_item in incoming:
            if not isinstance(raw_item, Mapping):
                continue
            item = _normalize_item(raw_item, section=section)
            if item is None:
                continue
            key = _item_dedupe_key(item)
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
        seen_debt = {_debt_dedupe_key(item) for item in current}
        added_debts: list[dict[str, Any]] = []
        for raw_item in incoming_debts:
            if not isinstance(raw_item, Mapping):
                continue
            item = _normalize_debt_item(raw_item)
            if item is None:
                continue
            key = _debt_dedupe_key(item)
            if key in seen_debt:
                skipped += 1
                continue
            seen_debt.add(key)
            added_debts.append(item)
        if added_debts:
            updates["debt_items"] = [dict(item) for item in current] + added_debts
            applied_sections.append("debt_items")
            counts["debt_items"] = len(added_debts)

    tax_patch = patch.get("tax_profile")
    if isinstance(tax_patch, Mapping):
        cleaned = _normalize_tax_profile(tax_patch)
        if cleaned:
            current_tax = profile.get("tax_profile")
            merged = dict(current_tax) if isinstance(current_tax, Mapping) else {}
            merged.update(cleaned)
            updates["tax_profile"] = merged
            applied_sections.append("tax_profile")
            counts["tax_profile"] = len(cleaned)

    if updates:
        profile_store.save(
            updates,
            metadata_source=APPLY_METADATA_SOURCE,
            metadata_status="user_confirmed",
        )
    return {
        "applied_sections": applied_sections,
        "counts": counts,
        "skipped_duplicates": skipped,
    }


def _normalize_debt_item(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    label = str(raw.get("label") or "").strip()
    balance = _numeric_or_none(raw.get("balance_usd"))
    if not label or balance is None:
        return None
    item: dict[str, Any] = {"label": label, "balance_usd": round(balance, 2)}
    rate = _numeric_or_none(raw.get("interest_rate"))
    if rate is not None:
        # Rates are stored as fractions in 0..1; a value > 1 reads as a percent.
        item["interest_rate"] = round(rate / 100.0 if rate > 1 else rate, 6)
    minimum = _numeric_or_none(raw.get("minimum_payment_usd"))
    if minimum is not None:
        item["minimum_payment_usd"] = round(minimum, 2)
    return item


def _debt_dedupe_key(item: Mapping[str, Any]) -> tuple[str, float | None]:
    label = str(item.get("label") or "").strip().lower()
    balance = _numeric_or_none(item.get("balance_usd"))
    return (label, round(balance, 2) if balance is not None else None)


def _normalize_tax_profile(raw: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    filing = str(raw.get("filing_status") or "").strip().lower()
    if filing in FILING_STATUSES:
        cleaned["filing_status"] = filing
    state = str(raw.get("state") or "").strip()
    if state:
        cleaned["state"] = state
    for key in TAX_RATE_FIELDS:
        value = _numeric_or_none(raw.get(key))
        if value is None:
            continue
        if value > 1:
            value = value / 100.0
        if 0 <= value <= 1:
            cleaned[key] = round(value, 4)
    return cleaned
