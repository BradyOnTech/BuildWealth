from buildwealth_orchestrator.services.portfolio_risk_alerts import (
    calculate_portfolio_risk_alerts,
    normalize_risk_thresholds,
)


def _holding(
    symbol: str,
    value: float,
    account: str = "default",
    *,
    asset_class: str | None = None,
    sector: str | None = None,
    region: str | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "account": account,
        "current_value": value,
        "asset_class": asset_class,
        "sector": sector,
        "region": region,
    }


def test_calculate_portfolio_risk_alerts_flags_breaches() -> None:
    holdings = {
        "default:AAPL": _holding("AAPL", 70000, "default"),
        "default:MSFT": _holding("MSFT", 20000, "default"),
        "roth_ira:BND": _holding("BND", 10000, "roth_ira"),
    }
    account_totals = {
        "default": {"total_value": 90000},
        "roth_ira": {"total_value": 10000},
    }
    allocation_breakdowns = {
        "asset_class": [{"key": "US Stocks", "value": 90000, "allocation_pct": 90.0}],
        "sector": [{"key": "Technology", "value": 70000, "allocation_pct": 70.0}],
        "region": [{"key": "US", "value": 90000, "allocation_pct": 90.0}],
    }

    payload = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals=account_totals,
        allocation_breakdowns=allocation_breakdowns,
        thresholds=None,
    )

    assert payload["status"] == "critical"
    assert payload["breach_count"] >= 6
    alert_ids = {item["id"] for item in payload["alerts"]}
    assert "single_holding_concentration" in alert_ids
    assert "top3_concentration" in alert_ids
    assert "account_cluster_risk" in alert_ids
    assert "hhi_concentration" in alert_ids
    assert payload["metrics"]["top_holding_symbol"] == "AAPL"
    assert payload["metrics"]["top_holding_pct"] == 70.0


def test_calculate_portfolio_risk_alerts_supports_watch_state() -> None:
    holdings = {
        "default:AAPL": _holding("AAPL", 37_000, asset_class="US Stocks", sector="Technology", region="US"),
        "default:MSFT": _holding("MSFT", 31_000, asset_class="US Stocks", sector="Technology", region="US"),
        "default:BND": _holding("BND", 19_000, asset_class="US Bonds", sector="Fixed Income", region="US"),
        "default:VXUS": _holding("VXUS", 13_000, asset_class="International Stocks", sector="International", region="International"),
    }
    account_totals = {"default": {"total_value": 100000}}
    allocation_breakdowns = {
        "asset_class": [{"key": "US Stocks", "value": 74000, "allocation_pct": 74.0}],
        "sector": [{"key": "Technology", "value": 37000, "allocation_pct": 37.0}],
        "region": [{"key": "US", "value": 68000, "allocation_pct": 68.0}],
    }
    thresholds = {
        "single_holding_max_pct": 40.0,
        "top3_holdings_max_pct": 95.0,
        "account_max_pct": 100.0,
        "asset_class_max_pct": 75.0,
        "sector_max_pct": 70.0,
        "region_max_pct": 90.0,
        "hhi_max": 1.0,
        "effective_positions_min": 1.0,
    }

    payload = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals=account_totals,
        allocation_breakdowns=allocation_breakdowns,
        thresholds=thresholds,
    )

    assert payload["status"] == "warning"
    assert payload["breach_count"] == 0
    assert payload["watch_count"] > 0
    assert all(item["state"] == "watch" for item in payload["alerts"])


def test_normalize_risk_thresholds_clamps_bounds() -> None:
    normalized = normalize_risk_thresholds(
        {
            "single_holding_max_pct": 150,
            "top3_holdings_max_pct": -5,
            "hhi_max": -1,
            "effective_positions_min": 1000,
        }
    )
    assert normalized["single_holding_max_pct"] == 100.0
    assert normalized["top3_holdings_max_pct"] == 0.0
    assert normalized["hhi_max"] == 0.01
    assert normalized["effective_positions_min"] == 100.0
