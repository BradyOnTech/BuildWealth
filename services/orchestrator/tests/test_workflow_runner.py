from datetime import datetime, timezone

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine
from buildwealth_orchestrator.services.workflow_runner import WorkflowRunner


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        base_currency="USD",
        total_value_usd=250000.0,
        total_investment_usd=200000.0,
        net_performance_usd=50000.0,
        net_performance_percent=0.25,
        holdings=[
            Holding(symbol="VTI", name="Vanguard Total Stock Market", value_usd=90000, allocation_percent=36.0),
            Holding(symbol="AAPL", name="Apple", value_usd=70000, allocation_percent=28.0),
            Holding(symbol="MSFT", name="Microsoft", value_usd=45000, allocation_percent=18.0),
            Holding(symbol="VXUS", name="Vanguard Total Intl", value_usd=45000, allocation_percent=18.0),
        ],
    )


def _engine() -> ScenarioEngine:
    return ScenarioEngine(
        years_to_retirement=25,
        annual_contribution_usd=18000,
        baseline_return=0.065,
        optimistic_return=0.085,
        conservative_return=0.045,
        return_volatility=0.14,
        inflation=0.025,
        monte_carlo_runs=100,
        hsa_delta_default=1000,
        marginal_tax_rate=0.28,
    )


def test_workflow_runner_risk_concentration_output() -> None:
    runner = WorkflowRunner(
        scenario_engine=_engine(),
        default_annual_contribution_usd=18000,
        default_years=25,
        default_hsa_delta=1000,
    )

    result = runner.run(workflow_id="risk_concentration_review", snapshot=_snapshot())
    assert result["workflow_id"] == "risk_concentration_review"
    assert "Risk Concentration Review" in result["report_markdown"]
    assert "risk_level" in result["data"]
    assert "top_holding_percent" in result["data"]


def test_workflow_runner_contribution_optimization_output() -> None:
    runner = WorkflowRunner(
        scenario_engine=_engine(),
        default_annual_contribution_usd=18000,
        default_years=25,
        default_hsa_delta=1000,
    )

    result = runner.run(
        workflow_id="contribution_optimization",
        snapshot=_snapshot(),
        params={"increment_options_usd": [0, 2000, 4000], "years": 20},
    )
    assert result["workflow_id"] == "contribution_optimization"
    assert "Contribution Comparisons" in result["report_markdown"]
    assert len(result["data"]["runs"]) == 3
    assert result["data"]["best_run"]["annual_contribution_usd"] >= 18000
