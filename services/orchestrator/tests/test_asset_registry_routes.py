from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore


class FakeAssetRegistry:
    def search(self, query: str = "", limit: int = 100) -> dict:
        return {
            "query": query,
            "count": 1,
            "items": [
                {
                    "symbol": "ODD1",
                    "name": "Odd Asset",
                    "asset_type": None,
                    "asset_class": None,
                    "held": False,
                    "watchlisted": False,
                    "custom": True,
                    "manual_price": False,
                    "manual_price_detail": {},
                    "provenance": [
                        {
                            "source": "manual",
                            "label": "Manual metadata",
                            "detail": "Saved in the local asset registry.",
                        }
                    ],
                    "tags": ["Custom"],
                    "quality_status": "needs_review",
                    "quality_label": "Needs review",
                    "review_reasons": ["Asset class is missing."],
                }
            ],
        }

    def detail(self, symbol: str) -> dict | None:
        if symbol.upper() != "ODD1":
            return None
        return self.search(query=symbol)["items"][0]

    def update_metadata(self, symbol: str, updates: dict) -> dict:
        item = self.detail(symbol)
        if item is None:
            raise ValueError("Asset not found.")
        return {
            **item,
            **updates,
            "quality_status": "ready",
            "quality_label": "Ready",
            "review_reasons": [],
        }


def test_asset_registry_routes(monkeypatch) -> None:
    services = SimpleNamespace(
        context=SimpleNamespace(permissions=ControlPlaneStore.OWNER_PERMISSIONS),
        asset_registry=FakeAssetRegistry(),
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services

    try:
        with TestClient(main.app) as client:
            search_response = client.get("/api/portfolio/assets/search?q=odd")
            assert search_response.status_code == 200
            assert search_response.json()["items"][0]["quality_label"] == "Needs review"

            detail_response = client.get("/api/portfolio/assets/ODD1")
            assert detail_response.status_code == 200
            assert detail_response.json()["symbol"] == "ODD1"
            assert detail_response.json()["provenance"][0]["label"] == "Manual metadata"

            update_response = client.put(
                "/api/portfolio/assets/ODD1/metadata",
                json={"asset_class": "Alternatives", "asset_type": "Collectible"},
            )
            assert update_response.status_code == 200
            assert update_response.json()["quality_label"] == "Ready"
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)
