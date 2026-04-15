from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from buildwealth_orchestrator.services.backup_restore import BackupRestoreService
from buildwealth_orchestrator.services.data_protection import DataProtectionService


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _seed_data_root(data_root: Path) -> None:
    _write_json(
        data_root / "portfolio" / "transactions.json",
        [{"id": "tx-1", "symbol": "AAPL", "action": "BUY", "quantity": 1}],
    )
    _write_json(
        data_root / "profile" / "financial_profile.json",
        {"schema_version": 2, "notes": "baseline"},
    )
    _write_json(
        data_root / "conversations" / "conv-1.json",
        {"conversation_id": "conv-1", "messages": []},
    )
    _write_json(
        data_root / "plans" / "plan-alpha" / "settings.json",
        {"schema_version": 2, "title": "Plan Alpha"},
    )


def test_storage_backup_restore_and_protection_policy_smoke(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    backup_dir = data_root / "backups"
    policy_path = data_root / "security" / "protection_policy.json"
    profile_file = data_root / "profile" / "financial_profile.json"

    _seed_data_root(data_root)

    backup_service = BackupRestoreService(data_root=data_root, backup_dir=backup_dir)
    protection_service = DataProtectionService(
        policy_path=policy_path,
        sensitive_paths=[
            data_root / "portfolio",
            data_root / "profile",
            data_root / "plans",
            data_root / "conversations",
        ],
        backup_dir=backup_dir,
    )

    baseline_backup = backup_service.create_backup(reason="storage_reliability_smoke:baseline")
    assert baseline_backup["files_backed_up"] >= 4
    assert Path(baseline_backup["archive_path"]).exists()

    _write_json(profile_file, {"schema_version": 999, "notes": "mutated"})
    mutated = json.loads(profile_file.read_text(encoding="utf-8"))
    assert mutated["schema_version"] == 999

    policy = protection_service.update_policy(
        {
            "protection_level": "hardened",
            "include_backups": True,
            "auto_apply_on_startup": True,
        }
    )
    assert policy["protection_level"] == "hardened"
    assert policy["include_backups"] is True
    assert policy["auto_apply_on_startup"] is True

    apply_report = protection_service.apply_protection()
    assert apply_report["include_backups"] is True

    if os.name == "posix":
        backup_archive = Path(baseline_backup["archive_path"])
        assert stat.S_IMODE(profile_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(backup_archive.stat().st_mode) == 0o600
        assert apply_report["non_compliant_files_after"] == 0
        assert apply_report["non_compliant_directories_after"] == 0

    restore_report = backup_service.restore_backup(
        backup_id=baseline_backup["backup_id"],
        create_pre_restore_backup=True,
    )
    assert restore_report["backup_id"] == baseline_backup["backup_id"]
    assert restore_report["files_restored"] == baseline_backup["files_backed_up"]
    assert restore_report["pre_restore_backup_id"] is not None

    restored = json.loads(profile_file.read_text(encoding="utf-8"))
    assert restored["schema_version"] == 2
    assert restored["notes"] == "baseline"

    listing = backup_service.list_backups()
    assert len(listing["backups"]) >= 2

    reapplied = protection_service.apply_protection()
    if os.name == "posix":
        assert reapplied["non_compliant_files_after"] == 0
        assert reapplied["non_compliant_directories_after"] == 0
