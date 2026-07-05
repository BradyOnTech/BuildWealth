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
