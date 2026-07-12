"""Storage routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_durable_storage_status",
    "migrate_durable_storage",
    "rollback_durable_storage",
    "list_backups",
    "create_backup",
    "restore_backup",
    "get_storage_protection_status",
    "update_storage_protection_policy",
    "apply_storage_protection",
]


@router.get("/api/storage/durable/status", response_model=m.DurableStorageStatusResponse)
def get_durable_storage_status(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.DurableStorageStatusResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    return m.DurableStorageStatusResponse.model_validate(
        m.durable_storage_service_for_workspace(resolved_services).get_status()
    )


@router.post("/api/storage/durable/migrate", response_model=m.DurableStorageMigrationResponse)
def migrate_durable_storage(
    request: m.DurableStorageMigrationRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.DurableStorageMigrationResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = m.durable_storage_service_for_workspace(resolved_services).run_upgrade(
            run_rollback_check=request.run_rollback_check
        )
    except m.DurableStorageMigrationError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.DurableStorageMigrationResponse.model_validate(report)


@router.post("/api/storage/durable/rollback", response_model=m.DurableStorageRollbackResponse)
def rollback_durable_storage(
    request: m.DurableStorageRollbackRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.DurableStorageRollbackResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = m.durable_storage_service_for_workspace(resolved_services).rollback_latest_migration(
            migration_id=request.migration_id
        )
    except m.DurableStorageMigrationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except m.DurableStorageMigrationError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.DurableStorageRollbackResponse.model_validate(report)


@router.get("/api/storage/backups", response_model=m.BackupListResponse)
def list_backups(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.BackupListResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    return m.BackupListResponse.model_validate(
        m.backup_restore_service_for_workspace(resolved_services).list_backups()
    )


@router.post("/api/storage/backups", response_model=m.BackupCreateResponse)
def create_backup(
    request: m.BackupCreateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.BackupCreateResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = m.backup_restore_service_for_workspace(resolved_services).create_backup(reason=request.reason)
    except m.BackupRestoreError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.BackupCreateResponse.model_validate(report)


@router.post("/api/storage/backups/restore", response_model=m.BackupRestoreResponse)
def restore_backup(
    request: m.BackupRestoreRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.BackupRestoreResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = m.backup_restore_service_for_workspace(resolved_services).restore_backup(
            backup_id=request.backup_id,
            create_pre_restore_backup=request.create_pre_restore_backup,
        )
    except m.BackupNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except m.BackupRestoreError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.BackupRestoreResponse.model_validate(report)


@router.get("/api/storage/protection/status", response_model=m.StorageProtectionStatusResponse)
def get_storage_protection_status(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.StorageProtectionStatusResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    return m.StorageProtectionStatusResponse.model_validate(
        m.data_protection_service_for_workspace(resolved_services).get_status()
    )


@router.put("/api/storage/protection/policy", response_model=m.StorageProtectionPolicyResponse)
def update_storage_protection_policy(
    request: m.StorageProtectionPolicyUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.StorageProtectionPolicyResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        policy = m.data_protection_service_for_workspace(resolved_services).update_policy(
            request.model_dump(exclude_none=True)
        )
    except m.DataProtectionError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("protection_policy_updated")
    return m.StorageProtectionPolicyResponse.model_validate(policy)


@router.post("/api/storage/protection/apply", response_model=m.StorageProtectionApplyResponse)
def apply_storage_protection(
    request: m.StorageProtectionApplyRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.StorageProtectionApplyResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = m.data_protection_service_for_workspace(resolved_services).apply_protection(
            request.model_dump(exclude_none=True)
        )
    except m.DataProtectionError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.StorageProtectionApplyResponse.model_validate(report)
