from datetime import datetime, timezone

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.coordinator import Coordinator


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        base_currency="USD",
        total_value_usd=100000.0,
        total_investment_usd=80000.0,
        net_performance_usd=20000.0,
        net_performance_percent=0.25,
        holdings=[
            Holding(symbol="VTI", name="Vanguard Total Stock Market", value_usd=60000, allocation_percent=60.0),
            Holding(symbol="VXUS", name="Vanguard Total Intl", value_usd=40000, allocation_percent=40.0),
        ],
    )


def test_coordinator_routes_portfolio_questions() -> None:
    coordinator = Coordinator()

    result = coordinator.answer("Show my allocation concentration", snapshot=_snapshot())

    assert result.route == "portfolio"
    assert "Current portfolio value" in result.answer
    assert "concentration" in result.data


def test_coordinator_routes_planning_questions() -> None:
    coordinator = Coordinator()
    planning = {
        "scenarios": [
            {"label": "baseline", "future_value_usd": 1000000.0},
            {"label": "optimistic", "future_value_usd": 1200000.0},
            {"label": "conservative", "future_value_usd": 850000.0},
            {"label": "hsa_delta", "future_value_usd": 1015000.0},
        ]
    }

    result = coordinator.answer("retirement projection", snapshot=_snapshot(), planning=planning)

    assert result.route == "planning"
    assert "Baseline projection" in result.answer


def test_coordinator_routes_research_questions() -> None:
    coordinator = Coordinator()
    research = {
        "available": True,
        "message": "Ready",
        "records": [{"symbol": "AAPL"}],
    }

    result = coordinator.answer("options research", snapshot=_snapshot(), research=research)

    assert result.route == "research"
    assert result.data["records"] == [{"symbol": "AAPL"}]
