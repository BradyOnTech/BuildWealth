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
