from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


def test_scenario_engine_returns_four_scenarios() -> None:
    engine = ScenarioEngine(
        years_to_retirement=30,
        annual_contribution_usd=12000,
        baseline_return=0.06,
        optimistic_return=0.08,
        conservative_return=0.04,
        return_volatility=0.12,
        inflation=0.025,
        monte_carlo_runs=200,
        hsa_delta_default=1000,
        marginal_tax_rate=0.25,
    )

    result = engine.run(current_portfolio_value_usd=100000)

    assert len(result.scenarios) == 4
    labels = {scenario.label for scenario in result.scenarios}
    assert labels == {"baseline", "optimistic", "conservative", "hsa_delta"}
    assert result.monte_carlo["runs"] == 200


def test_scenario_engine_respects_explicit_zero_hsa_delta() -> None:
    engine = ScenarioEngine(
        years_to_retirement=30,
        annual_contribution_usd=12000,
        baseline_return=0.06,
        optimistic_return=0.08,
        conservative_return=0.04,
        return_volatility=0.12,
        inflation=0.025,
        monte_carlo_runs=200,
        hsa_delta_default=1000,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=100000,
        annual_contribution_usd=15000,
        hsa_extra_contribution_usd=0,
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    hsa_delta = next(item for item in result.scenarios if item.label == "hsa_delta")
    assert hsa_delta.assumptions["annual_contribution_usd"] == baseline.assumptions["annual_contribution_usd"]
