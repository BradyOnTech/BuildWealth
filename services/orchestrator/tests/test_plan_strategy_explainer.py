from __future__ import annotations

from buildwealth_orchestrator.services.plan_strategy_explainer import (
    explain_withdrawal_strategy_comparison,
)


def test_withdrawal_strategy_explainer_recommends_consistent_winner() -> None:
    explanation = explain_withdrawal_strategy_comparison(
        {
            "comparisons": [
                {
                    "strategy": "dynamic_guardrails",
                    "baseline_future_value_usd": 1_250_000,
                    "baseline_real_value_usd": 900_000,
                    "monte_carlo_p10_future_value_usd": 760_000,
                    "monte_carlo_p50_future_value_usd": 1_180_000,
                    "total_withdrawals_usd": 820_000,
                    "total_taxes_usd": 140_000,
                    "terminal_balance_usd": 510_000,
                },
                {
                    "strategy": "four_percent_rule",
                    "baseline_future_value_usd": 1_100_000,
                    "baseline_real_value_usd": 830_000,
                    "monte_carlo_p10_future_value_usd": 700_000,
                    "monte_carlo_p50_future_value_usd": 1_090_000,
                    "total_withdrawals_usd": 760_000,
                    "total_taxes_usd": 120_000,
                    "terminal_balance_usd": 430_000,
                },
            ]
        }
    )

    assert explanation["recommended_strategy"] == "dynamic_guardrails"
    assert "Dynamic Guardrails has the strongest overall result" in explanation["summary"]
    assert any(driver["label"] == "Highest ending value" for driver in explanation["drivers"])
    assert any("4% Rule projects $20,000 less in taxes" in item for item in explanation["tradeoffs"])


def test_withdrawal_strategy_explainer_surfaces_warnings_and_depletion() -> None:
    explanation = explain_withdrawal_strategy_comparison(
        {
            "warnings": ["Dynamic guardrails used local projection fallback."],
            "comparisons": [
                {
                    "strategy": "bucket_strategy",
                    "baseline_future_value_usd": 900_000,
                    "baseline_real_value_usd": 650_000,
                    "monte_carlo_p10_future_value_usd": 0,
                    "monte_carlo_p50_future_value_usd": 870_000,
                    "total_withdrawals_usd": 840_000,
                    "total_taxes_usd": 150_000,
                    "terminal_balance_usd": 0,
                    "engine_status": "degraded",
                    "warnings": ["Provider fallback used."],
                }
            ],
        }
    )

    assert explanation["recommended_strategy"] == "bucket_strategy"
    assert "Review the warnings" in explanation["summary"]
    assert "Provider fallback used." in explanation["warnings"]
    assert any("runs out of money" in item for item in explanation["tradeoffs"])
    assert any("lower-confidence model" in item for item in explanation["tradeoffs"])
