from __future__ import annotations

import json
from pathlib import Path

from buildwealth_orchestrator.services.backup_restore import BackupRestoreService


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_fixture(tmp_path: Path) -> tuple[BackupRestoreService, Path]:
    data_root = tmp_path / "data"
    backup_dir = data_root / "backups"
    _write_text(data_root / "portfolio" / "transactions.json", json.dumps([{"id": "tx-1"}], indent=2))
    _write_text(data_root / "profile" / "financial_profile.json", json.dumps({"schema_version": 2}, indent=2))
    _write_text(data_root / "plans" / "plan-alpha" / "plan.md", "# Plan Alpha\n")
    _write_text(
        data_root / "conversations" / "conv-1.json",
        json.dumps({"conversation_id": "conv-1", "messages": []}, indent=2),
    )
    service = BackupRestoreService(data_root=data_root, backup_dir=backup_dir)
    return service, data_root


def test_create_and_list_backups(tmp_path: Path) -> None:
    service, _ = _build_fixture(tmp_path)

    report = service.create_backup(reason="test_run")
    listing = service.list_backups()

    assert report["backup_id"]
    assert report["files_backed_up"] >= 4
    assert Path(report["archive_path"]).exists()
    assert len(listing["backups"]) == 1
    assert listing["backups"][0]["backup_id"] == report["backup_id"]


def test_backup_excludes_and_restore_preserves_local_decryption_key(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    backup_dir = data_root / "backups"
    key_path = data_root / "control" / "local_secret.key"
    _write_text(key_path, "key-material-that-must-not-be-archived")
    _write_text(data_root / "workspaces" / "one" / "workspace_secrets.json", "encrypted")
    service = BackupRestoreService(
        data_root=data_root,
        backup_dir=backup_dir,
        excluded_paths=(key_path,),
    )

    backup = service.create_backup(reason="secret-boundary")
    import tarfile

    with tarfile.open(backup["archive_path"], "r:gz") as archive:
        assert "control/local_secret.key" not in archive.getnames()
    key_path.write_text("current-key", encoding="utf-8")
    service.restore_backup(backup_id=backup["backup_id"], create_pre_restore_backup=False)
    assert key_path.read_text(encoding="utf-8") == "current-key"


def test_restore_backup_replaces_current_data_and_creates_pre_restore_backup(tmp_path: Path) -> None:
    service, data_root = _build_fixture(tmp_path)
    backup = service.create_backup(reason="baseline")

    mutated_path = data_root / "profile" / "financial_profile.json"
    mutated_path.write_text(json.dumps({"schema_version": 999}, indent=2), encoding="utf-8")
    assert json.loads(mutated_path.read_text(encoding="utf-8"))["schema_version"] == 999

    restore_report = service.restore_backup(
        backup_id=backup["backup_id"],
        create_pre_restore_backup=True,
    )

    restored = json.loads(mutated_path.read_text(encoding="utf-8"))
    assert restored["schema_version"] == 2
    assert restore_report["backup_id"] == backup["backup_id"]
    assert restore_report["files_restored"] == backup["files_backed_up"]
    assert restore_report["pre_restore_backup_id"] is not None

    listing = service.list_backups()
    assert len(listing["backups"]) == 2
