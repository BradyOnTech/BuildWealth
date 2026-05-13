from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.portfolio_audit import build_portfolio_audit_payload


def test_portfolio_audit_summarizes_import_and_registry_follow_through() -> None:
    payload = build_portfolio_audit_payload(
        import_reports=[
            {
                "report_id": "ir_1",
                "created_at": "2026-05-09T12:00:00+00:00",
                "source_file": {"name": "broker.csv"},
                "imported_activities": 4,
                "summary": {
                    "accepted_count": 4,
                    "rejected_count": 2,
                    "unresolved_count": 1,
                    "duplicate_count": 1,
                    "account_review_count": 1,
                },
            }
        ],
        asset_registry_payload={
            "items": [
                {
                    "symbol": "ODD1",
                    "held": True,
                    "quality_status": "needs_review",
                    "cost_basis": 0,
                },
                {
                    "symbol": "READY",
                    "held": True,
                    "quality_status": "unpriced",
                    "cost_basis": 100,
                },
            ]
        },
        accounts=[{"id": "default"}],
        transactions=[{"id": "txn_1"}],
        manual_prices_payload={"by_symbol": {"ODD1": {"price": 100}}},
        cost_basis_payload={"global": "FIFO", "by_symbol": {"ODD1": "FIFO"}},
        recommendations=[
            {
                "status": "proposed",
                "source": "import_workbench",
                "action_payload": {"kind": "asset_review_item"},
            }
        ],
        generated_at="2026-05-09T12:30:00+00:00",
    )

    assert payload["status"] == "attention"
    assert payload["summary"]["unresolved_import_rows"] == 1
    assert payload["summary"]["duplicate_rows"] == 1
    assert payload["summary"]["asset_review_items"] == 1
    assert payload["summary"]["asset_price_items"] == 1
    assert payload["summary"]["pending_inbox_items"] == 1
    assert payload["recent_reports"][0]["source_file_name"] == "broker.csv"
    assert payload["recent_reports"][0]["href"] == "#import-sync?report=ir_1"
    assert payload["audit_events"][0]["title"]
    assert any(item["kind"] == "import_report" for item in payload["audit_events"])
    findings = {item["id"]: item for item in payload["findings"]}
    assert findings["import_rows_need_review"]["status"] == "open"
    assert findings["asset_metadata_needed"]["href"] == "#portfolio?section=assets"


def test_portfolio_audit_clear_when_no_follow_through_needed() -> None:
    payload = build_portfolio_audit_payload(
        import_reports=[],
        asset_registry_payload={"items": []},
        accounts=[],
        transactions=[],
        manual_prices_payload={"by_symbol": {}},
        cost_basis_payload={},
        recommendations=[],
        generated_at="2026-05-09T12:30:00+00:00",
    )

    assert payload["status"] == "clear"
    assert payload["summary"]["open_findings"] == 0
    assert all(item["status"] == "clear" for item in payload["findings"])


class FakePortfolioStore:
    def list_transactions(self, limit: int = 10000):
        return [{"id": "txn_1", "symbol": "VTI"}]

    def get_holdings(self):
        return {"holdings_by_symbol": {"VTI": {"lots": [{"lot_id": "lot_1", "quantity": 2}]}}}

    def get_accounts(self):
        return [{"id": "default", "name": "Taxable"}]

    def get_manual_prices(self):
        return {"by_symbol": {"VTI": {"price": 250}}}

    def get_cost_basis_methods(self):
        return {"global": "FIFO"}

    def get_asset_metadata_map(self):
        return {"VTI": {"asset_class": "Equity"}}

    def get_fx_rates(self):
        return {"base_currency": "USD", "rates": {"USD": 1}}

    def get_fx_rates_history(self):
        return {"base_currency": "USD", "pairs": {}}


class FakeImportWorkbenchStore:
    def list_reports(self, limit: int = 200):
        return [
            {
                "report_id": "ir_1",
                "source_file": {"name": "broker.csv"},
                "imported_activities": 1,
                "summary": {},
            }
        ]


class FakeAssetRegistry:
    def search(self, limit: int = 500):
        return {"items": [{"symbol": "VTI", "quality_status": "ready"}]}


def test_portfolio_export_bundle_route_contains_recovery_evidence(monkeypatch) -> None:
    portfolio_store = FakePortfolioStore()
    import_workbench_store = FakeImportWorkbenchStore()
    monkeypatch.setattr(main, "portfolio_store", portfolio_store)
    monkeypatch.setattr(main, "import_workbench_store", import_workbench_store)
    monkeypatch.setattr(main, "asset_registry", FakeAssetRegistry())
    main.app.dependency_overrides[main.get_workspace_services] = lambda: SimpleNamespace(
        context=SimpleNamespace(permissions=ControlPlaneStore.OWNER_PERMISSIONS),
        portfolio_store=portfolio_store,
        import_workbench_store=import_workbench_store,
        recommendation_inbox=main.recommendation_inbox,
        plan_workspace=main.plan_workspace,
        snapshot_store=main.snapshot_store,
        asset_registry=main.asset_registry,
    )

    try:
        with TestClient(main.app) as client:
            response = client.get("/api/portfolio/export-bundle?limit=25")
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["transactions"] == 1
    assert payload["summary"]["lots"] == 1
    assert payload["import_reports"][0]["report_id"] == "ir_1"
    assert "manual_changes" in payload["recovery_posture"]
