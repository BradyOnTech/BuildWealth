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


def test_near_dated_goals_claim_cash_before_investing() -> None:
    plan = build_excess_cash_deployment(
        excess_cash_usd=50_000.0,
        holdings=_holdings(),
        targets_pct=_TARGETS,
        total_market_value=460_000.0,
        goal_items=[
            {"id": "g1", "label": "House down payment", "target_amount_usd": 30_000.0, "target_date": "2027-06-01T00:00:00+00:00", "priority": "high"},
            {"id": "g2", "label": "Retirement", "target_amount_usd": 900_000.0, "target_date": "2060-01-01T00:00:00+00:00", "priority": "high"},
        ],
        now=__import__("datetime").datetime(2026, 7, 7, tzinfo=__import__("datetime").timezone.utc),
    )
    rows = plan["rows"]
    # The 2027 goal claims its $30k first, held as cash; the 2060 goal is
    # beyond the cash horizon and claims nothing.
    assert rows[0]["reason"] == "goal_reserve"
    assert rows[0]["goal_label"] == "House down payment"
    assert rows[0]["amount_usd"] == 30_000.0
    assert not any(row.get("goal_label") == "Retirement" for row in rows)
    # Only the remaining $20k gets invest suggestions.
    invested = sum(row["amount_usd"] for row in rows if row["reason"] != "goal_reserve")
    assert round(invested, 0) == 20_000.0
    assert "goals first" in plan["sentence"]
    assert "set aside in cash for House down payment (due 2027)" in plan["sentence"]


def test_risk_tolerance_scales_the_reserve_ceiling() -> None:
    def run(policy: dict) -> object:
        return generate_cash_liquidity_recommendations(
            holdings_payload={"holdings": _holdings(), "total_cash": 28_000.0, "total_value": 460_000.0},
            financial_profile_payload={
                "expense_items": [{"id": "e1", "label": "Living", "monthly_amount_usd": 3_500.0}],
                "debt_items": [],
                "investment_policy": policy,
            },
            existing_recommendations=[],
            dry_run=True,
        )

    # $28k on $3.5k/mo = 8 months of cash.
    # Moderate (6-month ceiling): flagged as excess.
    moderate = run({"risk_tolerance": "moderate", "target_asset_class_allocation_pct": _TARGETS})
    assert moderate.generated_count == 1
    assert "6-month reserve target" in moderate.candidates[0]["detail"]
    # Conservative (9-month ceiling): an 8-month cushion is a choice, not idle.
    conservative = run({"risk_tolerance": "conservative", "target_asset_class_allocation_pct": _TARGETS})
    assert conservative.generated_count == 0
    # Aggressive (4-month ceiling): flagged sooner, and the sentence says why.
    aggressive = run({"risk_tolerance": "aggressive", "target_asset_class_allocation_pct": _TARGETS})
    assert aggressive.generated_count == 1
    assert "4-month reserve target" in aggressive.candidates[0]["detail"]
    assert "fits a aggressive risk tolerance" in aggressive.candidates[0]["detail"]


def test_missing_goals_prompt_the_life_planning_question() -> None:
    result = generate_cash_liquidity_recommendations(
        holdings_payload={"holdings": _holdings(), "total_cash": 71_000.0, "total_value": 460_000.0},
        financial_profile_payload={
            "expense_items": [{"id": "e1", "label": "Living", "monthly_amount_usd": 3_500.0}],
            "debt_items": [],
            "goal_items": [],
            "investment_policy": {"target_asset_class_allocation_pct": _TARGETS},
        },
        existing_recommendations=[],
        dry_run=True,
    )
    detail = result.candidates[0]["detail"]
    assert "No dated goals are on file" in detail
    assert "a home down payment, children" in detail


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
