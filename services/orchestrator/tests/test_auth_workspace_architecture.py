from __future__ import annotations

from copy import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import asyncio
import jwt
from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services import workspace_services as workspace_services_module
from buildwealth_orchestrator.services.control_plane import (
    ControlPlaneStore,
    DEFAULT_HOUSEHOLD_WORKSPACE_ID,
    DEMO_HOUSEHOLD_WORKSPACE_ID,
)
from buildwealth_orchestrator.services.hosted_identity import (
    HostedIdentityConfigError,
    HostedIdentityExchangeError,
    HostedIdentityProfile,
    OIDCAuthProvider,
)
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory
from buildwealth_orchestrator.services.workspace_settings import (
    WorkspaceSecretStore,
    WorkspaceSettingsStore,
    load_or_create_local_secret_key,
)


def _install_temp_workspace_spine(monkeypatch, tmp_path: Path) -> None:
    test_settings = copy(main.settings)
    test_settings.auth_mode = "dev"
    test_settings.auth_dev_email = "owner@example.test"
    test_settings.auth_oidc_client_id = ""
    test_settings.auth_oidc_client_secret = ""
    test_settings.auth_oidc_issuer_url = ""
    test_settings.auth_oidc_logout_url = ""
    test_settings.auth_post_logout_redirect_uri = ""
    test_settings.control_db_path = tmp_path / "control" / "control.db"
    test_settings.workspace_root_dir = tmp_path / "workspaces"
    test_settings.secret_key_path = tmp_path / "control" / "local_secret.key"

    control_plane = ControlPlaneStore(test_settings.control_db_path)
    control_plane.bootstrap_default_household(
        owner_email=test_settings.auth_dev_email,
        default_storage_root=tmp_path / "real",
        demo_storage_root=tmp_path / "demo",
    )
    factory = WorkspaceServiceFactory(settings=test_settings, control_plane=control_plane)

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "control_plane_store", control_plane)
    monkeypatch.setattr(main, "workspace_service_factory", factory)


def _csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    return {"x-buildwealth-csrf-token": response.json()["csrf_token"]}


def test_workspace_settings_store_encrypts_api_key(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "local_secret.key")
    secret_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)
    settings_store = WorkspaceSettingsStore(tmp_path / "workspace_settings.json", secret_store)

    saved = settings_store.save({"llm_provider": "openai", "llm_api_key": "sk-test-secret-1234"})
    masked = settings_store.load_masked()

    assert saved["llm_api_key"] == "sk-test-secret-1234"
    assert masked["llm_api_key"] == "••••••••1234"
    assert masked["llm_api_key_configured"] is True
    assert "sk-test-secret-1234" not in (tmp_path / "workspace_settings.json").read_text(
        encoding="utf-8"
    )
    assert "sk-test-secret-1234" not in (tmp_path / "workspace_secrets.json").read_text(
        encoding="utf-8"
    )

    new_key = b"1" * 32
    rotation = secret_store.rotate_key(new_key)
    rotated_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", new_key)
    stale_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)

    assert rotation["secret_count"] == 1
    assert rotated_store.get_secret("llm_api_key") == "sk-test-secret-1234"
    assert stale_store.get_secret("llm_api_key") == ""


def test_service_status_endpoint_uses_buildwealth_service_language(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        service_response = client.get("/api/services/status")
        removed_compatibility_response = client.get("/api/engines/status")
        removed_classic_response = client.get("/classic")

    assert service_response.status_code == 200
    assert removed_compatibility_response.status_code == 404
    assert removed_classic_response.status_code == 404
    service_payload = service_response.json()
    assert [item["name"] for item in service_payload["services"]] == [
        "portfolio_benchmark",
        "portfolio_attribution",
        "plan_simulation",
    ]
    assert "engines" not in service_payload
    assert all(not key.startswith("contract_") for key in service_payload["services"][0])


def test_profile_route_uses_active_workspace_context(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        real_update = client.put(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEFAULT_HOUSEHOLD_WORKSPACE_ID},
            json={
                "notes": "real household profile",
                "household_members": [
                    {"id": "real-self", "display_name": "Real Owner", "relationship": "self"}
                ],
            },
        )
        demo_update = client.put(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEMO_HOUSEHOLD_WORKSPACE_ID},
            json={"notes": "demo household profile"},
        )
        real_response = client.get(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEFAULT_HOUSEHOLD_WORKSPACE_ID},
        )
        demo_response = client.get(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEMO_HOUSEHOLD_WORKSPACE_ID},
        )

    assert real_update.status_code == 200
    assert demo_update.status_code == 200
    assert real_response.status_code == 200
    assert demo_response.status_code == 200
    assert real_response.json()["notes"] == "real household profile"
    assert real_response.json()["household_members"][0]["display_name"] == "Real Owner"
    assert demo_response.json()["notes"] == "demo household profile"


def test_registered_users_get_separate_household_workspaces(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Bob",
            },
        )

        alice_workspace_id = alice_register.json()["workspace_id"]
        bob_workspace_id = bob_register.json()["workspace_id"]
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        alice_update = alice.put(
            "/api/financial-profile",
            headers=alice_csrf,
            json={"notes": "alice household"},
        )
        bob_update = bob.put(
            "/api/financial-profile",
            headers=bob_csrf,
            json={"notes": "bob household"},
        )
        alice_profile = alice.get("/api/financial-profile")
        bob_profile = bob.get("/api/financial-profile")
        blocked_missing_csrf = alice.put("/api/financial-profile", json={"notes": "blocked"})
        blocked_cross_read = alice.get(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": bob_workspace_id},
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_workspace_id != bob_workspace_id
    assert alice_update.status_code == 200
    assert bob_update.status_code == 200
    assert alice_profile.json()["notes"] == "alice household"
    assert bob_profile.json()["notes"] == "bob household"
    assert blocked_missing_csrf.status_code == 403
    assert blocked_cross_read.status_code == 403


def test_settings_route_uses_workspace_secret_store(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        response = client.put(
            "/api/settings",
            headers={"x-buildwealth-workspace-id": DEMO_HOUSEHOLD_WORKSPACE_ID},
            json={"llm_provider": "openai", "llm_api_key": "sk-demo-secret-9876"},
        )
        loaded = client.get(
            "/api/settings",
            headers={"x-buildwealth-workspace-id": DEMO_HOUSEHOLD_WORKSPACE_ID},
        )

    assert response.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["llm_api_key"] == "••••••••9876"
    assert loaded.json()["llm_api_key_configured"] is True
    assert "sk-demo-secret-9876" not in (
        tmp_path / "demo" / "settings" / "workspace_settings.json"
    ).read_text(encoding="utf-8")
    assert "sk-demo-secret-9876" not in (
        tmp_path / "demo" / "settings" / "workspace_secrets.json"
    ).read_text(encoding="utf-8")


def test_registered_users_get_separate_masked_api_key_settings(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "settings-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Settings Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "settings-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Settings Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        blocked_missing_csrf = alice.put(
            "/api/settings",
            json={"llm_provider": "openai", "llm_api_key": "sk-blocked-secret-0000"},
        )
        alice_save = alice.put(
            "/api/settings",
            headers=alice_csrf,
            json={"llm_provider": "openai", "llm_api_key": "sk-alice-secret-1111"},
        )
        bob_save = bob.put(
            "/api/settings",
            headers=bob_csrf,
            json={"llm_provider": "openai", "llm_api_key": "sk-bob-secret-2222"},
        )
        alice_loaded = alice.get("/api/settings")
        bob_loaded = bob.get("/api/settings")

        alice_context = main.control_plane_store.request_context_for_token(
            token=alice.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        bob_context = main.control_plane_store.request_context_for_token(
            token=bob.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        alice_services = main.workspace_service_factory.for_context(alice_context)
        bob_services = main.workspace_service_factory.for_context(bob_context)

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert alice_save.status_code == 200
    assert bob_save.status_code == 200
    assert alice_loaded.json()["llm_api_key"] == "••••••••1111"
    assert bob_loaded.json()["llm_api_key"] == "••••••••2222"
    assert alice_loaded.json()["llm_api_key_configured"] is True
    assert bob_loaded.json()["llm_api_key_configured"] is True

    alice_settings = alice_services.paths.settings_path.read_text(encoding="utf-8")
    alice_secrets = alice_services.paths.secrets_path.read_text(encoding="utf-8")
    bob_settings = bob_services.paths.settings_path.read_text(encoding="utf-8")
    bob_secrets = bob_services.paths.secrets_path.read_text(encoding="utf-8")
    for raw_secret in ("sk-alice-secret-1111", "sk-bob-secret-2222", "sk-blocked-secret-0000"):
        assert raw_secret not in alice_settings
        assert raw_secret not in alice_secrets
        assert raw_secret not in bob_settings
        assert raw_secret not in bob_secrets


def test_account_export_password_change_and_deactivation_controls(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as client:
        register = client.post(
            "/api/auth/register",
            json={
                "email": "account-owner@example.test",
                "password": "correct-horse-1",
                "display_name": "Account Owner",
            },
        )
        csrf = _csrf_headers(client)
        export_response = client.get("/api/account/export")
        missing_csrf = client.post(
            "/api/account/password",
            json={
                "current_password": "correct-horse-1",
                "new_password": "correct-horse-2",
            },
        )
        password_change = client.post(
            "/api/account/password",
            headers=csrf,
            json={
                "current_password": "correct-horse-1",
                "new_password": "correct-horse-2",
            },
        )
        old_login = client.post(
            "/api/auth/login",
            json={"email": "account-owner@example.test", "password": "correct-horse-1"},
        )
        new_login = client.post(
            "/api/auth/login",
            json={"email": "account-owner@example.test", "password": "correct-horse-2"},
        )
        deactivate_csrf = _csrf_headers(client)
        bad_deactivate = client.request(
            "DELETE",
            "/api/account",
            headers=deactivate_csrf,
            json={"current_password": "correct-horse-2", "confirm": "delete"},
        )
        deactivate = client.request(
            "DELETE",
            "/api/account",
            headers=deactivate_csrf,
            json={"current_password": "correct-horse-2", "confirm": "deactivate"},
        )
        blocked_login = client.post(
            "/api/auth/login",
            json={"email": "account-owner@example.test", "password": "correct-horse-2"},
        )

    assert register.status_code == 200
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["user"]["email"] == "account-owner@example.test"
    assert "password_hash" not in exported["user"]
    assert len(exported["workspaces"]) == 2
    assert missing_csrf.status_code == 403
    assert password_change.status_code == 200
    assert password_change.json()["requires_login"] is True
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert bad_deactivate.status_code == 400
    assert deactivate.status_code == 200
    assert deactivate.json()["requires_login"] is True
    assert blocked_login.status_code == 401


def test_account_data_deletion_request_lifecycle_marks_workspace_pending(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    context = main.control_plane_store.dev_request_context(auth_mode="dev")
    purge_after = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    request = main.control_plane_store.create_account_data_deletion_request(
        user_id=context.user_id,
        requested_by_user_id=context.user_id,
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        scope="workspace",
        purge_after=purge_after,
        preview={
            "delete": ["workspace_files", "workspace_backups", "workspace_secrets"],
            "retain": ["minimal_audit_record"],
        },
    )
    duplicate_error = None
    try:
        main.control_plane_store.create_account_data_deletion_request(
            user_id=context.user_id,
            requested_by_user_id=context.user_id,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            scope="workspace",
            purge_after=purge_after,
            preview={},
        )
    except ValueError as exc:
        duplicate_error = str(exc)
    visible_workspaces = main.control_plane_store.list_workspaces_for_user(context.user_id)
    pending = main.control_plane_store.list_pending_account_data_deletion_requests(
        due_at=(datetime.now(timezone.utc) + timedelta(days=31)).isoformat()
    )
    not_due = main.control_plane_store.list_pending_account_data_deletion_requests(
        due_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    canceled = main.control_plane_store.cancel_account_data_deletion_request(
        request_id=request.id,
        canceled_by_user_id=context.user_id,
    )
    restored_workspaces = main.control_plane_store.list_workspaces_for_user(context.user_id)

    assert request.status == "pending"
    assert request.scope == "workspace"
    assert request.workspace_id == context.workspace_id
    assert request.preview["delete"] == ["workspace_files", "workspace_backups", "workspace_secrets"]
    assert duplicate_error == "A data deletion request is already pending for this household"
    assert context.workspace_id not in {workspace.id for workspace in visible_workspaces}
    assert request.id in {item.id for item in pending}
    assert request.id not in {item.id for item in not_due}
    assert canceled.status == "canceled"
    assert context.workspace_id in {workspace.id for workspace in restored_workspaces}


def test_account_data_deletion_completion_marks_records_deleted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    context = main.control_plane_store.dev_request_context(auth_mode="dev")
    purge_after = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    request = main.control_plane_store.create_account_data_deletion_request(
        user_id=context.user_id,
        requested_by_user_id=context.user_id,
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        scope="workspace",
        purge_after=purge_after,
        preview={"delete": ["workspace_root"]},
    )
    completed = main.control_plane_store.complete_account_data_deletion_request(
        request_id=request.id,
        result={"deleted_paths": ["/tmp/buildwealth-test-workspace"], "backup_archives_pruned": 1},
    )
    visible_workspaces = main.control_plane_store.list_workspaces_for_user(context.user_id)

    with main.control_plane_store._connect() as connection:
        workspace_row = connection.execute(
            "SELECT status, deletion_completed_at FROM workspaces WHERE id = ?",
            (context.workspace_id,),
        ).fetchone()
        audit_row = connection.execute(
            """
            SELECT metadata_json
            FROM audit_events
            WHERE action = 'account.data_deletion_completed'
              AND target_id = ?
            """,
            (request.id,),
        ).fetchone()

    assert completed.status == "completed"
    assert completed.completed_at
    assert completed.result["backup_archives_pruned"] == 1
    assert workspace_row["status"] == "deleted"
    assert workspace_row["deletion_completed_at"]
    assert context.workspace_id not in {workspace.id for workspace in visible_workspaces}
    assert audit_row is not None
    assert "backup_archives_pruned" in audit_row["metadata_json"]


def test_account_data_deletion_preview_request_and_cancel_routes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "dev"
    context = main.control_plane_store.dev_request_context(auth_mode="dev")
    workspace, _role = main.control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
    )
    paths = main.workspace_service_factory.paths_for_record(workspace)
    paths.profile_path.parent.mkdir(parents=True, exist_ok=True)
    paths.profile_path.write_text('{"household_name":"Test Household"}', encoding="utf-8")
    paths.portfolio_dir.mkdir(parents=True, exist_ok=True)
    (paths.portfolio_dir / "transactions.json").write_text("[]", encoding="utf-8")
    paths.backup_archive_dir.mkdir(parents=True, exist_ok=True)
    (paths.backup_archive_dir / "buildwealth-backup-test.tar.gz").write_bytes(b"backup")
    paths.secrets_path.parent.mkdir(parents=True, exist_ok=True)
    paths.secrets_path.write_text(
        '{"schema_version":1,"secrets":{"llm_api_key":{},"openai_api_key":{}}}',
        encoding="utf-8",
    )

    with TestClient(main.app) as client:
        preview = client.get("/api/account/data-deletion/preview?scope=workspace")
        bad_confirm = client.post(
            "/api/account/data-deletion/request",
            json={"scope": "workspace", "confirm": "delete everything"},
        )
        requested = client.post(
            "/api/account/data-deletion/request",
            json={"scope": "workspace", "confirm": "delete workspace data"},
        )
        pending_requests = client.get("/api/account/data-deletion/requests")
        request_id = requested.json()["request"]["id"]
        canceled = client.post(f"/api/account/data-deletion/{request_id}/cancel")
        workspaces_after_cancel = client.get("/api/workspaces")

    preview_payload = preview.json()
    preview_workspace = preview_payload["affected_workspaces"][0]
    assert preview.status_code == 200
    assert preview_payload["confirmation_phrase"] == "delete workspace data"
    assert preview_payload["recovery_window_days"] == 30
    assert preview_payload["can_request"] is True
    assert preview_workspace["workspace_id"] == context.workspace_id
    assert preview_workspace["file_count"] >= 4
    assert preview_workspace["backup_archive_count"] == 1
    assert preview_workspace["secret_count"] == 2
    assert preview_workspace["secret_keys"] == ["llm_api_key", "openai_api_key"]
    assert "provider account" in " ".join(preview_payload["will_retain"])
    assert bad_confirm.status_code == 400
    assert requested.status_code == 200
    assert requested.json()["request"]["status"] == "pending"
    assert requested.json()["request"]["preview"]["totals"]["secret_count"] == 2
    assert pending_requests.status_code == 200
    assert request_id in {item["id"] for item in pending_requests.json()["items"]}
    assert canceled.status_code == 200
    assert canceled.json()["request"]["status"] == "canceled"
    assert workspaces_after_cancel.status_code == 200
    assert context.workspace_id in {item["id"] for item in workspaces_after_cancel.json()["items"]}


def test_hosted_oidc_login_creates_buildwealth_session(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "hosted"
    main.settings.auth_post_login_redirect_path = "/v2"

    class FakeHostedIdentityProvider:
        provider_name = "Test OIDC"

        def is_configured(self) -> bool:
            return True

        async def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
            assert state
            assert nonce
            assert code_challenge
            return f"https://identity.example.test/authorize?state={state}"

        async def exchange_code_for_profile(
            self,
            *,
            code: str,
            code_verifier: str,
            expected_nonce: str,
        ) -> HostedIdentityProfile:
            assert code == "auth-code-123"
            assert code_verifier
            assert expected_nonce
            return HostedIdentityProfile(
                provider=self.provider_name,
                subject="provider-user-123",
                email="hosted@example.test",
                display_name="Hosted User",
                email_verified=True,
                mfa_enabled=True,
            )

    monkeypatch.setattr(main, "hosted_identity_provider", FakeHostedIdentityProvider())

    with TestClient(main.app, base_url="https://testserver") as client:
        config = client.get("/api/auth/config")
        local_login = client.post(
            "/api/auth/login",
            json={"email": "hosted@example.test", "password": "password-123"},
        )
        start = client.get(
            "/api/auth/hosted/login?redirect_to=/v2/settings",
            follow_redirects=False,
        )
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        callback = client.get(
            f"/api/auth/hosted/callback?code=auth-code-123&state={state}",
            follow_redirects=False,
        )
        session = client.get("/api/auth/session")

    assert config.status_code == 200
    assert config.json()["hosted_auth_enabled"] is True
    assert config.json()["local_auth_enabled"] is False
    assert config.json()["id_token_validation_required"] is True
    assert local_login.status_code == 403
    assert start.status_code == 307
    assert callback.status_code == 307
    assert callback.headers["location"] == "/v2/settings"
    assert "secure" in callback.headers["set-cookie"].lower()
    assert session.status_code == 200
    payload = session.json()
    assert payload["auth_mode"] == "hosted"
    assert payload["user"]["email"] == "hosted@example.test"
    assert payload["user"]["auth_provider"] == "Test OIDC"
    assert payload["user"]["mfa_enabled"] is True
    assert payload["workspace"]["name"] == "My Household"
    assert payload["csrf_token"]


def test_hosted_account_closure_revokes_access_and_retains_workspace_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "hosted"

    class FakeHostedIdentityProvider:
        provider_name = "Test OIDC"

        def is_configured(self) -> bool:
            return True

        async def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
            assert state
            assert nonce
            assert code_challenge
            return f"https://identity.example.test/authorize?state={state}"

        async def exchange_code_for_profile(
            self,
            *,
            code: str,
            code_verifier: str,
            expected_nonce: str,
        ) -> HostedIdentityProfile:
            assert code == "auth-code-123"
            assert code_verifier
            assert expected_nonce
            return HostedIdentityProfile(
                provider=self.provider_name,
                subject="provider-user-123",
                email="hosted-close@example.test",
                display_name="Hosted Close User",
                email_verified=True,
                mfa_enabled=True,
            )

    monkeypatch.setattr(main, "hosted_identity_provider", FakeHostedIdentityProvider())

    with TestClient(main.app, base_url="https://testserver") as client:
        start = client.get("/api/auth/hosted/login", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        callback = client.get(
            f"/api/auth/hosted/callback?code=auth-code-123&state={state}",
            follow_redirects=False,
        )
        session = client.get("/api/auth/session")
        csrf = {"x-buildwealth-csrf-token": session.json()["csrf_token"]}
        user_id = session.json()["user"]["id"]
        export_before_close = client.get("/api/account/export")
        missing_csrf = client.post(
            "/api/account/hosted/close",
            json={"confirm": "close buildwealth access"},
        )
        bad_confirm = client.post(
            "/api/account/hosted/close",
            headers=csrf,
            json={"confirm": "delete"},
        )
        close = client.post(
            "/api/account/hosted/close",
            headers=csrf,
            json={"confirm": "close buildwealth access"},
        )
        session_after_close = client.get("/api/auth/session")

    with main.control_plane_store._connect() as connection:
        user_row = connection.execute("SELECT status FROM users WHERE id = ?", (user_id,)).fetchone()
        membership_rows = connection.execute(
            "SELECT status FROM memberships WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        workspace_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM workspaces w
            JOIN memberships m ON m.organization_id = w.organization_id
            WHERE m.user_id = ?
            """,
            (user_id,),
        ).fetchone()["count"]
        audit_row = connection.execute(
            """
            SELECT metadata_json
            FROM audit_events
            WHERE actor_user_id = ? AND action = 'account.hosted_access_closed'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    assert callback.status_code == 307
    assert session.status_code == 200
    assert export_before_close.status_code == 200
    assert len(export_before_close.json()["workspaces"]) == 2
    assert missing_csrf.status_code == 403
    assert bad_confirm.status_code == 400
    assert close.status_code == 200
    assert close.json()["requires_login"] is True
    assert "retained" in close.json()["message"]
    assert session_after_close.status_code == 401
    assert user_row["status"] == "deleted"
    assert {row["status"] for row in membership_rows} == {"inactive"}
    assert workspace_count == 2
    assert audit_row is not None
    assert "workspace_files_backups_and_audit_records_retained" in audit_row["metadata_json"]


def test_hosted_oidc_callback_errors_redirect_to_v2_auth_gate(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "hosted"

    class FakeHostedIdentityProvider:
        provider_name = "Test OIDC"

        def is_configured(self) -> bool:
            return True

    monkeypatch.setattr(main, "hosted_identity_provider", FakeHostedIdentityProvider())

    with TestClient(main.app, base_url="https://testserver") as client:
        missing_flow = client.get(
            "/api/auth/hosted/callback?code=auth-code-123&state=unknown",
            follow_redirects=False,
        )
        rejected = client.get(
            "/api/auth/hosted/callback?error=access_denied&error_description=Nope",
            follow_redirects=False,
        )

    assert missing_flow.status_code == 307
    assert missing_flow.headers["location"].startswith("/v2?auth_error=")
    assert "Hosted+login+request+is+not+active" in missing_flow.headers["location"]
    assert rejected.status_code == 307
    assert "Hosted+identity+rejected+sign-in" in rejected.headers["location"]


def test_hosted_logout_uses_provider_logout_url(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "hosted"
    main.settings.auth_oidc_client_id = "buildwealth-client"
    main.settings.auth_oidc_logout_url = "https://identity.example.test/logout"
    main.settings.auth_post_logout_redirect_uri = "https://app.example.test/v2"

    class FakeHostedIdentityProvider:
        provider_name = "Test OIDC"

        def is_configured(self) -> bool:
            return True

    monkeypatch.setattr(main, "hosted_identity_provider", FakeHostedIdentityProvider())

    with TestClient(main.app, base_url="https://testserver") as client:
        config = client.get("/api/auth/config")
        logout = client.get("/api/auth/hosted/logout", follow_redirects=False)

    assert config.status_code == 200
    assert config.json()["hosted_logout_url"] == "/api/auth/hosted/logout"
    assert logout.status_code == 307
    assert logout.headers["location"].startswith("https://identity.example.test/logout?")
    assert "post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Fv2" in logout.headers["location"]
    assert "client_id=buildwealth-client" in logout.headers["location"]


def test_hosted_readiness_reports_missing_configuration(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "hosted"
    monkeypatch.setattr(main, "hosted_identity_provider", OIDCAuthProvider(main.settings))

    with TestClient(main.app, base_url="https://testserver") as client:
        readiness = client.get("/api/auth/hosted/readiness")

    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["status"] == "blocked"
    by_id = {check["id"]: check for check in payload["checks"]}
    assert by_id["auth_mode"]["status"] == "ready"
    assert by_id["client_id"]["status"] == "blocked"
    assert by_id["client_secret"]["status"] == "blocked"
    assert by_id["issuer"]["status"] == "blocked"


def test_hosted_readiness_reports_ready_auth0_configuration(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "hosted"
    main.settings.auth_oidc_provider_name = "Auth0"
    main.settings.auth_oidc_issuer_url = "https://tenant.us.auth0.com"
    main.settings.auth_oidc_client_id = "buildwealth-client"
    main.settings.auth_oidc_client_secret = "client-secret"
    main.settings.auth_oidc_redirect_uri = "https://app.example.test/api/auth/hosted/callback"
    main.settings.auth_oidc_allowed_id_token_algs = "RS256"
    main.settings.auth_oidc_require_id_token = True
    main.settings.auth_oidc_logout_url = "https://tenant.us.auth0.com/oidc/logout"
    provider = OIDCAuthProvider(main.settings)

    async def fake_metadata() -> dict[str, str]:
        return {
            "issuer": "https://tenant.us.auth0.com",
            "authorization_endpoint": "https://tenant.us.auth0.com/authorize",
            "token_endpoint": "https://tenant.us.auth0.com/oauth/token",
            "userinfo_endpoint": "https://tenant.us.auth0.com/userinfo",
            "jwks_uri": "https://tenant.us.auth0.com/.well-known/jwks.json",
        }

    monkeypatch.setattr(provider, "_metadata", fake_metadata)
    report = asyncio.run(provider.readiness_report())
    by_id = {check["id"]: check for check in report["checks"]}

    assert report["status"] == "warning"
    assert report["hosted_auth_enabled"] is True
    assert by_id["metadata"]["status"] == "ready"
    assert by_id["authorization_endpoint"]["status"] == "ready"
    assert by_id["jwks"]["status"] == "ready"
    assert by_id["id_token_algs"]["metadata"]["allowed_algs"] == ["RS256"]
    assert by_id["mfa_policy"]["status"] == "warning"


def test_hosted_readiness_blocks_discovery_issuer_mismatch(monkeypatch) -> None:
    settings = SimpleNamespace(
        auth_mode="hosted",
        auth_oidc_provider_name="Auth0",
        auth_oidc_issuer_url="https://tenant.us.auth0.com",
        auth_oidc_client_id="buildwealth-client",
        auth_oidc_client_secret="client-secret",
        auth_oidc_redirect_uri="https://app.example.test/api/auth/hosted/callback",
        auth_oidc_scopes="openid email profile",
        auth_oidc_allowed_id_token_algs="RS256",
        auth_oidc_require_id_token=True,
        auth_oidc_require_mfa=False,
        auth_oidc_jwks_uri="",
        auth_oidc_authorization_endpoint="",
        auth_oidc_token_endpoint="",
        auth_oidc_userinfo_endpoint="",
        auth_oidc_logout_url="",
        auth_account_management_url="",
        auth_password_reset_url="",
        auth_mfa_enrollment_url="",
        auth_passkey_enrollment_url="",
    )
    provider = OIDCAuthProvider(settings)

    async def fake_metadata() -> dict[str, str]:
        raise HostedIdentityConfigError("OIDC discovery issuer did not match the configured issuer")

    monkeypatch.setattr(provider, "_metadata", fake_metadata)
    report = asyncio.run(provider.readiness_report())
    by_id = {check["id"]: check for check in report["checks"]}

    assert report["status"] == "blocked"
    assert by_id["metadata"]["status"] == "blocked"
    assert "issuer" in by_id["metadata"]["detail"]


def test_oidc_id_token_validation_checks_issuer_audience_nonce_and_subject() -> None:
    settings = SimpleNamespace(
        auth_oidc_provider_name="Test OIDC",
        auth_oidc_client_id="buildwealth-client",
        auth_oidc_client_secret="super-secret",
        auth_oidc_allowed_id_token_algs="HS256",
        auth_oidc_require_id_token=True,
        auth_oidc_require_mfa=False,
        auth_oidc_issuer_url="https://issuer.example.test",
        auth_oidc_jwks_uri="",
    )
    provider = OIDCAuthProvider(settings)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": "https://issuer.example.test",
            "sub": "provider-user-123",
            "aud": "buildwealth-client",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "nonce": "nonce-123",
            "email": "hosted@example.test",
            "email_verified": True,
        },
        "super-secret",
        algorithm="HS256",
    )

    claims = provider._validate_id_token(
        token,
        access_token="access-token-123",
        metadata={"issuer": "https://issuer.example.test"},
        expected_nonce="nonce-123",
    )
    profile = provider._profile_from_claims(
        {"sub": "provider-user-123", "name": "Hosted User"},
        id_token_claims=claims,
        expected_nonce="nonce-123",
    )

    assert claims["sub"] == "provider-user-123"
    assert profile.email == "hosted@example.test"
    assert profile.display_name == "Hosted User"

    try:
        provider._validate_id_token(
            token,
            access_token="access-token-123",
            metadata={"issuer": "https://issuer.example.test"},
            expected_nonce="other-nonce",
        )
    except HostedIdentityExchangeError as exc:
        assert "nonce" in str(exc)
    else:
        raise AssertionError("Expected nonce mismatch to fail")

    try:
        provider._profile_from_claims(
            {"sub": "different-user"},
            id_token_claims=claims,
            expected_nonce="nonce-123",
        )
    except HostedIdentityExchangeError as exc:
        assert "subject" in str(exc)
    else:
        raise AssertionError("Expected userinfo subject mismatch to fail")


def test_workspace_secret_key_rotation_preview_and_apply(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as client:
        register = client.post(
            "/api/auth/register",
            json={
                "email": "rotation-owner@example.test",
                "password": "correct-horse-1",
                "display_name": "Rotation Owner",
            },
        )
        csrf = _csrf_headers(client)
        save_secret = client.put(
            "/api/settings",
            headers=csrf,
            json={"llm_provider": "openai", "llm_api_key": "sk-rotation-secret-1234"},
        )
        preview = client.get("/api/security/secrets/rotation/preview")
        rejected = client.post(
            "/api/security/secrets/rotation/apply",
            headers=csrf,
            json={"confirm": "nope"},
        )
        old_key_text = main.settings.secret_key_path.read_text(encoding="utf-8")
        applied = client.post(
            "/api/security/secrets/rotation/apply",
            headers=csrf,
            json={"confirm": "rotate"},
        )
        new_key_text = main.settings.secret_key_path.read_text(encoding="utf-8")
        loaded = client.get("/api/settings")

    assert register.status_code == 200
    assert save_secret.status_code == 200
    assert preview.status_code == 200
    assert preview.json()["workspace_count"] == 4
    assert preview.json()["secret_count"] == 1
    assert rejected.status_code == 400
    assert applied.status_code == 200
    assert applied.json()["rotated"] is True
    assert applied.json()["secret_count"] == 1
    assert old_key_text != new_key_text
    assert loaded.status_code == 200
    assert loaded.json()["llm_api_key"] == "••••••••1234"
    assert loaded.json()["llm_api_key_configured"] is True


def test_workspace_secret_key_rotation_rolls_back_on_key_write_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    def fail_key_write(_secret_key_path: Path, _secret_key: bytes) -> None:
        raise OSError("simulated key write failure")

    with TestClient(main.app, raise_server_exceptions=False) as client:
        register = client.post(
            "/api/auth/register",
            json={
                "email": "rollback-owner@example.test",
                "password": "correct-horse-1",
                "display_name": "Rollback Owner",
            },
        )
        csrf = _csrf_headers(client)
        save_secret = client.put(
            "/api/settings",
            headers=csrf,
            json={"llm_provider": "openai", "llm_api_key": "sk-rollback-secret-5678"},
        )
        old_key_text = main.settings.secret_key_path.read_text(encoding="utf-8")
        monkeypatch.setattr(workspace_services_module, "write_local_secret_key", fail_key_write)
        failed_rotation = client.post(
            "/api/security/secrets/rotation/apply",
            headers=csrf,
            json={"confirm": "rotate"},
        )
        restored_key_text = main.settings.secret_key_path.read_text(encoding="utf-8")
        loaded = client.get("/api/settings")

    assert register.status_code == 200
    assert save_secret.status_code == 200
    assert failed_rotation.status_code == 500
    assert restored_key_text == old_key_text
    assert loaded.status_code == 200
    assert loaded.json()["llm_api_key"] == "••••••••5678"
    assert loaded.json()["llm_api_key_configured"] is True


def test_registered_users_get_separate_portfolio_transactions(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "portfolio-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Portfolio Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "portfolio-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Portfolio Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        alice_workspace_id = alice_register.json()["workspace_id"]
        bob_workspace_id = bob_register.json()["workspace_id"]

        alice_add = alice.post(
            "/api/portfolio/transactions",
            headers=alice_csrf,
            json={
                "date": "2026-05-12",
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 2,
                "unit_price": 100,
                "account": "Alice Brokerage",
            },
        )
        bob_add = bob.post(
            "/api/portfolio/transactions",
            headers=bob_csrf,
            json={
                "date": "2026-05-12",
                "symbol": "MSFT",
                "action": "BUY",
                "quantity": 1,
                "unit_price": 200,
                "account": "Bob Brokerage",
            },
        )
        blocked_missing_csrf = alice.post(
            "/api/portfolio/transactions",
            json={"date": "2026-05-12", "symbol": "VTI", "action": "BUY", "quantity": 1, "unit_price": 1},
        )
        alice_transactions = alice.get("/api/portfolio/transactions")
        bob_transactions = bob.get("/api/portfolio/transactions")
        blocked_cross_read = alice.get(
            "/api/portfolio/transactions",
            headers={"x-buildwealth-workspace-id": bob_workspace_id},
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_workspace_id != bob_workspace_id
    assert alice_add.status_code == 200
    assert bob_add.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert blocked_cross_read.status_code == 403
    assert [item["symbol"] for item in alice_transactions.json()] == ["AAPL"]
    assert [item["symbol"] for item in bob_transactions.json()] == ["MSFT"]


def test_registered_users_get_separate_statement_import_suggestions(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "statement-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Statement Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "statement-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Statement Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        alice_apply = alice.post(
            "/api/import/statement/apply",
            headers=alice_csrf,
            json={
                "expenses": [
                    {
                        "label": "Rent",
                        "monthly_amount_usd": 1800,
                        "category": "housing",
                        "is_fixed": True,
                    }
                ]
            },
        )
        bob_apply = bob.post(
            "/api/import/statement/apply",
            headers=bob_csrf,
            json={
                "income": [
                    {
                        "label": "Salary",
                        "monthly_amount_usd": 7000,
                        "source_type": "salary",
                    }
                ]
            },
        )
        blocked_missing_csrf = alice.post(
            "/api/import/statement/apply",
            json={"income": [{"label": "Bonus", "monthly_amount_usd": 100}]},
        )
        alice_profile = alice.get("/api/financial-profile")
        bob_profile = bob.get("/api/financial-profile")

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_apply.status_code == 200
    assert bob_apply.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert alice_profile.json()["expense_items"][0]["label"] == "Rent"
    assert alice_profile.json()["income_items"] == []
    assert bob_profile.json()["income_items"][0]["label"] == "Salary"
    assert bob_profile.json()["expense_items"] == []


def test_registered_users_get_separate_plan_workspaces(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "plan-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Plan Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "plan-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Plan Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        blocked_missing_csrf = alice.post(
            "/api/plans",
            json={"title": "Blocked Plan"},
        )
        alice_create = alice.post(
            "/api/plans",
            headers=alice_csrf,
            json={"title": "Alice Independence Plan", "description": "Alice-only plan."},
        )
        bob_create = bob.post(
            "/api/plans",
            headers=bob_csrf,
            json={"title": "Bob Cash Flow Plan", "description": "Bob-only plan."},
        )
        alice_plan_id = alice_create.json()["id"]
        bob_plan_id = bob_create.json()["id"]

        alice_list = alice.get("/api/plans")
        bob_list = bob.get("/api/plans")
        bob_reads_alice = bob.get(f"/api/plans/{alice_plan_id}")
        alice_reads_bob = alice.get(f"/api/plans/{bob_plan_id}")
        alice_update = alice.patch(
            f"/api/plans/{alice_plan_id}/settings",
            headers=alice_csrf,
            json={"annual_contribution_usd": 18000},
        )
        bob_update_alice = bob.patch(
            f"/api/plans/{alice_plan_id}/settings",
            headers=bob_csrf,
            json={"annual_contribution_usd": 1},
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert alice_create.status_code == 200
    assert bob_create.status_code == 200
    assert [item["id"] for item in alice_list.json()] == [alice_plan_id]
    assert [item["id"] for item in bob_list.json()] == [bob_plan_id]
    assert bob_reads_alice.status_code == 404
    assert alice_reads_bob.status_code == 404
    assert alice_update.status_code == 200
    assert alice_update.json()["settings"]["annual_contribution_usd"] == 18000
    assert bob_update_alice.status_code == 404


def test_registered_users_cannot_act_on_other_workspace_recommendations(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "rec-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Recommendation Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "rec-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Recommendation Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        alice_context = main.control_plane_store.request_context_for_token(
            token=alice.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        alice_services = main.workspace_service_factory.for_context(alice_context)
        plan = alice_services.plan_workspace.create_plan("Alice BuildWealth Plan")
        recommendation = alice_services.recommendation_inbox.create(
            title="Increase emergency savings",
            detail="Route more monthly surplus to the emergency fund.",
            priority="high",
            recommendation_type="general",
            source="route-test",
            plan_id=plan["id"],
            action_payload={},
        )

        bob_read = bob.get(f"/api/recommendations/{recommendation['id']}")
        bob_apply = bob.post(
            f"/api/recommendations/{recommendation['id']}/apply",
            headers=bob_csrf,
            json={"plan_id": plan["id"], "rationale": "Not Bob's recommendation."},
        )
        missing_csrf = alice.post(
            f"/api/recommendations/{recommendation['id']}/apply",
            json={"plan_id": plan["id"], "rationale": "Missing CSRF should fail."},
        )
        alice_preview = alice.post(
            f"/api/recommendations/{recommendation['id']}/preview",
            headers=alice_csrf,
            json={"plan_id": plan["id"], "capture_scenario_diff": False},
        )
        alice_apply = alice.post(
            f"/api/recommendations/{recommendation['id']}/apply",
            headers=alice_csrf,
            json={
                "plan_id": plan["id"],
                "rationale": "This fits Alice's plan.",
                "capture_scenario_diff": False,
                "create_decision_packet": False,
            },
        )
        alice_outcome = alice.post(
            f"/api/recommendations/{recommendation['id']}/outcome",
            headers=alice_csrf,
            json={
                "plan_id": plan["id"],
                "note": "Checked one month later.",
                "measurement_source": "manual_review",
            },
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert bob_read.status_code == 404
    assert bob_apply.status_code == 404
    assert missing_csrf.status_code == 403
    assert alice_preview.status_code == 200
    assert alice_preview.json()["recommendation"]["id"] == recommendation["id"]
    assert alice_apply.status_code == 200
    assert alice_apply.json()["recommendation"]["status"] == "applied"
    assert alice_apply.json()["plan"]["id"] == plan["id"]
    assert alice_outcome.status_code == 200
    assert alice_outcome.json()["decision_closure"]["realized_outcome"]["note"] == "Checked one month later."


def test_registered_users_get_separate_backup_and_protection_state(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "backup-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Backup Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "backup-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Backup Bob",
            },
        )
        alice_workspace_id = alice_register.json()["workspace_id"]
        bob_workspace_id = bob_register.json()["workspace_id"]
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        alice_profile = alice.put(
            "/api/financial-profile",
            headers=alice_csrf,
            json={"notes": "alice backup source"},
        )
        bob_profile = bob.put(
            "/api/financial-profile",
            headers=bob_csrf,
            json={"notes": "bob backup source"},
        )
        blocked_missing_csrf = alice.post(
            "/api/storage/backups",
            json={"reason": "should be blocked"},
        )
        alice_backup = alice.post(
            "/api/storage/backups",
            headers=alice_csrf,
            json={"reason": "alice backup"},
        )
        bob_backup = bob.post(
            "/api/storage/backups",
            headers=bob_csrf,
            json={"reason": "bob backup"},
        )
        alice_backups = alice.get("/api/storage/backups")
        bob_backups = bob.get("/api/storage/backups")
        blocked_cross_read = alice.get(
            "/api/storage/backups",
            headers={"x-buildwealth-workspace-id": bob_workspace_id},
        )
        alice_durable_migration = alice.post(
            "/api/storage/durable/migrate",
            headers=alice_csrf,
            json={"run_rollback_check": False},
        )
        bob_durable_status = bob.get("/api/storage/durable/status")
        bob_policy = bob.put(
            "/api/storage/protection/policy",
            headers=bob_csrf,
            json={"protection_level": "hardened", "include_backups": True},
        )
        alice_protection = alice.get("/api/storage/protection/status")
        bob_protection = bob.get("/api/storage/protection/status")

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_workspace_id != bob_workspace_id
    assert alice_profile.status_code == 200
    assert bob_profile.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert blocked_cross_read.status_code == 403
    assert alice_backup.status_code == 200
    assert bob_backup.status_code == 200
    assert alice_backups.status_code == 200
    assert bob_backups.status_code == 200
    assert alice_backups.json()["data_root"] != bob_backups.json()["data_root"]
    assert alice_backups.json()["backup_dir"] != bob_backups.json()["backup_dir"]
    assert alice_backup.json()["archive_path"].startswith(alice_backups.json()["backup_dir"])
    assert bob_backup.json()["archive_path"].startswith(bob_backups.json()["backup_dir"])
    assert alice_durable_migration.status_code == 200
    assert alice_durable_migration.json()["data_root"] == alice_backups.json()["data_root"]
    assert bob_durable_status.status_code == 200
    assert bob_durable_status.json()["data_root"] == bob_backups.json()["data_root"]
    assert bob_policy.status_code == 200
    assert alice_protection.status_code == 200
    assert bob_protection.status_code == 200
    assert alice_protection.json()["policy"]["protection_level"] == "standard"
    assert bob_protection.json()["policy"]["protection_level"] == "hardened"
    assert bob_protection.json()["policy"]["include_backups"] is True


def test_registered_users_get_separate_context_candidates(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "context-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Context Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "context-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Context Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        blocked_missing_csrf = alice.post(
            "/api/context/candidates",
            json={"extracted_claim": "missing csrf should not be saved"},
        )
        alice_candidate = alice.post(
            "/api/context/candidates",
            headers=alice_csrf,
            json={
                "source_domain": "conversation",
                "source_ref": "conversation/alice",
                "extracted_claim": "Alice wants a plain-language portfolio review.",
                "target_domain": "profile",
                "target_area": "preferences",
                "target_field": "communication_style",
                "target_value": "plain language",
            },
        )
        bob_candidate = bob.post(
            "/api/context/candidates",
            headers=bob_csrf,
            json={
                "source_domain": "conversation",
                "source_ref": "conversation/bob",
                "extracted_claim": "Bob prefers detailed simulation notes.",
                "target_domain": "profile",
                "target_area": "preferences",
                "target_field": "communication_style",
                "target_value": "detailed",
            },
        )
        alice_list = alice.get("/api/context/candidates")
        bob_list = bob.get("/api/context/candidates")
        bob_updates_alice = bob.patch(
            f"/api/context/candidates/{alice_candidate.json()['id']}/lifecycle",
            headers=bob_csrf,
            json={"lifecycle_state": "applied"},
        )
        alice_updates_own = alice.patch(
            f"/api/context/candidates/{alice_candidate.json()['id']}/lifecycle",
            headers=alice_csrf,
            json={"lifecycle_state": "applied"},
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert alice_candidate.status_code == 200
    assert bob_candidate.status_code == 200
    assert [item["id"] for item in alice_list.json()["items"]] == [alice_candidate.json()["id"]]
    assert [item["id"] for item in bob_list.json()["items"]] == [bob_candidate.json()["id"]]
    assert bob_updates_alice.status_code == 404
    assert alice_updates_own.status_code == 200
    assert alice_updates_own.json()["lifecycle_state"] == "applied"


def test_registered_users_get_separate_git_workspaces(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "git-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Git Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "git-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Git Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        blocked_missing_csrf = alice.put(
            "/api/git/policy",
            json={"enabled": True},
        )
        alice_policy = alice.put(
            "/api/git/policy",
            headers=alice_csrf,
            json={"enabled": True, "include_financial_profile": True},
        )
        bob_policy = bob.put(
            "/api/git/policy",
            headers=bob_csrf,
            json={"enabled": True, "include_recommendations": False},
        )
        alice_init = alice.post("/api/git/init", headers=alice_csrf)
        bob_init = bob.post("/api/git/init", headers=bob_csrf)
        alice_checkpoint = alice.post(
            "/api/git/checkpoint",
            headers=alice_csrf,
            json={"message": "Alice checkpoint"},
        )
        bob_checkpoint = bob.post(
            "/api/git/checkpoint",
            headers=bob_csrf,
            json={"message": "Bob checkpoint"},
        )
        alice_status = alice.get("/api/git/status")
        bob_status = bob.get("/api/git/status")
        alice_activity = alice.get("/api/git/activity")
        bob_activity = bob.get("/api/git/activity")
        alice_loaded_policy = alice.get("/api/git/policy")
        bob_loaded_policy = bob.get("/api/git/policy")
        alice_workflow = alice.post(
            "/api/release-readiness/workflow-verification",
            headers=alice_csrf,
            json={
                "workflow": "product_testing",
                "status": "passed",
                "passed_count": 3,
                "failed_count": 0,
                "notes": "Alice-only workflow pass.",
            },
        )
        alice_readiness = alice.get("/api/release-readiness")
        bob_readiness = bob.get("/api/release-readiness")

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert alice_policy.status_code == 200
    assert bob_policy.status_code == 200
    assert alice_policy.json()["workspace_dir"] != bob_policy.json()["workspace_dir"]
    assert alice_policy.json()["include_financial_profile"] is True
    assert bob_policy.json()["include_recommendations"] is False
    assert alice_loaded_policy.json()["include_financial_profile"] is True
    assert bob_loaded_policy.json()["include_financial_profile"] is False
    assert alice_init.status_code == 200
    assert bob_init.status_code == 200
    assert alice_checkpoint.status_code == 200
    assert bob_checkpoint.status_code == 200
    assert alice_status.status_code == 200
    assert bob_status.status_code == 200
    assert alice_status.json()["workspace_dir"] != bob_status.json()["workspace_dir"]
    assert alice_status.json()["workspace_dir"] == alice_policy.json()["workspace_dir"]
    assert bob_status.json()["workspace_dir"] == bob_policy.json()["workspace_dir"]
    assert "Alice checkpoint" in [event["title"] for event in alice_activity.json()["events"]]
    assert "Bob checkpoint" not in [event["title"] for event in alice_activity.json()["events"]]
    assert "Bob checkpoint" in [event["title"] for event in bob_activity.json()["events"]]
    assert "Alice checkpoint" not in [event["title"] for event in bob_activity.json()["events"]]
    assert alice_workflow.status_code == 200
    assert alice_readiness.status_code == 200
    assert bob_readiness.status_code == 200
    alice_checks = {check["id"]: check for check in alice_readiness.json()["checks"]}
    bob_checks = {check["id"]: check for check in bob_readiness.json()["checks"]}
    assert alice_checks["workflow_verification"]["status"] == "ready"
    assert bob_checks["workflow_verification"]["status"] == "warning"


def test_registered_users_get_separate_today_review_checkpoints(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "today-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Today Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "today-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Today Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)

        blocked_missing_csrf = alice.post("/api/dashboard/today/review-checkpoint")
        alice_dashboard = alice.get("/api/dashboard/today")
        bob_dashboard = bob.get("/api/dashboard/today")
        alice_checkpoint = alice.post(
            "/api/dashboard/today/review-checkpoint",
            headers=alice_csrf,
        )

        alice_context = main.control_plane_store.request_context_for_token(
            token=alice.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        bob_context = main.control_plane_store.request_context_for_token(
            token=bob.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        alice_services = main.workspace_service_factory.for_context(alice_context)
        bob_services = main.workspace_service_factory.for_context(bob_context)

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert blocked_missing_csrf.status_code == 403
    assert alice_dashboard.status_code == 200
    assert bob_dashboard.status_code == 200
    assert alice_checkpoint.status_code == 200
    assert alice_services.today_review_checkpoint_store.latest() is not None
    assert bob_services.today_review_checkpoint_store.latest() is None


def test_registered_users_get_separate_snapshot_state(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "snapshot-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Snapshot Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "snapshot-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Snapshot Bob",
            },
        )
        alice_context = main.control_plane_store.request_context_for_token(
            token=alice.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        bob_context = main.control_plane_store.request_context_for_token(
            token=bob.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        alice_services = main.workspace_service_factory.for_context(alice_context)
        bob_services = main.workspace_service_factory.for_context(bob_context)
        alice_services.snapshot_store.write(
            main.PortfolioSnapshot(
                as_of=main.utc_now() - timedelta(days=1),
                total_value_usd=120_000,
            )
        )
        alice_services.snapshot_store.write(
            main.PortfolioSnapshot(
                as_of=main.utc_now(),
                total_value_usd=125_000,
            )
        )
        bob_services.snapshot_store.write(
            main.PortfolioSnapshot(
                as_of=main.utc_now(),
                total_value_usd=42_000,
            )
        )

        alice_latest = alice.get("/api/snapshot/latest")
        bob_latest = bob.get("/api/snapshot/latest")
        alice_history = alice.get("/api/snapshot/history")
        bob_history = bob.get("/api/snapshot/history")
        blocked_sync = alice.post("/api/snapshot/sync")
        blocked_backfill = alice.post("/api/snapshot/backfill-history", json={"days": 1})

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_latest.status_code == 200
    assert bob_latest.status_code == 200
    assert alice_latest.json()["total_value_usd"] == 125_000
    assert bob_latest.json()["total_value_usd"] == 42_000
    assert alice_history.status_code == 200
    assert bob_history.status_code == 200
    assert alice_history.json()["window_points"] == 2
    assert bob_history.json()["window_points"] == 1
    assert blocked_sync.status_code == 403
    assert blocked_backfill.status_code == 403


def test_registered_users_get_separate_financial_health_and_planning_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "planner-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Planner Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "planner-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Planner Bob",
            },
        )
        alice_context = main.control_plane_store.request_context_for_token(
            token=alice.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        bob_context = main.control_plane_store.request_context_for_token(
            token=bob.cookies.get(main.settings.auth_session_cookie_name),
            auth_mode="local",
        )
        alice_services = main.workspace_service_factory.for_context(alice_context)
        bob_services = main.workspace_service_factory.for_context(bob_context)

        alice_services.financial_profile_store.save(
            {
                "income_items": [
                    {
                        "id": "alice-salary",
                        "label": "Alice Salary",
                        "monthly_amount_usd": 10_000,
                        "source_type": "salary",
                    }
                ],
                "expense_items": [
                    {
                        "id": "alice-housing",
                        "label": "Alice Housing",
                        "monthly_amount_usd": 3_000,
                        "category": "housing",
                    }
                ],
                "debt_items": [
                    {
                        "id": "alice-loan",
                        "label": "Alice Loan",
                        "balance_usd": 1_000,
                        "minimum_payment_usd": 100,
                        "interest_rate": 0.05,
                    }
                ],
                "goal_items": [
                    {
                        "id": "alice-goal",
                        "label": "Alice Goal",
                        "target_amount_usd": 50_000,
                        "target_date": "2030-01-01T00:00:00Z",
                        "priority": "high",
                    }
                ],
                "physical_assets": [
                    {
                        "id": "alice-car",
                        "label": "Alice Car",
                        "current_value_usd": 18_000,
                        "asset_type": "vehicle",
                    }
                ],
            }
        )
        bob_services.financial_profile_store.save(
            {
                "income_items": [
                    {
                        "id": "bob-salary",
                        "label": "Bob Salary",
                        "monthly_amount_usd": 4_000,
                        "source_type": "salary",
                    }
                ],
                "expense_items": [
                    {
                        "id": "bob-housing",
                        "label": "Bob Housing",
                        "monthly_amount_usd": 3_500,
                        "category": "housing",
                    }
                ],
                "debt_items": [
                    {
                        "id": "bob-loan",
                        "label": "Bob Loan",
                        "balance_usd": 20_000,
                        "minimum_payment_usd": 550,
                        "interest_rate": 0.12,
                    }
                ],
                "goal_items": [
                    {
                        "id": "bob-goal",
                        "label": "Bob Goal",
                        "target_amount_usd": 80_000,
                        "target_date": "2030-01-01T00:00:00Z",
                        "priority": "medium",
                    }
                ],
            }
        )
        alice_services.snapshot_store.write(
            main.PortfolioSnapshot(
                as_of=main.utc_now(),
                total_value_usd=125_000,
                holdings=[
                    {
                        "symbol": "VTI",
                        "name": "Vanguard Total Stock Market ETF",
                        "value_usd": 100_000,
                        "allocation_percent": 80.0,
                    },
                    {
                        "symbol": "CASH",
                        "name": "Cash",
                        "value_usd": 25_000,
                        "allocation_percent": 20.0,
                        "asset_type": "cash",
                    },
                ],
            )
        )
        bob_services.snapshot_store.write(
            main.PortfolioSnapshot(
                as_of=main.utc_now(),
                total_value_usd=42_000,
                holdings=[
                    {
                        "symbol": "QQQ",
                        "name": "Invesco QQQ Trust",
                        "value_usd": 42_000,
                        "allocation_percent": 100.0,
                    }
                ],
            )
        )
        alice_services.portfolio_store.add_account("Alice 401k", account_type="401k")
        bob_services.portfolio_store.add_account("Bob Brokerage", account_type="taxable")

        alice_health = alice.get("/api/financial-health")
        bob_health = bob.get("/api/financial-health")
        alice_affordability = alice.post(
            "/api/affordability",
            json={"description": "Car payment", "monthly_amount_usd": 500},
        )
        bob_affordability = bob.post(
            "/api/affordability",
            json={"description": "Car payment", "monthly_amount_usd": 500},
        )
        alice_goal_progress = alice.get("/api/goals/progress")
        bob_goal_progress = bob.get("/api/goals/progress")
        alice_income_projection = alice.post("/api/planning/income-projection", json={"years": 1})
        bob_income_projection = bob.post("/api/planning/income-projection", json={"years": 1})
        alice_expense_projection = alice.post("/api/planning/expense-projection", json={"years": 1})
        bob_expense_projection = bob.post("/api/planning/expense-projection", json={"years": 1})
        alice_debt_projection = alice.post("/api/planning/debt-projection", json={"max_years": 1})
        bob_debt_projection = bob.post("/api/planning/debt-projection", json={"max_years": 1})
        alice_social_security = alice.post(
            "/api/planning/social-security-projection",
            json={"years": 1},
        )
        bob_social_security = bob.post(
            "/api/planning/social-security-projection",
            json={"years": 1},
        )
        alice_rmd_projection = alice.post("/api/planning/rmd-projection", json={"years": 1})
        bob_rmd_projection = bob.post("/api/planning/rmd-projection", json={"years": 1})
        alice_contribution = alice.post(
            "/api/planning/contribution-allocation",
            json={"annual_contribution_usd": 6_000},
        )
        bob_contribution = bob.post(
            "/api/planning/contribution-allocation",
            json={"annual_contribution_usd": 6_000},
        )
        alice_scenario = alice.post("/api/planning/scenarios", json={"years": 1})
        bob_scenario = bob.post("/api/planning/scenarios", json={"years": 1})
        alice_trade = alice.post(
            "/api/portfolio/simulate-trade",
            json={"symbol": "AAPL", "action": "buy", "amount_usd": 1_000},
        )
        bob_trade = bob.post(
            "/api/portfolio/simulate-trade",
            json={"symbol": "AAPL", "action": "buy", "amount_usd": 1_000},
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_health.status_code == 200
    assert bob_health.status_code == 200
    assert alice_health.json()["monthly_surplus_usd"] == 6_900
    assert bob_health.json()["monthly_surplus_usd"] == -50
    assert alice_health.json()["net_worth_usd"] > bob_health.json()["net_worth_usd"]
    assert alice_affordability.status_code == 200
    assert bob_affordability.status_code == 200
    assert alice_affordability.json()["assessment"] == "affordable"
    assert bob_affordability.json()["assessment"] == "not_affordable"
    assert alice_goal_progress.status_code == 200
    assert bob_goal_progress.status_code == 200
    assert alice_goal_progress.json()["monthly_surplus_usd"] == 6_900
    assert bob_goal_progress.json()["monthly_surplus_usd"] == -50
    assert alice_goal_progress.json()["goals"][0]["current_savings_usd"] == 125_000
    assert bob_goal_progress.json()["goals"][0]["current_savings_usd"] == 42_000
    assert alice_income_projection.status_code == 200
    assert bob_income_projection.status_code == 200
    assert alice_income_projection.json()["first_year_gross_income_usd"] == 120_000
    assert bob_income_projection.json()["first_year_gross_income_usd"] == 48_000
    assert alice_expense_projection.status_code == 200
    assert bob_expense_projection.status_code == 200
    assert alice_expense_projection.json()["first_year_expenses_usd"] == 36_000
    assert bob_expense_projection.json()["first_year_expenses_usd"] == 42_000
    assert alice_debt_projection.status_code == 200
    assert bob_debt_projection.status_code == 200
    assert alice_debt_projection.json()["debt_items_count"] == 1
    assert bob_debt_projection.json()["minimum_scenario"]["remaining_balance_usd"] > 0
    assert alice_social_security.status_code == 200
    assert bob_social_security.status_code == 200
    assert alice_social_security.json()["fra_monthly_benefit_usd"] > bob_social_security.json()["fra_monthly_benefit_usd"]
    assert alice_rmd_projection.status_code == 200
    assert bob_rmd_projection.status_code == 200
    assert alice_rmd_projection.json()["eligible_account_count"] == 1
    assert bob_rmd_projection.json()["eligible_account_count"] == 0
    assert alice_contribution.status_code == 200
    assert bob_contribution.status_code == 200
    assert alice_contribution.json()["annual_contribution_target_usd"] == 6_000
    assert bob_contribution.json()["annual_contribution_target_usd"] == 6_000
    assert alice_scenario.status_code == 200
    assert bob_scenario.status_code == 200
    assert alice_scenario.json()["scenarios"][0]["future_value_usd"] > bob_scenario.json()["scenarios"][0]["future_value_usd"]
    assert alice_trade.status_code == 200
    assert bob_trade.status_code == 200
    assert alice_trade.json()["current_total_value_usd"] == 125_000
    assert bob_trade.json()["current_total_value_usd"] == 42_000


def test_copilot_chat_and_tools_use_active_user_workspace(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    main.settings.auth_mode = "local"

    async def fake_assemble_copilot_context_payload(**kwargs):
        services = kwargs["services"]
        return {
            "trace": {"workspace_id": services.record.id},
            "question": kwargs.get("question"),
        }

    class ToolCheckingCopilot:
        async def chat(
            self,
            *,
            question,
            conversation_id=None,
            contextual_brief=None,
            context_trace=None,
            conversation_store=None,
        ):
            assert conversation_store is not None
            profile = await main.tool_get_financial_profile({})
            conversation = conversation_store.get_or_create(conversation_id, question)
            conversation_store.append_message(conversation, "user", question)
            answer = f"profile-notes:{profile.get('notes')}"
            conversation_store.append_message(
                conversation,
                "assistant",
                answer,
                metadata={"context_trace": context_trace or {}},
            )
            conversation_store.save(conversation)
            return {
                "conversation_id": conversation["id"],
                "answer": answer,
                "tool_calls": [],
                "model": "test-copilot",
                "context_trace": context_trace or {},
                "created_at": main.utc_now(),
            }

    monkeypatch.setattr(main, "assemble_copilot_context_payload", fake_assemble_copilot_context_payload)
    monkeypatch.setattr(main, "copilot", ToolCheckingCopilot())

    with TestClient(main.app) as alice, TestClient(main.app) as bob:
        alice_register = alice.post(
            "/api/auth/register",
            json={
                "email": "copilot-alice@example.test",
                "password": "correct-horse-1",
                "display_name": "Copilot Alice",
            },
        )
        bob_register = bob.post(
            "/api/auth/register",
            json={
                "email": "copilot-bob@example.test",
                "password": "correct-horse-2",
                "display_name": "Copilot Bob",
            },
        )
        alice_csrf = _csrf_headers(alice)
        bob_csrf = _csrf_headers(bob)

        alice_profile = alice.put(
            "/api/financial-profile",
            headers=alice_csrf,
            json={"notes": "alice copilot workspace"},
        )
        bob_profile = bob.put(
            "/api/financial-profile",
            headers=bob_csrf,
            json={"notes": "bob copilot workspace"},
        )

        alice_chat = alice.post("/api/copilot/chat", json={"question": "Who am I scoped to?"})
        bob_chat = bob.post("/api/copilot/chat", json={"question": "Who am I scoped to?"})
        alice_conversations = alice.get("/api/copilot/conversations")
        bob_conversations = bob.get("/api/copilot/conversations")
        bob_reads_alice = bob.get(
            f"/api/copilot/conversations/{alice_chat.json()['conversation_id']}"
        )

    assert alice_register.status_code == 200
    assert bob_register.status_code == 200
    assert alice_profile.status_code == 200
    assert bob_profile.status_code == 200
    assert alice_chat.status_code == 200
    assert bob_chat.status_code == 200
    assert alice_chat.json()["answer"] == "profile-notes:alice copilot workspace"
    assert bob_chat.json()["answer"] == "profile-notes:bob copilot workspace"
    assert [item["id"] for item in alice_conversations.json()] == [alice_chat.json()["conversation_id"]]
    assert [item["id"] for item in bob_conversations.json()] == [bob_chat.json()["conversation_id"]]
    assert bob_reads_alice.status_code == 404


def test_demo_workspace_reset_seeds_demo_without_touching_real_workspace(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        real_update = client.put(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEFAULT_HOUSEHOLD_WORKSPACE_ID},
            json={"notes": "do not touch real workspace"},
        )
        reset_response = client.post(
            f"/api/workspaces/{DEMO_HOUSEHOLD_WORKSPACE_ID}/demo/reset",
            headers={"x-buildwealth-workspace-id": DEMO_HOUSEHOLD_WORKSPACE_ID},
        )
        real_response = client.get(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEFAULT_HOUSEHOLD_WORKSPACE_ID},
        )
        demo_response = client.get(
            "/api/financial-profile",
            headers={"x-buildwealth-workspace-id": DEMO_HOUSEHOLD_WORKSPACE_ID},
        )
        blocked_reset = client.post(
            f"/api/workspaces/{DEFAULT_HOUSEHOLD_WORKSPACE_ID}/demo/reset",
            headers={"x-buildwealth-workspace-id": DEFAULT_HOUSEHOLD_WORKSPACE_ID},
        )

    assert real_update.status_code == 200
    assert reset_response.status_code == 200
    assert reset_response.json()["summary"]["profile_household_members"] == 3
    assert real_response.json()["notes"] == "do not touch real workspace"
    assert len(demo_response.json()["household_members"]) == 3
    assert demo_response.json()["tax_profile"]["filing_status"] == "married_filing_jointly"
    assert blocked_reset.status_code == 400
