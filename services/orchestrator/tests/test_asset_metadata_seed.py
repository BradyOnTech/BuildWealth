from buildwealth_orchestrator.services.asset_metadata_seed import (
    infer_asset_metadata,
    load_seed_asset_metadata,
)


def test_load_seed_asset_metadata_returns_known_symbol_records() -> None:
    metadata = load_seed_asset_metadata()

    assert "AAPL" in metadata
    apple = metadata["AAPL"]
    assert apple["name"] == "Apple Inc."
    assert apple["asset_type"] == "EQUITY"
    assert apple["data_source"] == "YAHOO"


def test_seed_carries_expense_ratios_for_common_funds() -> None:
    metadata = load_seed_asset_metadata()

    # Fractions, not percents: 0.0003 = 3 bps.
    assert metadata["VTI"]["expense_ratio"] == 0.0003
    assert metadata["BND"]["expense_ratio"] == 0.0003
    assert metadata["SCHD"]["expense_ratio"] == 0.0006
    assert metadata["SGOV"]["expense_ratio"] == 0.0009
    assert metadata["VXUS"]["expense_ratio"] == 0.0008
    # Individual stocks carry no expense ratio.
    assert "expense_ratio" not in metadata["AAPL"]

    for symbol, record in metadata.items():
        ratio = record.get("expense_ratio")
        if ratio is not None:
            assert 0 < ratio <= 0.05, f"{symbol} expense ratio {ratio} is not a sane fraction"


def test_infer_asset_metadata_returns_expected_fallbacks() -> None:
    cash = infer_asset_metadata("usd")
    crypto = infer_asset_metadata("btc-usd")
    forex = infer_asset_metadata("eur=x")
    equity = infer_asset_metadata("msft")

    assert cash is not None
    assert cash["asset_type"] == "CASH"
    assert crypto is not None
    assert crypto["asset_class"] == "Crypto"
    assert forex is not None
    assert forex["asset_type"] == "FOREX"
    assert equity is not None
    assert equity["metadata_source"] == "fallback"
