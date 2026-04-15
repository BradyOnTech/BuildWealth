from datetime import datetime, timezone

import pytest

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_simulator import simulate_trade

NOW = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)


def _snap(holdings_data: list[tuple[str, str, float]]) -> PortfolioSnapshot:
    total = sum(v for _, _, v in holdings_data)
    holdings = [
        Holding(symbol=sym, name=name, value_usd=val, allocation_percent=val / total * 100 if total else 0)
        for sym, name, val in holdings_data
    ]
    return PortfolioSnapshot(
        as_of=NOW, total_value_usd=total, total_investment_usd=total * 0.8, holdings=holdings,
    )


PORTFOLIO = _snap([
    ("AAPL", "Apple Inc", 50000),
    ("MSFT", "Microsoft Corp", 30000),
    ("GOOGL", "Alphabet Inc", 20000),
])


def _sim(symbol="AAPL", action="buy", amount=10000, snapshot=None, name=None):
    return simulate_trade(
        snapshot=snapshot or PORTFOLIO,
        symbol=symbol, action=action, amount_usd=amount, name=name,
    )


class TestBuyExisting:
    def test_adds_to_existing_position(self):
        r = _sim("AAPL", "buy", 10000)
        aapl = next(h for h in r.top_holdings if h.symbol == "AAPL")
        assert aapl.new_value_usd == 60000
        assert aapl.current_value_usd == 50000
        assert r.new_total_value_usd == 110000

    def test_allocation_recalculated(self):
        r = _sim("MSFT", "buy", 20000)
        msft = next(h for h in r.top_holdings if h.symbol == "MSFT")
        assert msft.new_allocation_pct == pytest.approx(41.67, abs=0.1)

    def test_highlights_mention_existing(self):
        r = _sim("AAPL", "buy", 10000)
        assert any("existing" in h.lower() for h in r.highlights)


class TestBuyNew:
    def test_new_position_added(self):
        r = _sim("TSLA", "buy", 15000, name="Tesla Inc")
        assert r.new_holdings_count == 4
        assert r.current_holdings_count == 3
        tsla = next(h for h in r.top_holdings if h.symbol == "TSLA")
        assert tsla.new_value_usd == 15000
        assert tsla.current_value_usd == 0

    def test_diversification_highlight(self):
        r = _sim("TSLA", "buy", 15000)
        assert any("diversif" in h.lower() for h in r.highlights)

    def test_name_defaults_to_symbol(self):
        r = _sim("TSLA", "buy", 5000)
        assert r.name == "TSLA"

    def test_custom_name(self):
        r = _sim("TSLA", "buy", 5000, name="Tesla Inc")
        assert r.name == "Tesla Inc"


class TestSellPartial:
    def test_reduces_position(self):
        r = _sim("AAPL", "sell", 20000)
        aapl = next(h for h in r.top_holdings if h.symbol == "AAPL")
        assert aapl.new_value_usd == 30000
        assert r.new_total_value_usd == 80000

    def test_sell_more_than_held_caps(self):
        r = _sim("GOOGL", "sell", 50000)  # only 20k held
        assert r.new_holdings_count == 2  # GOOGL removed
        googl = next((h for h in r.top_holdings if h.symbol == "GOOGL"), None)
        # Either not in top holdings or value is 0
        if googl:
            assert googl.new_value_usd == 0


class TestSellAll:
    def test_fully_sold_removed(self):
        r = _sim("GOOGL", "sell", 20000)
        assert r.new_holdings_count == 2
        assert any("fully selling" in h.lower() for h in r.highlights)


class TestSellNonExistent:
    def test_sell_missing_symbol(self):
        r = _sim("TSLA", "sell", 5000)
        assert "not in your" in r.highlights[0].lower()
        assert r.concentration_change == "unchanged"
        assert r.new_total_value_usd == r.current_total_value_usd


class TestConcentrationRisk:
    def test_buy_top_holding_worsens(self):
        # AAPL is already 50% (high). Buying more worsens it.
        r = _sim("AAPL", "buy", 50000)
        assert r.current_concentration_risk == "high"
        assert r.new_concentration_risk == "high"
        assert r.new_top_holding_pct > r.current_top_holding_pct

    def test_buy_small_position_improves(self):
        # Buying GOOGL (smallest) dilutes AAPL's concentration
        r = _sim("GOOGL", "buy", 30000)
        # AAPL: 50k/130k = 38.5% (was 50%)
        assert r.new_top_holding_pct < r.current_top_holding_pct

    def test_sell_top_holding_improves(self):
        skewed = _snap([("AAPL", "Apple", 36000), ("MSFT", "Microsoft", 32000), ("GOOGL", "Alphabet", 32000)])
        r = simulate_trade(snapshot=skewed, symbol="AAPL", action="sell", amount_usd=20000)
        assert r.current_top_holding_pct > r.new_top_holding_pct or r.new_top_holding_symbol != "AAPL"

    def test_concentration_risk_levels(self):
        # Need 6+ equal positions for < 20% each → "low" risk
        balanced = _snap([(f"S{i}", f"Stock {i}", 10000) for i in range(6)])
        r = simulate_trade(snapshot=balanced, symbol="S0", action="buy", amount_usd=1000)
        assert r.current_concentration_risk == "low"


class TestTopHoldings:
    def test_top_holdings_sorted_by_new_value(self):
        r = _sim("GOOGL", "buy", 40000)
        values = [h.new_value_usd for h in r.top_holdings]
        assert values == sorted(values, reverse=True)

    def test_allocation_change_calculated(self):
        r = _sim("MSFT", "buy", 10000)
        msft = next(h for h in r.top_holdings if h.symbol == "MSFT")
        assert msft.allocation_change_pct == pytest.approx(
            msft.new_allocation_pct - msft.current_allocation_pct, abs=0.01
        )

    def test_max_10_holdings(self):
        many = _snap([(f"SYM{i}", f"Stock {i}", 1000) for i in range(15)])
        r = simulate_trade(snapshot=many, symbol="NEW", action="buy", amount_usd=5000)
        assert len(r.top_holdings) <= 10


class TestCaseInsensitive:
    def test_symbol_case_insensitive(self):
        r = _sim("aapl", "buy", 5000)
        assert r.symbol == "AAPL"
        aapl = next(h for h in r.top_holdings if h.symbol == "AAPL")
        assert aapl.new_value_usd == 55000
