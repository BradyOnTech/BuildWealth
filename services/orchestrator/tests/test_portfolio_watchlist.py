from datetime import date, timedelta

import buildwealth_orchestrator.main as main


class _FakeResearchResponse:
    def __init__(self, records, *, available: bool = True, message: str = "ok") -> None:
        self.records = records
        self.available = available
        self.message = message


def test_build_portfolio_watchlist_payload_computes_market_metrics(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [
                {
                    "symbol": "NVDA",
                    "data_source": "OPENBB",
                    "note": "AI theme",
                    "target_price_usd": 1200.0,
                    "tags": ["ai", "semis"],
                }
            ]

    class FakeResearchService:
        def quote(self, symbol: str):
            assert symbol == "NVDA"
            return _FakeResearchResponse(
                [{"last": 80.0, "change_percent": -1.8}],
                available=True,
            )

        def price_history(self, symbol: str, period: str, interval: str):
            assert symbol == "NVDA"
            assert period == "2y"
            assert interval == "1d"
            start = date(2026, 12, 31)
            records = []
            for idx in range(500):
                records.append(
                    {
                        "date": (start - timedelta(days=idx)).isoformat(),
                        "close": 100.0 - (idx * 0.05),
                    }
                )
            return _FakeResearchResponse(records, available=True)

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = main.build_portfolio_watchlist_payload(period="2y", interval="1d")

    assert payload["count"] == 1
    assert payload["period"] == "2y"
    assert payload["interval"] == "1d"
    assert payload["warnings"] == []
    row = payload["items"][0]
    assert row["symbol"] == "NVDA"
    assert row["quote_price"] == 80.0
    assert row["quote_change_pct"] == -1.8
    assert row["trend50d"] == "UP"
    assert row["trend200d"] == "UP"
    assert row["market_condition"] == "BEAR_MARKET"
    assert row["all_time_high"] == 100.0
    assert row["performance_from_high_pct"] == -20.0


def test_build_portfolio_watchlist_payload_handles_empty_watchlist(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    payload = main.build_portfolio_watchlist_payload()

    assert payload["count"] == 0
    assert payload["items"] == []
