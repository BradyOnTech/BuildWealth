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
