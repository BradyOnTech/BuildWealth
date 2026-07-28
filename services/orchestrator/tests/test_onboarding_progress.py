from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.onboarding_progress import OnboardingProgressStore
from buildwealth_orchestrator.services.onboarding_reset import OnboardingResetService


def test_onboarding_progress_does_not_start_existing_workspaces_implicitly(tmp_path) -> None:
    path = tmp_path / "onboarding" / "progress.json"
    store = OnboardingProgressStore(path)

    state = store.get()

    assert state["started"] is False
    assert state["needs_setup"] is False
    assert state["status"] == "not_started"
    assert not path.exists()


def test_onboarding_progress_starts_and_resumes_from_disk(tmp_path) -> None:
    path = tmp_path / "onboarding" / "progress.json"
    store = OnboardingProgressStore(path)

    started = store.start()
    advanced = store.update(
        completed_step="welcome",
        current_step="foundation",
    )
    resumed = OnboardingProgressStore(path).get()

    assert started["current_step"] == "welcome"
    assert started["needs_setup"] is True
    assert advanced["completed_steps"] == ["welcome"]
    assert advanced["current_step"] == "foundation"
    assert resumed == advanced


def test_onboarding_progress_keeps_skips_distinct_from_financial_completion(tmp_path) -> None:
    store = OnboardingProgressStore(tmp_path / "onboarding" / "progress.json")
    store.start()

    skipped = store.update(skipped_step="portfolio", current_step="future")
    completed = store.update(completed_step="portfolio")

    assert skipped["skipped_steps"] == ["portfolio"]
    assert "portfolio" not in skipped["completed_steps"]
    assert completed["completed_steps"] == ["portfolio"]
    assert completed["skipped_steps"] == []


def test_onboarding_progress_completion_is_durable(tmp_path) -> None:
    path = tmp_path / "onboarding" / "progress.json"
    store = OnboardingProgressStore(path)
    store.start()

    completed = store.update(completed_step="first_picture", complete=True)
    raw = json.loads(path.read_text(encoding="utf-8"))

    assert completed["status"] == "complete"
    assert completed["needs_setup"] is False
    assert completed["completed_at"]
    assert raw["status"] == "complete"


def test_onboarding_progress_rejects_unknown_steps(tmp_path) -> None:
    store = OnboardingProgressStore(tmp_path / "onboarding" / "progress.json")
    store.start()

    with pytest.raises(ValueError, match="Unknown onboarding step"):
        store.update(current_step="taxes")


def test_onboarding_progress_routes_are_workspace_scoped(tmp_path) -> None:
    services = SimpleNamespace(
        paths=SimpleNamespace(root=tmp_path / "workspace-a"),
        context=SimpleNamespace(
            permissions={"workspace.read", "profile.write"},
            user_id="user-a",
            organization_id="org-a",
            workspace_id="workspace-a",
        ),
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    try:
        with TestClient(main.app) as client:
            initial = client.get("/api/onboarding/progress")
            started = client.post("/api/onboarding/progress/start")
            advanced = client.patch(
                "/api/onboarding/progress",
                json={"completed_step": "welcome", "current_step": "foundation"},
            )
            invalid = client.patch(
                "/api/onboarding/progress",
                json={"current_step": "taxes"},
            )
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert initial.status_code == 200
    assert initial.json()["started"] is False
    assert started.status_code == 200
    assert started.json()["needs_setup"] is True
    assert advanced.status_code == 200
    assert advanced.json()["current_step"] == "foundation"
    assert invalid.status_code == 400
    assert (tmp_path / "workspace-a" / "onboarding" / "progress.json").exists()


def test_onboarding_reset_archives_live_data_and_restarts_setup(tmp_path) -> None:
    root = tmp_path / "workspaces" / "workspace-a"
    backup_dir = root / "backups"
    profile_path = root / "profile" / "financial_profile.json"
    plan_path = root / "plans" / "active_plan.json"
    profile_path.parent.mkdir(parents=True)
    plan_path.parent.mkdir(parents=True)
    profile_path.write_text('{"household_members":[{"name":"Taylor"}]}', encoding="utf-8")
    plan_path.write_text('{"name":"Current plan"}', encoding="utf-8")
    progress_store = OnboardingProgressStore(root / "onboarding" / "progress.json")
    progress_store.start()
    progress_store.update(completed_step="first_picture", complete=True)

    service = OnboardingResetService(data_root=root, backup_dir=backup_dir)
    preview = service.preview()
    result = service.reset()

    assert preview["file_count"] == 3
    assert result["identity_preserved"] is True
    assert result["files_cleared"] == 3
    assert not profile_path.exists()
    assert not plan_path.exists()
    assert result["progress"]["status"] == "active"
    assert result["progress"]["current_step"] == "welcome"
    assert result["progress"]["completed_steps"] == []
    assert (backup_dir / f"buildwealth-backup-{result['backup_id']}.tar.gz").exists()


def test_onboarding_reset_routes_preserve_owner_identity_and_require_confirmation(tmp_path) -> None:
    root = tmp_path / "workspaces" / "workspace-a"
    profile_path = root / "profile" / "financial_profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text('{"income_items":[{"monthly_amount_usd":8000}]}', encoding="utf-8")
    identity_path = tmp_path / "control-plane-owner.json"
    identity_path.write_text('{"email":"owner@example.test"}', encoding="utf-8")
    services = SimpleNamespace(
        paths=SimpleNamespace(
            root=root,
            backup_archive_dir=root / "backups",
        ),
        context=SimpleNamespace(
            permissions={"account.delete"},
            user_id="user-a",
            organization_id="org-a",
            workspace_id="workspace-a",
            role="owner",
            is_demo_workspace=False,
        ),
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    try:
        with TestClient(main.app) as client:
            preview = client.get("/api/onboarding/reset/preview")
            rejected = client.post(
                "/api/onboarding/reset",
                json={"confirm": "reset"},
            )
            profile_survived_rejection = profile_path.exists()
            reset = client.post(
                "/api/onboarding/reset",
                json={"confirm": "reset and register again"},
            )
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

    assert preview.status_code == 200
    assert preview.json()["confirmation_phrase"] == "reset and register again"
    assert rejected.status_code == 400
    assert profile_survived_rejection is True
    assert reset.status_code == 200
    assert reset.json()["identity_preserved"] is True
    assert reset.json()["next_path"] == "/v2#setup"
    assert identity_path.read_text(encoding="utf-8") == '{"email":"owner@example.test"}'
    assert not profile_path.exists()
    restarted = OnboardingProgressStore(root / "onboarding" / "progress.json").get()
    assert restarted["needs_setup"] is True
    assert restarted["current_step"] == "welcome"
