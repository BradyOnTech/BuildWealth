from __future__ import annotations

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
