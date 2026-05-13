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
