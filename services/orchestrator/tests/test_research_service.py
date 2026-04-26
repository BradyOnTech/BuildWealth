from buildwealth_orchestrator.schemas import ResearchResponse
from buildwealth_orchestrator.services.research import OpenBBResearchService
import pytest


def test_research_service_quote_shape() -> None:
    service = OpenBBResearchService(provider="yfinance")
    result = service.quote("AAPL")

    assert result.symbol == "AAPL"
    assert isinstance(result.available, bool)
    assert isinstance(result.message, str)
    assert isinstance(result.records, list)


def test_research_service_price_history_shape() -> None:
    service = OpenBBResearchService(provider="yfinance")
    result = service.price_history("MSFT", period="6mo", interval="1d")

    assert result.symbol == "MSFT"
    assert isinstance(result.available, bool)
    assert isinstance(result.message, str)
    assert isinstance(result.records, list)


def test_research_service_compare_shape() -> None:
    service = OpenBBResearchService(provider="yfinance")
    result = service.compare(symbols=["AAPL", "MSFT"], period="6mo", interval="1d")

    assert result.provider == "yfinance"
    assert result.period == "6mo"
    assert result.interval == "1d"
    assert result.symbols == ["AAPL", "MSFT"]
    assert result.summary.requested_symbols == 2
    assert len(result.items) == 2
    assert isinstance(result.warnings, list)


def test_research_service_compare_scores_and_baseline_delta(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        row = (
            {"last": 110.0, "change_percent": 2.0, "market_cap": 2_000_000_000_000}
            if symbol == "AAPL"
            else {"last": 220.0, "change_percent": -1.0, "market_cap": 1_500_000_000_000}
        )
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote",
            records=[row],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del period, interval
        closes = [100.0, 110.0, 120.0] if symbol == "AAPL" else [200.0, 195.0, 190.0]
        records = [{"close": close} for close in closes]
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="history",
            records=records,
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    result = service.compare(
        symbols=["AAPL", "MSFT"],
        period="6mo",
        interval="1d",
        baseline_symbol="AAPL",
    )

    assert result.summary.best_period_return_symbol == "AAPL"
    assert result.summary.worst_period_return_symbol == "MSFT"
    assert result.summary.baseline_symbol == "AAPL"
    assert result.summary.baseline_relative_return_pct["AAPL"] == 0.0
    assert result.summary.baseline_relative_return_pct["MSFT"] < 0.0
    assert result.items[0].symbol == "AAPL"
    assert result.items[0].rank == 1


def test_research_service_compare_cites_evidence_packets(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote",
            records=[{"last": 110.0 if symbol == "AAPL" else 220.0, "change_percent": 1.0}],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del period, interval
        closes = [100.0, 110.0, 120.0] if symbol == "AAPL" else [200.0, 210.0, 220.0]
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="history",
            records=[{"close": close} for close in closes],
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    result = service.compare(symbols=["AAPL", "MSFT"], period="6mo", interval="1d")

    by_symbol = {item.symbol: item for item in result.items}
    assert by_symbol["AAPL"].research_evidence_packet_id == "research-evidence:yfinance:AAPL:6mo:1d"
    assert by_symbol["AAPL"].research_provider == "yfinance"
    assert by_symbol["AAPL"].research_freshness_status == "fresh"
    assert by_symbol["AAPL"].research_confidence == "high"
    assert by_symbol["AAPL"].research_coverage_score == 100.0
    assert by_symbol["AAPL"].research_blocking_gaps == []


def test_research_service_compare_surfaces_evidence_packet_warnings(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote",
            records=[{"last": 80.0}],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del period, interval
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=False,
            message="history unavailable",
            records=[],
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    result = service.compare(symbols=["MSFT", "AAPL"], period="6mo", interval="1d")

    by_symbol = {item.symbol: item for item in result.items}
    assert by_symbol["MSFT"].research_freshness_status == "partial"
    assert by_symbol["MSFT"].research_confidence == "medium"
    assert by_symbol["MSFT"].research_blocking_gaps == ["history"]
    assert "MSFT: history unavailable (history unavailable)" in result.warnings


def test_research_service_dossier_shape() -> None:
    service = OpenBBResearchService(provider="yfinance")
    result = service.dossier(
        symbols=["AAPL", "MSFT"],
        period="6mo",
        interval="1d",
        thesis="Quality compounders with durable cash generation.",
        risks=["valuation compression"],
        catalysts=["product cycle"],
        include_portfolio_fit=True,
        portfolio_weights_pct={"AAPL": 7.5},
    )

    assert result.provider == "yfinance"
    assert result.period == "6mo"
    assert result.interval == "1d"
    assert result.symbols == ["AAPL", "MSFT"]
    assert result.compare.summary.requested_symbols == 2
    assert isinstance(result.key_takeaways, list)
    assert isinstance(result.freshness, dict)
    assert "status" in result.freshness
    assert isinstance(result.dossier_markdown, str)
    assert "## Scorecard" in result.dossier_markdown
    assert isinstance(result.warnings, list)


def test_research_service_dossier_portfolio_fit_and_freshness(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        row = (
            {"last": 110.0, "change_percent": 2.0, "market_cap": 2_000_000_000_000}
            if symbol == "AAPL"
            else {"last": 220.0, "change_percent": -1.0, "market_cap": 1_500_000_000_000}
        )
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote",
            records=[row],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del period, interval
        closes = [100.0, 110.0, 120.0] if symbol == "AAPL" else [200.0, 195.0, 190.0]
        records = [{"close": close} for close in closes]
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="history",
            records=records,
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    result = service.dossier(
        symbols=["AAPL", "MSFT"],
        period="6mo",
        interval="1d",
        baseline_symbol="AAPL",
        thesis="Prefer higher quality growth with lower leverage.",
        risks=["macro slowdown", "valuation"],
        catalysts=["earnings beat", "new product cycle"],
        include_portfolio_fit=True,
        portfolio_weights_pct={"AAPL": 6.2, "SPY": 14.0},
    )

    assert result.headline
    assert result.compare.summary.best_period_return_symbol == "AAPL"
    assert result.compare.summary.baseline_symbol == "AAPL"
    assert result.freshness["status"] == "fresh"
    assert result.freshness["available_symbols"] == 2
    assert result.portfolio_fit["existing_symbols"] == ["AAPL"]
    assert result.portfolio_fit["new_symbols"] == ["MSFT"]
    assert result.portfolio_fit["overlap_weight_pct"] == 6.2
    assert "## Portfolio Fit" in result.dossier_markdown


def test_research_service_dossier_cites_research_evidence_packets(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote",
            records=[{"last": 110.0 if symbol == "AAPL" else 220.0, "change_percent": 1.0}],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del period, interval
        closes = [100.0, 110.0, 120.0] if symbol == "AAPL" else [200.0, 210.0, 220.0]
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="history",
            records=[{"date": f"2026-01-0{index + 1}", "close": close} for index, close in enumerate(closes)],
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    result = service.dossier(
        symbols=["AAPL", "MSFT"],
        period="6mo",
        interval="1d",
        thesis="Compare quality compounders.",
        include_portfolio_fit=False,
    )

    assert [packet["symbol"] for packet in result.evidence_packets] == ["AAPL", "MSFT"]
    assert result.evidence_packets[0]["packet_id"] == "research-evidence:yfinance:AAPL:6mo:1d"
    assert result.evidence_packets[0]["provider"] == "yfinance"
    assert result.evidence_packets[0]["freshness_status"] == "fresh"
    assert result.evidence_packets[0]["confidence"] == "high"
    assert result.evidence_packets[0]["coverage_score"] == 100.0
    assert result.evidence_packets[0]["blocking_gaps"] == []
    assert "## Evidence Packets" in result.dossier_markdown
    assert "research-evidence:yfinance:AAPL:6mo:1d" in result.dossier_markdown


def test_research_service_evidence_packet_full_data_is_fresh_and_inspectable(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote ok",
            records=[
                {
                    "name": "Apple Inc.",
                    "asset_type": "equity",
                    "last": 120.0,
                    "change_percent": 1.5,
                    "market_cap": 3_000_000_000_000,
                    "pe_ratio": 29.5,
                    "dividend_yield": 0.005,
                }
            ],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del symbol, period, interval
        return ResearchResponse(
            symbol="AAPL",
            provider="yfinance",
            available=True,
            message="history ok",
            records=[
                {"date": "2026-01-01", "close": 100.0},
                {"date": "2026-02-01", "close": 110.0},
                {"date": "2026-03-01", "close": 120.0},
            ],
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    packet = service.evidence_packet(symbol=" aapl ", period="6mo", interval="1d")

    assert packet.packet_id == "research-evidence:yfinance:AAPL:6mo:1d"
    assert packet.symbol == "AAPL"
    assert packet.name == "Apple Inc."
    assert packet.asset_type == "equity"
    assert packet.freshness["status"] == "fresh"
    assert packet.coverage["provider_status"] == "available"
    assert packet.coverage["quote_available"] is True
    assert packet.coverage["history_available"] is True
    assert packet.coverage["available_endpoint_count"] == 2
    assert packet.coverage["attempted_endpoint_count"] == 2
    assert packet.coverage["endpoint_statuses"] == [
        {"endpoint": "quote", "status": "available", "available": True, "message": "quote ok", "limitation_type": None},
        {
            "endpoint": "price_history",
            "status": "available",
            "available": True,
            "message": "history ok",
            "limitation_type": None,
        },
    ]
    assert packet.metrics["last_price"] == 120.0
    assert packet.metrics["period_change_pct"] == 20.0
    assert packet.metrics["dividend_yield_pct"] == 0.5
    assert packet.risk["drawdown_from_high_pct"] == 0.0
    assert packet.risk["all_time_high"] == 120.0
    assert packet.risk["trend50d"] == "UNKNOWN"
    assert packet.risk["trend200d"] == "UNKNOWN"
    assert packet.quality["confidence"] == "high"
    assert packet.quality["blocking_gaps"] == []
    assert packet.provenance["quote_records"] == 1
    assert packet.provenance["history_records"] == 3


def test_research_service_evidence_packet_marks_missing_history_as_partial(monkeypatch) -> None:
    service = OpenBBResearchService(provider="yfinance")

    def fake_quote(symbol: str) -> ResearchResponse:
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=True,
            message="quote ok",
            records=[{"last": 80.0, "change_percent": -0.5}],
        )

    def fake_price_history(symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        del period, interval
        return ResearchResponse(
            symbol=symbol,
            provider="yfinance",
            available=False,
            message="history unavailable",
            records=[],
        )

    monkeypatch.setattr(service, "quote", fake_quote)
    monkeypatch.setattr(service, "price_history", fake_price_history)

    packet = service.evidence_packet(symbol="msft", period="6mo", interval="1d")

    assert packet.symbol == "MSFT"
    assert packet.freshness["status"] == "partial"
    assert packet.coverage["provider_status"] == "partial"
    assert packet.coverage["endpoints_attempted"] == ["quote", "price_history"]
    assert packet.coverage["history_available"] is False
    assert packet.coverage["endpoint_statuses"][1]["status"] == "unavailable"
    assert packet.coverage["endpoint_statuses"][1]["limitation_type"] == "provider_unavailable"
    assert "history" in packet.quality["blocking_gaps"]
    assert packet.quality["confidence"] == "medium"
    assert packet.metrics["last_price"] == 80.0
    assert packet.metrics["period_change_pct"] is None
    assert packet.provenance["warnings"] == ["MSFT: history unavailable (history unavailable)"]


def test_research_service_evidence_packet_rejects_empty_symbol() -> None:
    service = OpenBBResearchService(provider="yfinance")

    with pytest.raises(ValueError, match="requires a symbol"):
        service.evidence_packet(symbol=" !!! ")
