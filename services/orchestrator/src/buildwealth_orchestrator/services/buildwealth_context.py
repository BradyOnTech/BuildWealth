"""Helpers for unified BuildWealth context packaging across portfolio/planning/research."""

from __future__ import annotations

from copy import deepcopy
import re
from datetime import datetime, timezone
from typing import Any

DEFAULT_RESEARCH_SYMBOL_LIMIT = 5
DEFAULT_CONTEXT_SUMMARY_MAX_CHARS = 2400
DEFAULT_CONTEXT_WARNING_LIMIT = 50
DEFAULT_CONTEXT_SNAPSHOT_STALE_AFTER_SECONDS = 86_400.0
DEFAULT_CONTEXT_DETAIL_LEVEL = "full"
VALID_CONTEXT_DETAIL_LEVELS = {"full", "light"}
_SYMBOL_PATTERN = re.compile(r"[^A-Z0-9._-]+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_currency(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    return f"${numeric:,.2f}"


def _format_percent(value: Any, *, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.{digits}f}%"


def _trim_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_context_warnings(
    raw_warnings: list[Any] | None,
    *,
    max_warnings: int = DEFAULT_CONTEXT_WARNING_LIMIT,
) -> list[str]:
    if not isinstance(raw_warnings, list):
        return []

    resolved_limit = max(0, min(int(max_warnings), 200))
    if resolved_limit == 0:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for warning in raw_warnings:
        text = _trim_text(warning, limit=220)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
        if len(normalized) >= resolved_limit:
            break
    return normalized


def normalize_context_detail_level(
    raw_level: Any,
    *,
    default: str = DEFAULT_CONTEXT_DETAIL_LEVEL,
) -> str:
    fallback = str(default or DEFAULT_CONTEXT_DETAIL_LEVEL).strip().lower() or DEFAULT_CONTEXT_DETAIL_LEVEL
    if fallback not in VALID_CONTEXT_DETAIL_LEVELS:
        fallback = DEFAULT_CONTEXT_DETAIL_LEVEL
    level = str(raw_level or "").strip().lower()
    if level in VALID_CONTEXT_DETAIL_LEVELS:
        return level
    return fallback


def normalize_research_symbols(raw_symbols: list[Any] | None, *, max_symbols: int = DEFAULT_RESEARCH_SYMBOL_LIMIT) -> list[str]:
    if not isinstance(raw_symbols, list):
        return []

    resolved_limit = max(0, min(int(max_symbols), 20))
    if resolved_limit == 0:
        return []

    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw_symbols:
        text = str(item or "").strip().upper()
        if not text:
            continue
        cleaned = _SYMBOL_PATTERN.sub("", text)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        symbols.append(cleaned)
        if len(symbols) >= resolved_limit:
            break

    return symbols


def derive_research_symbols(
    *,
    requested_symbols: list[Any] | None,
    snapshot_summary: dict[str, Any] | None,
    watchlist_symbols: list[Any] | None = None,
    max_symbols: int = DEFAULT_RESEARCH_SYMBOL_LIMIT,
) -> list[str]:
    resolved_limit = max(0, min(int(max_symbols), 20))
    if resolved_limit == 0:
        return []

    requested = normalize_research_symbols(requested_symbols, max_symbols=resolved_limit)
    if len(requested) >= resolved_limit:
        return requested

    watchlist = normalize_research_symbols(watchlist_symbols, max_symbols=resolved_limit)
    if len(requested) + len(watchlist) >= resolved_limit:
        merged: list[str] = []
        seen: set[str] = set()
        for symbol in [*requested, *watchlist]:
            if symbol in seen:
                continue
            seen.add(symbol)
            merged.append(symbol)
            if len(merged) >= resolved_limit:
                break
        return merged

    holdings_symbols: list[Any] = []
    if isinstance(snapshot_summary, dict):
        top_holdings = snapshot_summary.get("top_holdings")
        if isinstance(top_holdings, list):
            holdings_symbols = [
                item.get("symbol")
                for item in top_holdings
                if isinstance(item, dict)
            ]

    from_holdings = normalize_research_symbols(holdings_symbols, max_symbols=resolved_limit)
    merged: list[str] = []
    seen: set[str] = set()
    for symbol in [*requested, *watchlist, *from_holdings]:
        if symbol in seen:
            continue
        seen.add(symbol)
        merged.append(symbol)
        if len(merged) >= resolved_limit:
            break
    return merged


def _compute_snapshot_freshness(
    *,
    context_payload: dict[str, Any],
    snapshot_stale_after_seconds: float = DEFAULT_CONTEXT_SNAPSHOT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    financial_picture = context_payload.get("financial_picture")
    if not isinstance(financial_picture, dict):
        financial_picture = {}
    snapshot_summary = financial_picture.get("snapshot_summary")
    if not isinstance(snapshot_summary, dict):
        snapshot_summary = {}

    generated_dt = _parse_iso_datetime(context_payload.get("generated_at")) or datetime.now(timezone.utc)
    snapshot_as_of = _parse_iso_datetime(snapshot_summary.get("as_of"))

    stale_after = max(60.0, min(float(snapshot_stale_after_seconds), 2_592_000.0))
    snapshot_age_seconds: float | None = None
    snapshot_stale: bool | None = None
    if snapshot_as_of is not None:
        snapshot_age_seconds = max(0.0, (generated_dt - snapshot_as_of).total_seconds())
        snapshot_stale = snapshot_age_seconds > stale_after

    return {
        "generated_at": generated_dt.isoformat(),
        "snapshot_as_of": snapshot_as_of.isoformat() if snapshot_as_of else None,
        "snapshot_age_seconds": round(snapshot_age_seconds, 3) if snapshot_age_seconds is not None else None,
        "snapshot_stale": snapshot_stale,
        "snapshot_stale_threshold_seconds": stale_after,
    }


def build_context_summary_with_metadata(
    *,
    context_payload: dict[str, Any],
    max_chars: int = DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
) -> tuple[str, dict[str, Any]]:
    summary_limit = max(300, min(int(max_chars), 12_000))
    financial_picture = context_payload.get("financial_picture")
    if not isinstance(financial_picture, dict):
        financial_picture = {}
    snapshot_summary = financial_picture.get("snapshot_summary")
    if not isinstance(snapshot_summary, dict):
        snapshot_summary = {}
    watchlist = financial_picture.get("watchlist")
    if not isinstance(watchlist, dict):
        watchlist = {}
    dashboard = financial_picture.get("today_dashboard")
    if not isinstance(dashboard, dict):
        dashboard = {}

    planning = context_payload.get("planning")
    if not isinstance(planning, dict):
        planning = {}
    active_plan = planning.get("active_plan")
    if not isinstance(active_plan, dict):
        active_plan = {}
    tracking = planning.get("tracking")
    if not isinstance(tracking, dict):
        tracking = {}
    contribution_rules = planning.get("contribution_rules")
    if not isinstance(contribution_rules, dict):
        contribution_rules = {}
    contribution_allocation_preview = planning.get("contribution_allocation_preview")
    if not isinstance(contribution_allocation_preview, dict):
        contribution_allocation_preview = {}
    withdrawal_strategy = planning.get("withdrawal_strategy")
    if not isinstance(withdrawal_strategy, dict):
        withdrawal_strategy = {}
    baseline_projection = planning.get("baseline_projection")
    if not isinstance(baseline_projection, dict):
        baseline_projection = {}

    decisions = context_payload.get("decisions")
    if not isinstance(decisions, dict):
        decisions = {}
    recommendations = decisions.get("recommendations")
    if not isinstance(recommendations, dict):
        recommendations = {}

    research = context_payload.get("research")
    if not isinstance(research, dict):
        research = {}
    research_items = research.get("items")
    if not isinstance(research_items, list):
        research_items = []

    warnings = context_payload.get("warnings")
    if not isinstance(warnings, list):
        warnings = []

    generated_at = str(context_payload.get("generated_at") or "").strip() or utc_now_iso()
    freshness = _compute_snapshot_freshness(context_payload=context_payload)
    snapshot_as_of_label = str(freshness.get("snapshot_as_of") or "n/a")
    snapshot_age_seconds = _safe_float(freshness.get("snapshot_age_seconds"))
    snapshot_age_label = (
        f"{(snapshot_age_seconds / 3600.0):.1f}h old"
        if snapshot_age_seconds is not None
        else "age unavailable"
    )
    snapshot_stale = freshness.get("snapshot_stale")
    if snapshot_stale is True:
        snapshot_status_label = "stale"
    elif snapshot_stale is False:
        snapshot_status_label = "fresh"
    else:
        snapshot_status_label = "unknown"
    raw_watchlist_symbols_preview = watchlist.get("symbols_preview")
    watchlist_symbols_preview = (
        [str(item).strip().upper() for item in raw_watchlist_symbols_preview if str(item).strip()]
        if isinstance(raw_watchlist_symbols_preview, list)
        else []
    )

    lines: list[str] = [
        "BuildWealth Unified Context",
        f"Generated: {generated_at}",
        "",
        "Financial Picture",
        (
            f"- Portfolio value { _format_currency(snapshot_summary.get('total_value_usd')) } "
            f"(net {_format_currency(snapshot_summary.get('net_performance_usd'))}, "
            f"{_format_percent(snapshot_summary.get('net_performance_percent'), digits=2)})."
        ),
        (
            f"- Net worth {_format_currency(dashboard.get('net_worth_usd'))}, "
            f"monthly surplus {_format_currency(dashboard.get('monthly_surplus_usd'))}, "
            f"savings rate {_format_percent(dashboard.get('savings_rate_pct'), digits=1)}."
        ),
        (
            f"- Snapshot as-of {snapshot_as_of_label} "
            f"({snapshot_age_label}, status: {snapshot_status_label})."
        ),
        (
            f"- Watchlist: {int(_safe_float(watchlist.get('count')) or 0)} item(s)"
            + (
                f" ({', '.join(watchlist_symbols_preview)})."
                if watchlist_symbols_preview
                else "."
            )
        ),
        "",
        "Planning",
        (
            f"- Active plan: {str(active_plan.get('title') or 'none')} "
            f"(id: {str(active_plan.get('id') or 'n/a')})."
        ),
        (
            f"- Tracking status: {str(tracking.get('status') or 'n/a')} "
            f"with actual return {_format_percent(tracking.get('actual_annualized_return_pct'), digits=2)} "
            f"vs expected {_format_percent(tracking.get('expected_annualized_return_pct'), digits=2)}."
        ),
        (
            f"- Contribution rules: {int(_safe_float(len(contribution_rules.get('rules', []))) or 0)} rule(s), "
            f"base {str((contribution_rules.get('base_rule') or {}).get('type') or 'save')}, "
            f"profile {str(contribution_rules.get('profile_id') or 'n/a')}."
        ),
        (
            f"- Contribution allocation preview: total "
            f"{_format_currency(contribution_allocation_preview.get('total_contributions_usd'))} "
            f"(employee {_format_currency(contribution_allocation_preview.get('employee_contributions_usd'))}, "
            f"employer match {_format_currency(contribution_allocation_preview.get('employer_match_usd'))})."
        ),
        (
            f"- Withdrawal strategy: {str(withdrawal_strategy.get('active') or 'cashflow_only')} "
            f"(source: {str(withdrawal_strategy.get('source') or 'default')})."
        ),
        (
            f"- Drawdown order: {str(withdrawal_strategy.get('drawdown_order') or 'age_aware')} "
            f"(source: {str(withdrawal_strategy.get('drawdown_order_source') or 'default')})."
        ),
    ]

    if baseline_projection:
        scenario_rows = baseline_projection.get("scenarios")
        baseline_row: dict[str, Any] | None = None
        if isinstance(scenario_rows, list):
            for item in scenario_rows:
                if not isinstance(item, dict):
                    continue
                if str(item.get("label") or "").strip().lower() == "baseline":
                    baseline_row = item
                    break
            if baseline_row is None and scenario_rows:
                first = scenario_rows[0]
                if isinstance(first, dict):
                    baseline_row = first

        if isinstance(baseline_row, dict):
            lines.append(
                "- Baseline projection future value "
                f"{_format_currency(baseline_row.get('future_value_usd'))} "
                f"(real {_format_currency(baseline_row.get('real_value_usd'))})."
            )

    lines.extend(
        [
            "",
            "Decisions",
            (
                f"- Open recommendations: {int(_safe_float(recommendations.get('open_count')) or 0)} "
                f"(high priority: {int(_safe_float(recommendations.get('high_priority_count')) or 0)})."
            ),
        ]
    )

    if research_items:
        lines.extend(["", "Research Highlights"])
        for item in research_items[:5]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper() or "?"
            quote_price = _format_currency(item.get("quote_price"))
            period_change = _format_percent(item.get("period_change_pct"), digits=2)
            lines.append(f"- {symbol}: price {quote_price}, {item.get('period_label', 'period')} change {period_change}.")

    if warnings:
        lines.extend(["", "Warnings"])
        for warning in warnings[:4]:
            warning_text = _trim_text(warning, limit=220)
            if warning_text:
                lines.append(f"- {warning_text}")

    full_summary = "\n".join(lines).strip()
    if len(full_summary) <= summary_limit:
        return full_summary, {
            "max_chars": summary_limit,
            "full_chars": len(full_summary),
            "actual_chars": len(full_summary),
            "truncated": False,
        }

    trimmed = f"{full_summary[: summary_limit - 3].rstrip()}..."
    return trimmed, {
        "max_chars": summary_limit,
        "full_chars": len(full_summary),
        "actual_chars": len(trimmed),
        "truncated": True,
    }


def build_context_quality(
    *,
    context_payload: dict[str, Any],
    summary_metadata: dict[str, Any] | None = None,
    snapshot_stale_after_seconds: float = DEFAULT_CONTEXT_SNAPSHOT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    scope = context_payload.get("scope")
    if not isinstance(scope, dict):
        scope = {}
    include_research = bool(scope.get("include_research"))
    requested_plan_id = str(scope.get("plan_id") or "").strip()

    financial_picture = context_payload.get("financial_picture")
    if not isinstance(financial_picture, dict):
        financial_picture = {}
    planning = context_payload.get("planning")
    if not isinstance(planning, dict):
        planning = {}
    decisions = context_payload.get("decisions")
    if not isinstance(decisions, dict):
        decisions = {}
    recommendations = decisions.get("recommendations")
    if not isinstance(recommendations, dict):
        recommendations = {}
    research = context_payload.get("research")
    if not isinstance(research, dict):
        research = {}

    snapshot_summary = financial_picture.get("snapshot_summary")
    if not isinstance(snapshot_summary, dict):
        snapshot_summary = {}
    today_dashboard = financial_picture.get("today_dashboard")
    if not isinstance(today_dashboard, dict):
        today_dashboard = {}
    financial_profile = financial_picture.get("financial_profile")
    if not isinstance(financial_profile, dict):
        financial_profile = {}

    active_plan = planning.get("active_plan")
    has_planning_context = isinstance(active_plan, dict) and bool(active_plan.get("id"))

    research_items = research.get("items")
    has_research_context = isinstance(research_items, list)

    checks: list[tuple[str, bool, bool]] = [
        ("snapshot_summary", bool(snapshot_summary.get("as_of")), True),
        ("today_dashboard", "note" not in today_dashboard, True),
        ("financial_profile", "note" not in financial_profile, True),
        ("recommendations", "note" not in recommendations, True),
        ("planning_context", has_planning_context, bool(requested_plan_id)),
        ("research_context", has_research_context, include_research),
    ]

    expected_checks = [item for item in checks if item[2]]
    passed_checks = [item for item in expected_checks if item[1]]
    missing_sections = [name for name, passed, expected in checks if expected and not passed]
    score_pct = (
        round((len(passed_checks) / len(expected_checks)) * 100.0, 1)
        if expected_checks
        else 100.0
    )

    warnings = normalize_context_warnings(context_payload.get("warnings"))
    freshness = _compute_snapshot_freshness(
        context_payload=context_payload,
        snapshot_stale_after_seconds=snapshot_stale_after_seconds,
    )

    summary_meta = summary_metadata if isinstance(summary_metadata, dict) else {}
    summary_max = int(summary_meta.get("max_chars") or 0)
    summary_full = int(summary_meta.get("full_chars") or 0)
    summary_actual = int(summary_meta.get("actual_chars") or 0)
    summary_truncated = bool(summary_meta.get("truncated"))

    return {
        "freshness": freshness,
        "coverage": {
            "score_pct": score_pct,
            "checks": {name: passed for name, passed, _ in checks},
            "missing_sections": missing_sections,
        },
        "warnings": {
            "count": len(warnings),
            "has_warnings": bool(warnings),
        },
        "summary": {
            "max_chars": summary_max,
            "full_chars": summary_full,
            "actual_chars": summary_actual,
            "truncated": summary_truncated,
        },
    }


def shape_context_payload(
    *,
    context_payload: dict[str, Any],
    detail_level: str = DEFAULT_CONTEXT_DETAIL_LEVEL,
) -> dict[str, Any]:
    resolved_level = normalize_context_detail_level(detail_level)
    if resolved_level == "full":
        return context_payload

    payload = deepcopy(context_payload)

    scope = payload.get("scope")
    if not isinstance(scope, dict):
        scope = {}
    scope["detail_level"] = resolved_level
    payload["scope"] = scope

    financial_picture = payload.get("financial_picture")
    if isinstance(financial_picture, dict):
        snapshot_history = financial_picture.get("snapshot_history")
        if isinstance(snapshot_history, dict):
            financial_picture["snapshot_history"] = {
                "window_points": snapshot_history.get("window_points"),
                "latest_as_of": snapshot_history.get("latest_as_of"),
                "oldest_as_of": snapshot_history.get("oldest_as_of"),
                "delta_total_value_usd": snapshot_history.get("delta_total_value_usd"),
                "delta_total_value_percent": snapshot_history.get("delta_total_value_percent"),
            }

        financial_profile = financial_picture.get("financial_profile")
        if isinstance(financial_profile, dict):
            financial_picture["financial_profile"] = {
                "schema_version": financial_profile.get("schema_version"),
                "updated_at": financial_profile.get("updated_at"),
                "income_items_count": len(financial_profile.get("income_items", []))
                if isinstance(financial_profile.get("income_items"), list)
                else 0,
                "expense_items_count": len(financial_profile.get("expense_items", []))
                if isinstance(financial_profile.get("expense_items"), list)
                else 0,
                "debt_items_count": len(financial_profile.get("debt_items", []))
                if isinstance(financial_profile.get("debt_items"), list)
                else 0,
                "goal_items_count": len(financial_profile.get("goal_items", []))
                if isinstance(financial_profile.get("goal_items"), list)
                else 0,
                "physical_assets_count": len(financial_profile.get("physical_assets", []))
                if isinstance(financial_profile.get("physical_assets"), list)
                else 0,
                "tax_profile": (
                    financial_profile.get("tax_profile")
                    if isinstance(financial_profile.get("tax_profile"), dict)
                    else {}
                ),
                "flags": (
                    financial_profile.get("flags")
                    if isinstance(financial_profile.get("flags"), dict)
                    else {}
                ),
            }

        onboarding_status = financial_picture.get("onboarding_status")
        if isinstance(onboarding_status, dict):
            financial_picture["onboarding_status"] = {
                "completion_percent": onboarding_status.get("completion_percent"),
                "ready_for_daily_review": onboarding_status.get("ready_for_daily_review"),
            }

        watchlist = financial_picture.get("watchlist")
        if isinstance(watchlist, dict):
            financial_picture["watchlist"] = {
                "count": watchlist.get("count"),
                "symbols_preview": (
                    watchlist.get("symbols_preview")
                    if isinstance(watchlist.get("symbols_preview"), list)
                    else []
                ),
                "updated_at": watchlist.get("updated_at"),
            }

    planning = payload.get("planning")
    if isinstance(planning, dict):
        active_plan = planning.get("active_plan")
        if isinstance(active_plan, dict):
            planning["active_plan"] = {
                "id": active_plan.get("id"),
                "title": active_plan.get("title"),
                "description": active_plan.get("description"),
                "updated_at": active_plan.get("updated_at"),
            }

        tracking = planning.get("tracking")
        if isinstance(tracking, dict):
            warnings = tracking.get("warnings")
            planning["tracking"] = {
                "status": tracking.get("status"),
                "actual_annualized_return_pct": tracking.get("actual_annualized_return_pct"),
                "expected_annualized_return_pct": tracking.get("expected_annualized_return_pct"),
                "actual_return_method": tracking.get("actual_return_method"),
                "warnings": warnings[:3] if isinstance(warnings, list) else [],
            }

        assumption_sets = planning.get("assumption_sets")
        if isinstance(assumption_sets, dict):
            sets = assumption_sets.get("sets")
            planning["assumption_sets"] = {
                "schema_version": assumption_sets.get("schema_version"),
                "active_assumption_set_id": assumption_sets.get("active_assumption_set_id"),
                "sets_count": len(sets) if isinstance(sets, list) else 0,
                "set_names": [
                    str(item.get("name") or item.get("id") or "").strip()
                    for item in (sets[:5] if isinstance(sets, list) else [])
                    if isinstance(item, dict)
                ],
            }

        timeline = planning.get("timeline")
        if isinstance(timeline, dict):
            events = timeline.get("events")
            planning["timeline"] = {
                "schema_version": timeline.get("schema_version"),
                "events_count": len(events) if isinstance(events, list) else 0,
                "retirement": (
                    timeline.get("retirement")
                    if isinstance(timeline.get("retirement"), dict)
                    else {}
                ),
            }

        contribution_rules = planning.get("contribution_rules")
        if isinstance(contribution_rules, dict):
            rules = contribution_rules.get("rules")
            planning["contribution_rules"] = {
                "schema_version": contribution_rules.get("schema_version"),
                "base_rule": (
                    contribution_rules.get("base_rule")
                    if isinstance(contribution_rules.get("base_rule"), dict)
                    else {}
                ),
                "profile_id": contribution_rules.get("profile_id"),
                "rules": [item for item in (rules[:5] if isinstance(rules, list) else []) if isinstance(item, dict)],
                "rules_count": len(rules) if isinstance(rules, list) else 0,
                "employer_match_target_usd": contribution_rules.get("employer_match_target_usd"),
                "age": contribution_rules.get("age"),
            }

        allocation_preview = planning.get("contribution_allocation_preview")
        if isinstance(allocation_preview, dict):
            rules = allocation_preview.get("applied_rules")
            account_allocations = allocation_preview.get("account_allocations")
            planning["contribution_allocation_preview"] = {
                "total_contributions_usd": allocation_preview.get("total_contributions_usd"),
                "employee_contributions_usd": allocation_preview.get("employee_contributions_usd"),
                "employer_match_usd": allocation_preview.get("employer_match_usd"),
                "applied_rules": [item for item in (rules[:5] if isinstance(rules, list) else []) if isinstance(item, dict)],
                "account_allocations": [
                    item for item in (account_allocations[:5] if isinstance(account_allocations, list) else [])
                    if isinstance(item, dict)
                ],
            }

        branch_templates = planning.get("branch_templates")
        if isinstance(branch_templates, dict):
            templates = branch_templates.get("templates")
            planning["branch_templates"] = {
                "schema_version": branch_templates.get("schema_version"),
                "default_template_id": branch_templates.get("default_template_id"),
                "templates_count": len(templates) if isinstance(templates, list) else 0,
                "templates": [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "description": _trim_text(item.get("description"), limit=120),
                    }
                    for item in (templates[:5] if isinstance(templates, list) else [])
                    if isinstance(item, dict)
                ],
            }

        baseline_projection = planning.get("baseline_projection")
        if isinstance(baseline_projection, dict):
            scenarios = baseline_projection.get("scenarios")
            planning["baseline_projection"] = {
                "as_of": baseline_projection.get("as_of"),
                "warnings": baseline_projection.get("warnings", []),
                "scenarios": [
                    {
                        "label": item.get("label"),
                        "future_value_usd": item.get("future_value_usd"),
                        "real_value_usd": item.get("real_value_usd"),
                        "annualized_return_pct": item.get("annualized_return_pct"),
                    }
                    for item in (scenarios[:3] if isinstance(scenarios, list) else [])
                    if isinstance(item, dict)
                ],
            }

    decisions = payload.get("decisions")
    if isinstance(decisions, dict):
        recommendations = decisions.get("recommendations")
        if isinstance(recommendations, dict):
            items = recommendations.get("items")
            decisions["recommendations"] = {
                "open_count": recommendations.get("open_count"),
                "high_priority_count": recommendations.get("high_priority_count"),
                "items": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "priority": item.get("priority"),
                        "status": item.get("status"),
                        "plan_id": item.get("plan_id"),
                    }
                    for item in (items[:5] if isinstance(items, list) else [])
                    if isinstance(item, dict)
                ],
            }

        plan_decisions = decisions.get("plan_decisions_recent")
        if isinstance(plan_decisions, list):
            decisions["plan_decisions_recent"] = [
                {
                    "id": item.get("id"),
                    "status": item.get("status"),
                    "summary": _trim_text(item.get("summary"), limit=140),
                    "created_at": item.get("created_at"),
                }
                for item in plan_decisions[:5]
                if isinstance(item, dict)
            ]

    research = payload.get("research")
    if isinstance(research, dict):
        items = research.get("items")
        research["items"] = [
            {
                "symbol": item.get("symbol"),
                "quote_available": item.get("quote_available"),
                "quote_price": item.get("quote_price"),
                "quote_change_pct": item.get("quote_change_pct"),
                "history_available": item.get("history_available"),
                "period_label": item.get("period_label"),
                "period_change_pct": item.get("period_change_pct"),
            }
            for item in (items[:5] if isinstance(items, list) else [])
            if isinstance(item, dict)
        ]

    return payload


def build_context_summary(
    *,
    context_payload: dict[str, Any],
    max_chars: int = DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
) -> str:
    summary, _ = build_context_summary_with_metadata(
        context_payload=context_payload,
        max_chars=max_chars,
    )
    return summary
