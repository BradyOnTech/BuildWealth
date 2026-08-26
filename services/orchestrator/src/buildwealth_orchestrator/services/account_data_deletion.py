from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.backup_restore import (
    BACKUP_ARCHIVE_PREFIX,
    BACKUP_ARCHIVE_SUFFIX,
)
from buildwealth_orchestrator.services.control_plane import (
    ControlPlaneStore,
    RequestContext,
    WorkspaceRecord,
)
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


RECOVERY_WINDOW_DAYS = 30


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def purge_after_for_recovery_window(*, days: int = RECOVERY_WINDOW_DAYS) -> str:
    return (utc_now() + timedelta(days=max(1, days))).isoformat()


def required_confirmation_phrase(scope: str) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized == "workspace":
        return "delete workspace data"
    if normalized == "account":
        return "delete my buildwealth data"
    return "delete household data"


def build_account_data_deletion_preview(
    *,
    control_plane: ControlPlaneStore,
    workspace_service_factory: WorkspaceServiceFactory,
    context: RequestContext,
    scope: str,
    recovery_window_days: int = RECOVERY_WINDOW_DAYS,
) -> dict[str, Any]:
    normalized_scope = _normalize_scope(scope)
    workspaces = _workspaces_for_scope(
        control_plane=control_plane,
        context=context,
        scope=normalized_scope,
    )
    generated_at = utc_now_iso()
    purge_after = (utc_now() + timedelta(days=max(1, recovery_window_days))).isoformat()
    workspace_items = [
        _workspace_preview_item(workspace_service_factory=workspace_service_factory, workspace=workspace)
        for workspace in workspaces
    ]
    totals = _sum_workspace_items(workspace_items)
    warnings = []
    if not workspace_items:
        warnings.append("No active workspace data is available for this deletion scope.")
    if normalized_scope in {"household", "account"}:
        warnings.append("This affects every active workspace in the household.")
    if totals["financial_connection_index_count"]:
        warnings.append(
            "Connected institutions must be revoked before local workspace data can be purged."
        )
    return {
        "schema_version": 1,
        "scope": normalized_scope,
        "generated_at": generated_at,
        "recovery_window_days": max(1, recovery_window_days),
        "purge_after": purge_after,
        "confirmation_phrase": required_confirmation_phrase(normalized_scope),
        "can_request": bool(workspace_items),
        "affected_workspace_count": len(workspace_items),
        "affected_workspaces": workspace_items,
        "totals": totals,
        "will_delete": [
            "workspace files",
            "workspace backups",
            "encrypted workspace secrets",
            "imports and import reports",
            "Copilot conversations",
            "saved simulations and planning artifacts",
            "portfolio review packets",
            "financial connection metadata and observed holdings",
        ],
        "will_retain": [
            "minimal control-plane deletion request",
            "minimal audit events",
            "hosted identity provider account unless deleted by the provider",
        ],
        "warnings": warnings,
    }


def serialize_deletion_request(request: Any) -> dict[str, Any]:
    payload = asdict(request)
    return payload


class AccountDataDeletionPurgeError(RuntimeError):
    pass


class AccountDataDeletionPurgeWorker:
    def __init__(
        self,
        *,
        control_plane: ControlPlaneStore,
        workspace_service_factory: WorkspaceServiceFactory,
    ):
        self.control_plane = control_plane
        self.workspace_service_factory = workspace_service_factory

    def purge_due(self, *, due_at: str | None = None, limit: int = 20) -> dict[str, Any]:
        started_at = utc_now_iso()
        requests = self.control_plane.list_pending_account_data_deletion_requests(
            due_at=due_at or utc_now_iso(),
        )[: max(1, limit)]
        items = []
        for request in requests:
            items.append(self.purge_request(request))
        return {
            "ok": all(item.get("status") == "completed" for item in items),
            "started_at": started_at,
            "completed_at": utc_now_iso(),
            "request_count": len(items),
            "items": items,
        }

    def purge_request(self, request: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "request_id": request.id,
            "scope": request.scope,
            "started_at": utc_now_iso(),
            "workspace_count": 0,
            "workspaces": [],
            "deleted_paths": [],
            "skipped_paths": [],
            "file_count": 0,
            "size_bytes": 0,
            "backup_archives_pruned": 0,
            "secrets_shredded": 0,
        }
        try:
            if request.status != "pending":
                raise AccountDataDeletionPurgeError("Only pending deletion requests can be purged")
            workspaces = self.control_plane.workspaces_for_account_data_deletion_request(
                request_id=request.id,
            )
            if not workspaces:
                raise AccountDataDeletionPurgeError("Deletion request has no workspace records to purge")
            for workspace in workspaces:
                workspace_result = self._purge_workspace(workspace)
                result["workspaces"].append(workspace_result)
                result["deleted_paths"].extend(workspace_result["deleted_paths"])
                result["skipped_paths"].extend(workspace_result["skipped_paths"])
                result["file_count"] += workspace_result["file_count"]
                result["size_bytes"] += workspace_result["size_bytes"]
                result["backup_archives_pruned"] += workspace_result["backup_archives_pruned"]
                result["secrets_shredded"] += workspace_result["secrets_shredded"]
            result["workspace_count"] = len(workspaces)
            result["completed_at"] = utc_now_iso()
            completed = self.control_plane.complete_account_data_deletion_request(
                request_id=request.id,
                result=result,
            )
            result["status"] = completed.status
            return result
        except Exception as exc:
            result["completed_at"] = utc_now_iso()
            if "Connected institutions must be removed remotely" in str(exc):
                # Revocation is retryable and the workspace secrets must stay
                # intact. Leave the request pending so a later worker pass can
                # complete after provider cleanup succeeds.
                result["status"] = "pending"
                result["failure_reason"] = str(exc)
                return result
            result["status"] = "failed"
            result["failure_reason"] = str(exc)
            self.control_plane.fail_account_data_deletion_request(
                request_id=request.id,
                failure_reason=str(exc),
                result=result,
            )
            return result

    def _purge_workspace(self, workspace: WorkspaceRecord) -> dict[str, Any]:
        paths = self.workspace_service_factory.paths_for_record(workspace)
        root = paths.root.resolve()
        _assert_safe_workspace_root(root)
        indexed_connections = (
            self.control_plane.count_financial_connection_indexes_for_workspace(
                workspace_id=workspace.id
            )
        )
        if indexed_connections:
            raise AccountDataDeletionPurgeError(
                "Connected institutions must be removed remotely before workspace secrets are shredded"
            )
        before = _path_stats(root)
        backup_archives = _backup_archive_count(paths.backup_archive_dir)
        secrets_shredded = _shred_workspace_secrets(paths.secrets_path)
        result = {
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "workspace_type": workspace.workspace_type,
            "storage_path": str(root),
            "deleted_paths": [],
            "skipped_paths": [],
            "file_count": int(before["file_count"]),
            "size_bytes": int(before["size_bytes"]),
            "backup_archives_pruned": backup_archives,
            "secrets_shredded": secrets_shredded,
        }
        if root.exists():
            if root.is_dir():
                shutil.rmtree(root)
            else:
                root.unlink()
            result["deleted_paths"].append(str(root))
        else:
            result["skipped_paths"].append(str(root))
        return result


def _normalize_scope(scope: str) -> str:
    normalized = str(scope or "workspace").strip().lower()
    if normalized not in {"workspace", "household", "account"}:
        raise ValueError("Deletion scope must be workspace, household, or account")
    return normalized


def _workspaces_for_scope(
    *,
    control_plane: ControlPlaneStore,
    context: RequestContext,
    scope: str,
) -> list[WorkspaceRecord]:
    if scope == "workspace":
        workspace, _role = control_plane.get_workspace_for_user(
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        return [workspace]
    return [
        workspace
        for workspace in control_plane.list_workspaces_for_user(context.user_id)
        if workspace.organization_id == context.organization_id
    ]


def _workspace_preview_item(
    *,
    workspace_service_factory: WorkspaceServiceFactory,
    workspace: WorkspaceRecord,
) -> dict[str, Any]:
    paths = workspace_service_factory.paths_for_record(workspace)
    categories = [
        _category("profile", "Profile", [paths.profile_path]),
        _category("portfolio", "Portfolio", [paths.portfolio_dir]),
        _category(
            "financial_connections",
            "Financial connections",
            [paths.financial_connections_dir],
        ),
        _category("snapshots", "Snapshots", [paths.snapshot_dir]),
        _category("simulations", "Simulations", [paths.plans_dir]),
        _category("recommendations", "Recommendations", [paths.recommendations_path]),
        _category("copilot_conversations", "Copilot conversations", [paths.conversation_dir]),
        _category("context_storage", "Context storage", [paths.durable_storage_dir]),
        _category(
            "imports",
            "Imports",
            [
                paths.import_inbox_dir,
                paths.import_archive_dir,
                paths.import_workbench_dir,
                paths.import_reports_dir,
            ],
        ),
        _category("reports", "Reports", [paths.portfolio_review_packet_dir]),
        _category("today", "Today review", [paths.today_review_checkpoint_path]),
        _category("settings_and_secrets", "Settings and secrets", [paths.settings_path, paths.secrets_path]),
        _backup_category(paths.backup_archive_dir),
    ]
    secret_keys = _secret_keys(paths.secrets_path)
    financial_connection_index_count = (
        workspace_service_factory.control_plane.count_financial_connection_indexes_for_workspace(
            workspace_id=workspace.id
        )
    )
    totals = _sum_categories(categories)
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "status": workspace.status,
        "storage_mode": "file",
        "storage_path": str(workspace.storage_path),
        "categories": categories,
        "secret_count": len(secret_keys),
        "secret_keys": secret_keys,
        "financial_connection_index_count": financial_connection_index_count,
        **totals,
    }


def _category(category_id: str, label: str, paths: list[Path]) -> dict[str, Any]:
    file_count = 0
    size_bytes = 0
    existing_paths = 0
    for path in paths:
        stats = _path_stats(path)
        file_count += stats["file_count"]
        size_bytes += stats["size_bytes"]
        if stats["exists"]:
            existing_paths += 1
    return {
        "id": category_id,
        "label": label,
        "file_count": file_count,
        "size_bytes": size_bytes,
        "exists": existing_paths > 0,
    }


def _backup_category(backup_dir: Path) -> dict[str, Any]:
    archive_paths = []
    if backup_dir.exists():
        archive_paths = sorted(backup_dir.glob(f"{BACKUP_ARCHIVE_PREFIX}*{BACKUP_ARCHIVE_SUFFIX}"))
    size_bytes = sum(path.stat().st_size for path in archive_paths if path.is_file())
    return {
        "id": "backups",
        "label": "Backups",
        "file_count": len(archive_paths),
        "size_bytes": size_bytes,
        "exists": bool(archive_paths),
        "backup_archive_count": len(archive_paths),
    }


def _backup_archive_count(backup_dir: Path) -> int:
    if not backup_dir.exists():
        return 0
    return sum(1 for path in backup_dir.glob(f"{BACKUP_ARCHIVE_PREFIX}*{BACKUP_ARCHIVE_SUFFIX}") if path.is_file())


def _path_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "file_count": 0, "size_bytes": 0}
    if path.is_file():
        return {"exists": True, "file_count": 1, "size_bytes": path.stat().st_size}
    file_count = 0
    size_bytes = 0
    for child in path.rglob("*"):
        if child.is_file():
            file_count += 1
            size_bytes += child.stat().st_size
    return {"exists": True, "file_count": file_count, "size_bytes": size_bytes}


def _secret_keys(secrets_path: Path) -> list[str]:
    if not secrets_path.exists():
        return []
    try:
        payload = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    secrets = payload.get("secrets")
    if not isinstance(secrets, dict):
        return []
    return sorted(str(key) for key in secrets)


def _shred_workspace_secrets(secrets_path: Path) -> int:
    secret_keys = _secret_keys(secrets_path)
    if not secrets_path.exists():
        return 0
    secrets_path.write_text(
        json.dumps({"schema_version": 1, "secrets": {}, "shredded_at": utc_now_iso()}, indent=2),
        encoding="utf-8",
    )
    return len(secret_keys)


def _assert_safe_workspace_root(path: Path) -> None:
    resolved = path.resolve()
    if str(resolved) in {"", "/", "."}:
        raise AccountDataDeletionPurgeError(f"Unsafe workspace path: {resolved}")
    forbidden = {
        Path.home().resolve(),
        Path.cwd().resolve(),
        Path("/tmp").resolve(),
        Path("/private/tmp").resolve(),
        Path("/var").resolve(),
        Path("/private/var").resolve(),
    }
    if resolved in forbidden:
        raise AccountDataDeletionPurgeError(f"Refusing to purge unsafe workspace path: {resolved}")
    if len(resolved.parts) < 4:
        raise AccountDataDeletionPurgeError(f"Workspace path is too broad to purge: {resolved}")


def _sum_categories(categories: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "file_count": sum(int(category.get("file_count") or 0) for category in categories),
        "size_bytes": sum(int(category.get("size_bytes") or 0) for category in categories),
        "backup_archive_count": sum(int(category.get("backup_archive_count") or 0) for category in categories),
    }


def _sum_workspace_items(workspaces: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "workspace_count": len(workspaces),
        "file_count": sum(int(workspace.get("file_count") or 0) for workspace in workspaces),
        "size_bytes": sum(int(workspace.get("size_bytes") or 0) for workspace in workspaces),
        "backup_archive_count": sum(int(workspace.get("backup_archive_count") or 0) for workspace in workspaces),
        "secret_count": sum(int(workspace.get("secret_count") or 0) for workspace in workspaces),
        "financial_connection_index_count": sum(
            int(workspace.get("financial_connection_index_count") or 0)
            for workspace in workspaces
        ),
    }
