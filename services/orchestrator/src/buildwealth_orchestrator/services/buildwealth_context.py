"""Helpers for unified BuildWealth context packaging across portfolio/planning/research."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

DEFAULT_RESEARCH_SYMBOL_LIMIT = 5
DEFAULT_CONTEXT_SUMMARY_MAX_CHARS = 2400
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


def build_context_summary(
    *,
    context_payload: dict[str, Any],
    max_chars: int = DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
) -> str:
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

    summary = "\n".join(lines).strip()
    if len(summary) <= summary_limit:
        return summary
    return f"{summary[: summary_limit - 3].rstrip()}..."
