"""Session Focus: conversation-scoped domain priorities for Copilot.

Distinct from Context Materiality and Candidate Prompt Influence.
PR3: storage, normalize, resolve, trace focus_applied (stored_only).
PR4+: merge_focus_with_intent shaping and retrieval boost.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from buildwealth_orchestrator.services.copilot_runtime import utc_now_iso

FOCUS_DOMAIN_CATALOG: frozenset[str] = frozenset(
    {
        "profile",
        "profile.goals",
        "profile.cashflow",
        "profile.debt",
        "profile.tax",
        "profile.policy",
        "portfolio",
        "portfolio.holdings",
        "plan",
        "recommendation",
        "research",
    }
)

FOCUS_MODES = frozenset({"narrow", "balanced", "wide"})
FOCUS_SET_BY = frozenset({"user", "entry_surface", "planner", "default"})

MAX_PRIMARY = 3
MAX_SECONDARY = 5
MAX_MUTED = 8
MAX_PINS = 12
MAX_PIN_LEN = 128
MAX_PRIORITY_NOTE = 280
SESSION_FOCUS_SCHEMA_VERSION = 1

PIN_PREFIX_TO_FOCUS_DOMAIN: dict[str, str] = {
    "recommendation": "recommendation",
    "goal": "profile.goals",
    "symbol": "research",
    "plan": "plan",
    "artifact": "plan",
    "holding": "portfolio.holdings",
    "candidate": "profile",
}

FOCUS_DOMAIN_TO_REGISTRY: dict[str, tuple[str, ...]] = {
    "profile": ("profile",),
    "profile.goals": ("profile",),
    "profile.cashflow": ("profile",),
    "profile.debt": ("profile",),
    "profile.tax": ("profile",),
    "profile.policy": ("profile",),
    "portfolio": ("portfolio",),
    "portfolio.holdings": ("portfolio",),
    "plan": ("plan",),
    "recommendation": ("recommendation",),
    "research": ("research",),
}


def default_session_focus() -> dict[str, Any]:
    return {
        "mode": "balanced",
        "primary_domains": [],
        "secondary_domains": [],
        "muted_domains": [],
        "pinned_entity_ids": [],
        "priority_note": "",
        "set_by": "default",
        "updated_at": None,
        "schema_version": SESSION_FOCUS_SCHEMA_VERSION,
    }


def covers_focus_domain(parent: str, child: str) -> bool:
    """True if parent focus domain covers child (exact or parent.prefix)."""
    p = str(parent or "").strip().lower()
    c = str(child or "").strip().lower()
    if not p or not c:
        return False
    if p == c:
        return True
    return c.startswith(f"{p}.")


def list_covers(domains: Sequence[str], target: str) -> bool:
    return any(covers_focus_domain(domain, target) for domain in domains)


def focus_domains_to_registry_domains(focus_domains: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for domain in focus_domains:
        for registry in FOCUS_DOMAIN_TO_REGISTRY.get(str(domain).strip().lower(), ()):
            if registry not in seen:
                seen.add(registry)
                out.append(registry)
    return out


def pin_prefix_to_focus_domain(pin_id: str) -> str | None:
    text = str(pin_id or "").strip()
    if ":" not in text:
        return None
    prefix = text.split(":", 1)[0].strip().lower()
    return PIN_PREFIX_TO_FOCUS_DOMAIN.get(prefix)


def lowered_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _dedupe_preserve(items: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = str(item or "").strip()
        if not key:
            continue
        domain = lowered_domain(key)
        if domain in FOCUS_DOMAIN_CATALOG:
            key = domain
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out


class SessionFocusValidationError(ValueError):
    """Raised when write-path focus validation fails (unknown domains, etc.)."""


def _normalize_domain_list(
    raw: object,
    *,
    max_items: int,
    strict: bool,
    dropped: list[str],
) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        if strict:
            raise SessionFocusValidationError("Domain lists must be arrays of strings.")
        return []
    values: list[str] = []
    for item in raw:
        text = lowered_domain(str(item))
        if not text:
            continue
        if text not in FOCUS_DOMAIN_CATALOG:
            if strict:
                raise SessionFocusValidationError(f"Unknown focus domain: {text}")
            dropped.append(text)
            continue
        values.append(text)
    return _dedupe_preserve(values)[: max(0, max_items)]


def _normalize_pins(raw: object, *, strict: bool) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        if strict:
            raise SessionFocusValidationError("pinned_entity_ids must be an array of strings.")
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > MAX_PIN_LEN:
            if strict:
                raise SessionFocusValidationError(
                    f"pinned_entity_id exceeds {MAX_PIN_LEN} characters."
                )
            text = text[:MAX_PIN_LEN]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= MAX_PINS:
            break
    return out


def _apply_user_list_conflicts(
    *,
    primary: list[str],
    secondary: list[str],
    muted: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """API write / request.focus path: user primary wins over mute."""
    primary_out = list(primary)
    muted_out = [
        domain
        for domain in muted
        if not any(
            covers_focus_domain(domain, p) or covers_focus_domain(p, domain)
            for p in primary_out
        )
    ]
    secondary_out: list[str] = []
    for domain in secondary:
        if list_covers(muted_out, domain) or any(
            covers_focus_domain(m, domain) or covers_focus_domain(domain, m) for m in muted_out
        ):
            continue
        if list_covers(primary_out, domain) or any(
            covers_focus_domain(p, domain) or covers_focus_domain(domain, p) for p in primary_out
        ):
            continue
        secondary_out.append(domain)
    return primary_out[:MAX_PRIMARY], secondary_out[:MAX_SECONDARY], muted_out[:MAX_MUTED]


def normalize_focus(
    raw: Mapping[str, Any] | None,
    *,
    strict: bool = False,
    set_by_override: str | None = None,
    touch_updated_at: bool = False,
) -> dict[str, Any]:
    """Normalize focus for read or write.

    strict=True: unknown domains raise SessionFocusValidationError (PATCH / request.focus).
    strict=False: drop unknown domains (legacy conversation JSON).
    """
    base = default_session_focus()
    if not isinstance(raw, Mapping):
        if touch_updated_at:
            base["updated_at"] = utc_now_iso()
        return base

    dropped: list[str] = []
    mode = str(raw.get("mode") or "balanced").strip().lower()
    if mode not in FOCUS_MODES:
        if strict:
            raise SessionFocusValidationError(f"Invalid focus mode: {mode}")
        mode = "balanced"

    primary = _normalize_domain_list(
        raw.get("primary_domains"), max_items=MAX_PRIMARY, strict=strict, dropped=dropped
    )
    secondary = _normalize_domain_list(
        raw.get("secondary_domains"), max_items=MAX_SECONDARY, strict=strict, dropped=dropped
    )
    muted = _normalize_domain_list(
        raw.get("muted_domains"), max_items=MAX_MUTED, strict=strict, dropped=dropped
    )
    pins = _normalize_pins(raw.get("pinned_entity_ids"), strict=strict)

    note = str(raw.get("priority_note") or "")
    if len(note) > MAX_PRIORITY_NOTE:
        if strict:
            raise SessionFocusValidationError(
                f"priority_note exceeds {MAX_PRIORITY_NOTE} characters."
            )
        note = note[:MAX_PRIORITY_NOTE]

    set_by = str(set_by_override or raw.get("set_by") or "default").strip().lower()
    if set_by not in FOCUS_SET_BY:
        if strict and set_by_override is not None:
            raise SessionFocusValidationError(f"Invalid set_by: {set_by}")
        set_by = "default"

    # User-specified lists on write path: primary wins over mute.
    primary, secondary, muted = _apply_user_list_conflicts(
        primary=primary, secondary=secondary, muted=muted
    )

    try:
        schema_version = int(raw.get("schema_version") or SESSION_FOCUS_SCHEMA_VERSION)
    except (TypeError, ValueError):
        schema_version = SESSION_FOCUS_SCHEMA_VERSION

    updated_at = raw.get("updated_at")
    if touch_updated_at or not updated_at:
        if touch_updated_at:
            updated_at = utc_now_iso()
        else:
            updated_at = str(updated_at) if updated_at else None

    result = {
        "mode": mode,
        "primary_domains": primary,
        "secondary_domains": secondary,
        "muted_domains": muted,
        "pinned_entity_ids": pins,
        "priority_note": note,
        "set_by": set_by,
        "updated_at": updated_at,
        "schema_version": schema_version,
    }
    if dropped:
        result["_dropped_domains"] = dropped
    return result


def merge_focus_patch(
    stored: Mapping[str, Any] | None,
    patch: Mapping[str, Any] | None,
    *,
    set_by: str = "user",
) -> dict[str, Any]:
    """Merge PATCH body onto stored focus. Omitted fields unchanged."""
    current = normalize_focus(stored, strict=False)
    if not isinstance(patch, Mapping):
        return normalize_focus(current, strict=True, set_by_override=set_by, touch_updated_at=True)

    merged = deepcopy(current)
    for key in (
        "mode",
        "primary_domains",
        "secondary_domains",
        "muted_domains",
        "pinned_entity_ids",
        "priority_note",
    ):
        if key in patch and patch[key] is not None:
            merged[key] = patch[key]
    return normalize_focus(merged, strict=True, set_by_override=set_by, touch_updated_at=True)


def focus_equal(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> bool:
    """Compare durable focus fields (ignore updated_at and private keys)."""
    a = normalize_focus(left, strict=False)
    b = normalize_focus(right, strict=False)
    keys = (
        "mode",
        "primary_domains",
        "secondary_domains",
        "muted_domains",
        "pinned_entity_ids",
        "priority_note",
        "set_by",
        "schema_version",
    )
    return all(a.get(key) == b.get(key) for key in keys)


def resolve_turn_focus(
    *,
    stored: Mapping[str, Any] | None,
    request_focus: Mapping[str, Any] | None = None,
    nl_patch: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve focus for one chat turn.

    Precedence:
    1. request.focus (UI chips) — full authority
    2. nl_patch (PR6; no-op until implemented)
    3. stored conversation focus
    """
    if isinstance(request_focus, Mapping) and request_focus:
        set_by = str(request_focus.get("set_by") or "user").strip().lower()
        if set_by not in FOCUS_SET_BY or set_by == "default":
            set_by = "user"
        return normalize_focus(
            request_focus,
            strict=True,
            set_by_override=set_by,
            touch_updated_at=True,
        )

    if isinstance(nl_patch, Mapping) and nl_patch:
        base = normalize_focus(stored, strict=False)
        return merge_focus_patch(base, nl_patch, set_by="user")

    return normalize_focus(stored, strict=False)


def focus_applied_stored_only(focus: Mapping[str, Any] | None) -> dict[str, Any]:
    """PR3 trace: focus is stored/resolved but does not shape brief/retrieval yet."""
    normalized = normalize_focus(focus, strict=False)
    return {
        "effect": "stored_only",
        "mode": normalized.get("mode"),
        "primary_domains": list(normalized.get("primary_domains") or []),
        "secondary_domains": list(normalized.get("secondary_domains") or []),
        "muted_domains": list(normalized.get("muted_domains") or []),
        "pinned_entity_ids": list(normalized.get("pinned_entity_ids") or []),
        "priority_note": normalized.get("priority_note") or "",
        "set_by": normalized.get("set_by") or "default",
        "schema_version": normalized.get("schema_version") or SESSION_FOCUS_SCHEMA_VERSION,
    }


def public_focus(focus: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop private keys before API responses."""
    normalized = normalize_focus(focus, strict=False)
    normalized.pop("_dropped_domains", None)
    return normalized
