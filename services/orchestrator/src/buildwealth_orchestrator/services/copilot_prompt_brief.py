"""Slim Prompt Brief builder for Copilot system messages.

Replaces dumping the full assembled context package into every chat turn.
Full Canonical State remains available via tools; the brief keeps summary,
retrieved evidence, compact conflicts, and safety signals.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping, MutableMapping, Sequence

BRIEF_VERSION = "copilot_prompt_brief_v1"
BRIEF_HARD_MAX_CHARS = 15_000
FOCUSED_STRUCTURED_HARD_MAX_CHARS = 12_000
MAX_CITATIONS = 12
MAX_SAFETY_WARNINGS = 5
MAX_CONFLICTS = 5
RETRIEVED_TEXT_CHARS = {"narrow": 4000, "balanced": 6000, "wide": 6000}
RETRIEVED_MAX_ITEMS = {"narrow": 8, "balanced": 12, "wide": 12}

_TOOL_GUIDANCE = {
    "deep_detail": (
        "Call domain tools or get_buildwealth_context with only the flags you need "
        "(default light, research/projection off unless required)."
    ),
    "search": "Call search_context with domain filters.",
}


def _as_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _compact_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, default=str, separators=(",", ":"), ensure_ascii=False)


def _trim_text(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."


def _quality_slice(quality: Mapping[str, Any]) -> dict[str, Any]:
    freshness = _as_mapping(quality.get("freshness"))
    coverage = _as_mapping(quality.get("coverage"))
    warnings = _as_mapping(quality.get("warnings"))
    return {
        "coverage_score_pct": coverage.get("score_pct"),
        "snapshot_stale": freshness.get("snapshot_stale"),
        "warning_count": warnings.get("count", 0),
    }


def _scope_slice(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": scope.get("plan_id"),
        "detail_level": scope.get("detail_level") or "light",
        "use_live_snapshot": bool(scope.get("use_live_snapshot")),
        "include_research": bool(scope.get("include_research")),
        "include_plan_projection": bool(scope.get("include_plan_projection")),
    }


def _compact_conflicts(conflicts: Sequence[Any], *, limit: int = MAX_CONFLICTS) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in conflicts[: max(0, limit)]:
        if not isinstance(item, Mapping):
            continue
        compact.append(
            {
                "type": item.get("type"),
                "severity": item.get("severity"),
                "message": item.get("plain_language") or item.get("detail") or item.get("title") or item.get("message"),
                "blocks_decision_grade_advice": bool(item.get("blocks_decision_grade_advice")),
                "source_refs": _as_list(item.get("source_refs"))[:4],
            }
        )
    return compact


def _collect_pr1_safety_warnings(
    *,
    assembled: Mapping[str, Any],
    conflicts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(
        *,
        source: str,
        message: str,
        materiality: str = "medium",
        blocks: bool = False,
        domain: str | None = None,
    ) -> None:
        text = str(message or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        entry: dict[str, Any] = {
            "source": source,
            "message": _trim_text(text, limit=280),
            "materiality": materiality,
            "blocks_decision_grade_advice": blocks,
        }
        if domain:
            entry["domain"] = domain
        warnings.append(entry)

    for conflict in conflicts:
        message = (
            conflict.get("plain_language")
            or conflict.get("detail")
            or conflict.get("title")
            or conflict.get("message")
        )
        _add(
            source="conflict",
            message=str(message or ""),
            materiality=str(conflict.get("severity") or "high"),
            blocks=bool(conflict.get("blocks_decision_grade_advice")),
        )

    quality = _as_mapping(assembled.get("quality"))
    freshness = _as_mapping(quality.get("freshness"))
    if freshness.get("snapshot_stale") is True:
        _add(
            source="quality",
            message="Portfolio snapshot is stale. Run sync or request a live snapshot before decision-grade advice.",
            materiality="high",
            blocks=False,
            domain="portfolio",
        )

    for raw in _as_list(assembled.get("warnings")):
        _add(source="package_warning", message=str(raw), materiality="medium")

    trace = _as_mapping(assembled.get("trace"))
    for raw in _as_list(trace.get("context_warnings")):
        if not isinstance(raw, Mapping):
            continue
        _add(
            source="trace_warning",
            message=str(raw.get("message") or ""),
            materiality=str(raw.get("severity") or "medium"),
            blocks=bool(raw.get("blocks_decision_grade_advice")),
        )

    decisions = _as_mapping(assembled.get("decisions"))
    recommendations = _as_mapping(decisions.get("recommendations"))
    high_priority = recommendations.get("high_priority_count")
    try:
        high_count = int(high_priority or 0)
    except (TypeError, ValueError):
        high_count = 0
    if high_count > 0:
        _add(
            source="structured",
            message=f"{high_count} high-priority open recommendation(s) may affect action advice.",
            materiality="high",
            blocks=False,
            domain="recommendation",
        )

    return warnings[:MAX_SAFETY_WARNINGS]


def _retrieved_slice(
    retrieved: Mapping[str, Any],
    *,
    max_items: int,
    max_text_chars: int,
) -> dict[str, Any]:
    items_out: list[dict[str, Any]] = []
    text_budget = max(0, int(max_text_chars))
    used_text = 0
    for item in _as_list(retrieved.get("items"))[: max(0, max_items)]:
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("text") or "")
        remaining = max(0, text_budget - used_text)
        if remaining <= 0 and items_out:
            break
        trimmed = _trim_text(text, limit=max(80, min(len(text), remaining or 80)))
        used_text += len(trimmed)
        items_out.append(
            {
                "id": item.get("id"),
                "domain": item.get("domain"),
                "entity_type": item.get("entity_type"),
                "source_ref": item.get("source_ref"),
                "authority": item.get("authority"),
                "materiality": item.get("materiality"),
                "text": trimmed,
                "score": item.get("score"),
            }
        )
    return {
        "count": len(items_out),
        "items": items_out,
    }


def _citations_slice(citations: Sequence[Any], *, limit: int = MAX_CITATIONS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in citations[: max(0, limit)]:
        if not isinstance(item, Mapping):
            continue
        out.append(
            {
                "context_item_id": item.get("context_item_id") or item.get("id"),
                "source_ref": item.get("source_ref"),
                "domain": item.get("domain"),
            }
        )
    return out


def _focused_structured_pr1(assembled: Mapping[str, Any]) -> dict[str, Any]:
    """Light, always-on structured subset for PR1 (pre Session Focus shaping)."""
    financial = _as_mapping(assembled.get("financial_picture"))
    planning = _as_mapping(assembled.get("planning"))
    decisions = _as_mapping(assembled.get("decisions"))
    research = _as_mapping(assembled.get("research"))

    snapshot = _as_mapping(financial.get("snapshot_summary"))
    dashboard = _as_mapping(financial.get("today_dashboard"))
    profile = _as_mapping(financial.get("financial_profile"))
    onboarding = _as_mapping(financial.get("onboarding_status"))
    watchlist = _as_mapping(financial.get("watchlist"))

    active_plan = _as_mapping(planning.get("active_plan"))
    tracking = _as_mapping(planning.get("tracking"))
    recommendations = _as_mapping(decisions.get("recommendations"))

    profile_light: dict[str, Any]
    if profile:
        if "income_items_count" in profile or "note" in profile:
            profile_light = {
                "updated_at": profile.get("updated_at"),
                "income_items_count": profile.get("income_items_count"),
                "expense_items_count": profile.get("expense_items_count"),
                "debt_items_count": profile.get("debt_items_count"),
                "goal_items_count": profile.get("goal_items_count"),
                "physical_assets_count": profile.get("physical_assets_count"),
                "insurance_policies_count": profile.get("insurance_policies_count"),
                "benefit_items_count": profile.get("benefit_items_count"),
                "estate_readiness": (
                    profile.get("estate_readiness")
                    if isinstance(profile.get("estate_readiness"), Mapping)
                    else {}
                ),
                "tax_profile": profile.get("tax_profile") if isinstance(profile.get("tax_profile"), Mapping) else {},
                "investment_policy": (
                    profile.get("investment_policy")
                    if isinstance(profile.get("investment_policy"), Mapping)
                    else {}
                ),
                "flags": profile.get("flags") if isinstance(profile.get("flags"), Mapping) else {},
            }
        else:
            profile_light = {
                "updated_at": profile.get("updated_at"),
                "income_items_count": len(_as_list(profile.get("income_items"))),
                "expense_items_count": len(_as_list(profile.get("expense_items"))),
                "debt_items_count": len(_as_list(profile.get("debt_items"))),
                "goal_items_count": len(_as_list(profile.get("goal_items"))),
                "physical_assets_count": len(_as_list(profile.get("physical_assets"))),
                "insurance_policies_count": len(_as_list(profile.get("insurance_policies"))),
                "benefit_items_count": len(_as_list(profile.get("benefit_items"))),
                "estate_readiness": (
                    profile.get("estate_readiness")
                    if isinstance(profile.get("estate_readiness"), Mapping)
                    else {}
                ),
                "tax_profile": profile.get("tax_profile") if isinstance(profile.get("tax_profile"), Mapping) else {},
                "investment_policy": (
                    profile.get("investment_policy")
                    if isinstance(profile.get("investment_policy"), Mapping)
                    else {}
                ),
                "flags": profile.get("flags") if isinstance(profile.get("flags"), Mapping) else {},
            }
    else:
        profile_light = {}

    rec_items = []
    for item in _as_list(recommendations.get("items"))[:5]:
        if not isinstance(item, Mapping):
            continue
        rec_items.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "priority": item.get("priority"),
                "status": item.get("status"),
            }
        )

    research_items = []
    for item in _as_list(research.get("items"))[:5]:
        if not isinstance(item, Mapping):
            continue
        research_items.append(
            {
                "symbol": item.get("symbol"),
                "quote_price": item.get("quote_price"),
                "period_change_pct": item.get("period_change_pct"),
                "period_label": item.get("period_label"),
            }
        )

    return {
        "financial_picture": {
            "snapshot_summary": {
                "as_of": snapshot.get("as_of"),
                "total_value_usd": snapshot.get("total_value_usd"),
                "net_performance_usd": snapshot.get("net_performance_usd"),
                "net_performance_percent": snapshot.get("net_performance_percent"),
            },
            "today_dashboard": {
                "net_worth_usd": dashboard.get("net_worth_usd"),
                "monthly_surplus_usd": dashboard.get("monthly_surplus_usd"),
                "savings_rate_pct": dashboard.get("savings_rate_pct"),
                "note": dashboard.get("note"),
            },
            "financial_profile": profile_light,
            "onboarding_status": {
                "completion_percent": onboarding.get("completion_percent"),
                "ready_for_daily_review": onboarding.get("ready_for_daily_review"),
            },
            "watchlist": {
                "count": watchlist.get("count"),
                "symbols_preview": _as_list(watchlist.get("symbols_preview"))[:8],
            },
        },
        "planning": {
            "active_plan": {
                "id": active_plan.get("id"),
                "title": active_plan.get("title"),
                "updated_at": active_plan.get("updated_at"),
            },
            "tracking": {
                "status": tracking.get("status"),
                "actual_annualized_return_pct": tracking.get("actual_annualized_return_pct"),
                "expected_annualized_return_pct": tracking.get("expected_annualized_return_pct"),
            },
        },
        "decisions": {
            "recommendations": {
                "open_count": recommendations.get("open_count"),
                "high_priority_count": recommendations.get("high_priority_count"),
                "items": rec_items,
            }
        },
        "research": {
            "symbols": _as_list(research.get("symbols"))[:5],
            "items": research_items,
        },
    }


def _budget_focused_structured(structured: MutableMapping[str, Any]) -> dict[str, Any]:
    serialized = _compact_json(structured)
    if len(serialized) <= FOCUSED_STRUCTURED_HARD_MAX_CHARS:
        return dict(structured)

    # Drop lower-priority sections first.
    drop_order = (
        ("research",),
        ("financial_picture", "watchlist"),
        ("planning", "tracking"),
        ("financial_picture", "today_dashboard"),
        ("decisions", "recommendations", "items"),
        ("financial_picture", "financial_profile"),
    )
    working = deepcopy(dict(structured))
    for path in drop_order:
        cursor: Any = working
        for key in path[:-1]:
            if not isinstance(cursor, MutableMapping) or key not in cursor:
                cursor = None
                break
            cursor = cursor[key]
        if isinstance(cursor, MutableMapping) and path[-1] in cursor:
            cursor[path[-1]] = {"omitted": True, "reason": "brief_budget"}
        if len(_compact_json(working)) <= FOCUSED_STRUCTURED_HARD_MAX_CHARS:
            return working
    return working


def _truncate_brief(brief: dict[str, Any], *, mode: str) -> dict[str, Any]:
    working = deepcopy(brief)
    mode_key = mode if mode in RETRIEVED_MAX_ITEMS else "balanced"

    def size() -> int:
        return len(_compact_json(working))

    if size() <= BRIEF_HARD_MAX_CHARS:
        return working

    # Step 1: shrink retrieved item texts.
    retrieved = _as_mapping(working.get("retrieved_context"))
    working["retrieved_context"] = _retrieved_slice(
        retrieved,
        max_items=int(RETRIEVED_MAX_ITEMS[mode_key]),
        max_text_chars=max(500, int(RETRIEVED_TEXT_CHARS[mode_key]) // 2),
    )
    if size() <= BRIEF_HARD_MAX_CHARS:
        working["brief_truncated"] = True
        return working

    # Step 2: drop half of retrieved items.
    items = _as_list(working["retrieved_context"].get("items"))
    half = max(1, len(items) // 2) if items else 0
    working["retrieved_context"] = {
        "count": half,
        "items": items[:half],
    }
    if size() <= BRIEF_HARD_MAX_CHARS:
        working["brief_truncated"] = True
        return working

    # Step 3: shrink focused_structured.
    focused = _as_mapping(working.get("focused_structured"))
    working["focused_structured"] = _budget_focused_structured(dict(focused))
    if size() <= BRIEF_HARD_MAX_CHARS:
        working["brief_truncated"] = True
        return working

    # Step 4: citations to 3.
    working["citations"] = _as_list(working.get("citations"))[:3]
    if size() <= BRIEF_HARD_MAX_CHARS:
        working["brief_truncated"] = True
        return working

    # Step 5: truncate summary.
    working["summary"] = _trim_text(working.get("summary"), limit=1200)
    if size() <= BRIEF_HARD_MAX_CHARS:
        working["brief_truncated"] = True
        return working

    # Step 6: omit remaining oversized blobs (never safety_warnings / session_focus / tool_guidance).
    for key in ("focused_structured", "retrieved_context", "citations", "conflicts"):
        working[key] = {"omitted": True, "reason": "brief_budget"}
        if size() <= BRIEF_HARD_MAX_CHARS:
            working["brief_truncated"] = True
            return working

    # Step 7: emergency minimal brief.
    working = {
        "brief_version": BRIEF_VERSION,
        "session_focus": working.get("session_focus") or {},
        "summary": _trim_text(brief.get("summary"), limit=800),
        "quality": working.get("quality") or {},
        "scope": working.get("scope") or {},
        "safety_warnings": working.get("safety_warnings") or [],
        "tool_guidance": _TOOL_GUIDANCE,
        "brief_truncated": True,
    }
    return working


def _shape_focused_structured_for_effective(
    assembled: Mapping[str, Any],
    effective_focus: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """PR4: start from light structured slice, strip muted domain expansions."""
    base = _focused_structured_pr1(assembled)
    if not isinstance(effective_focus, Mapping):
        return base
    muted = {
        str(item).strip().lower()
        for item in _as_list(effective_focus.get("muted_domains"))
        if str(item).strip()
    }
    financial = dict(_as_mapping(base.get("financial_picture")))
    profile = dict(_as_mapping(financial.get("financial_profile")))
    if "research" in muted:
        base["research"] = {"symbols": [], "items": [], "muted": True}
    if "recommendation" in muted:
        decisions = dict(_as_mapping(base.get("decisions")))
        recs = dict(_as_mapping(decisions.get("recommendations")))
        decisions["recommendations"] = {
            "open_count": recs.get("open_count"),
            "high_priority_count": recs.get("high_priority_count"),
            "items": [],
            "muted": True,
        }
        base["decisions"] = decisions
    if "plan" in muted:
        planning = dict(_as_mapping(base.get("planning")))
        planning["tracking"] = {"muted": True}
        if isinstance(planning.get("active_plan"), dict):
            planning["active_plan"] = {
                "id": planning["active_plan"].get("id"),
                "title": planning["active_plan"].get("title"),
            }
        base["planning"] = planning
    if "portfolio" in muted or "portfolio.holdings" in muted:
        financial["snapshot_summary"] = {
            "as_of": _as_mapping(financial.get("snapshot_summary")).get("as_of"),
            "muted": True,
        }
    if "profile" in muted:
        financial["financial_profile"] = {"muted": True}
    else:
        if "profile.tax" in muted:
            profile["tax_profile"] = {}
        if "profile.policy" in muted:
            profile["investment_policy"] = {}
        if "profile.goals" in muted:
            profile["goal_items_count"] = profile.get("goal_items_count")
        if "profile.cashflow" in muted:
            profile["income_items_count"] = profile.get("income_items_count")
            profile["expense_items_count"] = profile.get("expense_items_count")
        if "profile.debt" in muted:
            profile["debt_items_count"] = profile.get("debt_items_count")
        financial["financial_profile"] = profile
    base["financial_picture"] = financial
    return base


def build_copilot_prompt_brief(
    assembled_context: Mapping[str, Any] | None,
    *,
    focus: Mapping[str, Any] | None = None,
    effective_focus: Mapping[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    """Build compact system-message Financial Context for Copilot chat."""
    assembled = _as_mapping(assembled_context)
    trace = _as_mapping(assembled.get("trace"))
    intent = _as_mapping(trace.get("intent"))
    quality = _as_mapping(assembled.get("quality"))
    scope = _as_mapping(assembled.get("scope"))
    conflicts_raw = [item for item in _as_list(assembled.get("conflicts")) if isinstance(item, Mapping)]
    retrieved = _as_mapping(assembled.get("retrieved_context"))
    citations = _as_list(assembled.get("citations"))
    context_budget = _as_mapping(assembled.get("context_budget"))

    mode_key = str(
        (effective_focus or {}).get("mode")
        or (focus or {}).get("mode")
        or mode
        or "balanced"
    ).strip().lower()
    if mode_key not in RETRIEVED_MAX_ITEMS:
        mode_key = "balanced"

    session_focus = dict(effective_focus or focus or {})
    # PR1 may not have focus yet; keep empty object for schema stability.
    if not session_focus:
        session_focus = {
            "mode": "balanced",
            "primary_domains": [],
            "secondary_domains": [],
            "muted_domains": [],
            "pinned_entity_ids": [],
            "priority_note": "",
            "set_by": "default",
        }

    assembly_warnings = _as_list(assembled.get("safety_warnings")) or _as_list(trace.get("safety_warnings"))
    if assembly_warnings:
        safety_warnings = [
            dict(item) if isinstance(item, Mapping) else {"message": str(item)}
            for item in assembly_warnings[:MAX_SAFETY_WARNINGS]
        ]
    else:
        safety_warnings = _collect_pr1_safety_warnings(assembled=assembled, conflicts=conflicts_raw)
    focused_structured = _budget_focused_structured(
        _shape_focused_structured_for_effective(assembled, effective_focus or focus)
    )

    brief: dict[str, Any] = {
        "brief_version": BRIEF_VERSION,
        "session_focus": session_focus,
        "intent": {
            "intent": intent.get("intent") or "general",
            "confidence": intent.get("confidence"),
            "domains": _as_list(intent.get("domains")),
        },
        "summary": str(assembled.get("summary") or "").strip(),
        "quality": _quality_slice(quality),
        "scope": _scope_slice(scope),
        "focused_structured": focused_structured,
        "retrieved_context": _retrieved_slice(
            retrieved,
            max_items=int(RETRIEVED_MAX_ITEMS[mode_key]),
            max_text_chars=int(RETRIEVED_TEXT_CHARS[mode_key]),
        ),
        "citations": _citations_slice(citations),
        "conflicts": _compact_conflicts(conflicts_raw),
        "safety_warnings": safety_warnings,
        "context_budget": {
            "truncated": bool(context_budget.get("truncated")),
            "returned_items": context_budget.get("returned_items")
            or len(_as_list(_as_mapping(retrieved).get("items"))),
        },
        "tool_guidance": dict(_TOOL_GUIDANCE),
    }

    brief = _truncate_brief(brief, mode=mode_key)
    return _compact_json(brief)
