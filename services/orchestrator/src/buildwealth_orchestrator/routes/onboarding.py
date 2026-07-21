"""Durable first-outcome onboarding routes."""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.onboarding_progress import OnboardingProgressStore


router = APIRouter()

__all__ = [
    "get_onboarding_progress",
    "start_onboarding_progress",
    "update_onboarding_progress",
]


def _progress_store(services: m.WorkspaceServices) -> OnboardingProgressStore:
    return OnboardingProgressStore(services.paths.root / "onboarding" / "progress.json")


@router.get("/api/onboarding/progress")
def get_onboarding_progress(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(services, permission="workspace.read")
    return _progress_store(resolved_services).get()


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
