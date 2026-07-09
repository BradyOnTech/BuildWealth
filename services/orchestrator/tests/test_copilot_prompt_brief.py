"""Tests for slim Copilot Prompt Brief builder (Session Focus design PR1)."""

from __future__ import annotations

import json

from buildwealth_orchestrator.services.copilot_prompt_brief import (
    BRIEF_HARD_MAX_CHARS,
    BRIEF_VERSION,
    build_copilot_prompt_brief,
)


def _base_assembled(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "generated_at": "2026-07-09T00:00:00+00:00",
        "scope": {
            "plan_id": "plan-1",
            "detail_level": "light",
            "use_live_snapshot": False,
            "include_research": False,
            "include_plan_projection": False,
        },
        "summary": "BuildWealth Unified Context\nPortfolio value $100,000.",
        "quality": {
            "freshness": {"snapshot_stale": False, "generated_at": "2026-07-09T00:00:00+00:00"},
            "coverage": {"score_pct": 90.0, "checks": {}, "missing_sections": []},
            "warnings": {"count": 0, "has_warnings": False},
            "summary": {"max_chars": 1800, "full_chars": 40, "actual_chars": 40, "truncated": False},
        },
        "warnings": [],
        "financial_picture": {
            "snapshot_summary": {
                "as_of": "2026-07-08T00:00:00+00:00",
                "total_value_usd": 100_000,
                "net_performance_usd": 1_000,
                "net_performance_percent": 1.0,
            },
            "today_dashboard": {
                "net_worth_usd": 250_000,
                "monthly_surplus_usd": 2_000,
                "savings_rate_pct": 20.0,
            },
            "financial_profile": {
                "updated_at": "2026-07-01T00:00:00+00:00",
                "income_items": [{"label": "Salary", "amount_usd": 10000}],
                "expense_items": [{"label": "Rent", "amount_usd": 2000}],
                "debt_items": [],
                "goal_items": [{"label": "Retirement", "target_amount_usd": 1_000_000}],
                "physical_assets": [],
                "tax_profile": {"filing_status": "single", "marginal_tax_rate": 0.24},
                "investment_policy": {"max_single_symbol_exposure_pct": 10},
                "flags": {},
            },
            "onboarding_status": {"completion_percent": 80, "ready_for_daily_review": True},
            "watchlist": {"count": 2, "symbols_preview": ["AAPL", "MSFT"]},
        },
        "planning": {
            "active_plan": {"id": "plan-1", "title": "Primary", "updated_at": "2026-07-01T00:00:00+00:00"},
            "tracking": {
                "status": "on_track",
                "actual_annualized_return_pct": 7.0,
                "expected_annualized_return_pct": 6.5,
            },
        },
        "research": {"symbols": [], "items": []},
        "decisions": {
            "recommendations": {
                "open_count": 1,
                "high_priority_count": 1,
                "items": [
                    {
                        "id": "rec-1",
                        "title": "Review cash runway",
                        "priority": "high",
                        "status": "proposed",
                    }
                ],
            }
        },
        "retrieved_context": {
            "count": 1,
            "items": [
                {
                    "id": "ctx_1",
                    "domain": "profile",
                    "entity_type": "tax_profile_field",
                    "source_ref": "profile/financial_profile.json#tax_profile",
                    "authority": "canonical",
                    "materiality": "high",
                    "text": "Marginal tax rate is 24%.",
                    "score": 0.9,
                }
            ],
        },
        "citations": [
            {"context_item_id": "ctx_1", "source_ref": "profile/financial_profile.json#tax_profile", "domain": "profile"}
        ],
        "context_budget": {"truncated": False, "returned_items": 1},
        "conflicts": [
            {
                "type": "material_mismatch",
                "severity": "high",
                "plain_language": "Tax profile needs review before decision-grade advice.",
                "blocks_decision_grade_advice": True,
                "source_refs": ["profile/tax"],
            }
        ],
        "trace": {
            "assembler_version": "context_intelligence_assembler_v1",
            "intent": {
                "intent": "profile_question",
                "confidence": "medium",
                "domains": ["profile", "plan", "recommendation"],
            },
            "context_warnings": [],
            "registry": {"item_count": 49, "database_path": "data/storage/context_index.db"},
        },
        "cache": {"enabled": True, "research": {"hit": False}},
    }
    payload.update(overrides)
    return payload


def test_brief_includes_required_fields_and_version() -> None:
    brief_text = build_copilot_prompt_brief(_base_assembled())
    brief = json.loads(brief_text)

    assert brief["brief_version"] == BRIEF_VERSION
    assert "summary" in brief
    assert "quality" in brief
    assert "scope" in brief
    assert "focused_structured" in brief
    assert "retrieved_context" in brief
    assert "citations" in brief
    assert "conflicts" in brief
    assert "safety_warnings" in brief
    assert "tool_guidance" in brief
    assert "session_focus" in brief
    assert brief["intent"]["intent"] == "profile_question"
    assert brief["scope"]["plan_id"] == "plan-1"
    assert brief["retrieved_context"]["items"][0]["id"] == "ctx_1"
    assert brief["conflicts"][0]["blocks_decision_grade_advice"] is True


def test_brief_omits_full_trace_registry_and_cache() -> None:
    brief_text = build_copilot_prompt_brief(_base_assembled())
    brief = json.loads(brief_text)

    assert "trace" not in brief
    assert "registry" not in brief
    assert "cache" not in brief
    assert "assembler_version" not in brief
    # Compact JSON — no pretty-print indent.
    assert "\n" not in brief_text


def test_brief_preserves_safety_warnings_from_conflicts_and_high_priority() -> None:
    brief = json.loads(build_copilot_prompt_brief(_base_assembled()))
    messages = [str(item.get("message") or "") for item in brief["safety_warnings"]]
    assert any("Tax profile needs review" in msg for msg in messages)
    assert any("high-priority open recommendation" in msg for msg in messages)


def test_fat_profile_fixture_stays_under_hard_max() -> None:
    fat_items = [
        {
            "id": f"ctx_{index}",
            "domain": "plan",
            "entity_type": "decision",
            "source_ref": f"plans/plan-1/decisions/{index}",
            "authority": "canonical",
            "materiality": "medium",
            "text": ("Decision narrative with lots of filler words. " * 80),
            "score": 0.5,
        }
        for index in range(40)
    ]
    fat_profile = {
        "updated_at": "2026-07-01T00:00:00+00:00",
        "income_items": [{"label": f"Income {i}", "amount_usd": 1000 + i, "notes": "x" * 200} for i in range(50)],
        "expense_items": [{"label": f"Expense {i}", "amount_usd": 100 + i, "notes": "y" * 200} for i in range(80)],
        "debt_items": [{"label": f"Debt {i}", "balance_usd": 5000 + i, "notes": "z" * 200} for i in range(20)],
        "goal_items": [{"label": f"Goal {i}", "target_amount_usd": 10000 * i, "notes": "g" * 200} for i in range(30)],
        "physical_assets": [{"label": f"Asset {i}", "current_value_usd": 2000 * i} for i in range(25)],
        "tax_profile": {"filing_status": "married_joint", "marginal_tax_rate": 0.32, "state": "CA"},
        "investment_policy": {"max_single_symbol_exposure_pct": 5, "notes": "p" * 500},
        "flags": {},
    }
    assembled = _base_assembled(
        financial_picture={
            "snapshot_summary": {
                "as_of": "2026-07-08T00:00:00+00:00",
                "total_value_usd": 1_000_000,
                "net_performance_usd": 50_000,
                "net_performance_percent": 5.0,
                "top_holdings": [{"symbol": f"SYM{i}", "weight_pct": 1.0} for i in range(100)],
            },
            "today_dashboard": {
                "net_worth_usd": 2_000_000,
                "monthly_surplus_usd": 5_000,
                "savings_rate_pct": 30.0,
                "extra": "d" * 5000,
            },
            "financial_profile": fat_profile,
            "onboarding_status": {"completion_percent": 100, "ready_for_daily_review": True},
            "watchlist": {
                "count": 50,
                "symbols_preview": [f"T{i}" for i in range(50)],
                "items": [{"symbol": f"T{i}", "notes": "n" * 300} for i in range(50)],
            },
        },
        retrieved_context={"count": len(fat_items), "items": fat_items},
        citations=[
            {"context_item_id": f"ctx_{i}", "source_ref": f"ref/{i}", "domain": "plan"} for i in range(40)
        ],
        summary=("Huge summary line. " * 400),
        conflicts=[
            {
                "type": "material_mismatch",
                "severity": "critical",
                "plain_language": "Critical conflict: liquidity vs equity concentration.",
                "blocks_decision_grade_advice": True,
                "source_refs": ["portfolio", "plan"],
            }
        ],
    )

    brief_text = build_copilot_prompt_brief(assembled)
    brief = json.loads(brief_text)

    assert len(brief_text) < BRIEF_HARD_MAX_CHARS
    assert brief["brief_version"] == BRIEF_VERSION
    assert isinstance(brief.get("safety_warnings"), list)
    assert any(
        "Critical conflict" in str(item.get("message") or "") for item in brief["safety_warnings"]
    )
    # Full income arrays must not appear in the brief.
    assert "Income 49" not in brief_text
    assert "Decision narrative with lots of filler words." * 5 not in brief_text or brief.get(
        "brief_truncated"
    )


def test_stale_snapshot_adds_quality_safety_warning() -> None:
    assembled = _base_assembled()
    quality = dict(assembled["quality"])  # type: ignore[arg-type]
    freshness = dict(quality["freshness"])  # type: ignore[arg-type]
    freshness["snapshot_stale"] = True
    quality["freshness"] = freshness
    assembled["quality"] = quality
    assembled["conflicts"] = []
    assembled["decisions"] = {"recommendations": {"open_count": 0, "high_priority_count": 0, "items": []}}

    brief = json.loads(build_copilot_prompt_brief(assembled))
    messages = [str(item.get("message") or "") for item in brief["safety_warnings"]]
    assert any("stale" in msg.lower() for msg in messages)
