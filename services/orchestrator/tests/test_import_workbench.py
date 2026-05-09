from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.schemas import (
    CsvImportReconciliationReport,
    CsvImportReconciliationRow,
    CsvImportResponse,
)
from buildwealth_orchestrator.services.import_workbench import (
    ImportWorkbenchStore,
    build_import_workbench_summary,
)


def _import_response(path: Path, *, dry_run: bool, imported_activities: int = 0) -> CsvImportResponse:
    accepted = CsvImportReconciliationRow(
        row_number=2,
        status="accepted",
        confidence_flag="medium",
        confidence_score=0.72,
        normalization_flags=["account_missing_mapping"],
        normalized_row={
            "date": "2026-01-02",
            "action": "BUY",
            "symbol": "VTI",
            "quantity": 2,
            "unit_price": 250,
            "currency": "USD",
            "account_name": "Taxable",
        },
    )
    duplicate = CsvImportReconciliationRow(
        row_number=3,
        status="rejected",
        confidence_flag="high",
        confidence_score=0.94,
        rejection_reasons=["duplicate_existing_transaction"],
        normalized_row={"date": "2026-01-02", "action": "BUY", "symbol": "VTI"},
    )
    unresolved = CsvImportReconciliationRow(
        row_number=4,
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
        parsed_rows=3,
        valid_activities=1,
        imported_activities=imported_activities,
        warnings=["Row 2: Account 'Taxable' was not found in local accounts."],
        errors=["Row 4: Missing symbol/ticker."],
        reconciliation_report=CsvImportReconciliationReport(
            parser_confidence_flag="medium",
            parser_confidence_score=0.66,
            total_rows=3,
            accepted_count=1,
            normalized_count=1,
            rejected_count=2,
            accepted_rows=[accepted],
            normalized_rows=[accepted],
            rejected_rows=[duplicate, unresolved],
        ),
    )


def test_import_workbench_summary_separates_duplicates_from_unresolved_rows(tmp_path: Path) -> None:
    source = tmp_path / "sample.csv"
    source.write_text("date,action,symbol\n", encoding="utf-8")
    summary = build_import_workbench_summary(_import_response(source, dry_run=True))

    assert summary["parsed_rows"] == 3
    assert summary["accepted_count"] == 1
    assert summary["duplicate_count"] == 1
    assert summary["unresolved_count"] == 1
    assert summary["account_review_count"] == 1
    assert summary["parser_confidence_flag"] == "medium"
    assert summary["warnings_count"] == 1
    assert summary["errors_count"] == 1


def test_import_workbench_session_apply_report_lifecycle(tmp_path: Path) -> None:
    source = tmp_path / "sample.csv"
    source.write_text("date,action,symbol\n2026-01-02,BUY,VTI\n", encoding="utf-8")
    store = ImportWorkbenchStore(
        workbench_dir=tmp_path / "workbench",
        reports_dir=tmp_path / "reports",
    )

    preview = _import_response(source, dry_run=True)
    session = store.create_session(
        file_path=source,
        original_file_name="sample.csv",
        options={"delimiter": ",", "broker_template": "auto"},
        preview_response=preview,
    )

    loaded = store.load_session(session["session_id"])
    assert loaded["status"] == "previewed"
    assert loaded["source_file"]["name"] == "sample.csv"
    assert loaded["summary"]["accepted_count"] == 1

    applied = _import_response(source, dry_run=False, imported_activities=1)
    report = store.create_report(session=loaded, apply_response=applied, operator="user")
    updated = store.update_session_after_apply(
        loaded["session_id"],
        apply_response=applied,
        report=report,
    )

    assert updated["status"] == "applied"
    assert updated["report_id"] == report["report_id"]
    assert report["imported_activities"] == 1
    assert report["summary"]["unresolved_count"] == 1
    assert report["affected_links"]["portfolio_transactions"] == "#portfolio?section=transactions"
    assert len(report["review_items"]) == 2
    review_types = {item["recommendation_type"] for item in report["review_items"]}
    assert review_types == {"asset_review_item", "portfolio_account_review_item"}
    asset_review = next(item for item in report["review_items"] if item["recommendation_type"] == "asset_review_item")
    assert asset_review["action_payload"]["row_number"] == 4
    account_review = next(
        item for item in report["review_items"] if item["recommendation_type"] == "portfolio_account_review_item"
    )
    assert account_review["action_payload"]["review_route"]["target"] == "accounts"
    assert store.load_report(report["report_id"])["session_id"] == loaded["session_id"]
    assert [item["report_id"] for item in store.list_reports()] == [report["report_id"]]
