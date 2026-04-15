from buildwealth_orchestrator.services.buildwealth_context import (
    build_context_quality,
    build_context_summary,
    build_context_summary_with_metadata,
    derive_research_symbols,
    normalize_context_detail_level,
    normalize_context_warnings,
    normalize_research_symbols,
    shape_context_payload,
)


def test_normalize_research_symbols_dedupes_and_bounds() -> None:
    symbols = normalize_research_symbols(
        ["aapl", "MSFT", "msft", "  ", None, "brk.b", "^bad", "TSLA"],
        max_symbols=4,
    )

    assert symbols == ["AAPL", "MSFT", "BRK.B", "BAD"]


def test_normalize_research_symbols_accepts_tuple_inputs() -> None:
    symbols = normalize_research_symbols(("msft", "aapl", "msft", "", None))

    assert symbols == ["MSFT", "AAPL"]


def test_derive_research_symbols_uses_requested_then_top_holdings() -> None:
    snapshot_summary = {
        "top_holdings": [
            {"symbol": "VTI"},
            {"symbol": "VXUS"},
            {"symbol": "AAPL"},
        ]
    }

    symbols = derive_research_symbols(
        requested_symbols=["aapl", "msft"],
        snapshot_summary=snapshot_summary,
        max_symbols=4,
    )

    assert symbols == ["AAPL", "MSFT", "VTI", "VXUS"]


def test_derive_research_symbols_includes_watchlist_before_holdings() -> None:
    snapshot_summary = {
        "top_holdings": [
            {"symbol": "VTI"},
            {"symbol": "VXUS"},
            {"symbol": "AAPL"},
        ]
    }

    symbols = derive_research_symbols(
        requested_symbols=["msft"],
        watchlist_symbols=["nvda", "vti"],
        snapshot_summary=snapshot_summary,
        max_symbols=5,
    )

    assert symbols == ["MSFT", "NVDA", "VTI", "VXUS", "AAPL"]


def test_build_context_summary_contains_core_sections_and_trims() -> None:
    payload = {
        "generated_at": "2026-04-12T12:00:00+00:00",
        "financial_picture": {
            "snapshot_summary": {
                "total_value_usd": 350000.0,
                "net_performance_usd": 50000.0,
                "net_performance_percent": 16.2,
            },
            "today_dashboard": {
                "net_worth_usd": 420000.0,
                "monthly_surplus_usd": 1200.0,
                "savings_rate_pct": 18.4,
            },
        },
        "planning": {
            "active_plan": {"id": "plan-1", "title": "Primary Plan"},
            "tracking": {
                "status": "on_track",
                "actual_annualized_return_pct": 7.4,
                "expected_annualized_return_pct": 7.0,
            },
            "baseline_projection": {
                "scenarios": [
                    {"label": "baseline", "future_value_usd": 2100000.0, "real_value_usd": 1200000.0}
                ]
            },
        },
        "decisions": {"recommendations": {"open_count": 3, "high_priority_count": 1}},
        "research": {
            "items": [
                {"symbol": "AAPL", "quote_price": 201.4, "period_label": "6mo", "period_change_pct": 8.2}
            ]
        },
        "warnings": ["OpenBB quote endpoint unavailable for one symbol."],
    }

    summary = build_context_summary(context_payload=payload, max_chars=1200)

    assert "BuildWealth Unified Context" in summary
    assert "Financial Picture" in summary
    assert "Planning" in summary
    assert "Decisions" in summary
    assert "Research" in summary
    assert len(summary) <= 1200


def test_build_context_summary_includes_planning_controls() -> None:
    payload = {
        "generated_at": "2026-04-14T18:45:00+00:00",
        "financial_picture": {
            "snapshot_summary": {
                "total_value_usd": 500000.0,
                "net_performance_usd": 65000.0,
                "net_performance_percent": 14.95,
            },
            "today_dashboard": {
                "net_worth_usd": 620000.0,
                "monthly_surplus_usd": 1500.0,
                "savings_rate_pct": 22.0,
            },
            "watchlist": {
                "count": 2,
                "symbols_preview": ["NVDA", "MSFT"],
            },
        },
        "planning": {
            "active_plan": {"id": "plan-1", "title": "Retirement 2055"},
            "tracking": {
                "status": "on_track",
                "actual_annualized_return_pct": 7.2,
                "expected_annualized_return_pct": 6.9,
            },
            "contribution_rules": {
                "base_rule": {"type": "save"},
                "rules": [{"account_type": "traditional_401k", "priority": 1}],
                "profile_id": "tax_optimized_high_earner",
            },
            "contribution_allocation_preview": {
                "total_contributions_usd": 30000.0,
                "employee_contributions_usd": 24000.0,
                "employer_match_usd": 6000.0,
            },
            "withdrawal_strategy": {"active": "dynamic_guardrails", "source": "settings"},
            "household": {"mode": "couple", "filing_status": "married_filing_jointly", "source": "settings"},
        },
        "decisions": {"recommendations": {"open_count": 2, "high_priority_count": 1}},
        "research": {"items": []},
        "warnings": [],
    }

    summary = build_context_summary(context_payload=payload, max_chars=2000)

    assert "Contribution rules:" in summary
    assert "Contribution allocation preview:" in summary
    assert "Watchlist: 2 item(s) (NVDA, MSFT)." in summary
    assert "Withdrawal strategy: dynamic_guardrails" in summary
    assert "Household mode: couple" in summary


def test_build_context_summary_with_metadata_reports_truncation() -> None:
    payload = {
        "generated_at": "2026-04-14T18:45:00+00:00",
        "financial_picture": {
            "snapshot_summary": {
                "as_of": "2026-04-14T17:45:00+00:00",
                "total_value_usd": 500000.0,
                "net_performance_usd": 65000.0,
                "net_performance_percent": 14.95,
            },
            "today_dashboard": {
                "net_worth_usd": 620000.0,
                "monthly_surplus_usd": 1500.0,
                "savings_rate_pct": 22.0,
            },
            "watchlist": {
                "count": 4,
                "symbols_preview": ["NVDA", "MSFT", "AAPL", "GOOGL"],
            },
        },
        "planning": {
            "active_plan": {"id": "plan-1", "title": "Retirement 2055"},
            "tracking": {
                "status": "on_track",
                "actual_annualized_return_pct": 7.2,
                "expected_annualized_return_pct": 6.9,
            },
        },
        "decisions": {"recommendations": {"open_count": 2, "high_priority_count": 1}},
        "research": {"items": [{"symbol": "AAPL", "quote_price": 210.0, "period_label": "6mo", "period_change_pct": 8.1}]},
        "warnings": [],
    }

    summary, metadata = build_context_summary_with_metadata(context_payload=payload, max_chars=420)

    assert metadata["max_chars"] == 420
    assert metadata["truncated"] is True
    assert metadata["actual_chars"] <= 420
    assert metadata["full_chars"] > metadata["actual_chars"]
    assert len(summary) <= 420


def test_build_context_quality_reports_freshness_and_coverage() -> None:
    payload = {
        "generated_at": "2026-04-14T12:00:00+00:00",
        "scope": {
            "plan_id": "plan-1",
            "include_research": True,
        },
        "financial_picture": {
            "snapshot_summary": {
                "as_of": "2026-04-12T12:00:00+00:00",
            },
            "today_dashboard": {"note": "unavailable"},
            "financial_profile": {"schema_version": 2},
        },
        "planning": {
            "active_plan": {"id": "plan-1"},
        },
        "research": {"items": []},
        "decisions": {"recommendations": {"open_count": 0, "high_priority_count": 0}},
        "warnings": ["A warning", "A warning"],
    }

    quality = build_context_quality(
        context_payload=payload,
        summary_metadata={"max_chars": 800, "full_chars": 900, "actual_chars": 800, "truncated": True},
        snapshot_stale_after_seconds=3600,
    )

    freshness = quality["freshness"]
    assert freshness["snapshot_stale"] is True
    assert freshness["snapshot_age_seconds"] == 172800.0
    assert freshness["snapshot_stale_threshold_seconds"] == 3600.0

    coverage = quality["coverage"]
    assert coverage["checks"]["planning_context"] is True
    assert coverage["checks"]["today_dashboard"] is False
    assert "today_dashboard" in coverage["missing_sections"]
    assert coverage["score_pct"] < 100

    warnings = quality["warnings"]
    assert warnings["count"] == 1
    assert warnings["has_warnings"] is True

    summary_meta = quality["summary"]
    assert summary_meta["truncated"] is True
    assert summary_meta["actual_chars"] == 800


def test_normalize_context_warnings_dedupes_and_caps() -> None:
    warnings = normalize_context_warnings(
        [" one ", "One", "", None, "two", "three", "two", "four"],
        max_warnings=3,
    )

    assert warnings == ["one", "two", "three"]


def test_normalize_context_detail_level_falls_back_to_default() -> None:
    assert normalize_context_detail_level("light") == "light"
    assert normalize_context_detail_level("FULL") == "full"
    assert normalize_context_detail_level("invalid", default="light") == "light"


def test_shape_context_payload_light_reduces_heavy_sections() -> None:
    payload = {
        "scope": {
            "detail_level": "full",
            "include_research": True,
        },
        "financial_picture": {
            "snapshot_history": {
                "window_points": 30,
                "latest_as_of": "2026-04-14T00:00:00+00:00",
                "oldest_as_of": "2026-03-15T00:00:00+00:00",
                "delta_total_value_usd": 1234.56,
                "delta_total_value_percent": 2.5,
                "points": [{"as_of": "2026-04-14T00:00:00+00:00", "total_value_usd": 1000.0}],
            },
            "financial_profile": {
                "schema_version": 2,
                "updated_at": "2026-04-14T00:00:00+00:00",
                "income_items": [{"label": "Salary"}],
                "expense_items": [{"label": "Rent"}],
                "debt_items": [],
                "goal_items": [{"name": "Emergency"}],
                "physical_assets": [{"name": "Home"}],
                "tax_profile": {"filing_status": "single"},
                "flags": {"ready": True},
            },
            "watchlist": {
                "count": 8,
                "symbols_preview": ["AAPL", "MSFT"],
                "items": [{"symbol": "AAPL"}],
                "updated_at": "2026-04-14T00:00:00+00:00",
            },
        },
        "planning": {
            "active_plan": {
                "id": "plan-1",
                "title": "Primary Plan",
                "description": "Detailed plan payload",
                "updated_at": "2026-04-14T00:00:00+00:00",
                "settings": {"years": 30},
            },
            "tracking": {
                "status": "on_track",
                "actual_annualized_return_pct": 7.1,
                "expected_annualized_return_pct": 6.8,
                "actual_return_method": "dietz",
                "warnings": ["one", "two", "three", "four"],
            },
            "assumption_sets": {
                "schema_version": 2,
                "active_assumption_set_id": "set-1",
                "sets": [{"id": "set-1", "name": "Default"}],
            },
            "timeline": {
                "schema_version": 2,
                "events": [{"id": "event-1"}],
                "retirement": {"target_retirement_age": 60},
            },
            "contribution_rules": {
                "schema_version": 2,
                "base_rule": {"type": "save"},
                "profile_id": "default",
                "rules": [{"priority": 1}],
                "employer_match_target_usd": 1000,
                "age": 40,
            },
            "contribution_allocation_preview": {
                "total_contributions_usd": 10000,
                "employee_contributions_usd": 8000,
                "employer_match_usd": 2000,
                "applied_rules": [{"priority": 1}],
                "account_allocations": [{"account_id": "a1"}],
            },
            "branch_templates": {
                "schema_version": 2,
                "default_template_id": "t1",
                "templates": [{"id": "t1", "name": "Base", "description": "A long description here"}],
            },
            "baseline_projection": {
                "as_of": "2026-04-14T00:00:00+00:00",
                "warnings": [],
                "scenarios": [{"label": "baseline", "future_value_usd": 1.0}],
            },
        },
        "decisions": {
            "recommendations": {
                "open_count": 1,
                "high_priority_count": 1,
                "items": [{"id": "r1", "title": "Do thing", "priority": "high", "status": "proposed"}],
            },
            "plan_decisions_recent": [
                {"id": "d1", "status": "accepted", "summary": "Long summary text", "created_at": "2026-04-14T00:00:00+00:00"}
            ],
        },
        "research": {
            "items": [
                {"symbol": "AAPL", "quote_available": True, "quote_price": 200.0, "history_available": True, "period_label": "6mo"},
                {"symbol": "MSFT", "quote_available": True, "quote_price": 300.0, "history_available": True, "period_label": "6mo"},
                {"symbol": "NVDA", "quote_available": True, "quote_price": 400.0, "history_available": True, "period_label": "6mo"},
                {"symbol": "TSLA", "quote_available": True, "quote_price": 500.0, "history_available": True, "period_label": "6mo"},
                {"symbol": "GOOGL", "quote_available": True, "quote_price": 600.0, "history_available": True, "period_label": "6mo"},
                {"symbol": "META", "quote_available": True, "quote_price": 700.0, "history_available": True, "period_label": "6mo"},
            ]
        },
    }

    shaped = shape_context_payload(context_payload=payload, detail_level="light")

    assert shaped["scope"]["detail_level"] == "light"
    assert "points" not in shaped["financial_picture"]["snapshot_history"]
    assert "income_items" not in shaped["financial_picture"]["financial_profile"]
    assert shaped["financial_picture"]["financial_profile"]["income_items_count"] == 1
    assert "settings" not in shaped["planning"]["active_plan"]
    assert len(shaped["planning"]["tracking"]["warnings"]) == 3
    assert shaped["planning"]["branch_templates"]["templates_count"] == 1
    assert len(shaped["research"]["items"]) == 5
