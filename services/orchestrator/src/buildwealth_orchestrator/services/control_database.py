"""Connection seam for the control-plane database.

This is the boundary between ControlPlaneStore's business logic (which owns
the SQL) and the engine underneath (which owns connections, transactions,
and dialect quirks). SQLite is the default forever — it IS the local-first
product. Postgres becomes a hosted deployment choice by implementing this
same small surface, not by rewriting the store.

The seam is deliberately a connection adapter, not a repository layer:
the store's SQL is simple enough that engines agree on nearly all of it,
and abstracting eight tables into repository interfaces against a single
implementation would be speculation, not architecture.

## Adding a Postgres adapter (the recipe, so it stays a bounded task)

1. Implement ControlDatabase for psycopg: connect() must return connections
   whose rows support mapping access by column name (dict_row), with
   qmark-style parameters translated or the store's queries adapted via
   this adapter's `paramstyle`.
2. Review the dialect-divergent sites, all marked `# dialect:` in
   control_plane.py / control_db_migrations.py:
   - `INSERT OR IGNORE` (2 sites)  → `ON CONFLICT DO NOTHING`
   - `PRAGMA foreign_keys` / `PRAGMA table_info` (this file + migrations)
     → no-op / information_schema
   - the runner's isolation_level/BEGIN handling is a sqlite3-module
     workaround; psycopg transactions are already DDL-safe
3. Give each migration a Postgres variant only where its SQL diverges
   (TEXT/INTEGER columns and partial indexes carry over as-is).
4. Run the existing auth/workspace suite against the new adapter; it
   exercises the store end to end and is the acceptance gate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Protocol

from buildwealth_orchestrator.services.control_db_migrations import apply_migrations


class ControlDatabase(Protocol):
    """What ControlPlaneStore needs from a database engine."""

    #: DB-API parameter style the store's SQL is written in.
    paramstyle: str

    def connect(self) -> Any:
        """A DB-API connection; rows must support access by column name."""
        ...

    def migrate(self) -> list[str]:
        """Apply pending schema migrations; returns ids applied this run."""
        ...


class SQLiteControlDatabase:
    """The local-first default: one file, zero services to run."""

    paramstyle = "qmark"

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        # dialect: SQLite requires opting into FK enforcement per connection.
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def migrate(self) -> list[str]:
        with self.connect() as connection:
            return apply_migrations(connection)
