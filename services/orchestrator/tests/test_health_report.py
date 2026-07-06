from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services import health_report
from buildwealth_orchestrator.services.control_database import SQLiteControlDatabase
from buildwealth_orchestrator.services.health_report import (
    build_health_report,
    check_database,
    check_disk,
    check_storage_writable,
)


def _migrated_db(tmp_path: Path) -> SQLiteControlDatabase:
    database = SQLiteControlDatabase(tmp_path / "control" / "control.db")
    database.migrate()
    return database


def test_healthy_report(monkeypatch, tmp_path: Path) -> None:
    # Pin disk usage — the report must not depend on the CI machine's disk.
    class Usage:
        total = 100
        free = 50

    monkeypatch.setattr(health_report.shutil, "disk_usage", lambda _: Usage)
    database = _migrated_db(tmp_path)
    report = build_health_report(connect=database.connect, data_dir=tmp_path)
    assert report["status"] == "ok"
    assert report["checks"]["database"] == "ok"
    assert report["checks"]["storage"] == "ok"
    assert report["checks"]["disk"] == "ok (50% free)"


def test_database_failure_degrades(tmp_path: Path) -> None:
    def broken_connect():
        raise sqlite3.OperationalError("unable to open database file")

    report = build_health_report(connect=broken_connect, data_dir=tmp_path)
    assert report["status"] == "degraded"
    assert report["checks"]["database"] == "database check failed"
    # Reason strings stay generic — no paths, no exception text.
    assert "control.db" not in str(report)


def test_unmigrated_database_is_not_healthy(tmp_path: Path) -> None:
    # A database file that exists but never migrated (schema_migrations
    # missing) must not report healthy.
    bare = sqlite3.connect(tmp_path / "bare.db")
    bare.close()

    def connect():
        return sqlite3.connect(tmp_path / "bare.db")

    ok, detail = check_database(connect)
    assert ok is False


def test_unwritable_storage_degrades(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    ok, detail = check_storage_writable(missing)
    assert ok is False
    assert detail == "data directory is not writable"


def test_disk_thresholds(monkeypatch, tmp_path: Path) -> None:
    class Usage:
        total = 100
        free = 2

    monkeypatch.setattr(health_report.shutil, "disk_usage", lambda _: Usage)
    ok, detail = check_disk(tmp_path)
    assert ok is False and "critically full" in detail

    Usage.free = 7
    ok, detail = check_disk(tmp_path)
    assert ok is True and "low disk" in detail


def test_health_endpoint_returns_503_when_degraded(monkeypatch, tmp_path: Path) -> None:
    with TestClient(main.app) as client:
        healthy = client.get("/health")
        assert healthy.status_code == 200
        assert healthy.json()["status"] == "ok"

        def broken(**_kwargs):
            raise sqlite3.OperationalError("boom")

        monkeypatch.setattr(
            main.control_plane_store.database, "connect", broken
        )
        degraded = client.get("/health")
        assert degraded.status_code == 503
        assert degraded.json()["status"] == "degraded"
