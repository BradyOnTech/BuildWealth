from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from buildwealth_orchestrator.services import control_db_migrations as mig
from buildwealth_orchestrator.services.control_database import SQLiteControlDatabase
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def test_fresh_database_applies_baseline_once(tmp_path: Path) -> None:
    db = tmp_path / "control.db"
    with _connect(db) as connection:
        applied = mig.apply_migrations(connection)
        assert applied == ["0001"]
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"users", "workspaces", "sessions", "schema_migrations"} <= tables
        # Post-baseline columns exist on a fresh database too.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        assert "deletion_requested_at" in columns

        # Re-running is a recorded no-op.
        assert mig.apply_migrations(connection) == []
        assert mig.applied_migrations(connection) == ["0001"]


def test_pre_runner_database_adopts_baseline_without_touching_data(tmp_path: Path) -> None:
    db = tmp_path / "control.db"
    # Simulate a database created by an older build: schema exists (including
    # patched columns), data exists, but no schema_migrations table.
    with _connect(db) as connection:
        connection.executescript(mig._BASELINE_SCHEMA)
        connection.execute(
            "INSERT INTO users (id, email, email_normalized, created_at, updated_at)"
            " VALUES ('usr_1', 'a@b.c', 'a@b.c', 'now', 'now')"
        )
        connection.commit()

    with _connect(db) as connection:
        applied = mig.apply_migrations(connection)
        assert applied == ["0001"]
        row = connection.execute("SELECT email FROM users WHERE id = 'usr_1'").fetchone()
        assert row["email"] == "a@b.c"


def test_failing_migration_rolls_back_and_is_not_recorded(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "control.db"

    def _bad(connection) -> None:
        connection.execute("CREATE TABLE half_done (id TEXT PRIMARY KEY)")
        raise RuntimeError("boom")

    monkeypatch.setattr(
        mig,
        "MIGRATIONS",
        [*mig.MIGRATIONS, ("0002", "explodes", _bad)],
    )
    with _connect(db) as connection:
        with pytest.raises(RuntimeError):
            mig.apply_migrations(connection)
        # 0001 committed before the failure; 0002 rolled back and unrecorded.
        assert mig.applied_migrations(connection) == ["0001"]
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "half_done" not in tables

    # Fixing the migration lets the runner resume from where it stopped.
    def _good(connection) -> None:
        connection.execute("CREATE TABLE now_done (id TEXT PRIMARY KEY)")

    monkeypatch.setattr(
        mig,
        "MIGRATIONS",
        [*mig.MIGRATIONS[:-1], ("0002", "fixed", _good)],
    )
    with _connect(db) as connection:
        assert mig.apply_migrations(connection) == ["0002"]
        assert mig.applied_migrations(connection) == ["0001", "0002"]


def test_control_plane_store_boots_through_the_seam(tmp_path: Path) -> None:
    db = tmp_path / "control.db"
    store = ControlPlaneStore(db)
    store.bootstrap_default_household(
        owner_email="owner@example.test",
        default_storage_root=tmp_path / "real",
        demo_storage_root=tmp_path / "demo",
    )
    workspaces = store.list_active_workspaces()
    assert workspaces

    # A second boot over the same file (as every app restart does) is clean,
    # and the migration ledger shows exactly one baseline application.
    again = ControlPlaneStore(db)
    assert [w.id for w in again.list_active_workspaces()] == [w.id for w in workspaces]
    with SQLiteControlDatabase(db).connect() as connection:
        assert mig.applied_migrations(connection) == ["0001"]
