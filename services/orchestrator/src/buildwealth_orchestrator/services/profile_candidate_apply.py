"""Bridge from confirmed context candidates into the financial profile.

The inbox "Apply to Profile" action calls apply_candidate_to_profile with a
context candidate payload (see context_intelligence.build_context_candidate_payload)
and the workspace FinancialProfileStore. The store's save() is a shallow
top-level merge, so list sections are always written as the complete new list
and dict sections are merged here before saving.
"""

from __future__ import annotations

from typing import Any, Mapping

from buildwealth_orchestrator.services.profile_mutation import (
    normalize_monthly_item as _normalize_item,
    numeric_or_none as _numeric_or_none,
    profile_item_dedupe_key as _item_dedupe_key,
)

APPLY_METADATA_SOURCE = "context_candidate_apply"

# Rates stored as fractions in 0..1 — a numeric value > 1 is treated as a
# percentage and divided by 100. Exposure percentages (…_pct) stay as-is.
FRACTION_RATE_FIELDS = {
    "tax_profile.marginal_tax_rate",
    "tax_profile.effective_tax_rate",
    "tax_profile.state_tax_rate",
}

ITEM_PATCH_KINDS = ("income_items", "expense_items")

def apply_candidate_to_profile(
    candidate: Mapping[str, Any],
    profile_store: Any,
) -> dict[str, Any]:
    """Write a context candidate's target_value into the financial profile.

    Returns {"applied": bool, ...}. Unsupported targets return
    {"applied": False, "reason": ...} without touching the profile.
    """
    metadata = candidate.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    patch_kind = str(metadata.get("profile_patch_kind") or "").strip().lower()
    target_field = str(candidate.get("target_field") or "").strip()

    if patch_kind in ITEM_PATCH_KINDS or target_field in ITEM_PATCH_KINDS:
        section = patch_kind if patch_kind in ITEM_PATCH_KINDS else target_field
        return _apply_profile_items(candidate, profile_store, section=section)

    if target_field.startswith(("tax_profile.", "investment_policy.")):
        return _apply_scalar_field(candidate, profile_store, target_field)

    return {
        "applied": False,
        "reason": (
            "This capture does not target a profile section the apply bridge "
            f"supports (target: {target_field or patch_kind or 'unknown'})."
        ),
    }


def _apply_profile_items(
    candidate: Mapping[str, Any],
    profile_store: Any,
    *,
    section: str,
) -> dict[str, Any]:
    incoming = _candidate_items(candidate.get("target_value"), section=section)
    if not incoming:
        return {
            "applied": False,
            "reason": f"The capture has no {section.replace('_', ' ')} to add.",
        }

    profile = profile_store.get()
    current = [item for item in (profile.get(section) or []) if isinstance(item, Mapping)]
    seen = {_item_dedupe_key(item) for item in current}

    added: list[dict[str, Any]] = []
    skipped = 0
    for raw_item in incoming:
        item = _normalize_item(raw_item, section=section)
        if item is None:
            continue
        key = _item_dedupe_key(item)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        added.append(item)

    label = section.replace("_", " ")
    if not added:
        return {
            "applied": True,
            "sections": [],
            "added": 0,
            "skipped_duplicates": skipped,
            "detail": f"All {label} from this capture were already in the profile; nothing was added.",
        }

    full_list = [dict(item) for item in current] + added
    profile_store.save(
        {section: full_list},
        metadata_source=APPLY_METADATA_SOURCE,
        metadata_status="user_confirmed",
    )
    names = ", ".join(str(item.get("label") or "item") for item in added)
    duplicate_note = f" ({skipped} duplicate{'s' if skipped != 1 else ''} skipped)" if skipped else ""
    return {
        "applied": True,
        "sections": [section],
        "added": len(added),
        "skipped_duplicates": skipped,
        "detail": f"Added {len(added)} {label.rstrip('s')} item{'s' if len(added) != 1 else ''} to the profile: {names}{duplicate_note}.",
    }


def _apply_scalar_field(
    candidate: Mapping[str, Any],
    profile_store: Any,
    target_field: str,
) -> dict[str, Any]:
    section, _, field_name = target_field.partition(".")
    if not field_name:
        return {"applied": False, "reason": f"Malformed profile field path: {target_field}"}

    value = _coerce_scalar_value(candidate.get("target_value"), field_path=target_field)
    if value is None or (isinstance(value, str) and not value):
        return {
            "applied": False,
            "reason": f"The capture has no usable value for {target_field}.",
        }

    profile = profile_store.get()
    section_payload = profile.get(section)
    merged_section = dict(section_payload) if isinstance(section_payload, Mapping) else {}
    merged_section[field_name] = value
    profile_store.save(
        {section: merged_section},
        metadata_source=APPLY_METADATA_SOURCE,
        metadata_status="user_confirmed",
    )
    return {
        "applied": True,
        "sections": [section],
        "detail": f"Set {_human_field(target_field)} to {_format_value(target_field, value)}.",
    }


def _candidate_items(target_value: Any, *, section: str) -> list[Mapping[str, Any]]:
    if isinstance(target_value, Mapping):
        raw = target_value.get(section)
    elif isinstance(target_value, list):
        raw = target_value
    else:
        raw = None
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _coerce_scalar_value(value: Any, *, field_path: str) -> Any:
    if isinstance(value, Mapping):
        if "value" in value:
            value = value["value"]
        else:
            return None
    if isinstance(value, bool):
        return value
    numeric: float | None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        numeric = _numeric_or_none(text)
        if numeric is None:
            return text
    else:
        return value
    if field_path in FRACTION_RATE_FIELDS and numeric > 1:
        numeric = numeric / 100.0
    return numeric


def _human_field(field_path: str) -> str:
    return field_path.replace(".", " ").replace("_", " ").strip()


def _format_value(field_path: str, value: Any) -> str:
    if isinstance(value, float) and field_path in FRACTION_RATE_FIELDS:
        return f"{value * 100:.4g}%"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
