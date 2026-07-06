from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore


class FakePortfolioStore:
    def get_holdings(self) -> dict:
        return {
            "total_portfolio_value": 1200,
            "performance": {
                "total_return_usd": 200,
                "price_return_usd": 180,
                "income_return_usd": 20,
            },
        }


class FakeBenchmarkService:
    last_kwargs: dict = {}

    async def compare(self, **kwargs) -> dict:
        self.last_kwargs = kwargs
        return {
            "benchmark_symbols": kwargs["benchmark_symbols"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
            "summary": {
                "portfolio_return_pct": 20,
                "benchmark_return_pct_by_symbol": {"SPY": 10},
                "alpha_pct_by_symbol": {"SPY": 10},
            },
            "series": [],
            "warnings": ["Portfolio benchmark local calculation selected; using local fallback"],
        }


class FakeAttributionService:
    async def analyze(self, **kwargs) -> dict:
        return {
            "summary": {
                "portfolio_total_return_base": 200,
                "portfolio_total_value_base": 1200,
                "accounted_return_base": 200,
                "residual_return_base": 0,
                "contributors_count": 1,
                "detractors_count": 0,
            },
            "contributors": [{"symbol": "VTI", "total_return_base": 200, "contribution_pct": 100}],
            "detractors": [],
            "warnings": [],
        }


def test_portfolio_analytics_route(monkeypatch) -> None:
    benchmark = FakeBenchmarkService()
    services = SimpleNamespace(
        context=SimpleNamespace(permissions=ControlPlaneStore.OWNER_PERMISSIONS),
        portfolio_store=FakePortfolioStore(),
        asset_registry=SimpleNamespace(search=lambda limit=500: {"items": []}),
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(main, "benchmark_service_for_workspace", lambda services: benchmark)
    monkeypatch.setattr(main, "attribution_service_for_workspace", lambda services: FakeAttributionService())

    try:
        with TestClient(main.app) as client:
            response = client.get("/api/portfolio/analytics?symbols=SPY&period=mtd&limit=10&top_n=3")
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["period"]["id"] == "mtd"
    assert benchmark.last_kwargs["limit"] == 31
    assert payload["benchmark"]["rows"][0]["symbol"] == "SPY"
    assert payload["attribution"]["contributors"][0]["symbol"] == "VTI"
    assert "Portfolio Analysis" not in " ".join(payload["warnings"])
