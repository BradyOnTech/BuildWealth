"""Backup and restore utilities for BuildWealth local data."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKUP_ARCHIVE_PREFIX = "buildwealth-backup-"
BACKUP_ARCHIVE_SUFFIX = ".tar.gz"
BACKUP_STRATEGY = "tar_snapshot_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _aggregate_checksum(entries: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for relative_path, content_hash in sorted(entries):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b":")
        digest.update(content_hash.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class BackupRestoreError(RuntimeError):
    pass


class BackupNotFoundError(BackupRestoreError):
    pass


class BackupRestoreService:
    """Creates timestamped backup archives and restores them into data root."""

    def __init__(self, *, data_root: Path, backup_dir: Path):
        self.data_root = data_root.resolve()
        self.backup_dir = backup_dir.resolve()

    @classmethod
    def from_settings(cls, settings: Any) -> "BackupRestoreService":
        return cls(
            data_root=settings.snapshot_dir.parent,
            backup_dir=settings.backup_archive_dir,
        )

    def list_backups(self) -> dict[str, Any]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backups: list[dict[str, Any]] = []
        for archive_path in sorted(self.backup_dir.glob(f"{BACKUP_ARCHIVE_PREFIX}*{BACKUP_ARCHIVE_SUFFIX}"), reverse=True):
            backup_id = self._backup_id_from_path(archive_path)
            stat = archive_path.stat()
            backups.append(
                {
                    "backup_id": backup_id,
                    "archive_path": str(archive_path),
                    "size_bytes": int(stat.st_size),
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return {
            "strategy": BACKUP_STRATEGY,
            "data_root": str(self.data_root),
            "backup_dir": str(self.backup_dir),
            "backups": backups,
        }

    def create_backup(self, *, reason: str | None = None) -> dict[str, Any]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_id = _utc_now_slug()
        archive_path = self.backup_dir / f"{BACKUP_ARCHIVE_PREFIX}{backup_id}{BACKUP_ARCHIVE_SUFFIX}"
        files = self._collect_files()
        file_entries: list[tuple[str, str]] = []
        total_bytes = 0

        with tarfile.open(archive_path, mode="w:gz") as tar:
            for source_path, relative_path in files:
                payload = source_path.read_bytes()
                total_bytes += len(payload)
                content_sha256 = _sha256_bytes(payload)
                file_entries.append((relative_path, content_sha256))
                tar_info = tarfile.TarInfo(name=relative_path)
                tar_info.size = len(payload)
                tar_info.mtime = source_path.stat().st_mtime
                tar_info.mode = source_path.stat().st_mode
                tar.addfile(tar_info, io.BytesIO(payload))

            manifest = {
                "backup_id": backup_id,
                "strategy": BACKUP_STRATEGY,
                "created_at": utc_now_iso(),
                "reason": reason,
                "data_root": str(self.data_root),
                "file_count": len(file_entries),
                "total_bytes": total_bytes,
                "files": [
                    {"path": relative_path, "content_sha256": content_hash}
                    for relative_path, content_hash in sorted(file_entries)
                ],
                "aggregate_checksum": _aggregate_checksum(file_entries),
            }
            manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            manifest_info.mtime = datetime.now(timezone.utc).timestamp()
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

        archive_size = archive_path.stat().st_size
        return {
            "backup_id": backup_id,
            "strategy": BACKUP_STRATEGY,
            "archive_path": str(archive_path),
            "created_at": utc_now_iso(),
            "files_backed_up": len(file_entries),
            "total_bytes": total_bytes,
            "archive_size_bytes": int(archive_size),
            "aggregate_checksum": _aggregate_checksum(file_entries),
            "reason": reason,
        }

    def restore_backup(self, *, backup_id: str, create_pre_restore_backup: bool = True) -> dict[str, Any]:
        archive_path = self._archive_path_for_id(backup_id)
        if not archive_path.exists():
            raise BackupNotFoundError(f"Backup archive not found: {backup_id}")

        pre_restore_backup_id: str | None = None
        if create_pre_restore_backup:
            pre_restore_report = self.create_backup(reason=f"pre_restore:{backup_id}")
            pre_restore_backup_id = str(pre_restore_report["backup_id"])

        with tempfile.TemporaryDirectory(prefix="buildwealth-restore-") as tmp_dir_raw:
            tmp_dir = Path(tmp_dir_raw)
            extracted_dir = tmp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)

            with tarfile.open(archive_path, mode="r:gz") as tar:
                members = tar.getmembers()
                for member in members:
                    self._validate_tar_member(member)
                tar.extractall(path=extracted_dir)

            manifest_path = extracted_dir / "manifest.json"
            if not manifest_path.exists():
                raise BackupRestoreError("Backup archive is missing manifest.json")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise BackupRestoreError("Backup manifest is not valid JSON") from exc

            files_manifest = manifest.get("files")
            if not isinstance(files_manifest, list):
                raise BackupRestoreError("Backup manifest has invalid files list")

            restored_entries: list[tuple[str, str]] = []
            restored_bytes = 0
            for entry in files_manifest:
                if not isinstance(entry, dict):
                    raise BackupRestoreError("Backup manifest file entry is invalid")
                relative_path = str(entry.get("path") or "")
                expected_hash = str(entry.get("content_sha256") or "")
                if not relative_path or not expected_hash:
                    raise BackupRestoreError("Backup manifest file entry is missing path/checksum")
                extracted_file = extracted_dir / relative_path
                if not extracted_file.exists() or not extracted_file.is_file():
                    raise BackupRestoreError(f"Backup manifest file is missing from archive: {relative_path}")
                payload = extracted_file.read_bytes()
                actual_hash = _sha256_bytes(payload)
                if actual_hash != expected_hash:
                    raise BackupRestoreError(f"Backup manifest checksum mismatch for {relative_path}")
                restored_entries.append((relative_path, actual_hash))
                restored_bytes += len(payload)

            expected_aggregate = str(manifest.get("aggregate_checksum") or "")
            actual_aggregate = _aggregate_checksum(restored_entries)
            if expected_aggregate and actual_aggregate != expected_aggregate:
                raise BackupRestoreError("Backup aggregate checksum mismatch")

            self._clear_data_root_except_backups()
            files_restored = 0
            for relative_path, _ in restored_entries:
                source = extracted_dir / relative_path
                destination = self.data_root / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                files_restored += 1

        return {
            "backup_id": backup_id,
            "strategy": BACKUP_STRATEGY,
            "restored_at": utc_now_iso(),
            "archive_path": str(archive_path),
            "files_restored": files_restored,
            "bytes_restored": restored_bytes,
            "pre_restore_backup_id": pre_restore_backup_id,
        }

    def _collect_files(self) -> list[tuple[Path, str]]:
        if not self.data_root.exists():
            self.data_root.mkdir(parents=True, exist_ok=True)
        files: list[tuple[Path, str]] = []
        for path in sorted(self.data_root.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved.is_relative_to(self.backup_dir):
                continue
            relative = resolved.relative_to(self.data_root).as_posix()
            files.append((resolved, relative))
        return files

    def _clear_data_root_except_backups(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        for child in self.data_root.iterdir():
            resolved = child.resolve()
            if resolved == self.backup_dir:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    def _archive_path_for_id(self, backup_id: str) -> Path:
        cleaned = str(backup_id or "").strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
            raise BackupRestoreError("Invalid backup_id")
        return self.backup_dir / f"{BACKUP_ARCHIVE_PREFIX}{cleaned}{BACKUP_ARCHIVE_SUFFIX}"

    @staticmethod
    def _backup_id_from_path(path: Path) -> str:
        name = path.name
        prefix_len = len(BACKUP_ARCHIVE_PREFIX)
        suffix_len = len(BACKUP_ARCHIVE_SUFFIX)
        if not name.startswith(BACKUP_ARCHIVE_PREFIX) or not name.endswith(BACKUP_ARCHIVE_SUFFIX):
            return name
        return name[prefix_len : len(name) - suffix_len]

    @staticmethod
    def _validate_tar_member(member: tarfile.TarInfo) -> None:
        if member.isdir():
            return
        if member.name.startswith("/") or member.name.startswith("\\"):
            raise BackupRestoreError("Backup archive contains an absolute path")
        parts = Path(member.name).parts
        if any(part == ".." for part in parts):
            raise BackupRestoreError("Backup archive contains unsafe traversal path")
