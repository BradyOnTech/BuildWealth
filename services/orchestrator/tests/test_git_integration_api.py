from __future__ import annotations

import json
from pathlib import Path
import subprocess

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import (
    GitCheckpointRequest,
    GitPolicyUpdateRequest,
    GitRemoteConnectRequest,
    GitRemoteOperationRequest,
    GitRestoreApplyRequest,
    PlanCreateRequest,
    RecommendationCreateRequest,
)
from buildwealth_orchestrator.services.git_integration_settings import GitIntegrationSettingsStore
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_review_packets import PortfolioReviewPacketStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_bare_remote(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True, text=True)
    return path


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
    monkeypatch.setattr(main, "plan_workspace", PlanWorkspace(plans_dir))
    monkeypatch.setattr(main, "recommendation_inbox", RecommendationInbox(recommendations_path))
    monkeypatch.setattr(main, "portfolio_review_packet_store", PortfolioReviewPacketStore(review_packet_dir))
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
    (workspace_dir / "recommendations" / "index.json").write_text(
        json.dumps({"recommendations": [{"id": "changed"}]}, indent=2),
        encoding="utf-8",
    )
    restore_preview = main.get_git_restore_preview(
        ref=history.commits[0].hash,
        path="recommendations/index.json",
    )

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
    assert restore_preview.read_only is True
    assert restore_preview.files[0].path == "recommendations/index.json"
    assert restore_preview.files[0].status == "modified"
    assert (workspace_dir / "recommendations" / "index.json").exists()


def test_git_restore_apply_restores_selected_plan_file_through_service(monkeypatch, tmp_path: Path) -> None:
    _configure_git_api_fixture(monkeypatch, tmp_path)
    main.update_git_policy(GitPolicyUpdateRequest(enabled=True))
    plan = main.create_plan(PlanCreateRequest(title="Restore Plan", description="Original"))
    plan_id = plan.id
    main.plan_workspace.update_plan_files(plan_id, plan_markdown="# Historical plan\n")

    main.initialize_git_repository()
    old_checkpoint = main.create_git_checkpoint(GitCheckpointRequest(message="Historical checkpoint"))
    old_hash = old_checkpoint.commit.hash

    main.plan_workspace.update_plan_files(plan_id, plan_markdown="# Current plan\n")
    main.create_git_checkpoint(GitCheckpointRequest(message="Current checkpoint"))
    preview = main.get_git_restore_preview(ref=old_hash, path=f"plans/{plan_id}/plan.md")
    result = main.apply_git_restore(
        GitRestoreApplyRequest(
            ref=old_hash,
            paths=[f"plans/{plan_id}/plan.md"],
            confirmation="APPLY_GIT_RESTORE",
        )
    )
    restored = main.plan_workspace.get_plan(plan_id)

    assert preview.files[0].status == "modified"
    assert result.status == "applied"
    assert result.applied_files == 1
    assert result.before_checkpoint is not None
    assert result.after_checkpoint is not None
    assert restored["files"]["plan_markdown"] == "# Historical plan\n"


def test_git_restore_apply_requires_confirmation(monkeypatch, tmp_path: Path) -> None:
    _configure_git_api_fixture(monkeypatch, tmp_path)
    main.initialize_git_repository()
    checkpoint = main.create_git_checkpoint(GitCheckpointRequest())

    try:
        main.apply_git_restore(
            GitRestoreApplyRequest(
                ref=checkpoint.commit.hash,
                paths=["recommendations/index.json"],
                confirmation="nope",
            )
        )
    except main.HTTPException as exc:
        assert exc.status_code == 400
        assert "confirmation phrase" in str(exc.detail)
    else:
        raise AssertionError("restore apply should require confirmation phrase")


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


def test_git_remote_api_connects_and_pushes_empty_remote(monkeypatch, tmp_path: Path) -> None:
    _configure_git_api_fixture(monkeypatch, tmp_path)
    remote = _create_bare_remote(tmp_path / "remote.git")

    main.initialize_git_repository()
    main.create_git_checkpoint(GitCheckpointRequest())
    connect = main.connect_git_remote(
        GitRemoteConnectRequest(remote_url=str(remote), remote_name="origin")
    )
    status = main.get_git_status()
    push = main.push_git_remote(GitRemoteOperationRequest(remote_name="origin"))

    assert connect.status == "connected"
    assert status.remote is not None
    assert status.remote.has_remote is True
    assert status.remote.url == str(remote)
    assert push.status == "pushed"
