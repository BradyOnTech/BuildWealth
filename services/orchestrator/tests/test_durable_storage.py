from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from buildwealth_orchestrator.services.durable_storage import DurableStorageMigrationService


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_service(tmp_path: Path) -> tuple[DurableStorageMigrationService, Path]:
    data_root = tmp_path / "data"
    profile_path = data_root / "profile" / "financial_profile.json"
    recommendations_path = data_root / "recommendations" / "inbox.json"
    conversation_dir = data_root / "conversations"
    plans_dir = data_root / "plans"
    portfolio_dir = data_root / "portfolio"
    snapshot_dir = data_root / "snapshots"

    _write_json(profile_path, {"schema_version": 2, "income_items": []})
    _write_json(recommendations_path, {"schema_version": 1, "items": []})
    _write_json(portfolio_dir / "transactions.json", [])
    _write_json(portfolio_dir / "holdings.json", {"schema_version": 8, "holdings": []})
    _write_json(snapshot_dir / "snapshot-20260415T000000Z.json", {"as_of": "2026-04-15T00:00:00Z"})
    _write_json(plans_dir / "index.json", {"schema_version": 2, "active_plan_id": None, "plans": []})

    conversation_dir.mkdir(parents=True, exist_ok=True)
    (conversation_dir / "conv-1.json").write_text(
        json.dumps({"conversation_id": "conv-1", "messages": []}, indent=2),
        encoding="utf-8",
    )
    plan_dir = plans_dir / "plan-alpha"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text("# Plan Alpha\n", encoding="utf-8")
    _write_json(plan_dir / "settings.json", {"schema_version": 2, "years": 30})
    (plan_dir / "decisions.jsonl").write_text(
        json.dumps({"id": "decision-1", "summary": "seed"}) + "\n",
        encoding="utf-8",
    )

    service = DurableStorageMigrationService(
        data_root=data_root,
        storage_dir=data_root / "storage",
        include_paths=[
            portfolio_dir,
            snapshot_dir,
            conversation_dir,
            plans_dir,
            profile_path,
            recommendations_path,
        ],
    )
    return service, data_root


def test_run_upgrade_creates_verified_sqlite_snapshot(tmp_path: Path) -> None:
    service, _ = _build_service(tmp_path)

    report = service.run_upgrade(run_rollback_check=True)

    assert report["documents_migrated"] > 0
    assert report["rollback_check_performed"] is True
    assert report["rollback_check_passed"] is True
    assert Path(report["database_path"]).exists()
    assert Path(report["report_path"]).exists()

    with sqlite3.connect(service.database_path) as connection:
        count = int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        assert count == report["documents_migrated"]
        migration_id = connection.execute(
            "SELECT migration_id FROM migration_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        assert migration_id == report["migration_id"]

    status = service.get_status()
    assert status["database_exists"] is True
    assert status["document_count"] == report["documents_migrated"]
    assert status["latest_migration_id"] == report["migration_id"]


def test_rollback_latest_migration_restores_source_files(tmp_path: Path) -> None:
    service, data_root = _build_service(tmp_path)
    report = service.run_upgrade(run_rollback_check=True)

    profile_path = data_root / "profile" / "financial_profile.json"
    profile_path.write_text('{"schema_version": 999, "income_items": []}', encoding="utf-8")
    assert '"schema_version": 999' in profile_path.read_text(encoding="utf-8")

    rollback_report = service.rollback_latest_migration()

    restored_payload = json.loads(profile_path.read_text(encoding="utf-8"))
    assert restored_payload["schema_version"] == 2
    assert rollback_report["migration_id"] == report["migration_id"]
    assert rollback_report["files_restored"] == report["documents_migrated"]
    assert rollback_report["database_removed"] is True
