"""Durable first-outcome onboarding routes."""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.onboarding_progress import OnboardingProgressStore
from buildwealth_orchestrator.services.onboarding_reset import (
    ONBOARDING_RESET_CONFIRMATION_PHRASE,
    OnboardingResetError,
    OnboardingResetService,
)


router = APIRouter()

__all__ = [
    "get_onboarding_progress",
    "preview_onboarding_reset",
    "reset_onboarding",
    "start_onboarding_progress",
    "update_onboarding_progress",
]


def _progress_store(services: m.WorkspaceServices) -> OnboardingProgressStore:
    return OnboardingProgressStore(services.paths.root / "onboarding" / "progress.json")


def _reset_service(services: m.WorkspaceServices) -> OnboardingResetService:
    return OnboardingResetService(
        data_root=services.paths.root,
        backup_dir=services.paths.backup_archive_dir,
    )


def _owner_reset_services(
    services: m.WorkspaceServices,
    *,
    http_request: m.Request | None = None,
    require_write_token: bool = False,
) -> m.WorkspaceServices:
    resolved_services = m.route_workspace_services(
        services,
        permission="account.delete",
        http_request=http_request,
        require_write_token=require_write_token,
    )
    if str(resolved_services.context.role or "").strip().lower() != "owner":
        raise m.HTTPException(
            status_code=403,
            detail="Only a household owner can reset workspace data",
        )
    if resolved_services.context.is_demo_workspace:
        raise m.HTTPException(
            status_code=400,
            detail="Use the demo workspace reset to restore demo data",
        )
    return resolved_services


@router.get("/api/onboarding/progress")
def get_onboarding_progress(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(services, permission="workspace.read")
    return _progress_store(resolved_services).get()


@router.get("/api/onboarding/reset/preview")
def preview_onboarding_reset(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = _owner_reset_services(services)
    return _reset_service(resolved_services).preview()


@router.post("/api/onboarding/reset")
def reset_onboarding(
    payload: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = _owner_reset_services(
        services,
        http_request=http_request,
        require_write_token=True,
    )
    if (
        str(payload.get("confirm") or "").strip().lower()
        != ONBOARDING_RESET_CONFIRMATION_PHRASE
    ):
        raise m.HTTPException(
            status_code=400,
            detail=f'Type "{ONBOARDING_RESET_CONFIRMATION_PHRASE}" to confirm the reset',
        )
    try:
        result = _reset_service(resolved_services).reset()
    except OnboardingResetError as exc:
        raise m.HTTPException(status_code=500, detail=str(exc)) from exc
    m._audit_event(
        "workspace.onboarding_reset",
        actor_user_id=resolved_services.context.user_id,
        organization_id=resolved_services.context.organization_id,
        workspace_id=resolved_services.context.workspace_id,
        target_type="workspace",
        target_id=resolved_services.context.workspace_id,
        metadata_json=m.json.dumps(
            {
                "backup_id": result["backup_id"],
                "files_cleared": result["files_cleared"],
                "identity_preserved": True,
            },
            sort_keys=True,
        ),
    )
    return result


@router.post("/api/onboarding/progress/start")
def start_onboarding_progress(
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="profile.write",
        http_request=http_request,
        require_write_token=True,
    )
    return _progress_store(resolved_services).start()


@router.patch("/api/onboarding/progress")
def update_onboarding_progress(
    payload: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="profile.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        return _progress_store(resolved_services).update(
            current_step=(
                str(payload["current_step"]).strip()
                if payload.get("current_step") is not None
                else None
            ),
            completed_step=(
                str(payload["completed_step"]).strip()
                if payload.get("completed_step") is not None
                else None
            ),
            skipped_step=(
                str(payload["skipped_step"]).strip()
                if payload.get("skipped_step") is not None
                else None
            ),
            complete=payload.get("complete") is True,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
