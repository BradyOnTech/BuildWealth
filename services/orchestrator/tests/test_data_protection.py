from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from buildwealth_orchestrator.services.data_protection import DataProtectionService


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions required")
def test_apply_hardened_permissions_updates_sensitive_targets(tmp_path: Path) -> None:
    policy_path = tmp_path / "data" / "security" / "protection_policy.json"
    backup_dir = tmp_path / "data" / "backups"
    sensitive_file = tmp_path / "data" / "profile" / "financial_profile.json"
    sensitive_dir = tmp_path / "data" / "conversations"
    sensitive_nested_file = sensitive_dir / "conv-1.json"

    _write_text(sensitive_file, "{}")
    _write_text(sensitive_nested_file, '{"messages":[]}')
    sensitive_file.chmod(0o666)
    sensitive_dir.chmod(0o777)
    sensitive_nested_file.chmod(0o666)

    service = DataProtectionService(
        policy_path=policy_path,
        sensitive_paths=[sensitive_file, sensitive_dir],
        backup_dir=backup_dir,
    )
    report = service.apply_protection({"protection_level": "hardened", "include_backups": False})

    assert report["supported"] is True
    assert report["files_updated"] >= 2
    assert report["directories_updated"] >= 1
    assert report["non_compliant_files_after"] == 0
    assert report["non_compliant_directories_after"] == 0
    assert stat.S_IMODE(sensitive_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(sensitive_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(sensitive_nested_file.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions required")
def test_include_backups_option_controls_backup_hardening(tmp_path: Path) -> None:
    policy_path = tmp_path / "data" / "security" / "protection_policy.json"
    backup_dir = tmp_path / "data" / "backups"
    sensitive_file = tmp_path / "data" / "profile" / "financial_profile.json"
    backup_file = backup_dir / "buildwealth-backup-20260415T000000000000Z.tar.gz"

    _write_text(sensitive_file, "{}")
    _write_text(backup_file, "archive")
    sensitive_file.chmod(0o666)
    backup_dir.chmod(0o777)
    backup_file.chmod(0o666)

    service = DataProtectionService(
        policy_path=policy_path,
        sensitive_paths=[sensitive_file],
        backup_dir=backup_dir,
    )

    # First apply without backup inclusion: backup file should remain permissive.
    service.apply_protection({"protection_level": "hardened", "include_backups": False})
    assert stat.S_IMODE(backup_file.stat().st_mode) == 0o666

    # Then apply with backup inclusion: backup files/directories should harden too.
    report = service.apply_protection({"protection_level": "hardened", "include_backups": True})
    assert report["include_backups"] is True
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup_file.stat().st_mode) == 0o600
