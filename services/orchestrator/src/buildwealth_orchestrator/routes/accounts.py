"""Accounts routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "change_account_password",
    "export_account_bundle",
    "preview_account_data_deletion",
    "list_account_data_deletion_requests",
    "request_account_data_deletion",
    "cancel_account_data_deletion",
    "deactivate_account",
    "close_hosted_account_access",
]


@router.post("/api/account/password")
def change_account_password(
    request: m.Request,
    response: m.Response,
    payload: dict[str, m.Any],
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    try:
        m.control_plane_store.change_local_password(
            user_id=context.user_id,
            current_password=str(payload.get("current_password") or ""),
            new_password=str(payload.get("new_password") or ""),
        )
    except m.AuthenticationError as exc:
        raise m.HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    # A password change means the old credential may be compromised — every
    # session dies with it, not just this device's.
    revoked = m.control_plane_store.revoke_all_sessions_for_user(context.user_id)
    m._audit_event(
        "auth.password_changed",
        actor_user_id=context.user_id,
        metadata_json=m.json.dumps({"revoked_sessions": revoked}),
    )
    response.delete_cookie(m.settings.auth_session_cookie_name, path="/")
    return {
        "ok": True,
        "requires_login": True,
        "message": "Password changed. Sign in again on all devices.",
    }


@router.get("/api/account/export")
def export_account_bundle(context: m.RequestContext = m.Depends(m.get_request_context)) -> dict[str, m.Any]:
    m.require_permission(context, "account.export")
    return m.control_plane_store.export_account_bundle(context.user_id)


@router.get("/api/account/data-deletion/preview")
def preview_account_data_deletion(
    scope: str = "workspace",
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_permission(context, "account.delete")
    try:
        return m.build_account_data_deletion_preview(
            control_plane=m.control_plane_store,
            workspace_service_factory=m.workspace_service_factory,
            context=context,
            scope=scope,
            recovery_window_days=m.RECOVERY_WINDOW_DAYS,
        )
    except (m.AuthorizationError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/account/data-deletion/requests")
def list_account_data_deletion_requests(
    account_user: dict[str, m.Any] = m.Depends(m.get_authenticated_account_user),
) -> dict[str, m.Any]:
    requests = m.control_plane_store.list_account_data_deletion_requests_for_user(
        user_id=str(account_user["id"]),
    )
    return {"items": [m.serialize_deletion_request(request) for request in requests]}


@router.post("/api/account/data-deletion/request")
async def request_account_data_deletion(
    request: m.Request,
    payload: dict[str, m.Any],
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(context, "account.delete")
    scope = str(payload.get("scope") or "workspace").strip().lower()
    phrase = m.required_confirmation_phrase(scope)
    if str(payload.get("confirm") or "").strip().lower() != phrase:
        raise m.HTTPException(status_code=400, detail=f'Type "{phrase}" to confirm data deletion request')
    try:
        preview = m.build_account_data_deletion_preview(
            control_plane=m.control_plane_store,
            workspace_service_factory=m.workspace_service_factory,
            context=context,
            scope=scope,
            recovery_window_days=m.RECOVERY_WINDOW_DAYS,
        )
        if not preview.get("can_request"):
            raise ValueError("No active workspace data is available for deletion")
        deletion_request = m.control_plane_store.create_account_data_deletion_request(
            user_id=context.user_id,
            requested_by_user_id=context.user_id,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id if preview["scope"] == "workspace" else None,
            scope=str(preview["scope"]),
            purge_after=str(preview["purge_after"] or m.purge_after_for_recovery_window()),
            preview=preview,
        )
        connection_revocation = await m.revoke_financial_connections_for_deletion(preview)
    except m.AuthenticationError as exc:
        raise m.HTTPException(status_code=401, detail=str(exc)) from exc
    except m.AuthorizationError as exc:
        raise m.HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": (
            "Data deletion scheduled. You can cancel local deletion during the recovery window, "
            "but revoked financial connections are not restored."
        ),
        "request": m.serialize_deletion_request(deletion_request),
        "connection_revocation": connection_revocation,
    }


@router.post("/api/account/data-deletion/{request_id}/cancel")
def cancel_account_data_deletion(
    request_id: str,
    request: m.Request,
    account_user: dict[str, m.Any] = m.Depends(m.get_authenticated_account_user),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    try:
        deletion_request = m.control_plane_store.cancel_account_data_deletion_request(
            request_id=request_id,
            canceled_by_user_id=str(account_user["id"]),
        )
    except m.AuthorizationError as exc:
        raise m.HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": (
            "Data deletion canceled. Financial connections revoked when deletion was requested "
            "remain disconnected and can be connected again manually."
        ),
        "request": m.serialize_deletion_request(deletion_request),
    }


@router.delete("/api/account")
def deactivate_account(
    request: m.Request,
    response: m.Response,
    payload: dict[str, m.Any],
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(context, "account.delete")
    if str(payload.get("confirm") or "").strip().lower() != "deactivate":
        raise m.HTTPException(status_code=400, detail='Type "deactivate" to confirm account deactivation')
    try:
        m.control_plane_store.deactivate_user_account(
            user_id=context.user_id,
            current_password=str(payload.get("current_password") or ""),
        )
    except m.AuthenticationError as exc:
        raise m.HTTPException(status_code=401, detail=str(exc)) from exc
    response.delete_cookie(m.settings.auth_session_cookie_name, path="/")
    return {
        "ok": True,
        "requires_login": True,
        "message": "Account deactivated. Local workspace files were left in place for manual recovery.",
    }


@router.post("/api/account/hosted/close")
def close_hosted_account_access(
    request: m.Request,
    response: m.Response,
    payload: dict[str, m.Any],
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(context, "account.delete")
    try:
        m.control_plane_store.close_hosted_user_access(
            user_id=context.user_id,
            confirm=str(payload.get("confirm") or ""),
        )
    except m.AuthenticationError as exc:
        raise m.HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    response.delete_cookie(m.settings.auth_session_cookie_name, path="/")
    return {
        "ok": True,
        "requires_login": True,
        "message": (
            "BuildWealth access closed. Workspace files, backups, and audit records were retained "
            "under the current hosted retention policy."
        ),
    }
