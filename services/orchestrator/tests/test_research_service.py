from buildwealth_orchestrator.schemas import ResearchResponse
from buildwealth_orchestrator.services.research import OpenBBResearchService


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
