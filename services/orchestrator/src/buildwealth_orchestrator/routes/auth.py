"""Auth routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "auth_config",
    "hosted_auth_readiness",
    "hosted_login",
    "hosted_callback",
    "register_owner",
    "login",
    "logout",
    "logout_all",
    "hosted_logout",
    "auth_session",
]


@router.get("/api/auth/config")
def auth_config() -> dict[str, m.Any]:
    hosted_enabled = m._hosted_auth_enabled()
    return {
        "auth_mode": m._auth_mode(),
        "local_auth_enabled": m._local_auth_enabled(),
        "hosted_auth_enabled": hosted_enabled,
        "hosted_provider_name": m.hosted_identity_provider.provider_name,
        "hosted_login_url": "/api/auth/hosted/login" if hosted_enabled else "",
        "hosted_logout_url": "/api/auth/hosted/logout" if hosted_enabled and m._hosted_logout_redirect_url() else "",
        "id_token_validation_required": bool(getattr(m.settings, "auth_oidc_require_id_token", True)),
        "mfa_required": bool(getattr(m.settings, "auth_oidc_require_mfa", False)),
        "password_reset_managed_by_provider": hosted_enabled,
        "mfa_managed_by_provider": hosted_enabled,
        "passkeys_managed_by_provider": hosted_enabled,
        "account_management_url": str(m.settings.auth_account_management_url or "").strip(),
        "password_reset_url": str(m.settings.auth_password_reset_url or "").strip(),
        "mfa_enrollment_url": str(m.settings.auth_mfa_enrollment_url or "").strip(),
        "passkey_enrollment_url": str(m.settings.auth_passkey_enrollment_url or "").strip(),
    }


@router.get("/api/auth/hosted/readiness")
async def hosted_auth_readiness() -> dict[str, m.Any]:
    return await m.hosted_identity_provider.readiness_report()


@router.get("/api/auth/hosted/login")
async def hosted_login(redirect_to: str = "") -> m.Response:
    if not m._hosted_auth_enabled():
        raise m.HTTPException(status_code=404, detail="Hosted identity is not configured")
    code_verifier = m.generate_code_verifier()
    nonce = m.generate_nonce()
    flow = m.control_plane_store.create_hosted_login_flow(
        provider=m.hosted_identity_provider.provider_name,
        code_verifier=code_verifier,
        nonce=nonce,
        redirect_to=m._safe_post_login_redirect(redirect_to),
    )
    try:
        authorization_url = await m.hosted_identity_provider.authorization_url(
            state=flow["state"],
            nonce=nonce,
            code_challenge=m.code_challenge_for(code_verifier),
        )
    except (m.HostedIdentityConfigError, m.httpx.HTTPError) as exc:
        raise m.HTTPException(status_code=502, detail=f"Hosted identity login is unavailable: {exc}") from exc
    return m.RedirectResponse(url=authorization_url, status_code=307)


@router.get("/api/auth/hosted/callback")
async def hosted_callback(
    request: m.Request,
    response: m.Response,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
) -> m.Response:
    if not m._hosted_auth_enabled():
        return m._auth_error_redirect("Hosted identity is not configured")
    if error:
        detail = error_description or error
        return m._auth_error_redirect(f"Hosted identity rejected sign-in: {detail}")
    if not code or not state:
        return m._auth_error_redirect("Hosted identity callback is missing code or state")
    try:
        flow = m.control_plane_store.consume_hosted_login_flow(
            provider=m.hosted_identity_provider.provider_name,
            state=state,
        )
        profile = await m.hosted_identity_provider.exchange_code_for_profile(
            code=code,
            code_verifier=flow["code_verifier"],
            expected_nonce=flow["nonce"],
        )
        user = m.control_plane_store.upsert_hosted_owner_user(
            provider=profile.provider,
            subject=profile.subject,
            email=profile.email,
            display_name=profile.display_name,
            email_verified=profile.email_verified,
            mfa_enabled=profile.mfa_enabled,
            workspace_root_dir=m.settings.workspace_root_dir,
        )
    except (m.AuthenticationError, m.HostedIdentityExchangeError) as exc:
        return m._auth_error_redirect(str(exc))
    except (m.HostedIdentityConfigError, m.httpx.HTTPError) as exc:
        return m._auth_error_redirect(f"Hosted identity callback failed: {exc}")

    workspace = m.control_plane_store.default_workspace_for_user(str(user["id"]))
    session = m.control_plane_store.create_session(
        user_id=str(user["id"]),
        active_workspace_id=workspace.id,
        ttl_days=m.settings.auth_session_days,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response = m.RedirectResponse(url=flow["redirect_to"], status_code=307)
    response.set_cookie(
        m.settings.auth_session_cookie_name,
        session["session_token"],
        **m._session_cookie_kwargs(),
    )
    return response


@router.post("/api/auth/register")
def register_owner(request: m.Request, response: m.Response, payload: dict[str, m.Any]) -> dict[str, m.Any]:
    if not m._local_auth_enabled():
        raise m.HTTPException(status_code=403, detail="Local registration is disabled")
    m._enforce_auth_rate_limit(
        request,
        key=f"register:ip:{m._client_ip(request)}",
        limit=5,
        window_seconds=3600,
        action="register",
    )
    # A private instance registers its owner on first visit and then closes
    # the door: strangers who find the URL must not get accounts. Households
    # that want more members set AUTH_ALLOW_OPEN_REGISTRATION=true.
    if (
        m._auth_mode() == "secure"
        and not m.settings.auth_allow_open_registration
        and m.control_plane_store.count_active_local_users() > 0
    ):
        raise m.HTTPException(status_code=403, detail="Registration is closed on this instance")
    try:
        user = m.control_plane_store.create_owner_user(
            email=str(payload.get("email") or ""),
            password=str(payload.get("password") or ""),
            display_name=str(payload.get("display_name") or ""),
            workspace_root_dir=m.settings.workspace_root_dir,
        )
    except m.sqlite3.IntegrityError as exc:
        raise m.HTTPException(status_code=409, detail="User already exists") from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    workspace = m.control_plane_store.default_workspace_for_user(str(user["id"]))
    session = m.control_plane_store.create_session(
        user_id=str(user["id"]),
        active_workspace_id=workspace.id,
        ttl_days=m.settings.auth_session_days,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        m.settings.auth_session_cookie_name,
        session["session_token"],
        **m._session_cookie_kwargs(),
    )
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or "",
            "auth_provider": user.get("auth_provider") or "local",
            "mfa_enabled": bool(user.get("mfa_enabled")),
        },
        "workspace_id": workspace.id,
        "csrf_token": session["csrf_token"],
    }


@router.post("/api/auth/login")
def login(request: m.Request, response: m.Response, payload: dict[str, m.Any]) -> dict[str, m.Any]:
    if not m._local_auth_enabled():
        raise m.HTTPException(status_code=403, detail="Local password login is disabled")
    email = str(payload.get("email") or "")
    email_key = f"login:email:{m.control_plane_store.normalize_email(email)}"
    m._enforce_auth_rate_limit(
        request,
        key=f"login:ip:{m._client_ip(request)}",
        limit=10,
        window_seconds=60,
        action="login",
    )
    # Per-account window counts attempts and is cleared on success, so only
    # sustained failures accumulate — credential stuffing hits this wall.
    m._enforce_auth_rate_limit(
        request,
        key=email_key,
        limit=8,
        window_seconds=900,
        action="login",
    )
    try:
        user = m.control_plane_store.authenticate_local(
            email=email,
            password=str(payload.get("password") or ""),
        )
    except m.AuthenticationError as exc:
        m._audit_event(
            "auth.login_failed",
            outcome="denied",
            target_type="user_email",
            target_id=m.control_plane_store.normalize_email(email),
            metadata_json=m.json.dumps({"ip": m._client_ip(request)}),
        )
        raise m.HTTPException(status_code=401, detail=str(exc)) from exc
    m.auth_rate_limiter.clear(email_key)
    workspace = m.control_plane_store.default_workspace_for_user(str(user["id"]))
    session = m.control_plane_store.create_session(
        user_id=str(user["id"]),
        active_workspace_id=workspace.id,
        ttl_days=m.settings.auth_session_days,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        m.settings.auth_session_cookie_name,
        session["session_token"],
        **m._session_cookie_kwargs(),
    )
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or "",
            "auth_provider": user.get("auth_provider") or "local",
            "mfa_enabled": bool(user.get("mfa_enabled")),
        },
        "workspace_id": workspace.id,
        "csrf_token": session["csrf_token"],
    }


@router.post("/api/auth/logout")
def logout(request: m.Request, response: m.Response) -> dict[str, m.Any]:
    m.control_plane_store.revoke_session(request.cookies.get(m.settings.auth_session_cookie_name) or "")
    response.delete_cookie(m.settings.auth_session_cookie_name, path="/")
    return {"ok": True, "redirect_to": m._hosted_logout_redirect_url() if m._hosted_auth_enabled() else ""}


@router.post("/api/auth/logout-all")
def logout_all(
    request: m.Request,
    response: m.Response,
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    """Sign out everywhere: revoke every live session for the current user,
    including this one. The control for a lost device or a suspected leak."""
    m.require_csrf(request)
    revoked = m.control_plane_store.revoke_all_sessions_for_user(context.user_id)
    response.delete_cookie(m.settings.auth_session_cookie_name, path="/")
    m._audit_event(
        "auth.logout_all",
        actor_user_id=context.user_id,
        metadata_json=m.json.dumps({"revoked_sessions": revoked}),
    )
    return {"ok": True, "revoked_sessions": revoked, "requires_login": True}


@router.get("/api/auth/hosted/logout")
def hosted_logout(request: m.Request) -> m.Response:
    m.control_plane_store.revoke_session(request.cookies.get(m.settings.auth_session_cookie_name) or "")
    redirect_to = m._hosted_logout_redirect_url() or "/v2"
    response = m.RedirectResponse(url=redirect_to, status_code=307)
    response.delete_cookie(m.settings.auth_session_cookie_name, path="/")
    return response


@router.get("/api/auth/session")
def auth_session(
    request: m.Request,
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    workspace, _role = m.control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
    )
    user = m.control_plane_store.get_user(context.user_id)
    payload = {
        "authenticated": True,
        "auth_mode": context.auth_mode,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or "",
            "auth_provider": user.get("auth_provider") or "local",
            "mfa_enabled": bool(user.get("mfa_enabled")),
        },
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "workspace_type": workspace.workspace_type,
            "is_demo": context.is_demo_workspace,
        },
        "role": context.role,
        "permissions": sorted(context.permissions),
    }
    session_token = request.cookies.get(m.settings.auth_session_cookie_name) or ""
    if session_token:
        try:
            payload["csrf_token"] = m.control_plane_store.rotate_csrf_token(session_token)
        except m.AuthenticationError:
            pass
    return payload
