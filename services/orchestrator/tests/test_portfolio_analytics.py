from __future__ import annotations

from buildwealth_orchestrator.services.portfolio_analytics import build_portfolio_analytics_payload


def test_portfolio_analytics_payload_sanitizes_internal_engine_labels() -> None:
    payload = build_portfolio_analytics_payload(
        holdings_payload={
            "total_portfolio_value": 1200,
            "net_performance": 200,
            "net_performance_pct": 20,
            "performance": {
                "total_return_usd": 200,
                "price_return_usd": 180,
                "income_return_usd": 20,
                "fees_paid_usd": 3.5,
                "twr_annualized_return_pct": 12.5,
                "xirr_annualized_return_pct": 11.2,
                "net_contributions": 1000,
            },
            "allocation_breakdowns": {
                "asset_class": [{"key": "Equity", "allocation_pct": 80, "value": 960}],
                "sector": [{"key": "Technology", "allocation_pct": 40, "value": 480}],
                "region": [{"key": "US", "allocation_pct": 90, "value": 1080}],
            },
            "risk_alerts": {
                "status": "warning",
                "breach_count": 1,
                "watch_count": 0,
                "metrics": {
                    "top_holding_symbol": "VTI",
                    "top_holding_pct": 40,
                    "largest_account_id": "taxable",
                    "largest_account_pct": 70,
                    "largest_asset_class": "Equity",
                    "largest_asset_class_pct": 80,
                    "largest_sector": "Technology",
                    "largest_sector_pct": 40,
                    "largest_region": "US",
                    "largest_region_pct": 90,
                    "effective_positions": 3.4,
                },
                "alerts": [
                    {
                        "metric": "sector",
                        "label": "Largest sector concentration",
                        "message": "Technology is above the limit.",
                        "recommendation": "Broaden sector exposure.",
                    }
                ],
            },
        },
        benchmark_response={
            "benchmark_symbols": ["SPY"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
            "summary": {
                "portfolio_return_pct": 20,
                "benchmark_return_pct_by_symbol": {"SPY": 10},
                "alpha_pct_by_symbol": {"SPY": 10},
                "max_drawdown_pct": -2,
            },
            "series": [],
            "warnings": ["Portfolio benchmark local calculation selected; using local fallback"],
        },
        attribution_response={
            "summary": {
                "portfolio_total_return_base": 200,
                "portfolio_total_value_base": 1200,
                "accounted_return_base": 200,
                "residual_return_base": 0,
                "contributors_count": 1,
                "detractors_count": 0,
            },
            "contributors": [
                {
                    "symbol": "VTI",
                    "name": "Vanguard Total Stock Market ETF",
                    "total_return_base": 200,
                    "total_return_pct": 20,
                    "contribution_pct": 100,
                    "allocation_pct": 100,
                }
            ],
            "detractors": [],
            "warnings": ["Portfolio attribution local calculation selected; using local fallback"],
        },
        period="mtd",
        snapshot_limit=31,
        generated_at="2026-05-09T12:00:00+00:00",
    )

    assert payload["status"] == "ready"
    assert payload["period"]["id"] == "mtd"
    assert payload["performance"]["total_return_usd"] == 200
    assert payload["performance"]["fees_paid_usd"] == 3.5
    assert payload["benchmark"]["rows"][0]["alpha_pct"] == 10
    assert payload["attribution"]["contributors"][0]["symbol"] == "VTI"
    assert payload["risk_explanations"]["rows"][0]["label"] == "Largest holding"
    assert payload["risk_explanations"]["alerts"][0]["metric"] == "sector"
    assert "Portfolio Analysis" not in " ".join(payload["warnings"])


def test_portfolio_analytics_payload_can_be_partial_without_snapshots() -> None:
    payload = build_portfolio_analytics_payload(
        holdings_payload={"performance": {}},
        benchmark_error="At least 2 snapshots are required for benchmark comparison",
        attribution_response={
            "summary": {
                "portfolio_total_return_base": 0,
                "portfolio_total_value_base": 0,
                "accounted_return_base": 0,
                "residual_return_base": 0,
                "contributors_count": 0,
                "detractors_count": 0,
            },
            "contributors": [],
            "detractors": [],
        },
        generated_at="2026-05-09T12:00:00+00:00",
    )

    assert payload["status"] == "partial"
    assert payload["benchmark"]["status"] == "unavailable"
    assert payload["attribution"]["status"] == "ready"
