from __future__ import annotations

from copy import copy
from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import (
    ControlPlaneStore,
    DEFAULT_HOUSEHOLD_WORKSPACE_ID,
    DEMO_HOUSEHOLD_WORKSPACE_ID,
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
