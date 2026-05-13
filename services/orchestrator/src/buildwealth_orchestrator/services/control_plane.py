from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_HOUSEHOLD_WORKSPACE_ID = "ws_default_household"
DEMO_HOUSEHOLD_WORKSPACE_ID = "ws_demo_household"
DEFAULT_ORGANIZATION_ID = "org_default_household"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"pbkdf2_sha256$210000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    organization_id: str
    workspace_id: str
    role: str
    permissions: frozenset[str]
    is_demo_workspace: bool
    auth_mode: str


@dataclass(frozen=True)
class WorkspaceRecord:
    id: str
    organization_id: str
    name: str
    workspace_type: str
    storage_path: Path
    status: str


class AuthenticationError(ValueError):
    pass


class AuthorizationError(PermissionError):
    pass


class ControlPlaneStore:
    """Small SQLite control plane for users, orgs, memberships, workspaces, and sessions."""

    OWNER_PERMISSIONS = frozenset(
        {
            "workspace.read",
            "workspace.manage",
            "profile.read",
            "profile.write",
            "portfolio.read",
            "portfolio.write",
            "plan.read",
            "plan.write",
            "recommendations.read",
            "recommendations.write",
            "copilot.use",
            "settings.read",
            "settings.write",
            "secrets.write",
            "imports.read",
            "imports.write",
            "backup.read",
            "backup.write",
            "export.create",
            "demo.reset",
        }
    )

    ROLE_PERMISSIONS = {
        "owner": OWNER_PERMISSIONS,
        "member": frozenset(
            permission
            for permission in OWNER_PERMISSIONS
            if permission not in {"workspace.manage", "demo.reset"}
        ),
        "read_only": frozenset(
            permission
            for permission in OWNER_PERMISSIONS
            if permission.endswith(".read") or permission in {"workspace.read"}
        ),
        "advisor": frozenset(
            permission
            for permission in OWNER_PERMISSIONS
            if permission.endswith(".read")
            or permission in {"workspace.read", "copilot.use", "recommendations.write"}
        ),
        "admin": frozenset({"workspace.read", "workspace.manage", "settings.read"}),
    }

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
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
                """
            )

    @staticmethod
    def normalize_email(email: str) -> str:
        return str(email or "").strip().lower()

    def bootstrap_default_household(
        self,
        *,
        owner_email: str,
        default_storage_root: Path,
        demo_storage_root: Path,
    ) -> None:
        now = utc_now_iso()
        email = self.normalize_email(owner_email)
        if not email:
            email = "owner@buildwealth.local"
        with self._connect() as connection:
            user = connection.execute(
                "SELECT id FROM users WHERE email_normalized = ?",
                (email,),
            ).fetchone()
            if user is None:
                owner_user_id = "usr_default_owner"
                connection.execute(
                    """
                    INSERT INTO users (
                        id, email, email_normalized, display_name, password_hash,
                        auth_provider, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'local', 'active', ?, ?)
                    """,
                    (
                        "usr_default_owner",
                        email,
                        email,
                        "BuildWealth Owner",
                        _hash_password(secrets.token_urlsafe(24)),
                        now,
                        now,
                    ),
                )
            else:
                owner_user_id = str(user["id"])
            connection.execute(
                """
                INSERT OR IGNORE INTO organizations (id, name, org_type, status, created_at, updated_at)
                VALUES (?, 'My Household', 'household', 'active', ?, ?)
                """,
                (DEFAULT_ORGANIZATION_ID, now, now),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO memberships (
                    id, user_id, organization_id, role, status, created_at, updated_at
                )
                VALUES (?, ?, ?, 'owner', 'active', ?, ?)
                """,
                ("mem_default_owner", owner_user_id, DEFAULT_ORGANIZATION_ID, now, now),
            )
            self._upsert_workspace(
                connection,
                workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID,
                organization_id=DEFAULT_ORGANIZATION_ID,
                name="My Household",
                workspace_type="household",
                storage_path=default_storage_root,
                now=now,
            )
            self._upsert_workspace(
                connection,
                workspace_id=DEMO_HOUSEHOLD_WORKSPACE_ID,
                organization_id=DEFAULT_ORGANIZATION_ID,
                name="Demo Household",
                workspace_type="demo",
                storage_path=demo_storage_root,
                now=now,
            )

    def _upsert_workspace(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        organization_id: str,
        name: str,
        workspace_type: str,
        storage_path: Path,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO workspaces (
                id, organization_id, name, workspace_type, storage_mode,
                storage_path, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'file', ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                workspace_type = excluded.workspace_type,
                storage_path = excluded.storage_path,
                updated_at = excluded.updated_at
            """,
            (workspace_id, organization_id, name, workspace_type, str(storage_path), now, now),
        )

    def create_owner_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str = "",
    ) -> dict[str, Any]:
        normalized = self.normalize_email(email)
        if not normalized:
            raise ValueError("email is required")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        now = utc_now_iso()
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, email, email_normalized, display_name, password_hash,
                    auth_provider, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'local', 'active', ?, ?)
                """,
                (
                    user_id,
                    normalized,
                    normalized,
                    display_name.strip(),
                    _hash_password(password),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO memberships (
                    id, user_id, organization_id, role, status, created_at, updated_at
                )
                VALUES (?, ?, ?, 'owner', 'active', ?, ?)
                """,
                (f"mem_{uuid.uuid4().hex[:16]}", user_id, DEFAULT_ORGANIZATION_ID, now, now),
            )
        return self.get_user(user_id)

    def authenticate_local(self, *, email: str, password: str) -> dict[str, Any]:
        normalized = self.normalize_email(email)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email_normalized = ? AND status = 'active'",
                (normalized,),
            ).fetchone()
            if row is None or not _verify_password(password, str(row["password_hash"] or "")):
                raise AuthenticationError("Invalid email or password")
            now = utc_now_iso()
            connection.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        return self.get_user(str(row["id"]))

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise AuthenticationError("User not found")
        return dict(row)

    def create_session(
        self,
        *,
        user_id: str,
        active_workspace_id: str | None,
        ttl_days: int,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, str]:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = utc_now()
        expires_at = now + timedelta(days=max(1, ttl_days))
        session_id = f"ses_{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, user_id, session_token_hash, csrf_token_hash, active_workspace_id,
                    created_at, last_seen_at, expires_at, ip_hash, user_agent_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    _token_hash(token),
                    _token_hash(csrf_token),
                    active_workspace_id,
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                    _token_hash(ip or "") if ip else None,
                    _token_hash(user_agent or "") if user_agent else None,
                ),
            )
        return {"session_id": session_id, "session_token": token, "csrf_token": csrf_token}

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE session_token_hash = ?",
                (utc_now_iso(), _token_hash(token)),
            )

    def select_workspace_for_session(self, *, token: str, workspace_id: str) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET active_workspace_id = ?, last_seen_at = ?
                WHERE session_token_hash = ? AND revoked_at IS NULL
                """,
                (workspace_id, utc_now_iso(), _token_hash(token)),
            )

    def default_workspace_for_user(self, user_id: str) -> WorkspaceRecord:
        workspaces = self.list_workspaces_for_user(user_id)
        for workspace in workspaces:
            if workspace.id == DEFAULT_HOUSEHOLD_WORKSPACE_ID:
                return workspace
        if not workspaces:
            raise AuthorizationError("No workspace is available for this user")
        return workspaces[0]

    def list_workspaces_for_user(self, user_id: str) -> list[WorkspaceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT w.*
                FROM workspaces w
                JOIN memberships m ON m.organization_id = w.organization_id
                WHERE m.user_id = ?
                  AND m.status = 'active'
                  AND w.status = 'active'
                ORDER BY CASE w.workspace_type WHEN 'household' THEN 0 WHEN 'demo' THEN 1 ELSE 2 END, w.name
                """,
                (user_id,),
            ).fetchall()
        return [self._workspace_from_row(row) for row in rows]

    def get_workspace_for_user(self, *, user_id: str, workspace_id: str) -> tuple[WorkspaceRecord, str]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT w.*, m.role AS membership_role
                FROM workspaces w
                JOIN memberships m ON m.organization_id = w.organization_id
                WHERE m.user_id = ?
                  AND w.id = ?
                  AND m.status = 'active'
                  AND w.status = 'active'
                """,
                (user_id, workspace_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("Workspace is not available for this user")
        return self._workspace_from_row(row), str(row["membership_role"] or "read_only")

    def request_context_for_token(
        self,
        *,
        token: str,
        auth_mode: str,
        requested_workspace_id: str | None = None,
    ) -> RequestContext:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, u.status AS user_status
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.session_token_hash = ?
                  AND s.revoked_at IS NULL
                """,
                (_token_hash(token),),
            ).fetchone()
            if row is None:
                raise AuthenticationError("Session is not active")
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= utc_now() or str(row["user_status"]) != "active":
                raise AuthenticationError("Session is not active")
            connection.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
                (utc_now_iso(), row["id"]),
            )

        workspace_id = requested_workspace_id or str(row["active_workspace_id"] or "")
        if not workspace_id:
            workspace_id = self.default_workspace_for_user(str(row["user_id"])).id
        workspace, role = self.get_workspace_for_user(user_id=str(row["user_id"]), workspace_id=workspace_id)
        return self._context_from_workspace(
            user_id=str(row["user_id"]),
            workspace=workspace,
            role=role,
            auth_mode=auth_mode,
        )

    def dev_request_context(self, *, auth_mode: str, requested_workspace_id: str | None = None) -> RequestContext:
        user_id = self._default_dev_user_id()
        workspace_id = requested_workspace_id or DEFAULT_HOUSEHOLD_WORKSPACE_ID
        workspace, role = self.get_workspace_for_user(user_id=user_id, workspace_id=workspace_id)
        return self._context_from_workspace(
            user_id=user_id,
            workspace=workspace,
            role=role,
            auth_mode=auth_mode,
        )

    def _default_dev_user_id(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id
                FROM users u
                JOIN memberships m ON m.user_id = u.id
                WHERE m.organization_id = ?
                  AND m.role = 'owner'
                  AND m.status = 'active'
                  AND u.status = 'active'
                ORDER BY u.created_at
                LIMIT 1
                """,
                (DEFAULT_ORGANIZATION_ID,),
            ).fetchone()
        if row is None:
            raise AuthenticationError("Default development user is not configured")
        return str(row["id"])

    def _context_from_workspace(
        self,
        *,
        user_id: str,
        workspace: WorkspaceRecord,
        role: str,
        auth_mode: str,
    ) -> RequestContext:
        permissions = self.ROLE_PERMISSIONS.get(role, frozenset())
        return RequestContext(
            user_id=user_id,
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            role=role,
            permissions=permissions,
            is_demo_workspace=workspace.workspace_type == "demo",
            auth_mode=auth_mode,
        )

    def record_audit_event(
        self,
        *,
        action: str,
        actor_user_id: str | None = None,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        outcome: str = "ok",
        metadata_json: str = "{}",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    id, actor_user_id, organization_id, workspace_id, action,
                    target_type, target_id, outcome, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:16]}",
                    actor_user_id,
                    organization_id,
                    workspace_id,
                    action,
                    target_type,
                    target_id,
                    outcome,
                    metadata_json,
                    utc_now_iso(),
                ),
            )

    @staticmethod
    def _workspace_from_row(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            name=str(row["name"]),
            workspace_type=str(row["workspace_type"]),
            storage_path=Path(str(row["storage_path"])),
            status=str(row["status"]),
        )
