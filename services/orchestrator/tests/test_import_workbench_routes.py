from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.schemas import (
    CsvImportReconciliationReport,
    CsvImportReconciliationRow,
    CsvImportResponse,
)


def _route_import_response(path: Path, *, dry_run: bool) -> CsvImportResponse:
    accepted = CsvImportReconciliationRow(
        row_number=2,
        status="accepted",
        confidence_flag="high",
        confidence_score=0.95,
        normalized_row={
            "date": "2026-01-02",
            "action": "BUY",
            "symbol": "VTI",
            "quantity": 2,
            "unit_price": 250,
            "currency": "USD",
        },
    )
    rejected = CsvImportReconciliationRow(
        row_number=3,
        status="rejected",
        confidence_flag="low",
        confidence_score=0.2,
        rejection_reasons=["missing_symbol"],
        raw_row={"date": "2026-01-03", "action": "BUY"},
    )
    return CsvImportResponse(
        file_path=str(path),
        dry_run=dry_run,
        selected_template="generic",
        detected_template="generic",
        parsed_rows=2,
        valid_activities=1,
        imported_activities=0 if dry_run else 1,
        errors=["Row 3: Missing symbol/ticker."],
        reconciliation_report=CsvImportReconciliationReport(
            parser_confidence_flag="high",
            parser_confidence_score=0.8,
            total_rows=2,
            accepted_count=1,
            rejected_count=1,
            accepted_rows=[accepted],
            rejected_rows=[rejected],
        ),
    )


def test_import_workbench_preview_apply_and_report_routes(monkeypatch) -> None:
    async def fake_execute_csv_import(*, file_path: Path, request):
        return _route_import_response(file_path, dry_run=bool(request.dry_run))

    monkeypatch.setattr(main, "execute_csv_import", fake_execute_csv_import)

    with TestClient(main.app) as client:
        preview_response = client.post(
            "/api/import/workbench/preview",
            files={"file": ("broker.csv", "date,action,symbol\n2026-01-02,BUY,VTI\n", "text/csv")},
            data={
                "delimiter": ",",
                "broker_template": "auto",
                "default_data_source": "YAHOO",
                "default_currency": "USD",
            },
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["status"] == "previewed"
        assert preview["source_file"]["name"] == "broker.csv"
        assert preview["summary"]["accepted_count"] == 1
        assert preview["summary"]["unresolved_count"] == 1
        assert preview["summary"]["asset_review_count"] == 1
        assert preview["summary"]["review_item_count"] == 1
        assert len(preview["review_items"]) == 1
        assert preview["review_items"][0]["action_payload"]["review_route"]["target"] == "assets"

        apply_response = client.post(
            f"/api/import/workbench/{preview['session_id']}/apply",
            json={"archive_after_success": False, "operator": "route-test"},
        )
        assert apply_response.status_code == 200
        applied = apply_response.json()
        assert applied["session"]["status"] == "applied"
        assert applied["report"]["imported_activities"] == 1
        assert applied["report"]["operator"] == "route-test"
        assert applied["report"]["affected_links"]["portfolio_transactions"] == "#portfolio?section=transactions"
        assert applied["report"]["affected_links"]["portfolio_history"].startswith("#portfolio?section=transactions&import_report=")
        assert applied["report"]["affected_links"]["import_report"].startswith("#import-sync?report=")
        assert len(applied["report"]["review_items"]) == 1
        assert applied["session"]["review_items"][0]["action_payload"]["report_id"] == applied["report"]["report_id"]

        report_id = applied["report"]["report_id"]
        review_items = [
            item
            for item in main.recommendation_inbox.list(limit=None, include_archived=True)
            if item.get("source") == "import_workbench"
            and item.get("action_payload", {}).get("report_id") == report_id
        ]
        assert len(review_items) == 1
        assert review_items[0]["recommendation_type"] == "asset_review_item"
        assert review_items[0]["action_payload"]["kind"] == "asset_review_item"
        assert review_items[0]["action_payload"]["review_route"]["route"] == "portfolio"

        inbox_response = client.get("/api/recommendations?source=import_workbench")
        assert inbox_response.status_code == 200

        report_response = client.get(f"/api/import/reports/{report_id}")
        assert report_response.status_code == 200
        assert report_response.json()["report_id"] == report_id

        list_response = client.get("/api/import/reports?limit=5")
        assert list_response.status_code == 200
        report_ids = [item["report_id"] for item in list_response.json()["reports"]]
        assert report_id in report_ids

        duplicate_apply_response = client.post(f"/api/import/workbench/{preview['session_id']}/apply", json={})
        assert duplicate_apply_response.status_code == 409
