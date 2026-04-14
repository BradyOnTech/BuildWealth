import asyncio
from types import SimpleNamespace

import buildwealth_orchestrator.main as main


def test_normalize_withdrawal_strategies_aliases_and_invalid() -> None:
    strategies, invalid = main.normalize_withdrawal_strategies(
        ["cashflow_only", "4_percent_rule", "dynamic_guardrails", "bad_strategy", "4_percent_rule"]
    )

    assert strategies == ["cashflow_only", "four_percent_rule", "dynamic_guardrails"]
    assert invalid == ["bad_strategy"]


def test_tool_compare_withdrawal_strategies_ranks_and_summarizes(monkeypatch) -> None:
    class FakePlanWorkspace:
        def get_plan(self, plan_id: str) -> dict[str, object]:
            return {
                "id": plan_id,
                "title": "Primary Plan",
                "settings": {
                    "annual_contribution_usd": 20000,
                    "expected_return_baseline": 0.07,
                    "expected_return_optimistic": 0.09,
                    "expected_return_conservative": 0.05,
                    "inflation_rate": 0.03,
                    "marginal_tax_rate": 0.24,
                },
                "files": {},
            }

    monkeypatch.setattr(main, "plan_workspace", FakePlanWorkspace())
    monkeypatch.setattr(main, "resolve_plan_assumption_sets", lambda detail: {})
    monkeypatch.setattr(
        main,
        "apply_assumption_set_to_settings",
        lambda **kwargs: (dict(kwargs.get("plan_settings") or {}), {"id": "default", "name": "Default"}),
    )
    monkeypatch.setattr(main, "resolve_plan_timeline_payload", lambda detail: {})
    monkeypatch.setattr(main, "resolve_timeline_retirement_age", lambda payload: None)
    monkeypatch.setattr(main, "resolve_timeline_withdrawal_strategy", lambda payload: None)
    monkeypatch.setattr(main, "resolve_plan_contribution_rules", lambda detail: {})
    monkeypatch.setattr(main, "build_income_projection_for_plan_settings", lambda settings: {})
    monkeypatch.setattr(main, "build_expense_projection_for_plan_settings", lambda settings: {})
    monkeypatch.setattr(main, "build_debt_projection_for_plan_settings", lambda settings: {})
    monkeypatch.setattr(main, "build_timeline_projection_for_plan_settings", lambda **kwargs: {})
    monkeypatch.setattr(main, "build_contribution_allocation_for_plan_settings", lambda **kwargs: None)
    monkeypatch.setattr(main, "build_social_security_projection_for_plan_settings", lambda **kwargs: None)
    monkeypatch.setattr(main, "build_rmd_projection_for_plan_settings", lambda **kwargs: None)

    class FakeResult:
        def __init__(self, strategy: str) -> None:
            if strategy == "four_percent_rule":
                future_value = 1_220_000.0
                real_value = 820_000.0
                p50 = 1_160_000.0
                terminal_balance = 640_000.0
            else:
                future_value = 1_180_000.0
                real_value = 790_000.0
                p50 = 1_090_000.0
                terminal_balance = 600_000.0

            timeline_points = [
                SimpleNamespace(
                    withdrawals_usd=40_000.0,
                    taxes_usd=6_500.0,
                    rmds_usd=0.0,
                    age=66,
                    ending_balance_usd=830_000.0,
                ),
                SimpleNamespace(
                    withdrawals_usd=45_000.0,
                    taxes_usd=7_100.0,
                    rmds_usd=1_200.0,
                    age=67,
                    ending_balance_usd=terminal_balance,
                ),
            ]
            baseline = SimpleNamespace(
                label="baseline",
                future_value_usd=future_value,
                real_value_usd=real_value,
                assumptions={"average_effective_tax_rate": 0.19},
                timeline_points=timeline_points,
            )
            self.scenarios = [baseline]
            self.monte_carlo = {
                "p10_future_value_usd": 900_000.0,
                "p50_future_value_usd": p50,
                "p90_future_value_usd": 1_320_000.0,
            }
            self.engine = "local"
            self.engine_status = "ok"
            self.fallback_method = None
            self.warnings = []

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {"engine": self.engine}

    async def fake_run_scenarios_for_plan_settings(**kwargs):
        strategy = str(kwargs.get("plan_settings", {}).get("withdrawal_strategy") or "cashflow_only")
        return FakeResult(strategy)

    monkeypatch.setattr(main, "run_scenarios_for_plan_settings", fake_run_scenarios_for_plan_settings)

    payload = asyncio.run(
        main.tool_compare_withdrawal_strategies(
            {
                "plan_id": "plan-abc",
                "current_portfolio_value_usd": 500_000,
                "strategies": ["cashflow_only", "4_percent_rule", "bad"],
            }
        )
    )

    assert payload["plan_id"] == "plan-abc"
    assert payload["current_portfolio_value_usd"] == 500_000.0
    assert payload["strategies"] == ["cashflow_only", "four_percent_rule"]
    assert payload["best_strategy_by_metric"]["future_value"] == "four_percent_rule"
    assert payload["best_strategy_by_metric"]["real_value"] == "four_percent_rule"
    assert payload["best_strategy_by_metric"]["monte_carlo_p50"] == "four_percent_rule"
    assert any("Ignored invalid strategies: bad" in warning for warning in payload["warnings"])

    comparisons = payload["comparisons"]
    assert len(comparisons) == 2
    assert comparisons[0]["strategy"] == "four_percent_rule"
    assert comparisons[0]["terminal_age"] == 67
    assert comparisons[0]["total_withdrawals_usd"] == 85_000.0
    assert comparisons[0]["total_taxes_usd"] == 13_600.0
    assert comparisons[0]["total_rmds_usd"] == 1_200.0
