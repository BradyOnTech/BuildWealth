import asyncio
from pathlib import Path

from buildwealth_orchestrator.services.portfolio_attribution import BuildWealthAttributionService
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


def test_attribution_service_computes_native_contributors_and_detractors(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    _seed_store(store)

    service = BuildWealthAttributionService(
        portfolio_store=store,
        base_currency="USD",
    )

    result = asyncio.run(service.analyze(top_n=2))

    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.summary.portfolio_total_return_base > 0
    assert result.contributors
    assert result.detractors
    assert result.contributors[0].symbol == "AAPL"
    assert result.detractors[0].symbol == "MSFT"


def test_attribution_service_limits_native_rankings(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    _seed_store(store)

    service = BuildWealthAttributionService(
        portfolio_store=store,
        base_currency="USD",
    )

    result = asyncio.run(service.analyze(top_n=1))

    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert len(result.contributors) == 1
    assert len(result.detractors) == 1
    assert result.contributors[0].symbol == "AAPL"
    assert result.detractors[0].symbol == "MSFT"
