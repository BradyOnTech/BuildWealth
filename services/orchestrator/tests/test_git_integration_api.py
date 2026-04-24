from __future__ import annotations

import json
from pathlib import Path

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import (
    GitCheckpointRequest,
    GitPolicyUpdateRequest,
    PlanCreateRequest,
    RecommendationCreateRequest,
)
from buildwealth_orchestrator.services.git_integration_settings import GitIntegrationSettingsStore


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _configure_git_api_fixture(monkeypatch, tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    workspace_dir = data_root / "versioned"
    plans_dir = data_root / "plans"
    recommendations_path = data_root / "recommendations" / "inbox.json"
    review_packet_dir = data_root / "reports" / "portfolio_review_packets"
    protection_policy_path = data_root / "security" / "protection_policy.json"
    financial_profile_path = data_root / "profile" / "financial_profile.json"

    _write_json(plans_dir / "index.json", {"plans": []})
    _write_json(recommendations_path, {"recommendations": []})
    _write_json(protection_policy_path, {"level": "standard"})
    _write_json(financial_profile_path, {"schema_version": 2})
    review_packet_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main.settings, "versioned_workspace_dir", workspace_dir)
    monkeypatch.setattr(main.settings, "git_integration_settings_path", data_root / "settings" / "git.json")
    monkeypatch.setattr(main.settings, "plans_dir", plans_dir)
    monkeypatch.setattr(main.settings, "recommendations_path", recommendations_path)
    monkeypatch.setattr(main.settings, "portfolio_review_packet_dir", review_packet_dir)
    monkeypatch.setattr(main.settings, "protection_policy_path", protection_policy_path)
    monkeypatch.setattr(main.settings, "financial_profile_path", financial_profile_path)
    monkeypatch.setattr(
        main,
        "git_integration_settings_store",
        GitIntegrationSettingsStore(
            data_root / "settings" / "git_integration.json",
            default_workspace_dir=workspace_dir,
        ),
    )
    return workspace_dir


def test_git_policy_api_persists_updates(monkeypatch, tmp_path: Path) -> None:
    workspace_dir = _configure_git_api_fixture(monkeypatch, tmp_path)

    updated = main.update_git_policy(
        GitPolicyUpdateRequest(enabled=True, include_financial_profile=True)
    )
    loaded = main.get_git_policy()

    assert updated.enabled is True
    assert updated.include_financial_profile is True
    assert loaded.workspace_dir == str(workspace_dir)
    assert loaded.include_financial_profile is True


def test_git_api_init_status_history_and_checkpoint_flow(monkeypatch, tmp_path: Path) -> None:
    workspace_dir = _configure_git_api_fixture(monkeypatch, tmp_path)

    before_init = main.get_git_status()
    init_result = main.initialize_git_repository()
    before_checkpoint_diff = main.get_git_diff()
    checkpoint = main.create_git_checkpoint(GitCheckpointRequest())
    status = main.get_git_status()
    history = main.get_git_history()
    checkpoint_diff = main.get_git_diff(ref=history.commits[0].hash)

    assert before_init.status == "no_repo"
    assert init_result.status == "initialized"
    assert before_checkpoint_diff.status == "ok"
    assert "recommendations/index.json" in before_checkpoint_diff.diff
    assert checkpoint.status == "committed"
    assert checkpoint.commit is not None
    assert status.status == "ok"
    assert status.dirty is False
    assert history.commits[0].message == "Update BuildWealth versioned workspace"
    assert checkpoint_diff.status == "ok"
    assert "recommendations/index.json" in checkpoint_diff.diff
    assert (workspace_dir / "recommendations" / "index.json").exists()


def test_plan_create_queues_autogit_event_when_enabled(monkeypatch, tmp_path: Path) -> None:
    _configure_git_api_fixture(monkeypatch, tmp_path)

    main.update_git_policy(GitPolicyUpdateRequest(enabled=True, autogit_enabled=True))
    main.create_plan(PlanCreateRequest(title="AutoGit Plan", description="Track this"))
    state = main.get_git_autogit_state()

    assert state.pending_event is not None
    assert state.pending_event.event_type == "plan_created"
    assert state.pending_event.event_count == 1


def test_recommendation_create_queues_autogit_event_when_enabled(monkeypatch, tmp_path: Path) -> None:
    _configure_git_api_fixture(monkeypatch, tmp_path)

    main.update_git_policy(GitPolicyUpdateRequest(enabled=True, autogit_enabled=True))
    main.create_recommendation(
        RecommendationCreateRequest(
            title="Rebalance",
            detail="Trim concentration risk.",
        )
    )
    state = main.get_git_autogit_state()

    assert state.pending_event is not None
    assert state.pending_event.event_type == "recommendation_created"
    assert state.pending_event.event_count == 1
