from __future__ import annotations

from buildwealth_orchestrator.services.housing_exposure import build_housing_exposure_payload


def _holdings() -> dict:
    return {
        "MY_HOME": {
            "symbol": "MY_HOME",
            "name": "Primary residence",
            "asset_type": "property",
            "asset_class": "real_estate",
            "current_value": 500000,
        },
        "VTI": {
            "symbol": "VTI",
            "name": "Total Market",
            "asset_type": "etf",
            "asset_class": "equity",
            "current_value": 80000,
        },
        "VNQ": {
            # REIT fund: real-estate asset CLASS but fully tradable — belongs
            # to invested money, not the housing lens.
            "symbol": "VNQ",
            "name": "REIT Index",
            "asset_type": "etf",
            "asset_class": "real_estate",
            "current_value": 20000,
        },
    }


def test_home_with_mortgage_yields_equity_picture() -> None:
    payload = build_housing_exposure_payload(
        _holdings(),
        debt_items=[
            {"id": "d1", "label": "Home mortgage", "balance_usd": 320000, "interest_rate": 0.052},
            {"id": "d2", "label": "Car loan", "balance_usd": 12000},
        ],
    )
    assert payload["status"] == "ready"
    assert payload["home_value_usd"] == 500000
    assert payload["mortgage_balance_usd"] == 320000
    assert payload["equity_usd"] == 180000
    assert payload["loan_to_value_pct"] == 64.0
    # 500k of 600k total assets
    assert payload["share_of_total_assets_pct"] == 83.3
    assert [row["label"] for row in payload["properties"]] == ["Primary residence"]
    assert any("Equity is what's yours" in note for note in payload["notes"])
    assert any("recommendation" in note for note in payload["notes"])


def test_home_without_mortgage_prompts_for_the_loan() -> None:
    payload = build_housing_exposure_payload(_holdings(), debt_items=[])
    assert payload["equity_usd"] is None
    assert payload["loan_to_value_pct"] is None
    assert any("No mortgage recorded" in note for note in payload["notes"])


def test_no_housing_returns_none_status() -> None:
    holdings = {key: value for key, value in _holdings().items() if key != "MY_HOME"}
    payload = build_housing_exposure_payload(holdings, debt_items=[])
    assert payload["status"] == "none"
    assert payload["properties"] == []


def test_profile_physical_asset_counts_once() -> None:
    # The same home recorded both as a portfolio custom asset and a profile
    # physical asset must not double-count.
    payload = build_housing_exposure_payload(
        _holdings(),
        physical_assets=[
            {"id": "p1", "label": "House", "asset_type": "real_estate", "current_value_usd": 500000},
            {"id": "p2", "label": "Lake cabin", "asset_type": "real_estate", "current_value_usd": 150000},
            {"id": "p3", "label": "Truck", "asset_type": "vehicle", "current_value_usd": 30000},
        ],
    )
    assert payload["home_value_usd"] == 650000
    assert len(payload["properties"]) == 2
    # Vehicle counts toward other assets, not housing: 650k / (650k + 100k + 30k)
    assert payload["share_of_total_assets_pct"] == 83.3


def test_explicit_portfolio_symbol_wins_when_profile_value_is_stale() -> None:
    payload = build_housing_exposure_payload(
        _holdings(),
        physical_assets=[
            {
                "id": "p1",
                "label": "House",
                "asset_type": "real_estate",
                "current_value_usd": 475000,
                "portfolio_symbol": "MY_HOME",
            }
        ],
    )

    assert payload["home_value_usd"] == 500000
    assert len(payload["properties"]) == 1
