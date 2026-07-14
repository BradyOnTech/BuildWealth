"""Session Focus: conversation-scoped domain priorities for Copilot.

Distinct from Context Materiality and Candidate Prompt Influence.
PR3: storage, normalize, resolve, trace focus_applied (stored_only).
PR4+: merge_focus_with_intent shaping and retrieval boost.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from buildwealth_orchestrator.services.copilot_runtime import utc_now_iso
from buildwealth_orchestrator.services.action_readiness import action_readiness_for_materiality

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


def covers_focus_domain(holder: str, candidate: str) -> bool:
    """True if holder already covers candidate for list-dedup purposes.

    Parent covers children and children cover bare parent (profile.goals covers profile)
    so intent top-level domains can be treated as redundant with focused children.
    """
    h = str(holder or "").strip().lower()
    c = str(candidate or "").strip().lower()
    if not h or not c:
        return False
    if h == c:
        return True
    if c.startswith(f"{h}."):
        return True
    if h.startswith(f"{c}."):
        return True
    return False


def list_covers(domains: Sequence[str], target: str) -> bool:
    return any(covers_focus_domain(domain, target) for domain in domains)


def is_domain_muted(muted: Sequence[str], domain: str) -> bool:
    """Mute is one-directional for expansion: muting profile mutes profile.*; muting profile.tax does not mute profile.goals."""
    d = lowered_domain(domain)
    for m in muted:
        m_norm = lowered_domain(m)
        if not m_norm:
            continue
        if m_norm == d or d.startswith(f"{m_norm}."):
            return True
    return False


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
        if is_domain_muted(muted_out, domain):
            continue
        if list_covers(primary_out, domain):
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


_NL_DOMAIN_ALIASES: dict[str, str] = {
    "goals": "profile.goals",
    "goal": "profile.goals",
    "cashflow": "profile.cashflow",
    "budget": "profile.cashflow",
    "income": "profile.cashflow",
    "expenses": "profile.cashflow",
    "debt": "profile.debt",
    "debts": "profile.debt",
    "tax": "profile.tax",
    "taxes": "profile.tax",
    "policy": "profile.policy",
    "investment policy": "profile.policy",
    "portfolio": "portfolio",
    "holdings": "portfolio.holdings",
    "plan": "plan",
    "retirement": "plan",
    "inbox": "recommendation",
    "recommendations": "recommendation",
    "recommendation": "recommendation",
    "research": "research",
    "stocks": "research",
    "profile": "profile",
}


def parse_session_focus_utterance(question: str) -> dict[str, Any] | None:
    """Deterministic NL focus patch for explicit mute/focus phrases. Returns None if no match."""
    text = str(question or "").strip().lower()
    if not text:
        return None

    muted: list[str] = []
    primary: list[str] = []
    mode: str | None = None

    # Longer aliases first so "investment policy" wins over "policy".
    aliases = sorted(_NL_DOMAIN_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)

    mute_verbs = ("ignore ", "mute ", "don't talk about ", "do not talk about ", "skip ")
    for verb in mute_verbs:
        for alias, domain in aliases:
            needle = f"{verb}{alias}"
            if needle in text:
                muted.append(domain)

    focus_prefixes = (
        "focus only on ",
        "only talk about ",
        "only discuss ",
        "just talk about ",
        "just discuss ",
    )
    for prefix in focus_prefixes:
        for alias, domain in aliases:
            needle = f"{prefix}{alias}"
            if needle in text:
                primary.append(domain)
                mode = "narrow"
                break
        if primary:
            break

    muted = _unique_preserve(muted)
    primary = _unique_preserve(primary)
    if not muted and not primary:
        return None

    patch: dict[str, Any] = {}
    if muted:
        patch["muted_domains"] = muted
    if primary:
        patch["primary_domains"] = primary
        patch["secondary_domains"] = []
    if mode:
        patch["mode"] = mode
    return patch


def pinned_focus_domains(pinned_entity_ids: Sequence[str]) -> set[str]:
    """Map pin ids like 'recommendation:rec-1' to catalog domains."""
    out: set[str] = set()
    for raw in pinned_entity_ids:
        domain = pin_prefix_to_focus_domain(str(raw))
        if domain:
            out.add(domain)
    return out


def _unique_preserve(items: Sequence[str]) -> list[str]:
    return _dedupe_preserve([str(item) for item in items if str(item or "").strip()])


@dataclass(frozen=True)
class EffectiveFocus:
    mode: str
    primary_domains: tuple[str, ...]
    secondary_domains: tuple[str, ...]
    muted_domains: tuple[str, ...]
    pinned_entity_ids: tuple[str, ...]
    priority_note: str
    set_by: str
    retrieval_registry_domains: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "primary_domains": list(self.primary_domains),
            "secondary_domains": list(self.secondary_domains),
            "muted_domains": list(self.muted_domains),
            "pinned_entity_ids": list(self.pinned_entity_ids),
            "priority_note": self.priority_note,
            "set_by": self.set_by,
            "retrieval_registry_domains": list(self.retrieval_registry_domains),
        }


FOCUS_SCORE_MULTIPLIER = {
    "primary": 1.25,
    "secondary": 1.10,
    "muted": 0.55,
    "pinned": 1.35,
    "none": 1.0,
}


def merge_focus_with_intent(
    focus: Mapping[str, Any] | None,
    intent: Mapping[str, Any] | None,
) -> EffectiveFocus:
    """Merge stored/request Session Focus with turn intent into EffectiveFocus."""
    normalized = normalize_focus(focus, strict=False)
    intent_payload = dict(intent) if isinstance(intent, Mapping) else {}
    intent_domains = [
        lowered_domain(str(item))
        for item in (intent_payload.get("domains") or [])
        if lowered_domain(str(item)) in {"profile", "plan", "recommendation", "research", "portfolio"}
        or lowered_domain(str(item)) in FOCUS_DOMAIN_CATALOG
    ]
    # Intent domains are top-level; keep only known top-level ids.
    intent_domains = [
        d
        for d in _unique_preserve(intent_domains)
        if d in {"profile", "plan", "recommendation", "research", "portfolio"}
        or d in FOCUS_DOMAIN_CATALOG
    ]
    confidence = str(intent_payload.get("confidence") or "low").strip().lower()
    n = 1 if confidence == "high" else 2
    mode = str(normalized.get("mode") or "balanced")
    if mode not in FOCUS_MODES:
        mode = "balanced"

    user_primary = list(normalized.get("primary_domains") or [])
    user_secondary = list(normalized.get("secondary_domains") or [])
    user_muted = list(normalized.get("muted_domains") or [])
    primary_from_user = len(user_primary) > 0
    pin_domains = pinned_focus_domains(list(normalized.get("pinned_entity_ids") or []))

    if primary_from_user:
        primary = user_primary[:MAX_PRIMARY]
    else:
        primary = intent_domains[:n]

    if user_secondary:
        secondary = [d for d in user_secondary if not list_covers(primary, d)][:MAX_SECONDARY]
    elif mode == "narrow" and primary_from_user:
        secondary = []
    else:
        secondary = [d for d in intent_domains if not list_covers(primary, d)][:MAX_SECONDARY]

    muted = list(user_muted)

    if primary_from_user:
        muted = [
            m
            for m in muted
            if not list_covers(primary, m)
            and not any(covers_focus_domain(m, p) for p in primary)
        ]
    else:
        primary = [d for d in primary if not is_domain_muted(muted, d)]
        if not primary:
            primary = [d for d in intent_domains if not is_domain_muted(muted, d)][:n]

    secondary = [
        d
        for d in secondary
        if not list_covers(primary, d) and not is_domain_muted(muted, d)
    ][:MAX_SECONDARY]

    if mode == "narrow":
        allowed = set(primary) | set(secondary) | set(pin_domains)
        for domain in sorted(FOCUS_DOMAIN_CATALOG):
            if is_domain_muted(muted, domain):
                continue
            if any(covers_focus_domain(a, domain) for a in allowed):
                continue
            muted.append(domain)

    primary = _unique_preserve(primary)[:MAX_PRIMARY]
    secondary = _unique_preserve(secondary)[:MAX_SECONDARY]
    muted = _unique_preserve(muted)

    retrieval = focus_domains_to_registry_domains(list(primary) + list(secondary) + sorted(pin_domains))
    return EffectiveFocus(
        mode=mode,
        primary_domains=tuple(primary),
        secondary_domains=tuple(secondary),
        muted_domains=tuple(muted),
        pinned_entity_ids=tuple(normalized.get("pinned_entity_ids") or ()),
        priority_note=str(normalized.get("priority_note") or ""),
        set_by=str(normalized.get("set_by") or "default"),
        retrieval_registry_domains=tuple(retrieval),
    )


def plan_in_focus(effective: EffectiveFocus) -> bool:
    ids = list(effective.primary_domains) + list(effective.secondary_domains)
    return list_covers(ids, "plan")


def run_plan_id_pass(*, plan_id: str | None, effective: EffectiveFocus) -> bool:
    if not plan_id:
        return False
    if effective.mode != "narrow":
        return True
    return plan_in_focus(effective)


def plan_pass_domains(effective: EffectiveFocus) -> list[str]:
    domains = ["plan", "research", "recommendation"]
    return [d for d in domains if not is_domain_muted(effective.muted_domains, d)]


def _registry_domain_to_focus_candidates(registry_domain: str) -> list[str]:
    domain = lowered_domain(registry_domain)
    if domain == "profile":
        return ["profile", "profile.goals", "profile.cashflow", "profile.debt", "profile.tax", "profile.policy"]
    if domain == "portfolio":
        return ["portfolio", "portfolio.holdings"]
    if domain in FOCUS_DOMAIN_CATALOG:
        return [domain]
    return [domain] if domain else []


def focus_tier_for_item(
    item: Mapping[str, Any],
    effective: EffectiveFocus,
) -> str:
    """Return primary|secondary|muted|pinned|none for a retrieved context item."""
    item_id = str(item.get("id") or item.get("entity_id") or "").strip().lower()
    entity_id = str(item.get("entity_id") or "").strip().lower()
    source_ref = str(item.get("source_ref") or "").strip().lower()
    for pin in effective.pinned_entity_ids:
        pin_text = str(pin or "").strip().lower()
        if not pin_text:
            continue
        pin_body = pin_text.split(":", 1)[-1] if ":" in pin_text else pin_text
        if pin_text in item_id or pin_body and (
            pin_body == entity_id or pin_body in source_ref or pin_body in item_id
        ):
            return "pinned"

    registry_domain = lowered_domain(str(item.get("domain") or ""))
    candidates = _registry_domain_to_focus_candidates(registry_domain)
    # Prefer most specific tier among candidates.
    for candidate in candidates:
        if any(covers_focus_domain(p, candidate) or covers_focus_domain(candidate, p) for p in effective.primary_domains):
            return "primary"
    for candidate in candidates:
        if any(covers_focus_domain(s, candidate) or covers_focus_domain(candidate, s) for s in effective.secondary_domains):
            return "secondary"
    for candidate in candidates:
        if is_domain_muted(effective.muted_domains, candidate):
            return "muted"
    return "none"


def apply_focus_score_boost(
    items: Sequence[Mapping[str, Any]],
    effective: EffectiveFocus,
    *,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    boosted: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        tier = focus_tier_for_item(item, effective)
        pre = float(item.get("score") or 0.0)
        mult = FOCUS_SCORE_MULTIPLIER.get(tier, 1.0) if enabled else 1.0
        item["score"] = round(min(1.0, pre * mult), 4)
        breakdown = dict(item.get("score_breakdown") or {})
        breakdown["focus"] = mult
        breakdown["pre_focus_score"] = pre
        breakdown["focus_tier"] = tier
        item["score_breakdown"] = breakdown
        boosted.append(item)
    boosted.sort(
        key=lambda row: (
            float(row.get("score") or 0.0),
            str(row.get("updated_at") or ""),
        ),
        reverse=True,
    )
    return boosted


_ACTION_ADVICE_TERMS = (
    "should i",
    "what should",
    "next action",
    "recommendation",
    "apply",
    "reject",
)


def wants_action_advice(question: str, *, intent: Mapping[str, Any] | None = None) -> bool:
    if isinstance(intent, Mapping) and str(intent.get("intent") or "") == "recommendation_review":
        return True
    lowered = str(question or "").strip().lower()
    return any(term in lowered for term in _ACTION_ADVICE_TERMS)


def collect_muted_safety_warnings(
    *,
    structured_context: Mapping[str, Any],
    conflicts: Sequence[Mapping[str, Any]],
    quality: Mapping[str, Any] | None,
    effective_focus: EffectiveFocus,
    question: str,
    intent: Mapping[str, Any] | None = None,
    muted_registry_candidates: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(
        *,
        domain: str,
        materiality: str,
        message: str,
        blocks: bool,
        source: str,
        action_readiness: str = "",
    ) -> None:
        text = str(message or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        readiness = action_readiness or action_readiness_for_materiality(
            materiality,
            default="medium",
        )
        warnings.append(
            {
                "domain": domain,
                "materiality": materiality,
                "action_readiness": readiness,
                "message": text[:220],
                "blocks_decision_grade_advice": bool(blocks),
                "source": source,
            }
        )

    for conflict in conflicts:
        if not isinstance(conflict, Mapping):
            continue
        message = (
            conflict.get("plain_language")
            or conflict.get("detail")
            or conflict.get("title")
            or conflict.get("message")
        )
        severity = str(conflict.get("severity") or "medium").lower()
        blocks = bool(conflict.get("blocks_decision_grade_advice"))
        if blocks or severity in {"high", "critical"}:
            _add(
                domain="conflict",
                materiality="critical" if severity == "critical" or blocks else "high",
                message=str(message or ""),
                blocks=blocks,
                source="conflict",
            )

    quality_payload = quality if isinstance(quality, Mapping) else {}
    freshness = quality_payload.get("freshness")
    freshness = freshness if isinstance(freshness, Mapping) else {}
    if freshness.get("snapshot_stale") is True:
        _add(
            domain="portfolio",
            materiality="high",
            message="Portfolio snapshot is stale; run sync or use live snapshot before relying on balances.",
            blocks=False,
            source="quality",
        )

    decisions = structured_context.get("decisions") if isinstance(structured_context, Mapping) else {}
    decisions = decisions if isinstance(decisions, Mapping) else {}
    recommendations = decisions.get("recommendations")
    recommendations = recommendations if isinstance(recommendations, Mapping) else {}
    try:
        high_count = int(recommendations.get("high_priority_count") or 0)
    except (TypeError, ValueError):
        high_count = 0
    if (
        high_count > 0
        and wants_action_advice(question, intent=intent)
        and is_domain_muted(effective_focus.muted_domains, "recommendation")
    ):
        _add(
            domain="recommendation",
            materiality="high",
            message=(
                f"{high_count} high-priority inbox items exist; "
                "unmute Inbox focus or call list_recommendations."
            ),
            blocks=False,
            source="structured_signal",
        )

    financial = structured_context.get("financial_picture") if isinstance(structured_context, Mapping) else {}
    financial = financial if isinstance(financial, Mapping) else {}
    profile = financial.get("financial_profile")
    profile = profile if isinstance(profile, Mapping) else {}
    tax_profile = profile.get("tax_profile")
    tax_profile = tax_profile if isinstance(tax_profile, Mapping) else {}
    intent_name = str((intent or {}).get("intent") or "") if isinstance(intent, Mapping) else ""
    tax_intent = intent_name in {"planning_question", "profile_question"} or any(
        term in str(question or "").lower() for term in ("tax", "contribution", "roth", "401")
    )
    tax_missing = not tax_profile or (
        tax_profile.get("marginal_tax_rate") in (None, "", 0, 0.0)
        and not tax_profile.get("filing_status")
    )
    if tax_intent and tax_missing:
        _add(
            domain="profile.tax",
            materiality="high",
            message="Tax profile needs review before decision-grade tax or contribution advice.",
            blocks=True,
            source="structured_signal",
        )

    for candidate in muted_registry_candidates:
        if not isinstance(candidate, Mapping):
            continue
        materiality = str(candidate.get("materiality") or "").lower()
        if materiality not in {"high", "critical"}:
            continue
        domain = str(candidate.get("domain") or "muted")
        text = str(candidate.get("text") or candidate.get("message") or "").strip()
        if not text:
            continue
        sentence = text.split(".")[0].strip()
        _add(
            domain=domain if domain in FOCUS_DOMAIN_CATALOG else domain,
            materiality=materiality,
            message=sentence[:220],
            blocks=materiality == "critical",
            source="muted_registry_postfilter",
        )

    return warnings[:5]


def focus_applied_brief_and_retrieval(
    *,
    effective: EffectiveFocus,
    brief_chars: int,
    brief_truncated: bool,
    safety_warnings: Sequence[Mapping[str, Any]],
    package_sections_included: Sequence[str],
    package_sections_omitted: Sequence[str],
    retrieval_focus_boost: bool,
    detail_level: str = "light",
) -> dict[str, Any]:
    muted_safety = [
        str(item.get("domain") or "")
        for item in safety_warnings
        if isinstance(item, Mapping) and item.get("domain")
    ]
    return {
        "effect": "brief_and_retrieval",
        "mode": effective.mode,
        "primary_domains": list(effective.primary_domains),
        "secondary_domains": list(effective.secondary_domains),
        "muted_domains": list(effective.muted_domains),
        "pinned_entity_ids": list(effective.pinned_entity_ids),
        "priority_note": effective.priority_note,
        "set_by": effective.set_by,
        "effective_domains_for_retrieval": list(effective.retrieval_registry_domains),
        "detail_level": detail_level,
        "brief_version": "copilot_prompt_brief_v1",
        "brief_chars": brief_chars,
        "brief_truncated": brief_truncated,
        "safety_warnings_count": len(safety_warnings),
        "muted_safety_surfaced": muted_safety[:8],
        "package_sections_included": list(package_sections_included),
        "package_sections_omitted": list(package_sections_omitted),
        "retrieval_focus_boost": bool(retrieval_focus_boost),
        "score_formula": "min(1.0, pre_boost * focus_multiplier)",
    }
