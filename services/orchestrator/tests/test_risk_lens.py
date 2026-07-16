from __future__ import annotations

from buildwealth_orchestrator.services.risk_lens import (
    build_risk_comparison,
    normalize_risk_posture,
    resolve_risk_lens,
)


def _profile(risk: str | None = "moderate") -> dict:
    return {
        "updated_at": "2026-07-15T00:00:00Z",
        "investment_policy": {"risk_tolerance": risk},
        "expense_items": [{"monthly_amount_usd": 4_000}],
        "debt_items": [{"minimum_payment_usd": 1_000}],
    }


def test_balanced_alias_normalizes_to_canonical_moderate() -> None:
    assert normalize_risk_posture("balanced") == "moderate"


def test_override_is_reversible_and_does_not_mutate_profile() -> None:
    profile = _profile("moderate")
    lens = resolve_risk_lens(
        {"mode": "override", "posture": "aggressive"},
        profile=profile,
    )

    assert lens["effective_posture"] == "aggressive"
    assert lens["profile_posture"] == "moderate"
    assert lens["is_override"] is True
    assert profile["investment_policy"]["risk_tolerance"] == "moderate"


def test_comparison_freezes_inputs_and_always_returns_every_posture() -> None:
    profile = _profile("moderate")
    lens = resolve_risk_lens({"mode": "profile"}, profile=profile)
    comparison = build_risk_comparison(
        question="Compare risk tolerance",
        profile=profile,
        holdings={"total_cash": 20_000, "updated_at": "2026-07-15T00:00:00Z"},
        lens=lens,
        plan_id="plan-1",
        source_turn_id="turn-1",
    )

    assert [item["posture"] for item in comparison["variants"]] == [
        "conservative",
        "moderate",
        "aggressive",
    ]
    assert len({item["reserve_months"] for item in comparison["variants"]}) == 3
    assert comparison["policy"] == {
        "exploration_is_never_blocked": True,
        "warnings_are_advisory": True,
        "saved_profile_changed": False,
    }
    assert comparison["frozen_conditions"]["total_cash_usd"] == 20_000
    assert comparison["frozen_conditions"]["monthly_outflow_usd"] == 5_000
    assert comparison["source_turn_id"] == "turn-1"
    assert comparison["policy_version"] == "cash-liquidity-v1"
    assert comparison["adapter_versions"] == {"cash_liquidity": "v1"}
    assert all(item["exploration_status"] == "complete" for item in comparison["variants"])
    assert any(item["recommendation_status"] == "caution" for item in comparison["variants"])
    assert len({item["leading_candidate"] for item in comparison["variants"]}) == 3
    assert all(item["upside"] and item["downside"] for item in comparison["variants"])


def test_missing_capacity_is_partial_not_unavailable() -> None:
    profile = _profile("moderate")
    profile["expense_items"] = []
    profile["debt_items"] = []
    comparison = build_risk_comparison(
        question="Compare risk tolerance",
        profile=profile,
        holdings={"total_cash": 20_000},
        lens=resolve_risk_lens({"mode": "profile"}, profile=profile),
    )

    assert len(comparison["variants"]) == 3
    assert all(item["exploration_status"] == "partial" for item in comparison["variants"])
    assert all(item["capacity_fit"] == "unknown" for item in comparison["variants"])


def test_not_recommended_capacity_never_makes_exploration_unavailable() -> None:
    profile = _profile("moderate")
    comparison = build_risk_comparison(
        question="Show risky positions too",
        profile=profile,
        holdings={"total_cash": 10_000},
        lens=resolve_risk_lens({"mode": "override", "posture": "aggressive"}, profile=profile),
    )

    assert all(item["recommendation_status"] == "not_recommended" for item in comparison["variants"])
    assert all(item["capacity_fit"] == "exceeds" for item in comparison["variants"])
    assert all(item["exploration_status"] == "complete" for item in comparison["variants"])
    assert all("blocked" in item["action"] for item in comparison["variants"])
