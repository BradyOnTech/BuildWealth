"""Fee drag: the unit conversion from percentages to felt dollars."""

from buildwealth_orchestrator.services.portfolio_fees import (
    build_portfolio_fee_payload,
    normalize_expense_ratio,
)


def test_normalize_expense_ratio_conventions() -> None:
    assert normalize_expense_ratio(0.0003) == 0.0003     # provider fraction, 3 bps
    assert normalize_expense_ratio(0.02) == 0.02         # boundary stays a fraction
    assert normalize_expense_ratio(0.75) == 0.0075       # human-typed percent
    assert normalize_expense_ratio(3) == 0.03            # percent entry
    assert normalize_expense_ratio(25) is None           # 25% is a data error
    assert normalize_expense_ratio(0) is None
    assert normalize_expense_ratio(-1) is None
    assert normalize_expense_ratio("bad") is None
    assert normalize_expense_ratio(None) is None


def test_fee_payload_converts_ratios_to_dollars() -> None:
    holdings = [
        {"symbol": "SPICY", "name": "Spicy Active Fund", "asset_type": "etf", "value_usd": 100_000, "expense_ratio": 0.0075},
        {"symbol": "VTI", "name": "Total Market", "asset_type": "etf", "value_usd": 200_000, "expense_ratio": None},
        {"symbol": "AAPL", "name": "Apple", "asset_type": "stock", "value_usd": 50_000, "expense_ratio": None},
        {"symbol": "MYSTERY", "name": "Mystery Fund", "asset_type": "fund", "value_usd": 10_000, "expense_ratio": None},
    ]
    registry = [{"symbol": "VTI", "expense_ratio": 0.0003}]

    payload = build_portfolio_fee_payload(holdings, registry_rows=registry)

    assert payload["status"] == "ready"
    assert [row["symbol"] for row in payload["rows"]] == ["SPICY", "VTI"]

    spicy = payload["rows"][0]
    assert spicy["annual_fee_usd"] == 750.0
    assert spicy["index_alternative_fee_usd"] == 50.0
    assert spicy["excess_fee_usd"] == 700.0

    vti = payload["rows"][1]
    assert vti["annual_fee_usd"] == 60.0
    assert vti["excess_fee_usd"] == 0.0  # already cheaper than nothing to gain

    assert payload["total_annual_fee_usd"] == 810.0
    assert payload["total_excess_vs_index_usd"] == 700.0
    assert payload["ten_year_excess_usd"] == 7000.0
    assert payload["covered_value_usd"] == 300_000.0
    # stocks are free to hold; only the fund with no ratio counts as unknown
    assert payload["uncovered_symbols"] == ["MYSTERY"]


def test_fee_payload_without_data() -> None:
    payload = build_portfolio_fee_payload([
        {"symbol": "AAPL", "asset_type": "stock", "value_usd": 1000},
    ])
    assert payload["status"] == "no_data"
    assert payload["rows"] == []
    assert payload["weighted_expense_ratio_pct"] is None


def test_fee_payload_aggregates_multi_account_holdings() -> None:
    holdings = [
        {"symbol": "VTI", "name": "Total Market", "asset_type": "etf", "value_usd": 30_000, "expense_ratio": 0.0003},
        {"symbol": "VTI", "name": "Total Market", "asset_type": "etf", "value_usd": 10_000, "expense_ratio": None},
        {"symbol": "VTI", "name": "Total Market", "asset_type": "etf", "value_usd": 4_509.60, "expense_ratio": None},
    ]
    payload = build_portfolio_fee_payload(holdings)

    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["symbol"] == "VTI"
    assert row["value_usd"] == 44_509.60
    assert row["annual_fee_usd"] == round(44_509.60 * 0.0003, 2)
    assert payload["uncovered_symbols"] == []
