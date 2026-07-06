"""AUTH_MODE=secure — the private hosted-instance contract.

Password login stays enabled (no identity provider required), cookies are
Secure, CSRF is enforced, and registration closes after the first account.
"""

from __future__ import annotations

from copy import copy
from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


def _install_secure_spine(monkeypatch, tmp_path: Path) -> None:
    test_settings = copy(main.settings)
    test_settings.auth_mode = "secure"
    test_settings.auth_allow_open_registration = False
    test_settings.control_db_path = tmp_path / "control" / "control.db"
    test_settings.workspace_root_dir = tmp_path / "workspaces"
    test_settings.secret_key_path = tmp_path / "control" / "local_secret.key"

    control_plane = ControlPlaneStore(test_settings.control_db_path)
    factory = WorkspaceServiceFactory(settings=test_settings, control_plane=control_plane)

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "control_plane_store", control_plane)
    monkeypatch.setattr(main, "workspace_service_factory", factory)
    # The rate limiter is process-global; earlier tests' attempts must not
    # bleed into this spine.
    main.auth_rate_limiter.reset_all()


def test_secure_mode_full_auth_contract(monkeypatch, tmp_path: Path) -> None:
    _install_secure_spine(monkeypatch, tmp_path)

    # https base URL so the client accepts Secure cookies.
    with TestClient(main.app, base_url="https://testserver") as client:
        # No dev auto-login: everything is 401 before registration.
        assert client.get("/api/recommendations").status_code == 401
        assert client.get("/api/auth/session").status_code == 401

        config = client.get("/api/auth/config").json()
        assert config["auth_mode"] == "secure"
        assert config["local_auth_enabled"] is True
        assert config["hosted_auth_enabled"] is False

        # First visit registers the owner.
        registered = client.post(
            "/api/auth/register",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123", "display_name": "Owner"},
        )
        assert registered.status_code == 200
        csrf_token = registered.json()["csrf_token"]

        # The session cookie carries the Secure attribute.
        set_cookie = registered.headers.get("set-cookie", "")
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie

        session = client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["authenticated"] is True
        # Session reads rotate the CSRF token; the fresh one is authoritative.
        csrf_token = session.json().get("csrf_token") or csrf_token

        # CSRF is enforced on writes.
        blocked = client.put("/api/settings", json={"llm_provider": "openai"})
        assert blocked.status_code == 403
        allowed = client.put(
            "/api/settings",
            json={"llm_provider": "openai"},
            headers={"x-buildwealth-csrf-token": csrf_token},
        )
        assert allowed.status_code == 200

        # The door closes after the first account: strangers get 403.
        stranger = client.post(
            "/api/auth/register",
            json={"email": "stranger@evil.test", "password": "stranger-pass-123"},
        )
        assert stranger.status_code == 403
        assert "closed" in stranger.json()["detail"].lower()

        # Password login still works for the owner.
        fresh = TestClient(main.app, base_url="https://testserver")
        login = fresh.post(
            "/api/auth/login",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        )
        assert login.status_code == 200
        assert fresh.post(
            "/api/auth/login",
            json={"email": "owner@example.test", "password": "wrong"},
        ).status_code == 401


def test_login_rate_limit_blocks_credential_stuffing(monkeypatch, tmp_path: Path) -> None:
    _install_secure_spine(monkeypatch, tmp_path)

    with TestClient(main.app, base_url="https://testserver") as client:
        assert client.post(
            "/api/auth/register",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        ).status_code == 200

        # Sustained failures against one account hit the per-email wall.
        # (The 10/min per-IP limit already absorbed register+failures, so the
        # denial may come from either wall — both are 429 with Retry-After.)
        last = None
        for _ in range(12):
            last = client.post(
                "/api/auth/login",
                json={"email": "owner@example.test", "password": "wrong-password"},
            )
            if last.status_code == 429:
                break
        assert last is not None
        assert last.status_code == 429
        assert int(last.headers.get("retry-after", "0")) >= 1

        # The failure trail is on the audit log.
        rows = main.control_plane_store.export_account_bundle  # noqa: F841 — presence only
        import sqlite3

        connection = sqlite3.connect(main.settings.control_db_path)
        connection.row_factory = sqlite3.Row
        actions = {row["action"] for row in connection.execute("SELECT action FROM audit_events").fetchall()}
        assert "auth.login_failed" in actions
        assert "auth.rate_limited" in actions


def test_password_change_revokes_every_session(monkeypatch, tmp_path: Path) -> None:
    _install_secure_spine(monkeypatch, tmp_path)

    with TestClient(main.app, base_url="https://testserver") as device_a:
        registered = device_a.post(
            "/api/auth/register",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        )
        assert registered.status_code == 200

        device_b = TestClient(main.app, base_url="https://testserver")
        assert device_b.post(
            "/api/auth/login",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        ).status_code == 200
        assert device_b.get("/api/auth/session").json()["authenticated"] is True

        csrf = device_a.get("/api/auth/session").json()["csrf_token"]
        changed = device_a.post(
            "/api/account/password",
            json={"current_password": "a-long-passphrase-123", "new_password": "an-even-longer-passphrase-456"},
            headers={"x-buildwealth-csrf-token": csrf},
        )
        assert changed.status_code == 200

        # The other device's session died with the old password.
        assert device_b.get("/api/auth/session").status_code == 401


def test_logout_all_revokes_other_devices(monkeypatch, tmp_path: Path) -> None:
    _install_secure_spine(monkeypatch, tmp_path)

    with TestClient(main.app, base_url="https://testserver") as device_a:
        device_a.post(
            "/api/auth/register",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        )
        device_b = TestClient(main.app, base_url="https://testserver")
        device_b.post(
            "/api/auth/login",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        )

        csrf = device_a.get("/api/auth/session").json()["csrf_token"]
        result = device_a.post("/api/auth/logout-all", headers={"x-buildwealth-csrf-token": csrf})
        assert result.status_code == 200
        assert result.json()["revoked_sessions"] >= 2
        assert device_a.get("/api/auth/session").status_code == 401
        assert device_b.get("/api/auth/session").status_code == 401


def test_secure_mode_open_registration_flag(monkeypatch, tmp_path: Path) -> None:
    _install_secure_spine(monkeypatch, tmp_path)
    main.settings.auth_allow_open_registration = True

    with TestClient(main.app, base_url="https://testserver") as client:
        first = client.post(
            "/api/auth/register",
            json={"email": "owner@example.test", "password": "a-long-passphrase-123"},
        )
        assert first.status_code == 200
        second = client.post(
            "/api/auth/register",
            json={"email": "partner@example.test", "password": "another-passphrase-456"},
        )
        assert second.status_code == 200
