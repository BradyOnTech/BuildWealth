from __future__ import annotations

import json
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
    }
