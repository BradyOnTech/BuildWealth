import asyncio
import json
from pathlib import Path

import httpx

from buildwealth_orchestrator.services.engine_adapter import SidecarAdapter
from buildwealth_orchestrator.services.portfolio_attribution import GhostfolioAttributionService
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


def _seed_store(store: PortfolioStore) -> None:
    store.add_transaction(
        date="2026-04-01",
        symbol="AAPL",
        action="BUY",
        quantity=10,
        unit_price=100,
        fee=0,
        account="default",
        currency="USD",
    )
    store.add_transaction(
        date="2026-04-02",
        symbol="MSFT",
        action="BUY",
        quantity=5,
        unit_price=200,
        fee=0,
        account="default",
        currency="USD",
    )
    store.add_transaction(
        date="2026-04-10",
        symbol="AAPL",
        action="DIVIDEND",
        quantity=10,
        unit_price=1.5,
        fee=0,
        account="default",
        currency="USD",
    )
    store.set_manual_price(symbol="AAPL", price=120.0)
    store.set_manual_price(symbol="MSFT", price=180.0)


def test_attribution_service_uses_local_fallback_when_sidecar_disabled(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    _seed_store(store)

    service = GhostfolioAttributionService(
        portfolio_store=store,
        sidecar_adapter=None,
        sidecar_enabled=False,
        sidecar_path="/v1/attribution/compute",
        base_currency="USD",
    )

    result = asyncio.run(service.analyze(top_n=2))

    assert result.engine_status == "degraded"
    assert result.fallback_method == "sidecar_disabled"
    assert result.summary.portfolio_total_return_base > 0
    assert result.contributors
    assert result.detractors
    assert result.contributors[0].symbol == "AAPL"
    assert result.detractors[0].symbol == "MSFT"


def test_attribution_service_uses_sidecar_response_when_enabled(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    _seed_store(store)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ghostfolio",
                "engine_status": "ok",
                "fallback_method": None,
                "summary": {
                    "portfolio_total_return_base": 115.0,
                    "portfolio_total_value_base": 2100.0,
                    "accounted_return_base": 115.0,
                    "residual_return_base": 0.0,
                    "contributors_count": 1,
                    "detractors_count": 1,
                },
                "contributors": [
                    {
                        "symbol": "AAPL",
                        "name": "Apple",
                        "account_id": "default",
                        "asset_class": "US Stocks",
                        "current_value_base": 1200.0,
                        "cost_basis_base": 1000.0,
                        "price_return_base": 200.0,
                        "income_return_base": 15.0,
                        "total_return_base": 215.0,
                        "total_return_pct": 21.5,
                        "contribution_pct": 186.9565,
                        "allocation_pct": 57.1428,
                    }
                ],
                "detractors": [
                    {
                        "symbol": "MSFT",
                        "name": "Microsoft",
                        "account_id": "default",
                        "asset_class": "US Stocks",
                        "current_value_base": 900.0,
                        "cost_basis_base": 1000.0,
                        "price_return_base": -100.0,
                        "income_return_base": 0.0,
                        "total_return_base": -100.0,
                        "total_return_pct": -10.0,
                        "contribution_pct": -86.9565,
                        "allocation_pct": 42.8572,
                    }
                ],
                "positions": [],
                "warnings": [],
                "generated_at": "2026-04-11T18:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = GhostfolioAttributionService(
        portfolio_store=store,
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/attribution/compute",
        base_currency="USD",
    )

    result = asyncio.run(service.analyze(top_n=3))

    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.summary.portfolio_total_return_base == 115.0
    assert result.contributors[0].symbol == "AAPL"
    assert result.detractors[0].symbol == "MSFT"


def test_attribution_service_falls_back_when_sidecar_call_fails(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    _seed_store(store)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": "service unavailable"})

    adapter = SidecarAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = GhostfolioAttributionService(
        portfolio_store=store,
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/attribution/compute",
        base_currency="USD",
    )

    result = asyncio.run(service.analyze(top_n=2))

    assert result.engine_status == "degraded"
    assert result.fallback_method == "local_attribution_fallback"
    assert any("sidecar unavailable" in warning.lower() for warning in result.warnings)


def test_attribution_service_skips_sidecar_when_contract_guarded(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    _seed_store(store)
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(status_code=200, json={})

    adapter = SidecarAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = GhostfolioAttributionService(
        portfolio_store=store,
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/attribution/compute",
        base_currency="USD",
    )

    result = asyncio.run(
        service.analyze(
            top_n=2,
            sidecar_guard_reason="Sidecar contract version mismatch (expected v1, got v2)",
        )
    )

    assert calls["count"] == 0
    assert result.engine_status == "degraded"
    assert result.fallback_method == "contract_version_guard"
    assert any("sidecar skipped" in warning.lower() for warning in result.warnings)
