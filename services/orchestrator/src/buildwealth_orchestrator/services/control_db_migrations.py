"""Ordered, recorded migrations for the control-plane database.

The control plane is the only shared multi-tenant state in BuildWealth;
everything else lives in per-workspace files. Before a second database
backend can exist, the schema needs a history both backends can implement —
that history lives here.

Rules:
- Migrations are append-only. Never edit an applied migration; add a new one.
- Each migration runs in a single transaction and is recorded in
  schema_migrations. Re-running the runner is always a no-op.
- Migration 0001 is the baseline: the schema as it existed before the runner.
  It is deliberately idempotent (IF NOT EXISTS + column checks) so databases
  created by older builds adopt the baseline without any special casing.
- SQL here targets SQLite today. When a second backend arrives, each
  migration gains a dialect-reviewed variant only where the SQL actually
  diverges (see control_database.py for the seam contract).

Deliberately not Alembic: eight tables of readable SQL don't justify an ORM
dependency. If the schema ever grows past what a list of scripts can carry,
revisit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

Connection = Any  # DB-API connection with executescript/execute (sqlite3 today)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(connection: Connection, table_name: str, column_name: str, column_sql: str) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in columns:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


_BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    email_normalized TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    auth_provider TEXT NOT NULL DEFAULT 'local',
    auth_provider_subject TEXT,
    mfa_enabled INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    org_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    invited_by_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, organization_id)
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    workspace_type TEXT NOT NULL,
    storage_mode TEXT NOT NULL DEFAULT 'file',
    storage_path TEXT NOT NULL,
    database_path TEXT,
    encryption_status TEXT NOT NULL DEFAULT 'not_configured',
    backup_policy_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token_hash TEXT NOT NULL UNIQUE,
    csrf_token_hash TEXT NOT NULL,
    active_workspace_id TEXT REFERENCES workspaces(id),
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    ip_hash TEXT,
    user_agent_hash TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT,
    organization_id TEXT,
    workspace_id TEXT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    outcome TEXT NOT NULL DEFAULT 'ok',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_login_flows (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    state_token_hash TEXT NOT NULL UNIQUE,
    code_verifier TEXT NOT NULL,
    nonce TEXT NOT NULL,
    redirect_to TEXT NOT NULL DEFAULT '/v2',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS account_data_deletion_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    requested_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    scope TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    purge_after TEXT NOT NULL,
    canceled_at TEXT,
    completed_at TEXT,
    preview_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_auth_provider_subject
ON users(auth_provider, auth_provider_subject)
WHERE auth_provider_subject IS NOT NULL AND auth_provider_subject != '';

CREATE INDEX IF NOT EXISTS idx_account_data_deletion_pending
ON account_data_deletion_requests(status, purge_after);

CREATE INDEX IF NOT EXISTS idx_account_data_deletion_org
ON account_data_deletion_requests(organization_id, status);
"""


def _split_statements(script: str) -> list[str]:
    # Migrations never use executescript: it force-commits any open
    # transaction, which would break the per-migration rollback guarantee.
    # This split is safe because migration SQL never embeds semicolons in
    # string literals or trigger bodies — keep it that way.
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def _migration_0001_baseline(connection: Connection) -> None:
    for statement in _split_statements(_BASELINE_SCHEMA):
        connection.execute(statement)
    # Columns added after the original CREATE TABLEs shipped; idempotent so
    # both fresh databases and every generation of existing ones converge.
    for table in ("users", "organizations", "workspaces"):
        _ensure_column(connection, table, "deletion_requested_at", "TEXT")
        _ensure_column(connection, table, "purge_after", "TEXT")
        _ensure_column(connection, table, "deletion_completed_at", "TEXT")


# Append-only. (id, description, apply callable). Ids are zero-padded and
# strictly increasing; the runner refuses gaps or reordering by design of the
# applied-check below.
MIGRATIONS: list[tuple[str, str, Callable[[Connection], None]]] = [
    ("0001", "baseline control-plane schema", _migration_0001_baseline),
]


def applied_migrations(connection: Connection) -> list[str]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    return [str(row["id"]) for row in connection.execute("SELECT id FROM schema_migrations ORDER BY id").fetchall()]


def apply_migrations(connection: Connection) -> list[str]:
    """Apply pending migrations in order; returns ids applied this run.

    Each migration runs in one EXPLICIT transaction. Python's sqlite3 module
    autocommits DDL under its legacy transaction handling, which would make
    "rollback on failure" a silent lie — so the runner takes over transaction
    control (isolation_level None + BEGIN/COMMIT/ROLLBACK) for its duration.
    A failure leaves prior migrations recorded and the failing one fully
    rolled back, including its DDL.
    """
    previous_isolation = getattr(connection, "isolation_level", None)
    has_isolation = hasattr(connection, "isolation_level")
    if has_isolation:
        connection.isolation_level = None  # autocommit; we manage transactions
    try:
        done = set(applied_migrations(connection))
        applied_now: list[str] = []
        for migration_id, description, apply in MIGRATIONS:
            if migration_id in done:
                continue
            connection.execute("BEGIN")
            try:
                apply(connection)
                connection.execute(
                    "INSERT INTO schema_migrations (id, description, applied_at) VALUES (?, ?, ?)",
                    (migration_id, description, _utc_now_iso()),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            applied_now.append(migration_id)
        return applied_now
    finally:
        if has_isolation:
            connection.isolation_level = previous_isolation
