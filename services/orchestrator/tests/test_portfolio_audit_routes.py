from __future__ import annotations

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main


class FakeImportWorkbenchStore:
    def list_reports(self, *, limit: int = 25) -> list[dict]:
        return [
            {
                "report_id": "ir_route",
                "created_at": "2026-05-09T12:00:00+00:00",
                "source_file": {"name": "route.csv"},
                "imported_activities": 2,
                "summary": {
                    "accepted_count": 2,
                    "rejected_count": 1,
                    "unresolved_count": 1,
                    "duplicate_count": 0,
                    "account_review_count": 0,
                },
            }
        ][:limit]


class FakeAssetRegistry:
    def search(self, query: str = "", limit: int = 100) -> dict:
        return {
            "query": query,
            "count": 1,
            "items": [
                {
                    "symbol": "ODD1",
                    "name": "Odd Asset",
                    "held": True,
                    "quality_status": "needs_review",
                    "quality_label": "Needs review",
                    "cost_basis": 0,
                }
            ],
        }


class FakePortfolioStore:
    def get_accounts(self) -> list[dict]:
        return [{"id": "default", "name": "Default"}]

    def list_transactions(self, limit: int = 500) -> list[dict]:
        return [{"id": "txn_route"}]

    def get_manual_prices(self) -> dict:
        return {"by_symbol": {}}

    def get_cost_basis_methods(self) -> dict:
        return {"global": "FIFO"}


class FakeRecommendationInbox:
    def list(self, **kwargs) -> list[dict]:
        return [
            {
                "status": "proposed",
                "source": "import_workbench",
                "action_payload": {"kind": "asset_review_item"},
            }
        ]


def test_portfolio_audit_route(monkeypatch) -> None:
    monkeypatch.setattr(main, "import_workbench_store", FakeImportWorkbenchStore())
    monkeypatch.setattr(main, "asset_registry", FakeAssetRegistry())
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "recommendation_inbox", FakeRecommendationInbox())

    with TestClient(main.app) as client:
        response = client.get("/api/portfolio/audit?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attention"
    assert payload["summary"]["import_reports"] == 1
    assert payload["summary"]["pending_inbox_items"] == 1
    assert payload["recent_reports"][0]["source_file_name"] == "route.csv"
    assert any(item["id"] == "asset_metadata_needed" for item in payload["findings"])
