from pathlib import Path

import pytest

from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.price_updater import refresh_fx_for_portfolio


class _FakeResearch:
    def __init__(self, quote_map: dict[str, dict], history_map: dict[str, list[dict]]):
        self.quote_map = quote_map
        self.history_map = history_map

    def get_quote(self, symbol: str) -> dict:
        return self.quote_map.get(symbol, {})

    def get_price_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict]:
        _ = (period, interval)
        return self.history_map.get(symbol, [])


@pytest.fixture
def store(tmp_path: Path) -> PortfolioStore:
    return PortfolioStore(tmp_path / "portfolio")


def test_refresh_fx_for_portfolio_updates_latest_and_historical_rates(store: PortfolioStore):
    euro = store.add_account("Euro Brokerage", currency="EUR")
    store.add_transaction(
        date="2026-01-01",
        symbol="SAP",
        action="BUY",
        quantity=10,
        unit_price=100,
        account=euro["id"],
        currency="EUR",
    )

    research = _FakeResearch(
        quote_map={
            "EURUSD=X": {"market_price": 1.1},
        },
        history_map={
            "EURUSD=X": [
                {"date": "2026-01-01", "close": 1.2},
                {"date": "2026-01-02", "close": 1.19},
            ]
        },
    )

    result = refresh_fx_for_portfolio(
        portfolio_store=store,
        research=research,  # type: ignore[arg-type]
        holdings_data=store.get_holdings(),
    )
    assert result["rates_updated"] == 1
    assert result["history_updated"] == 1

    fx_rates = store.get_fx_rates()
    assert fx_rates["rates"]["EUR"] == pytest.approx(1.1, abs=1e-6)

    fx_history = store.get_fx_rates_history()
    pair = fx_history["pairs"]["EURUSD"]
    assert pair["2026-01-01"] == pytest.approx(1.2, abs=1e-6)
    assert pair["2026-01-02"] == pytest.approx(1.19, abs=1e-6)
