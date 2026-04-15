"""Durable storage migration and rollback checks for BuildWealth local stores."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEXT_STORAGE_SUFFIXES = (".json", ".jsonl", ".md", ".yaml", ".yml", ".txt")
MIGRATION_STRATEGY = "sqlite_snapshot_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _aggregate_checksum(entries: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for relative_path, content_hash in sorted(entries):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b":")
        digest.update(content_hash.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True)
class StorageDocument:
    relative_path: str
    absolute_path: Path
    content: str
    content_sha256: str
    size_bytes: int


class DurableStorageMigrationError(RuntimeError):
    pass


class DurableStorageMigrationNotFoundError(DurableStorageMigrationError):
    pass


class DurableStorageMigrationService:
    """Create a SQLite durable snapshot from file-backed stores with rollback checks."""

    def __init__(self, *, data_root: Path, storage_dir: Path, include_paths: list[Path]):
        self.data_root = data_root.resolve()
        self.storage_dir = storage_dir.resolve()
        self.include_paths = tuple(path.resolve() for path in include_paths)
        self.migrations_dir = self.storage_dir / "migrations"
        self.database_path = self.storage_dir / "buildwealth_durable.db"
        self.latest_report_path = self.storage_dir / "latest_migration.json"

    @classmethod
    def from_settings(cls, settings: Any) -> "DurableStorageMigrationService":
        data_root = settings.snapshot_dir.parent
        include_paths = [
            data_root / "portfolio",
            settings.snapshot_dir,
            settings.conversation_dir,
            settings.plans_dir,
            settings.financial_profile_path,
            settings.recommendations_path,
        ]
        return cls(
            data_root=data_root,
            storage_dir=settings.durable_storage_dir,
            include_paths=include_paths,
        )

    def get_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "strategy": MIGRATION_STRATEGY,
            "data_root": str(self.data_root),
            "storage_dir": str(self.storage_dir),
            "database_path": str(self.database_path),
            "database_exists": self.database_path.exists(),
            "document_count": 0,
            "latest_migration_id": None,
            "latest_migration_at": None,
            "latest_source_checksum": None,
            "latest_database_checksum": None,
            "latest_rollback_check_passed": None,
        }
        if self.database_path.exists():
            with sqlite3.connect(self.database_path) as connection:
                status["document_count"] = int(
                    connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                )
                row = connection.execute(
                    """
                    SELECT migration_id, created_at, source_checksum, database_checksum, rollback_check_passed
                    FROM migration_runs
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    status["latest_migration_id"] = str(row[0])
                    status["latest_migration_at"] = str(row[1])
                    status["latest_source_checksum"] = str(row[2])
                    status["latest_database_checksum"] = str(row[3])
                    status["latest_rollback_check_passed"] = bool(int(row[4]))
        return status

    def run_upgrade(self, *, run_rollback_check: bool = True) -> dict[str, Any]:
        documents = self._collect_documents()
        document_entries = [(doc.relative_path, doc.content_sha256) for doc in documents]
        source_checksum = _aggregate_checksum(document_entries)
        total_bytes = sum(doc.size_bytes for doc in documents)

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

        migration_id = datetime.now(timezone.utc).strftime("migration-%Y%m%dT%H%M%S%fZ")
        migration_dir = self.migrations_dir / migration_id
        backup_dir = migration_dir / "backup"
        report_path = migration_dir / "report.json"
        migration_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)

        for document in documents:
            backup_path = backup_dir / document.relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(document.absolute_path, backup_path)

        rollback_check_passed = False
        if run_rollback_check:
            rollback_check_passed = self._run_rollback_check(
                backup_dir=backup_dir,
                migration_dir=migration_dir,
                documents=documents,
            )

        previous_database_backup_path: Path | None = None
        if self.database_path.exists():
            previous_database_backup_path = migration_dir / "previous_buildwealth_durable.db"
            shutil.copy2(self.database_path, previous_database_backup_path)

        tmp_database_path = self.storage_dir / f".tmp-{migration_id}.db"
        if tmp_database_path.exists():
            tmp_database_path.unlink()

        database_checksum = self._write_database_snapshot(
            database_path=tmp_database_path,
            migration_id=migration_id,
            created_at=utc_now_iso(),
            documents=documents,
            source_checksum=source_checksum,
            total_bytes=total_bytes,
            rollback_check_passed=rollback_check_passed,
        )
        try:
            tmp_database_path.replace(self.database_path)
        finally:
            if tmp_database_path.exists():
                tmp_database_path.unlink()

        report: dict[str, Any] = {
            "migration_id": migration_id,
            "strategy": MIGRATION_STRATEGY,
            "created_at": utc_now_iso(),
            "data_root": str(self.data_root),
            "storage_dir": str(self.storage_dir),
            "database_path": str(self.database_path),
            "backup_dir": str(backup_dir),
            "previous_database_backup_path": (
                str(previous_database_backup_path) if previous_database_backup_path is not None else None
            ),
            "documents_migrated": len(documents),
            "total_bytes": total_bytes,
            "source_checksum": source_checksum,
            "database_checksum": database_checksum,
            "rollback_check_performed": run_rollback_check,
            "rollback_check_passed": rollback_check_passed,
            "report_path": str(report_path),
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        self.latest_report_path.write_text(
            json.dumps(
                {
                    "migration_id": migration_id,
                    "report_path": str(report_path),
                    "updated_at": utc_now_iso(),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return report

    def rollback_latest_migration(self, migration_id: str | None = None) -> dict[str, Any]:
        report = self._load_report(migration_id=migration_id)
        backup_dir = Path(str(report["backup_dir"]))
        if not backup_dir.exists():
            raise DurableStorageMigrationNotFoundError(f"Backup directory does not exist: {backup_dir}")

        restored_files = 0
        restored_bytes = 0
        for backup_path in sorted(path for path in backup_dir.rglob("*") if path.is_file()):
            relative = backup_path.relative_to(backup_dir)
            target = self.data_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target)
            restored_files += 1
            restored_bytes += backup_path.stat().st_size

        restored_entries: list[tuple[str, str]] = []
        for backup_path in sorted(path for path in backup_dir.rglob("*") if path.is_file()):
            relative = backup_path.relative_to(backup_dir).as_posix()
            target = self.data_root / Path(relative)
            text = target.read_text(encoding="utf-8")
            restored_entries.append((relative, _sha256_text(text)))
        restored_checksum = _aggregate_checksum(restored_entries)
        expected_checksum = str(report.get("source_checksum") or "")
        if expected_checksum and restored_checksum != expected_checksum:
            raise DurableStorageMigrationError(
                "Rollback checksum mismatch: restored files do not match the migration backup."
            )

        database_restored = False
        database_removed = False
        previous_database_backup_path = report.get("previous_database_backup_path")
        if previous_database_backup_path:
            previous_path = Path(str(previous_database_backup_path))
            if previous_path.exists():
                previous_path.parent.mkdir(parents=True, exist_ok=True)
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(previous_path, self.database_path)
                database_restored = True
        elif self.database_path.exists():
            self.database_path.unlink()
            database_removed = True

        return {
            "migration_id": str(report["migration_id"]),
            "restored_at": utc_now_iso(),
            "backup_dir": str(backup_dir),
            "files_restored": restored_files,
            "bytes_restored": restored_bytes,
            "database_restored": database_restored,
            "database_removed": database_removed,
        }

    def _load_report(self, *, migration_id: str | None) -> dict[str, Any]:
        if migration_id:
            report_path = self.migrations_dir / migration_id / "report.json"
        else:
            try:
                latest_payload = json.loads(self.latest_report_path.read_text(encoding="utf-8"))
                report_path = Path(str(latest_payload.get("report_path") or ""))
            except (FileNotFoundError, json.JSONDecodeError):
                report_path = Path()

        if not report_path or not report_path.exists():
            raise DurableStorageMigrationNotFoundError("No durable storage migration report was found.")

        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DurableStorageMigrationError(f"Invalid migration report: {report_path}") from exc
        return payload

    def _collect_documents(self) -> list[StorageDocument]:
        discovered: list[Path] = []
        seen: set[Path] = set()
        for include_path in self.include_paths:
            if include_path.is_file():
                candidates = [include_path]
            elif include_path.is_dir():
                candidates = [
                    path
                    for path in sorted(include_path.rglob("*"))
                    if path.is_file() and path.suffix.lower() in TEXT_STORAGE_SUFFIXES
                ]
            else:
                continue

            for candidate in candidates:
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                discovered.append(resolved)

        documents: list[StorageDocument] = []
        for absolute_path in sorted(discovered, key=self._relative_path):
            relative_path = self._relative_path(absolute_path)
            content = absolute_path.read_text(encoding="utf-8")
            documents.append(
                StorageDocument(
                    relative_path=relative_path,
                    absolute_path=absolute_path,
                    content=content,
                    content_sha256=_sha256_text(content),
                    size_bytes=len(content.encode("utf-8")),
                )
            )
        return documents

    def _relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.data_root)
        except ValueError as exc:
            raise DurableStorageMigrationError(
                f"Path is outside data root and cannot be migrated: {resolved}"
            ) from exc
        return relative.as_posix()

    def _run_rollback_check(
        self,
        *,
        backup_dir: Path,
        migration_dir: Path,
        documents: list[StorageDocument],
    ) -> bool:
        restore_dir = migration_dir / "rollback_check_restore"
        restore_dir.mkdir(parents=True, exist_ok=True)
        try:
            for document in documents:
                source = backup_dir / document.relative_path
                target = restore_dir / document.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                restored_content = target.read_text(encoding="utf-8")
                restored_hash = _sha256_text(restored_content)
                if restored_hash != document.content_sha256:
                    raise DurableStorageMigrationError(
                        f"Rollback check failed for {document.relative_path}: checksum mismatch."
                    )
            return True
        finally:
            shutil.rmtree(restore_dir, ignore_errors=True)

    def _write_database_snapshot(
        self,
        *,
        database_path: Path,
        migration_id: str,
        created_at: str,
        documents: list[StorageDocument],
        source_checksum: str,
        total_bytes: int,
        rollback_check_passed: bool,
    ) -> str:
        with sqlite3.connect(database_path) as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    path TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    migrated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_runs (
                    migration_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    source_checksum TEXT NOT NULL,
                    database_checksum TEXT NOT NULL,
                    document_count INTEGER NOT NULL,
                    total_bytes INTEGER NOT NULL,
                    rollback_check_passed INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_documents (
                    migration_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    PRIMARY KEY (migration_id, path),
                    FOREIGN KEY (migration_id) REFERENCES migration_runs(migration_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute("DELETE FROM documents")
            connection.executemany(
                """
                INSERT INTO documents (path, content, content_sha256, size_bytes, migrated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        document.relative_path,
                        document.content,
                        document.content_sha256,
                        document.size_bytes,
                        created_at,
                    )
                    for document in documents
                ],
            )
            database_entries = [
                (str(row[0]), str(row[1]))
                for row in connection.execute(
                    "SELECT path, content_sha256 FROM documents ORDER BY path ASC"
                ).fetchall()
            ]
            source_entries = sorted(
                (document.relative_path, document.content_sha256) for document in documents
            )
            if database_entries != source_entries:
                raise DurableStorageMigrationError(
                    "Database verification failed: migrated document checksums do not match source files."
                )
            database_checksum = _aggregate_checksum(database_entries)

            connection.execute(
                """
                INSERT INTO migration_runs (
                    migration_id,
                    created_at,
                    source_checksum,
                    database_checksum,
                    document_count,
                    total_bytes,
                    rollback_check_passed
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    migration_id,
                    created_at,
                    source_checksum,
                    database_checksum,
                    len(documents),
                    total_bytes,
                    1 if rollback_check_passed else 0,
                ),
            )
            connection.executemany(
                """
                INSERT INTO migration_documents (migration_id, path, content_sha256, size_bytes)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        migration_id,
                        document.relative_path,
                        document.content_sha256,
                        document.size_bytes,
                    )
                    for document in documents
                ],
            )
            connection.commit()
            return database_checksum
