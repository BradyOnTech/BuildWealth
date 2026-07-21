from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.onboarding_progress import OnboardingProgressStore


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
