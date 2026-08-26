from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import buildwealth_orchestrator.main as main


class _FakeConnectionService:
    def list_connections(self) -> dict[str, object]:
        return {
            "enabled": True,
            "configured": True,
            "provider": "plaid",
            "items": [
                {
                    "connection_id": "conn_household_1",
                    "institution_name": "Hills Bank",
                    "status": "active",
                }
            ],
        }

    async def create_link_token(self, *, user_id: str) -> dict[str, object]:
        assert user_id == "user_household_owner"
        return {
            "provider": "plaid",
            "link_token": "link-sandbox-safe-for-browser",
            "expires_at": "2026-08-25T23:59:00+00:00",
        }

    async def exchange_public_token(
        self,
        *,
        user_id: str,
        public_token: str,
        institution: dict[str, object] | None,
    ) -> dict[str, object]:
        assert user_id == "user_household_owner"
        assert public_token == "public-sandbox-one-use"
        assert institution == {"institution_id": "ins_110476", "name": "Hills Bank"}
        return {
            "connection": {
                "connection_id": "conn_household_1",
                "institution_name": "Hills Bank",
                "status": "pending_review",
            },
            "preview": {
                "accounts": [
                    {
                        "provider_account_id": "opaque-account-id",
                        "name": "Individual Brokerage",
                        "suggested_buildwealth_account_id": None,
                    }
                ]
            },
        }

    def get_preview(self, connection_id: str) -> dict[str, object]:
        assert connection_id == "conn_household_1"
        return {
            "connection_id": connection_id,
            "accounts": [
                {
                    "provider_account_id": "opaque-account-id",
                    "name": "Individual Brokerage",
                    "suggested_buildwealth_account_id": None,
                }
            ],
        }

    async def activate_connection(
        self,
        *,
        connection_id: str,
        accounts: list[dict[str, object]],
    ) -> dict[str, object]:
        assert connection_id == "conn_household_1"
        assert accounts == [
            {
                "provider_account_id": "opaque-account-id",
                "include": True,
                "buildwealth_account_id": None,
            }
        ]
        return {
            "connection": {
                "connection_id": connection_id,
                "status": "active",
            },
            "report": {"accounts_created": 1, "accounts_confirmed": 0},
        }

    async def sync_connection(
        self, *, connection_id: str, trigger: str
    ) -> dict[str, object]:
        assert connection_id == "conn_household_1"
        assert trigger == "manual"
        return {
            "connection": {"connection_id": connection_id, "status": "active"},
            "change_summary": {"holdings_added": 0, "holdings_removed": 0},
        }

    async def create_update_link_token(
        self, *, connection_id: str, user_id: str
    ) -> dict[str, object]:
        assert connection_id == "conn_household_1"
        assert user_id == "user_household_owner"
        return {
            "provider": "plaid",
            "link_token": "link-update-mode",
            "expires_at": "2026-08-26T00:15:00+00:00",
        }

    def disconnect_preview(self, connection_id: str) -> dict[str, object]:
        assert connection_id == "conn_household_1"
        return {
            "connection_id": connection_id,
            "choices": ["keep_frozen", "remove_connected_data"],
            "affected_counts": {"accounts": 1, "holdings": 2},
        }

    async def disconnect_connection(
        self, *, connection_id: str, retention: str
    ) -> dict[str, object]:
        assert connection_id == "conn_household_1"
        assert retention == "keep_frozen"
        return {
            "connection": {"connection_id": connection_id, "status": "disconnected"},
            "retention": retention,
            "remote_access_removed": True,
        }


def _workspace_services(*, permissions: set[str]):
    return SimpleNamespace(
        context=SimpleNamespace(
            user_id="user_household_owner",
            organization_id="org_household",
            workspace_id="ws_household",
            role="owner",
            permissions=frozenset(permissions),
            is_demo_workspace=False,
            auth_mode="test",
        )
    )


def test_household_member_can_list_read_only_financial_connections(monkeypatch) -> None:
    services = _workspace_services(permissions={"connections.read"})
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(
        main,
        "financial_connection_service_for_workspace",
        lambda _services: _FakeConnectionService(),
        raising=False,
    )
    try:
        with TestClient(main.app) as client:
            response = client.get("/api/connections")
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "configured": True,
        "provider": "plaid",
        "items": [
            {
                "connection_id": "conn_household_1",
                "institution_name": "Hills Bank",
                "status": "active",
            }
        ],
    }


def test_listing_connections_requires_explicit_connection_permission(monkeypatch) -> None:
    services = _workspace_services(permissions={"portfolio.read"})
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(
        main,
        "financial_connection_service_for_workspace",
        lambda _services: _FakeConnectionService(),
        raising=False,
    )
    try:
        with TestClient(main.app) as client:
            response = client.get("/api/connections")
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing permission: connections.read"


def test_owner_can_create_short_lived_plaid_link_token(monkeypatch) -> None:
    services = _workspace_services(permissions={"connections.write"})
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(
        main,
        "financial_connection_service_for_workspace",
        lambda _services: _FakeConnectionService(),
        raising=False,
    )
    try:
        with TestClient(main.app) as client:
            response = client.post("/api/connections/plaid/link-token")
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert response.status_code == 200
    assert response.json() == {
        "provider": "plaid",
        "link_token": "link-sandbox-safe-for-browser",
        "expires_at": "2026-08-25T23:59:00+00:00",
    }


def test_public_token_exchange_returns_review_preview_without_echoing_token(monkeypatch) -> None:
    services = _workspace_services(permissions={"connections.write"})
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(
        main,
        "financial_connection_service_for_workspace",
        lambda _services: _FakeConnectionService(),
        raising=False,
    )
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/api/connections/plaid/exchange",
                json={
                    "public_token": "public-sandbox-one-use",
                    "institution": {
                        "institution_id": "ins_110476",
                        "name": "Hills Bank",
                    },
                },
            )
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"]["status"] == "pending_review"
    assert payload["preview"]["accounts"][0]["provider_account_id"] == "opaque-account-id"
    assert "public-sandbox-one-use" not in response.text


def test_initial_preview_requires_explicit_account_activation(monkeypatch) -> None:
    services = _workspace_services(
        permissions={"connections.read", "connections.write"}
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(
        main,
        "financial_connection_service_for_workspace",
        lambda _services: _FakeConnectionService(),
        raising=False,
    )
    try:
        with TestClient(main.app) as client:
            preview_response = client.get(
                "/api/connections/conn_household_1/preview"
            )
            activate_response = client.post(
                "/api/connections/conn_household_1/activate",
                json={
                    "accounts": [
                        {
                            "provider_account_id": "opaque-account-id",
                            "include": True,
                            "buildwealth_account_id": None,
                        }
                    ]
                },
            )
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert preview_response.status_code == 200
    assert preview_response.json()["accounts"][0]["suggested_buildwealth_account_id"] is None
    assert activate_response.status_code == 200
    assert activate_response.json()["connection"]["status"] == "active"
    assert activate_response.json()["report"]["accounts_created"] == 1


def test_active_connection_supports_check_repair_and_safe_disconnect(monkeypatch) -> None:
    services = _workspace_services(
        permissions={"connections.read", "connections.write"}
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    monkeypatch.setattr(
        main,
        "financial_connection_service_for_workspace",
        lambda _services: _FakeConnectionService(),
        raising=False,
    )
    try:
        with TestClient(main.app) as client:
            sync_response = client.post(
                "/api/connections/conn_household_1/sync"
            )
            repair_response = client.post(
                "/api/connections/conn_household_1/update-link-token"
            )
            preview_response = client.post(
                "/api/connections/conn_household_1/disconnect-preview"
            )
            disconnect_response = client.request(
                "DELETE",
                "/api/connections/conn_household_1",
                json={"retention": "keep_frozen"},
            )
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert sync_response.status_code == 200
    assert sync_response.json()["connection"]["status"] == "active"
    assert repair_response.status_code == 200
    assert repair_response.json()["link_token"] == "link-update-mode"
    assert preview_response.status_code == 200
    assert preview_response.json()["choices"] == [
        "keep_frozen",
        "remove_connected_data",
    ]
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["remote_access_removed"] is True
    assert disconnect_response.json()["retention"] == "keep_frozen"


def test_plaid_webhook_passes_exact_raw_body_and_verification_token(monkeypatch) -> None:
    raw_body = (
        b'{"webhook_type":"INVESTMENTS_TRANSACTIONS",'
        b'"webhook_code":"HOLDINGS_DEFAULT_UPDATE","item_id":"item-opaque"}'
    )

    async def fake_handle(*, body: bytes, verification_token: str):
        assert body == raw_body
        assert verification_token == "signed-jwt"
        return {"accepted": True, "scheduled": True}

    monkeypatch.setattr(main, "handle_plaid_webhook", fake_handle, raising=False)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/webhooks/plaid",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "plaid-verification": "signed-jwt",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "scheduled": True}
