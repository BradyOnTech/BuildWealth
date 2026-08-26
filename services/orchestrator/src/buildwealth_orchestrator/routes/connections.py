"""Read-only financial-connection routes.

User routes stay behind the ordinary workspace permission and CSRF boundaries.
The Plaid webhook is the sole unauthenticated entry point and is handled below
through provider verification before any workspace is resolved.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

import buildwealth_orchestrator.main as m


router = APIRouter()


@router.get("/api/connections")
def list_financial_connections(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "connections.read")
    return m.financial_connection_service_for_workspace(services).list_connections()


@router.post("/api/connections/plaid/link-token")
async def create_plaid_link_token(
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    return await m.financial_connection_service_for_workspace(services).create_link_token(
        user_id=services.context.user_id,
    )


@router.post("/api/connections/plaid/exchange")
async def exchange_plaid_public_token(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    public_token = str(request.get("public_token") or "").strip()
    if not public_token:
        raise m.HTTPException(status_code=400, detail="public_token is required")
    institution = request.get("institution")
    if institution is not None and not isinstance(institution, dict):
        raise m.HTTPException(status_code=400, detail="institution must be an object")
    return await m.financial_connection_service_for_workspace(services).exchange_public_token(
        user_id=services.context.user_id,
        public_token=public_token,
        institution=institution,
    )


@router.get("/api/connections/{connection_id}/preview")
def get_financial_connection_preview(
    connection_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "connections.read")
    return m.financial_connection_service_for_workspace(services).get_preview(connection_id)


@router.post("/api/connections/{connection_id}/activate")
async def activate_financial_connection(
    connection_id: str,
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    accounts = request.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise m.HTTPException(status_code=400, detail="accounts must be a non-empty list")
    if not all(isinstance(account, dict) for account in accounts):
        raise m.HTTPException(status_code=400, detail="each account selection must be an object")
    return await m.financial_connection_service_for_workspace(services).activate_connection(
        connection_id=connection_id,
        accounts=accounts,
    )


@router.post("/api/connections/{connection_id}/sync")
async def sync_financial_connection(
    connection_id: str,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    return await m.financial_connection_service_for_workspace(services).sync_connection(
        connection_id=connection_id,
        trigger="manual",
    )


@router.post("/api/connections/{connection_id}/update-link-token")
async def create_financial_connection_update_link_token(
    connection_id: str,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    return await m.financial_connection_service_for_workspace(
        services
    ).create_update_link_token(
        connection_id=connection_id,
        user_id=services.context.user_id,
    )


@router.post("/api/connections/{connection_id}/disconnect-preview")
def preview_financial_connection_disconnect(
    connection_id: str,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    return m.financial_connection_service_for_workspace(services).disconnect_preview(
        connection_id
    )


@router.delete("/api/connections/{connection_id}")
async def disconnect_financial_connection(
    connection_id: str,
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "connections.write")
    retention = str(request.get("retention") or "").strip().lower()
    if retention not in {"keep_frozen", "remove_connected_data"}:
        raise m.HTTPException(
            status_code=400,
            detail="retention must be keep_frozen or remove_connected_data",
        )
    return await m.financial_connection_service_for_workspace(
        services
    ).disconnect_connection(
        connection_id=connection_id,
        retention=retention,
    )


@router.post("/api/webhooks/plaid")
async def receive_plaid_webhook(
    http_request: m.Request,
    background_tasks: BackgroundTasks,
) -> dict[str, m.Any]:
    raw_body = await http_request.body()
    verification_token = str(
        http_request.headers.get("plaid-verification") or ""
    ).strip()
    if not verification_token:
        raise m.HTTPException(status_code=400, detail="Plaid verification is required")
    result = await m.handle_plaid_webhook(
        body=raw_body,
        verification_token=verification_token,
    )
    workspace_id = result.pop("_workspace_id", None)
    connection_id = result.pop("_connection_id", None)
    event_id = result.pop("_event_id", None)
    if result.get("scheduled") and workspace_id and connection_id and event_id:
        background_tasks.add_task(
            m.process_plaid_webhook_event,
            workspace_id=workspace_id,
            connection_id=connection_id,
            event_id=event_id,
        )
    return result
