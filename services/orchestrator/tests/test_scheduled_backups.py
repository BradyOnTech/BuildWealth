from __future__ import annotations

import tarfile
import time
from pathlib import Path

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.backup_restore import BackupRestoreService


def _service(tmp_path: Path) -> BackupRestoreService:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "portfolio").mkdir()
    (data_root / "portfolio" / "holdings.json").write_text('{"schema_version": 1}')
    return BackupRestoreService(data_root=data_root, backup_dir=tmp_path / "backups")


def test_latest_backup_age_none_when_empty(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert service.latest_backup_age_seconds() is None
    service.create_backup(reason="test")
    age = service.latest_backup_age_seconds()
    assert age is not None and age < 60


def test_prune_backups_keeps_newest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    ids = []
    for _ in range(3):
        ids.append(service.create_backup(reason="test")["backup_id"])
        time.sleep(0.02)  # distinct mtimes/slugs

    pruned = service.prune_backups(keep=2)
    remaining = [b["backup_id"] for b in service.list_backups()["backups"]]
    assert len(remaining) == 2
    assert ids[-1] in remaining and ids[-2] in remaining
    assert pruned == [ids[0]]


def test_run_scheduled_backup_if_due(monkeypatch, tmp_path: Path) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(main, "backup_restore_service", service)
    monkeypatch.setattr(main.settings, "backup_interval_hours", 24.0, raising=False)
    monkeypatch.setattr(main.settings, "backup_retention_count", 14, raising=False)

    # No backups yet -> one is created.
    result = main.run_scheduled_backup_if_due()
    assert result is not None
    assert service.list_backups()["backups"]

    # Fresh backup -> nothing to do.
    assert main.run_scheduled_backup_if_due() is None

    # Disabled -> no-op even when stale.
    monkeypatch.setattr(main.settings, "backup_interval_hours", 0.0, raising=False)
    assert main.run_scheduled_backup_if_due() is None


def test_scheduled_backup_archive_is_valid(monkeypatch, tmp_path: Path) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(main, "backup_restore_service", service)
    monkeypatch.setattr(main.settings, "backup_interval_hours", 1.0, raising=False)
    monkeypatch.setattr(main.settings, "backup_retention_count", 5, raising=False)

    result = main.run_scheduled_backup_if_due()
    archive = Path(result["archive_path"])
    assert archive.exists()
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert any("holdings.json" in name for name in names)
