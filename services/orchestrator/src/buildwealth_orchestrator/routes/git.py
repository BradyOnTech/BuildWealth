"""Git routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_git_policy",
    "update_git_policy",
    "initialize_git_repository",
    "get_git_status",
    "get_git_history",
    "get_git_diff",
    "get_git_restore_preview",
    "apply_git_restore",
    "create_git_checkpoint",
    "get_git_autogit_state",
    "run_due_git_autogit",
    "get_git_activity",
    "cleanup_git_activity",
    "connect_git_remote",
    "push_git_remote",
    "pull_git_remote",
]


@router.get("/api/git/policy", response_model=m.GitPolicyResponse)
def get_git_policy(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitPolicyResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    return m.GitPolicyResponse.model_validate(m._git_policy(resolved_services))


@router.put("/api/git/policy", response_model=m.GitPolicyResponse)
def update_git_policy(
    request: m.GitPolicyUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitPolicyResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m.git_integration_settings_store_for_workspace(resolved_services).save(
        request.model_dump(exclude_none=True)
    )
    return m.GitPolicyResponse.model_validate(policy)


@router.post("/api/git/init", response_model=m.GitInitResponse)
def initialize_git_repository(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitInitResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m._git_policy(resolved_services)
    try:
        result = m._git_checkpoint_service(policy, services=resolved_services).initialize(m._git_workspace_policy(policy))
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._git_activity_store(resolved_services).record(
        event_type="repository_initialized",
        title="Git repository initialized",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "initialized"),
        metadata={"workspace_dir": result.get("workspace_dir")},
    )
    return m.GitInitResponse.model_validate(result)


@router.get("/api/git/status", response_model=m.GitStatusResponse)
def get_git_status(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitStatusResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    policy = m._git_policy(resolved_services)
    try:
        status = m._git_repository_service(policy, services=resolved_services).status()
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.GitStatusResponse.model_validate(status)


@router.get("/api/git/history", response_model=m.GitHistoryResponse)
def get_git_history(
    limit: int = 20,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitHistoryResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    policy = m._git_policy(resolved_services)
    try:
        commits = m._git_repository_service(policy, services=resolved_services).history(limit=limit)
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.GitHistoryResponse.model_validate({"commits": commits})


@router.get("/api/git/diff", response_model=m.GitDiffResponse)
def get_git_diff(
    ref: str | None = None,
    path: str | None = None,
    max_chars: int = 200_000,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitDiffResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    policy = m._git_policy(resolved_services)
    try:
        diff = m._git_repository_service(policy, services=resolved_services).diff(
            ref=ref,
            path=path,
            max_chars=max_chars,
        )
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.GitDiffResponse.model_validate(diff)


@router.get("/api/git/restore-preview", response_model=m.GitRestorePreviewResponse)
def get_git_restore_preview(
    ref: str,
    path: str | None = None,
    max_chars: int = 120_000,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitRestorePreviewResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    policy = m._git_policy(resolved_services)
    try:
        m._versioned_workspace_service(policy, services=resolved_services).materialize(m._git_workspace_policy(policy))
        preview = m._git_repository_service(policy, services=resolved_services).restore_preview(
            ref=ref,
            path=path,
            max_chars=max_chars,
        )
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    token = m._git_restore_preview_token_store(resolved_services).create(preview=preview)
    preview["preview_token"] = token["token"]
    preview["preview_expires_at"] = token["expires_at"]
    m._git_activity_store(resolved_services).record(
        event_type="restore_preview",
        title="Restore preview generated",
        message=str(preview.get("message") or ""),
        status=str(preview.get("status") or "ok"),
        ref=preview.get("ref"),
        paths=[item.get("path") for item in preview.get("files", []) if isinstance(item, dict)],
        metadata={
            "path": preview.get("path"),
            "total_files": preview.get("total_files"),
            "read_only": preview.get("read_only"),
        },
    )
    return m.GitRestorePreviewResponse.model_validate(preview)


@router.post("/api/git/restore-apply", response_model=m.GitRestoreApplyResponse)
def apply_git_restore(
    request: m.GitRestoreApplyRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitRestoreApplyResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m._git_policy(resolved_services)
    try:
        if request.preview_token:
            token_store = m._git_restore_preview_token_store(resolved_services)
            token_payload = token_store.get(request.preview_token)
            preview_path = token_payload.get("path") if isinstance(token_payload, dict) else None
            m._versioned_workspace_service(policy, services=resolved_services).materialize(m._git_workspace_policy(policy))
            current_preview = m._git_repository_service(policy, services=resolved_services).restore_preview(
                ref=request.ref,
                path=preview_path,
                max_chars=120_000,
            )
            token_store.validate(
                token=request.preview_token,
                ref=request.ref,
                paths=request.paths,
                current_preview=current_preview,
            )
        result = m._git_restore_apply_service(policy, services=resolved_services).apply(
            ref=request.ref,
            paths=request.paths,
            confirmation=request.confirmation,
            rationale=request.rationale,
            create_checkpoint_before_apply=request.create_checkpoint_before_apply,
            create_checkpoint_after_apply=request.create_checkpoint_after_apply,
        )
    except (m.GitRepositoryError, m.GitRestoreApplyError, m.GitRestorePreviewTokenError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._git_activity_store(resolved_services).record(
        event_type="restore_apply",
        title="Restore apply completed",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "applied"),
        ref=result.get("ref"),
        paths=[item.get("path") for item in result.get("files", []) if isinstance(item, dict)],
        metadata={
            "applied_files": result.get("applied_files"),
            "before_checkpoint": (result.get("before_checkpoint") or {}).get("commit"),
            "after_checkpoint": (result.get("after_checkpoint") or {}).get("commit"),
        },
    )
    return m.GitRestoreApplyResponse.model_validate(result)


@router.post("/api/git/checkpoint", response_model=m.GitCheckpointResponse)
def create_git_checkpoint(
    request: m.GitCheckpointRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitCheckpointResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m._git_policy(resolved_services)
    try:
        result = m._git_checkpoint_service(policy, services=resolved_services).checkpoint(
            policy=m._git_workspace_policy(policy),
            event_type=request.event_type,
            message=request.message,
        )
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._git_activity_store(resolved_services).record(
        event_type="checkpoint",
        title=result.get("commit", {}).get("message") if isinstance(result.get("commit"), dict) else "Git checkpoint",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "ok"),
        ref=(result.get("commit") or {}).get("hash") if isinstance(result.get("commit"), dict) else None,
        metadata={
            "files_written": result.get("files_written"),
            "files_removed": result.get("files_removed"),
            "sections": result.get("sections"),
        },
    )
    return m.GitCheckpointResponse.model_validate(result)


@router.get("/api/git/autogit", response_model=m.GitAutoGitStateResponse)
def get_git_autogit_state(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitAutoGitStateResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    policy = m._git_policy(resolved_services)
    state = m._git_autogit_service(policy, services=resolved_services).state(policy=policy)
    return m.GitAutoGitStateResponse.model_validate(state)


@router.post("/api/git/autogit/run-due", response_model=m.GitAutoGitStateResponse)
def run_due_git_autogit(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitAutoGitStateResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    state = m._run_due_autogit(resolved_services)
    return m.GitAutoGitStateResponse.model_validate(state)


@router.get("/api/git/activity", response_model=m.GitActivityResponse)
def get_git_activity(
    limit: int = 50,
    event_type: str | None = None,
    status: str | None = None,
    ref: str | None = None,
    search: str | None = None,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitActivityResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    result = m._git_activity_store(resolved_services).query(
        limit=limit,
        event_type=event_type,
        status=status,
        ref=ref,
        search=search,
    )
    return m.GitActivityResponse.model_validate(result)


@router.post("/api/git/activity/cleanup", response_model=m.GitActivityCleanupResponse)
def cleanup_git_activity(
    request: m.GitActivityCleanupRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitActivityCleanupResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        result = m._git_activity_store(resolved_services).cleanup(
            dry_run=request.dry_run,
            max_events=request.max_events,
            max_age_days=request.max_age_days,
            include_protected=request.include_protected,
            export_confirmed=request.export_confirmed,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.GitActivityCleanupResponse.model_validate(result)


@router.post("/api/git/remote/connect", response_model=m.GitRemoteOperationResponse)
def connect_git_remote(
    request: m.GitRemoteConnectRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitRemoteOperationResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m._git_policy(resolved_services)
    try:
        result = m._git_repository_service(policy, services=resolved_services).connect_remote(
            remote_url=request.remote_url,
            name=request.remote_name,
        )
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._git_activity_store(resolved_services).record(
        event_type="remote_connect",
        title="Git remote connected",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "connected"),
        metadata={
            "remote_name": result.get("remote_name"),
            "remote": result.get("remote"),
        },
    )
    return m.GitRemoteOperationResponse.model_validate(result)


@router.post("/api/git/push", response_model=m.GitRemoteOperationResponse)
def push_git_remote(
    request: m.GitRemoteOperationRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitRemoteOperationResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m._git_policy(resolved_services)
    try:
        result = m._git_repository_service(policy, services=resolved_services).push(remote_name=request.remote_name)
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._git_activity_store(resolved_services).record(
        event_type="remote_push",
        title="Git push completed",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "pushed"),
        metadata={
            "remote_name": result.get("remote_name"),
            "remote": result.get("remote"),
        },
    )
    return m.GitRemoteOperationResponse.model_validate(result)


@router.post("/api/git/pull", response_model=m.GitRemoteOperationResponse)
def pull_git_remote(
    request: m.GitRemoteOperationRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitRemoteOperationResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = m._git_policy(resolved_services)
    try:
        result = m._git_repository_service(policy, services=resolved_services).pull(remote_name=request.remote_name)
    except m.GitRepositoryError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._git_activity_store(resolved_services).record(
        event_type="remote_pull",
        title="Git pull completed",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "pulled"),
        metadata={
            "remote_name": result.get("remote_name"),
            "remote": result.get("remote"),
        },
    )
    return m.GitRemoteOperationResponse.model_validate(result)
