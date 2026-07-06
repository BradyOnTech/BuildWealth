"""Trim plans: breaches become executable, tax-aware instructions."""

from datetime import datetime, timezone

from buildwealth_orchestrator.services.portfolio_rebalancing import (
    build_trim_plan,
    trim_plan_summary,
)
from buildwealth_orchestrator.services.recommendation_factory import (
    generate_portfolio_risk_recommendations,
)

AS_OF = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

ACCOUNTS = [
    {"id": "my_401k", "type": "401k"},
    {"id": "my_roth", "type": "roth_ira"},
    {"id": "my_taxable", "type": "taxable"},
]


def _alert(observed: float = 35.0, threshold: float = 25.0) -> dict:
    return {
        "id": "single_holding_concentration",
        "metric": "single_holding",
        "state": "breach",
        "severity": "high",
        "observed": observed,
        "threshold": threshold,
        "unit": "pct",
        "context": {"symbol": "NVDA"},
        "message": "NVDA is 35% of the portfolio.",
        "label": "Top holding concentration",
        "direction": "max",
        "drift_from_threshold": observed - threshold,
    }


def _holdings() -> dict:
    return {
        "my_401k:NVDA": {
            "symbol": "NVDA", "account": "my_401k", "current_value": 20_000.0,
            "current_price": 100.0, "asset_type": "stock",
            "lots": [{"acquired_date": "2024-01-01", "remaining_quantity": 200, "unit_cost": 40.0}],
        },
        "my_taxable:NVDA": {
            "symbol": "NVDA", "account": "my_taxable", "current_value": 15_000.0,
            "current_price": 100.0, "asset_type": "stock",
            "lots": [
                {"acquired_date": "2023-01-01", "remaining_quantity": 100, "unit_cost": 50.0},
                {"acquired_date": "2026-05-01", "remaining_quantity": 50, "unit_cost": 90.0},
            ],
        },
        "my_401k:VTI": {
            "symbol": "VTI", "account": "my_401k", "current_value": 65_000.0,
            "current_price": 260.0, "asset_type": "etf", "lots": [],
        },
    }


def test_trim_plan_prefers_tax_advantaged_accounts_first() -> None:
    plan = build_trim_plan(
        alert=_alert(),
        holdings=_holdings(),
        accounts=ACCOUNTS,
        total_market_value=100_000.0,
        as_of=AS_OF,
    )

    assert plan["status"] == "ready"
    assert plan["reduce_by_usd"] == 10_000.0
    assert len(plan["trades"]) == 1  # 401k position alone covers the trim
    trade = plan["trades"][0]
    assert trade["account_id"] == "my_401k"
    assert trade["tax_treatment"] == "tax_deferred"
    assert trade["sell_value_usd"] == 10_000.0
    assert trade["quantity"] == 100.0
    assert trade["tax_due_now"] is False
    assert plan["residual_usd"] == 0.0

    sentence = trim_plan_summary(plan)
    assert "$10,000" in sentence and "my_401k" in sentence and "no tax due now" in sentence


def test_trim_plan_spills_into_taxable_with_fifo_gain_split() -> None:
    plan = build_trim_plan(
        alert=_alert(observed=50.0, threshold=25.0),   # reduce by 25k > 20k in 401k
        holdings=_holdings(),
        accounts=ACCOUNTS,
        total_market_value=100_000.0,
        as_of=AS_OF,
    )

    assert [t["account_id"] for t in plan["trades"]] == ["my_401k", "my_taxable"]
    taxable = plan["trades"][1]
    assert taxable["sell_value_usd"] == 5_000.0
    # FIFO: 50 shares from the 2023 lot at $50 basis -> $2,500 long-term gain
    assert taxable["estimated_long_term_gain_usd"] == 2_500.0
    assert taxable["estimated_short_term_gain_usd"] == 0.0
    assert taxable["tax_due_now"] is True


def test_trim_plan_names_untradable_positions_instead_of_pretending() -> None:
    holdings = {
        "home:DEMO_HOME": {
            "symbol": "DEMO_HOME", "account": "home", "current_value": 420_000.0,
            "current_price": 0.0, "asset_type": "property", "is_custom_asset": True,
            "valuation_method": "manual", "lots": [],
        },
    }
    alert = _alert()
    alert["context"] = {"symbol": "DEMO_HOME"}
    plan = build_trim_plan(
        alert=alert,
        holdings=holdings,
        accounts=[{"id": "home", "type": "taxable"}],
        total_market_value=500_000.0,
        as_of=AS_OF,
    )

    assert plan["status"] == "no_tradable_position"
    assert plan["trades"] == []
    assert any("future contributions" in note for note in plan["notes"])


def test_factory_attaches_trades_to_risk_recommendations() -> None:
    holdings_payload = {
        "holdings": _holdings(),
        "total_value": 100_000.0,
        "risk_alerts": {
            "status": "critical",
            "alerts": [_alert()],
            "metrics": {"total_market_value": 100_000.0},
        },
    }
    result = generate_portfolio_risk_recommendations(
        holdings_payload=holdings_payload,
        existing_recommendations=[],
        dry_run=True,
        now=AS_OF,
        accounts=ACCOUNTS,
    )

    assert result.generated_count == 1
    action = result.candidates[0]["action_payload"]["suggested_action"]
    assert action["trim_plan_status"] == "ready"
    assert action["trades"][0]["account_id"] == "my_401k"
    assert "Sell ~$10,000 of NVDA from my_401k" in result.candidates[0]["detail"]


def test_allocation_drift_plan_flags_over_and_under_weights() -> None:
    from buildwealth_orchestrator.services.portfolio_rebalancing import (
        allocation_drift_sentence,
        build_allocation_drift_plan,
    )

    holdings = {
        "a:VTI": {"symbol": "VTI", "asset_class": "equity", "current_value": 90_000.0, "asset_type": "etf"},
        "a:BND": {"symbol": "BND", "asset_class": "fixed_income", "current_value": 5_000.0, "asset_type": "etf"},
        "a:CASH": {"symbol": "CASH", "asset_class": "cash", "current_value": 5_000.0, "asset_type": "cash"},
    }
    plan = build_allocation_drift_plan(
        holdings=holdings,
        targets_pct={"equity": 70, "fixed_income": 20, "cash": 10},
        total_market_value=100_000.0,
    )

    assert plan["status"] == "ready"
    by_class = {row["asset_class"]: row for row in plan["rows"]}
    assert by_class["equity"]["direction"] == "overweight"
    assert by_class["equity"]["drift_pct"] == 20.0
    assert by_class["equity"]["trim_candidates"] == ["VTI"]
    assert by_class["fixed_income"]["direction"] == "underweight"
    assert by_class["fixed_income"]["gap_usd"] == 15_000.0
    assert "cash" not in by_class  # exactly on target

    under = allocation_drift_sentence(by_class["fixed_income"])
    assert "under your 20% target" in under
    assert "without selling anything" in under
    over = allocation_drift_sentence(by_class["equity"])
    assert "over your 70% target" in over and "VTI" in over


def test_allocation_drift_plan_without_targets_or_within_tolerance() -> None:
    from buildwealth_orchestrator.services.portfolio_rebalancing import build_allocation_drift_plan

    empty = build_allocation_drift_plan(holdings={}, targets_pct={}, total_market_value=100_000.0)
    assert empty["status"] == "no_targets"

    on_target = build_allocation_drift_plan(
        holdings={
            "a:VTI": {"symbol": "VTI", "asset_class": "equity", "current_value": 68_000.0},
            "a:CASH": {"symbol": "CASH", "asset_class": "cash", "current_value": 32_000.0, "asset_type": "cash"},
        },
        targets_pct={"equity": 70},
        total_market_value=100_000.0,
    )
    assert on_target["status"] == "on_target"


def test_allocation_drift_measures_investable_money_not_the_house() -> None:
    from buildwealth_orchestrator.services.portfolio_rebalancing import build_allocation_drift_plan

    holdings = {
        "a:HOME": {
            "symbol": "MY_HOME",
            "asset_class": "real_estate",
            "asset_type": "property",
            "current_value": 420_000.0,
        },
        "a:VTI": {"symbol": "VTI", "asset_class": "equity", "current_value": 56_000.0, "asset_type": "etf"},
        "a:BND": {"symbol": "BND", "asset_class": "fixed_income", "current_value": 24_000.0, "asset_type": "etf"},
    }
    plan = build_allocation_drift_plan(
        holdings=holdings,
        targets_pct={"equity": 70, "fixed_income": 30, "real_estate": 20},
        total_market_value=500_000.0,
    )

    assert plan["investable_value_usd"] == 80_000.0
    by_class = {row["asset_class"]: row for row in plan["rows"]}
    # Equity is 70% of INVESTED money — exactly on target, no false alarm
    # from the home diluting the base.
    assert "equity" not in by_class
    # The home never makes real estate "overweight"; with no tradable real
    # estate the class simply reads underweight against its target.
    real_estate = by_class.get("real_estate")
    assert real_estate is not None
    assert real_estate["direction"] == "underweight"
    assert real_estate["trim_candidates"] == []


def test_allocation_drift_generator_emits_contribution_first_guidance() -> None:
    from buildwealth_orchestrator.services.recommendation_factory import (
        generate_allocation_drift_recommendations,
    )

    holdings_payload = {
        "holdings": {
            "a:VTI": {"symbol": "VTI", "asset_class": "equity", "current_value": 90_000.0, "asset_type": "etf"},
            "a:BND": {"symbol": "BND", "asset_class": "fixed_income", "current_value": 10_000.0, "asset_type": "etf"},
        },
        "total_value": 100_000.0,
        "risk_alerts": {"metrics": {"total_market_value": 100_000.0}},
    }
    result = generate_allocation_drift_recommendations(
        holdings_payload=holdings_payload,
        investment_policy={"target_asset_class_allocation_pct": {"equity": 70, "fixed_income": 30}},
        existing_recommendations=[],
        dry_run=True,
        now=AS_OF,
    )

    assert result.generated_count == 2
    titles = [c["title"] for c in result.candidates]
    assert any("drifted above target" in t for t in titles)
    assert any(t.startswith("Direct new contributions toward fixed income") for t in titles)
    under = next(c for c in result.candidates if "Direct new" in c["title"])
    assert "without selling anything" in under["detail"]
    assert under["action_payload"]["generator"]["dedupe_key"] == "allocation_drift:fixed_income:underweight"

    # second run against the created set dedupes — existing rows carry
    # title/detail because the supersede check compares content, not just keys
    second = generate_allocation_drift_recommendations(
        holdings_payload=holdings_payload,
        investment_policy={"target_asset_class_allocation_pct": {"equity": 70, "fixed_income": 30}},
        existing_recommendations=[
            {
                "status": "proposed",
                "title": c["title"],
                "detail": c["detail"],
                "action_payload": c["action_payload"],
            }
            for c in result.candidates
        ],
        dry_run=True,
        now=AS_OF,
    )
    assert second.generated_count == 0
    assert second.refreshed_count == 0
    assert {item["reason"] for item in second.skipped} == {"active_duplicate"}
