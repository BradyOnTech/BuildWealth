from buildwealth_orchestrator.services.portfolio_risk_alerts import (
    apply_investment_policy_thresholds,
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


def _untradable_home(value: float, account: str = "home") -> dict[str, object]:
    """A primary residence: housing, not invested money."""
    return {
        "symbol": "DEMO_HOME",
        "account": account,
        "current_value": value,
        "asset_type": "property",
        "asset_class": "Real Estate",
        "is_custom_asset": True,
        "valuation_method": "manual",
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
    # Fully investable portfolio: the investable base is the whole portfolio.
    assert payload["metrics"]["total_market_value"] == 100_000.0
    assert payload["metrics"]["investable_market_value"] == 100_000.0


def test_untradable_home_is_excluded_from_concentration() -> None:
    holdings = {
        "home:DEMO_HOME": _untradable_home(420_000.0),
        "default:AAPL": _holding("AAPL", 40_000.0, asset_class="US Stocks", sector="Technology", region="US"),
        # REIT ETF: asset_class real estate, but asset TYPE etf — fully investable.
        "default:VNQ": {
            "symbol": "VNQ",
            "account": "default",
            "current_value": 10_000.0,
            "asset_type": "etf",
            "asset_class": "Real Estate",
            "sector": "Real Estate",
            "region": "US",
        },
    }
    account_totals = {
        "home": {"total_value": 420_000.0},
        "default": {"total_value": 50_000.0},
    }

    payload = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals=account_totals,
        allocation_breakdowns=None,
        thresholds=None,
    )

    metrics = payload["metrics"]
    # Both bases are reported: full portfolio for other consumers,
    # investable for every concentration percentage.
    assert metrics["total_market_value"] == 470_000.0
    assert metrics["investable_market_value"] == 50_000.0
    # The home is not the top holding — the largest FUND is, on the investable base.
    assert metrics["top_holding_symbol"] == "AAPL"
    assert metrics["top_holding_pct"] == 80.0
    assert metrics["positions_count"] == 2  # home excluded, REIT ETF included
    assert metrics["largest_asset_class"] == "US Stocks"
    assert metrics["largest_asset_class_pct"] == 80.0

    alert_ids = {item["id"] for item in payload["alerts"]}
    assert "single_holding_concentration" in alert_ids
    single = next(item for item in payload["alerts"] if item["id"] == "single_holding_concentration")
    assert single["context"]["symbol"] == "AAPL"
    for alert in payload["alerts"]:
        assert "DEMO_HOME" not in str(alert)
    # Only one investable account remains once the house-only account drops
    # out, so account concentration is not compared at all.
    assert "account_cluster_risk" not in alert_ids
    assert metrics["largest_account_id"] == "default"


def test_untradable_home_in_shared_account_reduces_account_base() -> None:
    holdings = {
        "default:DEMO_HOME": _untradable_home(420_000.0, account="default"),
        "default:AAPL": _holding("AAPL", 30_000.0, account="default"),
        "roth_ira:BND": _holding("BND", 20_000.0, account="roth_ira"),
    }
    account_totals = {
        "default": {"total_value": 450_000.0},
        "roth_ira": {"total_value": 20_000.0},
    }

    payload = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals=account_totals,
        allocation_breakdowns=None,
        thresholds=None,
    )

    metrics = payload["metrics"]
    # default account: 450k total minus the 420k home leaves 30k investable
    # against roth_ira's 20k -> 60% of the investable account base.
    assert metrics["largest_account_id"] == "default"
    assert metrics["largest_account_pct"] == 60.0


def test_all_untradable_portfolio_produces_no_concentration_alerts() -> None:
    holdings = {"home:DEMO_HOME": _untradable_home(420_000.0)}
    payload = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals={"home": {"total_value": 420_000.0}, "cash": {"total_value": 5_000.0}},
        allocation_breakdowns={
            "asset_class": [{"key": "Real Estate", "value": 420_000.0, "allocation_pct": 100.0}],
        },
        thresholds=None,
    )

    assert payload["alerts"] == []
    assert payload["status"] == "ok"
    assert payload["metrics"]["total_market_value"] == 420_000.0
    assert payload["metrics"]["investable_market_value"] == 0.0
    assert payload["metrics"]["top_holding_symbol"] is None
    assert payload["metrics"]["herfindahl_index"] is None


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


def test_profile_investment_policy_overrides_generic_risk_defaults() -> None:
    thresholds = apply_investment_policy_thresholds(
        None,
        {
            "max_single_symbol_exposure_pct": 10,
            "max_sector_exposure_pct": 30,
            "max_asset_class_exposure_pct": {"equity": 75},
        },
    )

    assert thresholds["single_holding_max_pct"] == 10
    assert thresholds["sector_max_pct"] == 30
    assert thresholds["asset_class_max_pct"] == 75


def test_broad_index_fund_uses_company_lookthrough_not_wrapper_as_single_stock_risk() -> None:
    payload = calculate_portfolio_risk_alerts(
        holdings={
            "brokerage:VTI": {
                "symbol": "VTI",
                "account": "brokerage",
                "current_value": 100_000,
                "asset_type": "etf",
                "asset_class": "equity",
            }
        },
        account_totals={"brokerage": {"total_value": 100_000}},
        allocation_breakdowns=None,
        thresholds={
            "single_holding_max_pct": 10,
            "top3_holdings_max_pct": 60,
            "sector_max_pct": 35,
        },
    )

    metrics = payload["metrics"]
    assert metrics["top_wrapper_symbol"] == "VTI"
    assert metrics["top_wrapper_pct"] == 100
    assert metrics["lookthrough_covered_value_usd"] == 100_000
    assert metrics["top_holding_symbol"] != "VTI"
    assert metrics["top_holding_pct"] < 10
    alert_ids = {item["id"] for item in payload["alerts"]}
    assert "single_holding_concentration" not in alert_ids
    assert "hhi_concentration" not in alert_ids
    assert "effective_positions" not in alert_ids
    assert "fund_wrapper_concentration" in alert_ids
    wrapper = next(item for item in payload["alerts"] if item["id"] == "fund_wrapper_concentration")
    assert wrapper["state"] == "watch"
    assert wrapper["severity"] == "low"
