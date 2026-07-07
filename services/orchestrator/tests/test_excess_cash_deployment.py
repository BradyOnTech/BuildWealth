"""Spare money gets a destination: excess cash deploys against saved targets."""

from __future__ import annotations

from buildwealth_orchestrator.services.portfolio_rebalancing import build_excess_cash_deployment
from buildwealth_orchestrator.services.recommendation_factory import (
    generate_cash_liquidity_recommendations,
)


def _holdings() -> dict:
    # Investable: 56k equity + 4k fixed income (+ home excluded).
    return {
        "a:VTI": {"symbol": "VTI", "asset_class": "equity", "asset_type": "etf", "current_value": 56_000.0},
        "a:BND": {"symbol": "BND", "asset_class": "fixed_income", "asset_type": "etf", "current_value": 4_000.0},
        "a:HOME": {"symbol": "MY_HOME", "asset_class": "real_estate", "asset_type": "property", "current_value": 400_000.0},
    }


_TARGETS = {"equity": 60, "fixed_income": 25, "real_estate": 10, "cash": 5}


def test_gaps_fill_first_then_target_weights() -> None:
    plan = build_excess_cash_deployment(
        excess_cash_usd=50_000.0,
        holdings=_holdings(),
        targets_pct=_TARGETS,
        total_market_value=460_000.0,
    )
    assert plan["status"] == "ready"
    rows = plan["rows"]
    # One row per class (gap fill and remainder merged), never into cash.
    assert len({row["asset_class"] for row in rows}) == len(rows)
    assert all(row["asset_class"] != "cash" for row in rows)
    by_class = {row["asset_class"]: row for row in rows}
    # Investable base is 60k: fixed income sits at 6.7% vs 25%, real estate
    # funds at 0% vs 10% — both receive gap money plus their target share.
    assert by_class["fixed_income"]["reason"] == "closes_gap"
    assert by_class["fixed_income"]["add_candidates"] == ["BND"]
    assert by_class["real_estate"]["reason"] == "closes_gap"
    assert by_class["equity"]["reason"] == "target_weight"
    assert by_class["equity"]["add_candidates"] == ["VTI"]
    # Every excess dollar is placed.
    assert round(sum(row["amount_usd"] for row in rows), 0) == 50_000.0
    assert "One way to deploy it against your saved targets" in plan["sentence"]
    assert "A suggestion to review, not an order." in plan["sentence"]
    # Each class reads once in the sentence.
    assert plan["sentence"].count("fixed income") == 1


def test_no_targets_means_no_pretend_plan() -> None:
    plan = build_excess_cash_deployment(
        excess_cash_usd=50_000.0,
        holdings=_holdings(),
        targets_pct={},
        total_market_value=460_000.0,
    )
    assert plan["status"] == "no_targets"
    assert plan["rows"] == []


def test_excess_cash_recommendation_names_destinations() -> None:
    holdings_payload = {
        "holdings": _holdings(),
        "total_cash": 71_000.0,  # 6-month reserve at $3.5k/mo is $21k → $50k excess
        "total_value": 460_000.0,
    }
    profile = {
        "expense_items": [{"id": "e1", "label": "Living", "monthly_amount_usd": 3_500.0}],
        "debt_items": [],
        "investment_policy": {"target_asset_class_allocation_pct": _TARGETS},
    }
    result = generate_cash_liquidity_recommendations(
        holdings_payload=holdings_payload,
        financial_profile_payload=profile,
        existing_recommendations=[],
        dry_run=True,
    )
    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["title"] == "Review excess idle cash"
    assert "$50,000 to review" in candidate["detail"]
    assert "One way to deploy it against your saved targets" in candidate["detail"]
    assert "add to BND" in candidate["detail"]
    assert "add to VTI" in candidate["detail"]
    deployment = candidate["action_payload"]["suggested_action"]["deployment_plan"]
    by_class = {row["asset_class"]: row for row in deployment}
    assert by_class["fixed_income"]["reason"] == "closes_gap"
    assert by_class["equity"]["reason"] == "target_weight"


def test_without_targets_the_recommendation_stays_generic() -> None:
    holdings_payload = {
        "holdings": _holdings(),
        "total_cash": 71_000.0,
        "total_value": 460_000.0,
    }
    profile = {
        "expense_items": [{"id": "e1", "label": "Living", "monthly_amount_usd": 3_500.0}],
        "debt_items": [],
        "investment_policy": {},
    }
    result = generate_cash_liquidity_recommendations(
        holdings_payload=holdings_payload,
        financial_profile_payload=profile,
        existing_recommendations=[],
        dry_run=True,
    )
    candidate = result.candidates[0]
    assert "to review for goals, debt payoff, or investing." in candidate["detail"]
    assert "One way to deploy" not in candidate["detail"]
    assert candidate["action_payload"]["suggested_action"]["deployment_plan"] == []
