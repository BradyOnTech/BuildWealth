from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from buildwealth_orchestrator.services.control_database import ControlDatabase


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


@dataclass(frozen=True)
class AccountDataDeletionRequest:
    id: str
    user_id: str
    organization_id: str
    workspace_id: str | None
    requested_by_user_id: str
    status: str
    scope: str
    requested_at: str
    purge_after: str
    canceled_at: str | None
    completed_at: str | None
    preview: dict[str, Any]
    result: dict[str, Any]
    failure_reason: str


@dataclass(frozen=True)
class FinancialConnectionIndexRecord:
    """Token-free route from a provider Item to its workspace-owned record."""

    provider: str
    provider_item_id: str
    workspace_id: str
    connection_id: str
    created_at: str
    updated_at: str


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
            "connections.read",
            "connections.write",
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
            "account.export",
            "account.delete",
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

    def __init__(self, database_path: Path, *, database: "ControlDatabase | None" = None):
        # The seam: all connection handling and schema migration lives behind
        # the database object; this store owns SQL and business rules only.
        # SQLite (one file, zero services) is the default and stays the
        # local-first product; hosted deployments swap the adapter, not the
        # store. See control_database.py for the contract and the recipe.
        from buildwealth_orchestrator.services.control_database import SQLiteControlDatabase

        self.database_path = database_path
        self.database = database if database is not None else SQLiteControlDatabase(database_path)
        self.database.migrate()

    def _connect(self) -> sqlite3.Connection:
        return self.database.connect()

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
            # dialect: INSERT OR IGNORE is SQLite; Postgres uses
            # ON CONFLICT DO NOTHING (see control_database.py recipe).
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

    def _create_owned_household(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: str,
        organization_id: str,
        household_workspace_id: str,
        demo_workspace_id: str,
        root_dir: Path,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO organizations (id, name, org_type, status, created_at, updated_at)
            VALUES (?, ?, 'household', 'active', ?, ?)
            """,
            (organization_id, "My Household", now, now),
        )
        connection.execute(
            """
            INSERT INTO memberships (
                id, user_id, organization_id, role, status, created_at, updated_at
            )
            VALUES (?, ?, ?, 'owner', 'active', ?, ?)
            """,
            (f"mem_{uuid.uuid4().hex[:16]}", user_id, organization_id, now, now),
        )
        self._upsert_workspace(
            connection,
            workspace_id=household_workspace_id,
            organization_id=organization_id,
            name="My Household",
            workspace_type="household",
            storage_path=root_dir / household_workspace_id,
            now=now,
        )
        self._upsert_workspace(
            connection,
            workspace_id=demo_workspace_id,
            organization_id=organization_id,
            name="Demo Household",
            workspace_type="demo",
            storage_path=root_dir / demo_workspace_id,
            now=now,
        )

    def _ensure_user_has_household(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: str,
        root_dir: Path,
        now: str,
    ) -> None:
        existing = connection.execute(
            """
            SELECT m.organization_id
            FROM memberships m
            JOIN organizations o ON o.id = m.organization_id
            WHERE m.user_id = ?
              AND m.status = 'active'
              AND o.status = 'active'
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if existing is not None:
            return
        household_workspace_id = f"ws_{uuid.uuid4().hex[:16]}_household"
        demo_workspace_id = f"ws_{uuid.uuid4().hex[:16]}_demo"
        self._create_owned_household(
            connection,
            user_id=user_id,
            organization_id=f"org_{uuid.uuid4().hex[:16]}",
            household_workspace_id=household_workspace_id,
            demo_workspace_id=demo_workspace_id,
            root_dir=root_dir,
            now=now,
        )

    def create_owner_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str = "",
        workspace_root_dir: Path | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_email(email)
        if not normalized:
            raise ValueError("email is required")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        now = utc_now_iso()
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        organization_id = f"org_{uuid.uuid4().hex[:16]}"
        household_workspace_id = f"ws_{uuid.uuid4().hex[:16]}_household"
        demo_workspace_id = f"ws_{uuid.uuid4().hex[:16]}_demo"
        root_dir = workspace_root_dir or (self.database_path.parent.parent / "workspaces")
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
            self._create_owned_household(
                connection,
                user_id=user_id,
                organization_id=organization_id,
                household_workspace_id=household_workspace_id,
                demo_workspace_id=demo_workspace_id,
                root_dir=root_dir,
                now=now,
            )
            connection.execute(
                """
                INSERT INTO audit_events (
                    id, actor_user_id, organization_id, workspace_id, action,
                    target_type, target_id, outcome, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, 'workspace.created', 'organization', ?, 'ok', ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:16]}",
                    user_id,
                    organization_id,
                    household_workspace_id,
                    organization_id,
                    "{}",
                    now,
                ),
            )
        return self.get_user(user_id)

    def create_hosted_login_flow(
        self,
        *,
        provider: str,
        code_verifier: str,
        nonce: str,
        redirect_to: str,
        ttl_minutes: int = 10,
    ) -> dict[str, str]:
        state = secrets.token_urlsafe(32)
        now = utc_now()
        expires_at = now + timedelta(minutes=max(1, ttl_minutes))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_login_flows (
                    id, provider, state_token_hash, code_verifier, nonce,
                    redirect_to, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"alf_{uuid.uuid4().hex[:16]}",
                    provider,
                    _token_hash(state),
                    code_verifier,
                    nonce,
                    _safe_redirect_path(redirect_to),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return {"state": state, "nonce": nonce, "code_verifier": code_verifier}

    def consume_hosted_login_flow(self, *, provider: str, state: str) -> dict[str, str]:
        if not provider or not state:
            raise AuthenticationError("Hosted login request is not active")
        now = utc_now_iso()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM auth_login_flows
                WHERE provider = ?
                  AND state_token_hash = ?
                  AND consumed_at IS NULL
                  AND expires_at > ?
                """,
                (provider, _token_hash(state), now),
            ).fetchone()
            if row is None:
                raise AuthenticationError("Hosted login request is not active")
            connection.execute(
                "UPDATE auth_login_flows SET consumed_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        return {
            "code_verifier": str(row["code_verifier"]),
            "nonce": str(row["nonce"]),
            "redirect_to": _safe_redirect_path(str(row["redirect_to"] or "/v2")),
        }

    def upsert_hosted_owner_user(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        display_name: str,
        email_verified: bool,
        mfa_enabled: bool,
        workspace_root_dir: Path | None = None,
    ) -> dict[str, Any]:
        provider = str(provider or "").strip()
        subject = str(subject or "").strip()
        normalized = self.normalize_email(email)
        if not provider or not subject:
            raise AuthenticationError("Hosted identity did not include a stable subject")
        if not normalized:
            raise AuthenticationError("Hosted identity did not include an email")
        if not email_verified:
            raise AuthenticationError("Hosted identity email must be verified")

        now = utc_now_iso()
        root_dir = workspace_root_dir or (self.database_path.parent.parent / "workspaces")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM users
                WHERE auth_provider = ?
                  AND auth_provider_subject = ?
                  AND status = 'active'
                """,
                (provider, subject),
            ).fetchone()
            if row is not None:
                user_id = str(row["id"])
                connection.execute(
                    """
                    UPDATE users
                    SET email = ?, email_normalized = ?, display_name = ?,
                        mfa_enabled = ?, updated_at = ?, last_login_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized,
                        normalized,
                        display_name.strip() or str(row["display_name"] or "") or normalized,
                        1 if mfa_enabled else 0,
                        now,
                        now,
                        user_id,
                    ),
                )
                self._ensure_user_has_household(connection, user_id=user_id, root_dir=root_dir, now=now)
                return dict(connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

            email_row = connection.execute(
                "SELECT * FROM users WHERE email_normalized = ? AND status = 'active'",
                (normalized,),
            ).fetchone()
            if email_row is not None:
                existing_provider = str(email_row["auth_provider"] or "local")
                existing_subject = str(email_row["auth_provider_subject"] or "")
                if existing_subject and (
                    existing_provider != provider or existing_subject != subject
                ):
                    raise AuthenticationError("Email is already linked to a different identity provider")
                user_id = str(email_row["id"])
                connection.execute(
                    """
                    UPDATE users
                    SET auth_provider = ?, auth_provider_subject = ?, display_name = ?,
                        mfa_enabled = ?, updated_at = ?, last_login_at = ?
                    WHERE id = ?
                    """,
                    (
                        provider,
                        subject,
                        display_name.strip() or str(email_row["display_name"] or "") or normalized,
                        1 if mfa_enabled else 0,
                        now,
                        now,
                        user_id,
                    ),
                )
                self._ensure_user_has_household(connection, user_id=user_id, root_dir=root_dir, now=now)
                self._record_audit_event_with_connection(
                    connection,
                    action="auth.hosted_identity_linked",
                    actor_user_id=user_id,
                    target_type="user",
                    target_id=user_id,
                    metadata_json=json.dumps({"provider": provider}),
                )
                return dict(connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

            user_id = f"usr_{uuid.uuid4().hex[:16]}"
            connection.execute(
                """
                INSERT INTO users (
                    id, email, email_normalized, display_name, password_hash,
                    auth_provider, auth_provider_subject, mfa_enabled, status,
                    created_at, updated_at, last_login_at
                )
                VALUES (?, ?, ?, ?, '', ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    user_id,
                    normalized,
                    normalized,
                    display_name.strip() or normalized,
                    provider,
                    subject,
                    1 if mfa_enabled else 0,
                    now,
                    now,
                    now,
                ),
            )
            self._ensure_user_has_household(connection, user_id=user_id, root_dir=root_dir, now=now)
            self._record_audit_event_with_connection(
                connection,
                action="auth.hosted_user_created",
                actor_user_id=user_id,
                target_type="user",
                target_id=user_id,
                metadata_json=json.dumps({"provider": provider}),
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

    def verify_local_password(self, *, user_id: str, password: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash, auth_provider, status FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None or str(row["status"]) != "active":
            raise AuthenticationError("User not found")
        if str(row["auth_provider"] or "local") != "local":
            raise AuthenticationError("Password confirmation is unavailable for this account")
        if not _verify_password(password, str(row["password_hash"] or "")):
            raise AuthenticationError("Password confirmation failed")

    def change_local_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        self.verify_local_password(user_id=user_id, password=current_password)
        if len(str(new_password or "")) < 8:
            raise ValueError("new password must be at least 8 characters")
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (_hash_password(new_password), now, user_id),
            )
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self._record_audit_event_with_connection(
                connection,
                action="account.password_changed",
                actor_user_id=user_id,
                target_type="user",
                target_id=user_id,
                metadata_json="{}",
            )

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise AuthenticationError("User not found")
        return dict(row)

    def register_financial_connection_index(
        self,
        *,
        provider: str,
        provider_item_id: str,
        workspace_id: str,
        connection_id: str,
    ) -> FinancialConnectionIndexRecord:
        """Register an Item idempotently without ever storing its access token."""
        normalized_provider = str(provider or "").strip().lower()
        opaque_item_id = str(provider_item_id or "").strip()
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_connection_id = str(connection_id or "").strip()
        if not all(
            (
                normalized_provider,
                opaque_item_id,
                normalized_workspace_id,
                normalized_connection_id,
            )
        ):
            raise ValueError(
                "provider, provider_item_id, workspace_id, and connection_id are required"
            )

        now = utc_now_iso()
        with self._connect() as connection:
            workspace = connection.execute(
                "SELECT id FROM workspaces WHERE id = ? AND status != 'deleted'",
                (normalized_workspace_id,),
            ).fetchone()
            if workspace is None:
                raise ValueError("Workspace not found")
            existing = connection.execute(
                """
                SELECT * FROM financial_connection_index
                WHERE provider = ? AND provider_item_id = ?
                """,
                (normalized_provider, opaque_item_id),
            ).fetchone()
            if existing is not None and (
                str(existing["workspace_id"]) != normalized_workspace_id
                or str(existing["connection_id"]) != normalized_connection_id
            ):
                raise ValueError("Provider Item is already assigned to another connection")
            connection.execute(
                """
                INSERT INTO financial_connection_index (
                    provider, provider_item_id, workspace_id, connection_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_item_id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_provider,
                    opaque_item_id,
                    normalized_workspace_id,
                    normalized_connection_id,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM financial_connection_index
                WHERE provider = ? AND provider_item_id = ?
                """,
                (normalized_provider, opaque_item_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("Financial connection index was not stored")
        return self._financial_connection_index_from_row(row)

    def lookup_financial_connection_index(
        self,
        *,
        provider: str,
        provider_item_id: str,
    ) -> FinancialConnectionIndexRecord | None:
        normalized_provider = str(provider or "").strip().lower()
        opaque_item_id = str(provider_item_id or "").strip()
        if not normalized_provider or not opaque_item_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM financial_connection_index
                WHERE provider = ? AND provider_item_id = ?
                """,
                (normalized_provider, opaque_item_id),
            ).fetchone()
        return self._financial_connection_index_from_row(row) if row is not None else None

    def remove_financial_connection_index(
        self,
        *,
        provider: str,
        provider_item_id: str,
        workspace_id: str | None = None,
        connection_id: str | None = None,
    ) -> bool:
        normalized_provider = str(provider or "").strip().lower()
        opaque_item_id = str(provider_item_id or "").strip()
        if not normalized_provider or not opaque_item_id:
            return False
        clauses = ["provider = ?", "provider_item_id = ?"]
        params: list[str] = [normalized_provider, opaque_item_id]
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(str(workspace_id).strip())
        if connection_id is not None:
            clauses.append("connection_id = ?")
            params.append(str(connection_id).strip())
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM financial_connection_index WHERE {' AND '.join(clauses)}",
                tuple(params),
            )
        return int(cursor.rowcount or 0) == 1

    def remove_financial_connection_indexes_for_workspace(self, *, workspace_id: str) -> int:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return 0
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM financial_connection_index WHERE workspace_id = ?",
                (normalized_workspace_id,),
            )
        return int(cursor.rowcount or 0)

    def count_financial_connection_indexes_for_workspace(self, *, workspace_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM financial_connection_index WHERE workspace_id = ?",
                (str(workspace_id or "").strip(),),
            ).fetchone()
        return int(row["n"] or 0) if row is not None else 0

    def export_account_bundle(self, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            user_row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_row is None:
                raise AuthenticationError("User not found")
            memberships = connection.execute(
                """
                SELECT m.id, m.organization_id, m.role, m.status, m.created_at, m.updated_at,
                       o.name AS organization_name, o.org_type
                FROM memberships m
                JOIN organizations o ON o.id = m.organization_id
                WHERE m.user_id = ?
                ORDER BY m.created_at
                """,
                (user_id,),
            ).fetchall()
            workspaces = connection.execute(
                """
                SELECT w.id, w.organization_id, w.name, w.workspace_type, w.storage_mode,
                       w.storage_path, w.encryption_status, w.status, w.created_at, w.updated_at
                FROM workspaces w
                JOIN memberships m ON m.organization_id = w.organization_id
                WHERE m.user_id = ?
                ORDER BY w.created_at
                """,
                (user_id,),
            ).fetchall()
            sessions = connection.execute(
                """
                SELECT id, active_workspace_id, created_at, last_seen_at, expires_at, revoked_at
                FROM sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
            audit_events = connection.execute(
                """
                SELECT action, organization_id, workspace_id, target_type, target_id,
                       outcome, metadata_json, created_at
                FROM audit_events
                WHERE actor_user_id = ?
                ORDER BY created_at DESC
                LIMIT 250
                """,
                (user_id,),
            ).fetchall()
            financial_connection_indexes = connection.execute(
                """
                SELECT DISTINCT f.provider, f.provider_item_id, f.workspace_id,
                       f.connection_id, f.created_at, f.updated_at
                FROM financial_connection_index f
                JOIN workspaces w ON w.id = f.workspace_id
                JOIN memberships m ON m.organization_id = w.organization_id
                WHERE m.user_id = ?
                ORDER BY f.created_at, f.provider, f.provider_item_id
                """,
                (user_id,),
            ).fetchall()
        user = dict(user_row)
        user.pop("password_hash", None)
        user.pop("auth_provider_subject", None)
        return {
            "schema_version": 2,
            "exported_at": utc_now_iso(),
            "user": user,
            "memberships": [dict(row) for row in memberships],
            "workspaces": [dict(row) for row in workspaces],
            "sessions": [dict(row) for row in sessions],
            "audit_events": [
                {
                    **{key: value for key, value in dict(row).items() if key != "metadata_json"},
                    "metadata": _json_object(row["metadata_json"]),
                }
                for row in audit_events
            ],
            "financial_connection_indexes": [dict(row) for row in financial_connection_indexes],
        }

    def authenticated_user_for_token(self, *, token: str) -> dict[str, Any]:
        if not token:
            raise AuthenticationError("Authentication required")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.*, s.id AS session_id, s.expires_at, s.revoked_at
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
            if expires_at <= utc_now() or str(row["status"]) != "active":
                raise AuthenticationError("Session is not active")
            connection.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
                (utc_now_iso(), row["session_id"]),
            )
        user = dict(row)
        user.pop("password_hash", None)
        user.pop("auth_provider_subject", None)
        return user

    def default_dev_user(self) -> dict[str, Any]:
        return self.get_user(self._default_dev_user_id())

    def deactivate_user_account(self, *, user_id: str, current_password: str) -> None:
        self.verify_local_password(user_id=user_id, password=current_password)
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET status = 'deleted', updated_at = ? WHERE id = ?",
                (now, user_id),
            )
            connection.execute(
                "UPDATE memberships SET status = 'inactive', updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self._record_audit_event_with_connection(
                connection,
                action="account.deactivated",
                actor_user_id=user_id,
                target_type="user",
                target_id=user_id,
                metadata_json="{}",
            )

    def close_hosted_user_access(
        self,
        *,
        user_id: str,
        confirm: str,
    ) -> None:
        if confirm.strip().lower() != "close buildwealth access":
            raise ValueError('Type "close buildwealth access" to confirm hosted account closure')

        now = utc_now_iso()
        with self._connect() as connection:
            user_row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_row is None:
                raise AuthenticationError("User not found")
            if str(user_row["status"] or "") != "active":
                raise AuthenticationError("User is not active")

            auth_provider = str(user_row["auth_provider"] or "local")
            if auth_provider == "local":
                raise ValueError("Use password confirmation to deactivate a local account")

            connection.execute(
                "UPDATE users SET status = 'deleted', updated_at = ? WHERE id = ?",
                (now, user_id),
            )
            connection.execute(
                "UPDATE memberships SET status = 'inactive', updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self._record_audit_event_with_connection(
                connection,
                action="account.hosted_access_closed",
                actor_user_id=user_id,
                target_type="user",
                target_id=user_id,
                metadata_json=json.dumps(
                    {
                        "auth_provider": auth_provider,
                        "retention": "workspace_files_backups_and_audit_records_retained",
                    }
                ),
            )

    def create_account_data_deletion_request(
        self,
        *,
        user_id: str,
        requested_by_user_id: str,
        organization_id: str,
        scope: str,
        purge_after: str,
        preview: dict[str, Any] | None = None,
        workspace_id: str | None = None,
    ) -> AccountDataDeletionRequest:
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope not in {"workspace", "household", "account"}:
            raise ValueError("Deletion scope must be workspace, household, or account")
        if normalized_scope == "workspace" and not str(workspace_id or "").strip():
            raise ValueError("Workspace deletion requires a workspace_id")
        if not str(purge_after or "").strip():
            raise ValueError("Deletion request requires a purge_after timestamp")

        now = utc_now_iso()
        request_id = f"del_{uuid.uuid4().hex[:16]}"
        preview_json = json.dumps(preview or {}, sort_keys=True)
        with self._connect() as connection:
            owner_row = connection.execute(
                """
                SELECT m.role
                FROM memberships m
                JOIN users u ON u.id = m.user_id
                JOIN organizations o ON o.id = m.organization_id
                WHERE m.user_id = ?
                  AND m.organization_id = ?
                  AND m.status = 'active'
                  AND u.status = 'active'
                  AND o.status = 'active'
                """,
                (requested_by_user_id, organization_id),
            ).fetchone()
            if owner_row is None:
                raise AuthorizationError("User cannot request deletion for this household")
            if str(owner_row["role"] or "") != "owner":
                raise AuthorizationError("Only a household owner can request data deletion")

            user_row = connection.execute(
                "SELECT id FROM users WHERE id = ? AND status = 'active'",
                (user_id,),
            ).fetchone()
            if user_row is None:
                raise AuthenticationError("User is not active")

            duplicate = connection.execute(
                """
                SELECT id
                FROM account_data_deletion_requests
                WHERE organization_id = ?
                  AND status = 'pending'
                LIMIT 1
                """,
                (organization_id,),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("A data deletion request is already pending for this household")

            affected_workspace_ids = self._affected_workspace_ids_for_deletion(
                connection,
                organization_id=organization_id,
                workspace_id=workspace_id,
                scope=normalized_scope,
            )
            if not affected_workspace_ids:
                raise AuthorizationError("No active workspace data is available for deletion")

            connection.execute(
                """
                INSERT INTO account_data_deletion_requests (
                    id, user_id, organization_id, workspace_id, requested_by_user_id,
                    status, scope, requested_at, purge_after, preview_json
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    request_id,
                    user_id,
                    organization_id,
                    workspace_id,
                    requested_by_user_id,
                    normalized_scope,
                    now,
                    purge_after,
                    preview_json,
                ),
            )
            connection.executemany(
                """
                UPDATE workspaces
                SET status = 'pending_deletion',
                    deletion_requested_at = ?,
                    purge_after = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                [(now, purge_after, now, affected_id) for affected_id in affected_workspace_ids],
            )
            if normalized_scope in {"household", "account"}:
                connection.execute(
                    """
                    UPDATE organizations
                    SET status = 'pending_deletion',
                        deletion_requested_at = ?,
                        purge_after = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, purge_after, now, organization_id),
                )
            if normalized_scope == "account":
                connection.execute(
                    """
                    UPDATE users
                    SET deletion_requested_at = ?,
                        purge_after = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, purge_after, now, user_id),
                )
            self._record_audit_event_with_connection(
                connection,
                action="account.data_deletion_requested",
                actor_user_id=requested_by_user_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                target_type="account_data_deletion_request",
                target_id=request_id,
                metadata_json=json.dumps(
                    {
                        "scope": normalized_scope,
                        "purge_after": purge_after,
                        "affected_workspace_ids": affected_workspace_ids,
                    },
                    sort_keys=True,
                ),
            )
            row = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Deletion request was not created")
        return self._deletion_request_from_row(row)

    def cancel_account_data_deletion_request(
        self,
        *,
        request_id: str,
        canceled_by_user_id: str,
    ) -> AccountDataDeletionRequest:
        now = utc_now_iso()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Deletion request not found")
            if str(row["status"] or "") != "pending":
                raise ValueError("Only pending deletion requests can be canceled")

            membership = connection.execute(
                """
                SELECT role
                FROM memberships
                WHERE user_id = ? AND organization_id = ? AND status = 'active'
                """,
                (canceled_by_user_id, row["organization_id"]),
            ).fetchone()
            if membership is None or str(membership["role"] or "") != "owner":
                raise AuthorizationError("Only a household owner can cancel data deletion")

            connection.execute(
                """
                UPDATE account_data_deletion_requests
                SET status = 'canceled', canceled_at = ?
                WHERE id = ?
                """,
                (now, request_id),
            )
            workspace_id = row["workspace_id"]
            organization_id = str(row["organization_id"])
            if workspace_id and not self._has_pending_deletion_for_workspace(
                connection,
                workspace_id=str(workspace_id),
            ):
                connection.execute(
                    """
                    UPDATE workspaces
                    SET status = 'active',
                        deletion_requested_at = NULL,
                        purge_after = NULL,
                        updated_at = ?
                    WHERE id = ? AND status = 'pending_deletion'
                    """,
                    (now, workspace_id),
                )
            if not workspace_id and not self._has_pending_deletion_for_organization(
                connection,
                organization_id=organization_id,
            ):
                connection.execute(
                    """
                    UPDATE workspaces
                    SET status = 'active',
                        deletion_requested_at = NULL,
                        purge_after = NULL,
                        updated_at = ?
                    WHERE organization_id = ? AND status = 'pending_deletion'
                    """,
                    (now, organization_id),
                )
                connection.execute(
                    """
                    UPDATE organizations
                    SET status = 'active',
                        deletion_requested_at = NULL,
                        purge_after = NULL,
                        updated_at = ?
                    WHERE id = ? AND status = 'pending_deletion'
                    """,
                    (now, organization_id),
                )
            if str(row["scope"] or "") == "account":
                connection.execute(
                    """
                    UPDATE users
                    SET deletion_requested_at = NULL,
                        purge_after = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, row["user_id"]),
                )
            self._record_audit_event_with_connection(
                connection,
                action="account.data_deletion_canceled",
                actor_user_id=canceled_by_user_id,
                organization_id=organization_id,
                workspace_id=str(workspace_id) if workspace_id else None,
                target_type="account_data_deletion_request",
                target_id=request_id,
                metadata_json=json.dumps({"scope": row["scope"]}, sort_keys=True),
            )
            updated = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        if updated is None:
            raise ValueError("Deletion request not found")
        return self._deletion_request_from_row(updated)

    def complete_account_data_deletion_request(
        self,
        *,
        request_id: str,
        result: dict[str, Any] | None = None,
    ) -> AccountDataDeletionRequest:
        now = utc_now_iso()
        result_json = json.dumps(result or {}, sort_keys=True)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Deletion request not found")
            if str(row["status"] or "") != "pending":
                raise ValueError("Only pending deletion requests can be completed")
            connection.execute(
                """
                UPDATE account_data_deletion_requests
                SET status = 'completed', completed_at = ?, result_json = ?
                WHERE id = ?
                """,
                (now, result_json, request_id),
            )
            workspace_id = row["workspace_id"]
            organization_id = str(row["organization_id"])
            if workspace_id:
                connection.execute(
                    """
                    UPDATE workspaces
                    SET status = 'deleted',
                        deletion_completed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, workspace_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE workspaces
                    SET status = 'deleted',
                        deletion_completed_at = ?,
                        updated_at = ?
                    WHERE organization_id = ? AND status = 'pending_deletion'
                    """,
                    (now, now, organization_id),
                )
                connection.execute(
                    """
                    UPDATE organizations
                    SET status = 'deleted',
                        deletion_completed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, organization_id),
                )
            if str(row["scope"] or "") == "account":
                connection.execute(
                    """
                    UPDATE users
                    SET status = 'deleted',
                        deletion_completed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, row["user_id"]),
                )
                connection.execute(
                    "UPDATE memberships SET status = 'inactive', updated_at = ? WHERE user_id = ?",
                    (now, row["user_id"]),
                )
            self._record_audit_event_with_connection(
                connection,
                action="account.data_deletion_completed",
                actor_user_id=str(row["requested_by_user_id"]),
                organization_id=organization_id,
                workspace_id=str(workspace_id) if workspace_id else None,
                target_type="account_data_deletion_request",
                target_id=request_id,
                metadata_json=result_json,
            )
            updated = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        if updated is None:
            raise ValueError("Deletion request not found")
        return self._deletion_request_from_row(updated)

    def fail_account_data_deletion_request(
        self,
        *,
        request_id: str,
        failure_reason: str,
        result: dict[str, Any] | None = None,
    ) -> AccountDataDeletionRequest:
        now = utc_now_iso()
        result_json = json.dumps(result or {}, sort_keys=True)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Deletion request not found")
            if str(row["status"] or "") != "pending":
                raise ValueError("Only pending deletion requests can be marked failed")
            connection.execute(
                """
                UPDATE account_data_deletion_requests
                SET status = 'failed',
                    completed_at = ?,
                    result_json = ?,
                    failure_reason = ?
                WHERE id = ?
                """,
                (now, result_json, str(failure_reason or "").strip()[:500], request_id),
            )
            self._record_audit_event_with_connection(
                connection,
                action="account.data_deletion_failed",
                actor_user_id=str(row["requested_by_user_id"]),
                organization_id=str(row["organization_id"]),
                workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
                target_type="account_data_deletion_request",
                target_id=request_id,
                outcome="error",
                metadata_json=json.dumps({"failure_reason": str(failure_reason or "").strip()[:500]}),
            )
            updated = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        if updated is None:
            raise ValueError("Deletion request not found")
        return self._deletion_request_from_row(updated)

    def list_pending_account_data_deletion_requests(self, *, due_at: str | None = None) -> list[AccountDataDeletionRequest]:
        query = "SELECT * FROM account_data_deletion_requests WHERE status = 'pending'"
        params: tuple[str, ...] = ()
        if due_at is not None:
            query += " AND purge_after <= ?"
            params = (due_at,)
        query += " ORDER BY purge_after, requested_at"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._deletion_request_from_row(row) for row in rows]

    def list_account_data_deletion_requests_for_user(self, *, user_id: str) -> list[AccountDataDeletionRequest]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT d.*
                FROM account_data_deletion_requests d
                LEFT JOIN memberships m ON m.organization_id = d.organization_id
                WHERE d.user_id = ?
                   OR d.requested_by_user_id = ?
                   OR m.user_id = ?
                ORDER BY d.requested_at DESC
                """,
                (user_id, user_id, user_id),
            ).fetchall()
        return [self._deletion_request_from_row(row) for row in rows]

    def workspaces_for_account_data_deletion_request(self, *, request_id: str) -> list[WorkspaceRecord]:
        with self._connect() as connection:
            request_row = connection.execute(
                "SELECT * FROM account_data_deletion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if request_row is None:
                raise ValueError("Deletion request not found")
            if request_row["workspace_id"]:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM workspaces
                    WHERE id = ?
                    ORDER BY created_at, name
                    """,
                    (request_row["workspace_id"],),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM workspaces
                    WHERE organization_id = ?
                      AND status IN ('pending_deletion', 'deleted')
                    ORDER BY CASE workspace_type WHEN 'household' THEN 0 WHEN 'demo' THEN 1 ELSE 2 END, name
                    """,
                    (request_row["organization_id"],),
                ).fetchall()
        return [self._workspace_from_row(row) for row in rows]

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

    def count_active_local_users(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE status = 'active' AND auth_provider = 'local' AND password_hash != ''",
            ).fetchone()
        return int(row["n"] or 0)

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE session_token_hash = ?",
                (utc_now_iso(), _token_hash(token)),
            )

    def revoke_all_sessions_for_user(self, user_id: str, *, except_token: str | None = None) -> int:
        """Kill every live session for a user — sign-out-everywhere, and the
        blast radius control after a password change. Returns sessions revoked."""
        if not user_id:
            return 0
        params: list[Any] = [utc_now_iso(), user_id]
        exclusion = ""
        if except_token:
            exclusion = " AND session_token_hash != ?"
            params.append(_token_hash(except_token))
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE sessions
                SET revoked_at = ?
                WHERE user_id = ?
                  AND revoked_at IS NULL{exclusion}
                """,
                tuple(params),
            )
        return int(cursor.rowcount or 0)

    def rotate_csrf_token(self, token: str) -> str:
        if not token:
            raise AuthenticationError("Session is not active")
        csrf_token = secrets.token_urlsafe(32)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions
                SET csrf_token_hash = ?, last_seen_at = ?
                WHERE session_token_hash = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (_token_hash(csrf_token), utc_now_iso(), _token_hash(token), utc_now_iso()),
            )
        if cursor.rowcount != 1:
            raise AuthenticationError("Session is not active")
        return csrf_token

    def verify_csrf_token(self, *, session_token: str, csrf_token: str) -> bool:
        if not session_token or not csrf_token:
            return False
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT csrf_token_hash
                FROM sessions
                WHERE session_token_hash = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (_token_hash(session_token), utc_now_iso()),
            ).fetchone()
        if row is None:
            return False
        return hmac.compare_digest(str(row["csrf_token_hash"] or ""), _token_hash(csrf_token))

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

    def list_active_workspaces(self) -> list[WorkspaceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM workspaces
                WHERE status = 'active'
                ORDER BY created_at, name
                """
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
            self._record_audit_event_with_connection(
                connection,
                action=action,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                target_type=target_type,
                target_id=target_id,
                outcome=outcome,
                metadata_json=metadata_json,
            )

    @staticmethod
    def _record_audit_event_with_connection(
        connection: sqlite3.Connection,
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
    def _affected_workspace_ids_for_deletion(
        connection: sqlite3.Connection,
        *,
        organization_id: str,
        workspace_id: str | None,
        scope: str,
    ) -> list[str]:
        if scope == "workspace":
            row = connection.execute(
                """
                SELECT id
                FROM workspaces
                WHERE id = ?
                  AND organization_id = ?
                  AND status = 'active'
                """,
                (workspace_id, organization_id),
            ).fetchone()
            return [str(row["id"])] if row is not None else []
        rows = connection.execute(
            """
            SELECT id
            FROM workspaces
            WHERE organization_id = ?
              AND status = 'active'
            ORDER BY CASE workspace_type WHEN 'household' THEN 0 WHEN 'demo' THEN 1 ELSE 2 END, name
            """,
            (organization_id,),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    @staticmethod
    def _has_pending_deletion_for_workspace(
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT id
            FROM account_data_deletion_requests
            WHERE workspace_id = ?
              AND status = 'pending'
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _has_pending_deletion_for_organization(
        connection: sqlite3.Connection,
        *,
        organization_id: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT id
            FROM account_data_deletion_requests
            WHERE organization_id = ?
              AND status = 'pending'
            LIMIT 1
            """,
            (organization_id,),
        ).fetchone()
        return row is not None

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

    @staticmethod
    def _financial_connection_index_from_row(
        row: sqlite3.Row,
    ) -> FinancialConnectionIndexRecord:
        return FinancialConnectionIndexRecord(
            provider=str(row["provider"]),
            provider_item_id=str(row["provider_item_id"]),
            workspace_id=str(row["workspace_id"]),
            connection_id=str(row["connection_id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _deletion_request_from_row(row: sqlite3.Row) -> AccountDataDeletionRequest:
        return AccountDataDeletionRequest(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            organization_id=str(row["organization_id"]),
            workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
            requested_by_user_id=str(row["requested_by_user_id"]),
            status=str(row["status"]),
            scope=str(row["scope"]),
            requested_at=str(row["requested_at"]),
            purge_after=str(row["purge_after"]),
            canceled_at=str(row["canceled_at"]) if row["canceled_at"] else None,
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
            preview=_json_object(row["preview_json"]),
            result=_json_object(row["result_json"]),
            failure_reason=str(row["failure_reason"] or ""),
        )


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_redirect_path(value: str) -> str:
    path = str(value or "").strip()
    if not path.startswith("/") or path.startswith("//") or "\r" in path or "\n" in path:
        return "/v2"
    return path
