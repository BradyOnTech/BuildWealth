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


def _previous_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc).replace(day=1),
        base_currency="USD",
        total_value_usd=230000.0,
        total_investment_usd=198000.0,
        net_performance_usd=32000.0,
        net_performance_percent=0.16,
        holdings=[
            Holding(symbol="VTI", name="Vanguard Total Stock Market", value_usd=85000, allocation_percent=37.0),
            Holding(symbol="AAPL", name="Apple", value_usd=65000, allocation_percent=28.0),
            Holding(symbol="MSFT", name="Microsoft", value_usd=40000, allocation_percent=17.0),
            Holding(symbol="BND", name="Vanguard Total Bond", value_usd=40000, allocation_percent=18.0),
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
    assert "## Assumptions" in result["report_markdown"]
    assert "## Caveats" in result["report_markdown"]
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
    assert "## Assumptions" in result["report_markdown"]
    assert "## Caveats" in result["report_markdown"]
    assert len(result["data"]["runs"]) == 3
    assert result["data"]["best_run"]["annual_contribution_usd"] >= 18000


def test_workflow_runner_weekly_change_summary_with_history() -> None:
    runner = WorkflowRunner(
        scenario_engine=_engine(),
        default_annual_contribution_usd=18000,
        default_years=25,
        default_hsa_delta=1000,
    )

    result = runner.run(
        workflow_id="weekly_change_summary",
        snapshot=_snapshot(),
        previous_snapshot=_previous_snapshot(),
    )
    assert result["workflow_id"] == "weekly_change_summary"
    assert result["data"]["history_available"] is True
    assert "Portfolio Delta" in result["report_markdown"]
    assert isinstance(result["data"]["top_movers"], list)


def test_workflow_runner_weekly_change_summary_without_history() -> None:
    runner = WorkflowRunner(
        scenario_engine=_engine(),
        default_annual_contribution_usd=18000,
        default_years=25,
        default_hsa_delta=1000,
    )

    result = runner.run(
        workflow_id="weekly_change_summary",
        snapshot=_snapshot(),
        previous_snapshot=None,
    )
    assert result["workflow_id"] == "weekly_change_summary"
    assert result["data"]["history_available"] is False
    assert "No previous snapshot is available" in result["report_markdown"]
