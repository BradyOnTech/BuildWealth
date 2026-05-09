from __future__ import annotations

from buildwealth_orchestrator.services.asset_registry import AssetRegistry
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


def test_asset_registry_combines_holdings_metadata_prices_and_watchlist(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    store.add_transaction(
        date="2026-01-02",
        symbol="ZZZZ",
        action="BUY",
        quantity=2,
        unit_price=100,
        asset_class="Alternatives",
        asset_type="Private Fund",
        sector="Private Markets",
    )
    store.set_manual_price(symbol="ZZZZ", price=125, note="Statement value")
    store.upsert_watchlist_item(symbol="MSFT", note="Watch for plan fit")

    registry = AssetRegistry(store)
    payload = registry.search(query="", limit=20)
    by_symbol = {item["symbol"]: item for item in payload["items"]}

    assert by_symbol["ZZZZ"]["held"] is True
    assert by_symbol["ZZZZ"]["manual_price"] is True
    assert by_symbol["ZZZZ"]["quality_label"] == "Ready"
    assert by_symbol["ZZZZ"]["current_price"] == 125
    assert by_symbol["MSFT"]["watchlisted"] is True
    assert by_symbol["MSFT"]["quality_label"] == "Ready"


def test_asset_registry_update_metadata_resolves_review_state(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio")
    store.upsert_asset_metadata(
        "ODD1",
        {
            "name": "Odd Asset",
            "data_source": "MANUAL",
        },
    )

    registry = AssetRegistry(store)
    before = registry.detail("ODD1")
    assert before is not None
    assert before["quality_status"] == "needs_review"
    assert "Asset class is missing." in before["review_reasons"]

    after = registry.update_metadata(
        "ODD1",
        {
            "asset_type": "Collectible",
            "asset_class": "Alternatives",
            "sector": "Collectibles",
            "region": "US",
        },
    )

    assert after["quality_status"] == "ready"
    assert after["asset_class"] == "Alternatives"
    assert after["asset_type"] == "Collectible"


def test_asset_registry_uses_plain_needs_price_label_for_priced_gap() -> None:
    class FakePortfolioStore:
        def get_holdings(self) -> dict:
            return {
                "holdings_by_symbol": {
                    "READY": {
                        "symbol": "READY",
                        "name": "Ready Asset",
                        "asset_class": "Alternatives",
                        "asset_type": "Private Fund",
                        "accounts": ["default"],
                    }
                }
            }

        def get_asset_metadata_map(self) -> dict:
            return {}

        def get_manual_prices(self) -> dict:
            return {"by_symbol": {}}

        def list_watchlist(self) -> list:
            return []

    registry = AssetRegistry(FakePortfolioStore())  # type: ignore[arg-type]
    item = registry.detail("READY")

    assert item is not None
    assert item["quality_status"] == "unpriced"
    assert item["quality_label"] == "Needs price"
