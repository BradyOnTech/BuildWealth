from buildwealth_orchestrator.services.portfolio_metrics import concentration_metrics


def test_concentration_metrics_empty_holdings_returns_zeroed_metrics() -> None:
    metrics = concentration_metrics([])

    assert metrics == {
        "top_positions": [],
        "herfindahl_index": 0.0,
        "effective_number_of_positions": 0.0,
    }


def test_concentration_metrics_coerces_numeric_values_and_sorts_positions() -> None:
    metrics = concentration_metrics(
        [
            {"symbol": "VXUS", "name": "Intl", "value_usd": "30000"},
            {"symbol": "VTI", "name": "US", "value_usd": 50000},
            {"symbol": "BND", "name": "Bond", "value_usd": 20000.0},
        ]
    )

    assert [row["symbol"] for row in metrics["top_positions"]] == ["VTI", "VXUS", "BND"]
    assert metrics["herfindahl_index"] == 0.38
    assert metrics["effective_number_of_positions"] == 2.63


def test_concentration_metrics_limits_top_positions_to_ten() -> None:
    holdings = [{"symbol": f"S{i}", "name": f"Name {i}", "value_usd": 1000} for i in range(1, 12)]

    metrics = concentration_metrics(holdings)

    assert len(metrics["top_positions"]) == 10
    assert metrics["top_positions"][0]["symbol"] == "S1"
    assert metrics["herfindahl_index"] == 0.0909
    assert metrics["effective_number_of_positions"] == 11.0
