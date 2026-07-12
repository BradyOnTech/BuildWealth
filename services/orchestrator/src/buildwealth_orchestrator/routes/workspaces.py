"""Workspaces routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "list_workspaces",
    "current_workspace",
    "select_workspace",
    "reset_demo_workspace",
]


@router.get("/api/workspaces")
def list_workspaces(context: m.RequestContext = m.Depends(m.get_request_context)) -> dict[str, m.Any]:
    workspaces = m.control_plane_store.list_workspaces_for_user(context.user_id)
    return {
        "active_workspace_id": context.workspace_id,
        "items": [
            {
                "id": workspace.id,
                "name": workspace.name,
                "workspace_type": workspace.workspace_type,
                "is_demo": workspace.workspace_type == "demo",
            }
            for workspace in workspaces
        ],
    }


@router.get("/api/workspaces/current")
def current_workspace(context: m.RequestContext = m.Depends(m.get_request_context)) -> dict[str, m.Any]:
    workspace, _role = m.control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
    )
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "is_demo": workspace.workspace_type == "demo",
        "role": context.role,
        "permissions": sorted(context.permissions),
    }


@router.post("/api/workspaces/{workspace_id}/select")
def select_workspace(
    workspace_id: str,
    request: m.Request,
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    workspace, role = m.control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=workspace_id,
    )
    m.control_plane_store.select_workspace_for_session(
        token=request.cookies.get(m.settings.auth_session_cookie_name) or "",
        workspace_id=workspace.id,
    )
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "is_demo": workspace.workspace_type == "demo",
        "role": role,
    }


@router.post("/api/workspaces/{workspace_id}/demo/reset")
def reset_demo_workspace(
    workspace_id: str,
    request: m.Request,
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(context, "demo.reset")
    workspace, _role = m.control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=workspace_id,
    )
    if workspace.workspace_type != "demo":
        raise m.HTTPException(status_code=400, detail="Only demo workspaces can be reset")
    paths = m.workspace_service_factory.paths_for_record(workspace)
    if paths.root.exists():
        m.shutil.rmtree(paths.root)
    paths.root.mkdir(parents=True, exist_ok=True)
    try:
        summary = m._seed_demo_workspace_data(paths.root)
    except Exception as exc:
        raise m.HTTPException(status_code=500, detail=f"Demo workspace reset failed: {exc}") from exc
    m.control_plane_store.record_audit_event(
        action="demo_workspace.reset",
        actor_user_id=context.user_id,
        organization_id=context.organization_id,
        workspace_id=workspace.id,
        target_type="workspace",
        target_id=workspace.id,
    )
    return {
        "ok": True,
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "workspace_type": workspace.workspace_type,
            "is_demo": True,
        },
        "summary": summary,
    }
