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
    assert payload["score_model"] == "watchlist_v1"
    assert payload["sorted_by"] == "ranked"
    assert payload["warnings"] == []
    row = payload["items"][0]
    assert row["symbol"] == "NVDA"
    assert row["watchlist_rank"] == 1
    assert isinstance(row["watchlist_score_total"], float)
    assert isinstance(row["watchlist_score"], dict)
    assert row["watchlist_score"]["model_version"] == "watchlist_v1"
    assert row["quote_price"] == 80.0
    assert row["quote_change_pct"] == -1.8
    assert row["trend50d"] == "UP"
    assert row["trend200d"] == "UP"
    assert row["market_condition"] == "BEAR_MARKET"
    assert row["all_time_high"] == 100.0
    assert row["performance_from_high_pct"] == -20.0


def test_build_portfolio_watchlist_payload_cites_research_evidence_packet(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "NVDA", "data_source": "OPENBB"}]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str, interval: str):
            assert symbol == "NVDA"
            assert period == "2y"
            assert interval == "1d"
            return main.ResearchEvidencePacket(
                packet_id="research-evidence:yfinance:NVDA:2y:1d",
                symbol="NVDA",
                provider="yfinance",
                period="2y",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={
                    "quote_available": True,
                    "history_available": True,
                    "quote_message": "quote ok",
                    "history_message": "history ok",
                    "warnings": [],
                },
                freshness={"status": "fresh", "history_end": "2026-12-31"},
                metrics={
                    "last_price": 80.0,
                    "day_change_pct": -1.8,
                    "period_first_close": 70.0,
                    "period_last_close": 80.0,
                    "period_change_pct": 14.2857,
                },
                risk={
                    "drawdown_from_high_pct": -20.0,
                    "all_time_high": 100.0,
                    "trend50d": "UP",
                    "trend200d": "UP",
                },
                quality={"confidence": "high", "coverage_score": 100.0, "blocking_gaps": []},
                provenance={"quote_records": 1, "history_records": 500, "warnings": []},
            )

        def quote(self, symbol: str):
            raise AssertionError(f"watchlist should use evidence_packet before quote for {symbol}")

        def price_history(self, symbol: str, period: str, interval: str):
            raise AssertionError(f"watchlist should use evidence_packet before history for {symbol}")

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = main.build_portfolio_watchlist_payload(period="2y", interval="1d")

    row = payload["items"][0]
    assert row["research_evidence_packet_id"] == "research-evidence:yfinance:NVDA:2y:1d"
    assert row["research_provider"] == "yfinance"
    assert row["research_freshness_status"] == "fresh"
    assert row["research_confidence"] == "high"
    assert row["research_coverage_score"] == 100.0
    assert row["research_blocking_gaps"] == []
    assert row["quote_available"] is True
    assert row["history_available"] is True
    assert row["quote_price"] == 80.0
    assert row["trend50d"] == "UP"
    assert row["trend200d"] == "UP"
    assert row["all_time_high"] == 100.0
    assert row["history_records"] == 500


def test_build_portfolio_watchlist_payload_surfaces_packet_coverage_warnings(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "MSFT", "data_source": "OPENBB"}]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str, interval: str):
            del period, interval
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:2y:1d",
                symbol=symbol,
                provider="yfinance",
                period="2y",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={
                    "quote_available": True,
                    "history_available": False,
                    "quote_message": "quote ok",
                    "history_message": "history unavailable",
                    "warnings": [f"{symbol}: history unavailable (history unavailable)"],
                },
                freshness={"status": "partial"},
                metrics={"last_price": 80.0, "day_change_pct": -0.5},
                risk={"data_gaps": ["history"]},
                quality={"confidence": "medium", "coverage_score": 50.0, "blocking_gaps": ["history"]},
                provenance={"quote_records": 1, "history_records": 0, "warnings": []},
            )

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = main.build_portfolio_watchlist_payload(period="2y", interval="1d")

    row = payload["items"][0]
    assert row["research_freshness_status"] == "partial"
    assert row["research_blocking_gaps"] == ["history"]
    assert row["history_available"] is False
    assert "MSFT: history unavailable (history unavailable)" in payload["warnings"]


def test_build_portfolio_watchlist_payload_handles_empty_watchlist(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    payload = main.build_portfolio_watchlist_payload()

    assert payload["count"] == 0
    assert payload["items"] == []


def test_build_portfolio_watchlist_payload_ranks_items(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [
                {
                    "symbol": "AAA",
                    "data_source": "OPENBB",
                    "target_price_usd": 100.0,
                    "tags": ["growth"],
                },
                {
                    "symbol": "BBB",
                    "data_source": "OPENBB",
                    "target_price_usd": 102.0,
                    "tags": ["value"],
                },
            ]

    class FakeResearchService:
        def quote(self, symbol: str):
            if symbol == "AAA":
                return _FakeResearchResponse([{"last": 80.0, "change_percent": 2.5}], available=True)
            return _FakeResearchResponse([{"last": 100.0, "change_percent": -1.2}], available=True)

        def price_history(self, symbol: str, period: str, interval: str):
            assert period == "2y"
            assert interval == "1d"
            start = date(2026, 12, 31)
            if symbol == "AAA":
                base = 70.0
                step = 0.03
            else:
                base = 130.0
                step = -0.01
            records = []
            for idx in range(500):
                records.append(
                    {
                        "date": (start - timedelta(days=idx)).isoformat(),
                        "close": base + (idx * step),
                    }
                )
            return _FakeResearchResponse(records, available=True)

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = main.build_portfolio_watchlist_payload(period="2y", interval="1d", sort="ranked")

    assert payload["count"] == 2
    assert payload["sorted_by"] == "ranked"
    assert payload["items"][0]["symbol"] == "AAA"
    assert payload["items"][0]["watchlist_rank"] == 1
    assert payload["items"][1]["symbol"] == "BBB"
    assert payload["items"][1]["watchlist_rank"] == 2
    assert payload["items"][0]["watchlist_score_total"] > payload["items"][1]["watchlist_score_total"]


def test_build_portfolio_watchlist_payload_symbol_sort(monkeypatch) -> None:
    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [
                {"symbol": "ZZZ", "data_source": "OPENBB"},
                {"symbol": "AAA", "data_source": "OPENBB"},
            ]

    class FakeResearchService:
        def quote(self, symbol: str):
            return _FakeResearchResponse([{"last": 100.0, "change_percent": 0.0}], available=True)

        def price_history(self, symbol: str, period: str, interval: str):
            assert period == "2y"
            assert interval == "1d"
            records = [{"date": "2026-12-31", "close": 100.0}, {"date": "2026-12-30", "close": 100.0}]
            return _FakeResearchResponse(records, available=True)

    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = main.build_portfolio_watchlist_payload(sort="symbol")
    assert payload["sorted_by"] == "symbol"
    assert [row["symbol"] for row in payload["items"]] == ["AAA", "ZZZ"]
    assert payload["items"][0]["watchlist_rank"] is None
