from buildwealth_orchestrator.services.buildwealth_context import (
    build_context_summary,
    derive_research_symbols,
    normalize_research_symbols,
)


def test_normalize_research_symbols_dedupes_and_bounds() -> None:
    symbols = normalize_research_symbols(
        ["aapl", "MSFT", "msft", "  ", None, "brk.b", "^bad", "TSLA"],
        max_symbols=4,
    )

    assert symbols == ["AAPL", "MSFT", "BRK.B", "BAD"]


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

    summary = build_context_summary(context_payload=payload, max_chars=700)

    assert "BuildWealth Unified Context" in summary
    assert "Financial Picture" in summary
    assert "Planning" in summary
    assert "Decisions" in summary
    assert "Research Highlights" in summary
    assert len(summary) <= 700
