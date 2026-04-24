from __future__ import annotations

import json
from pathlib import Path

from buildwealth_orchestrator.services.git_checkpoint import GitCheckpointService
from buildwealth_orchestrator.services.git_repository import GitRepositoryService
from buildwealth_orchestrator.services.versioned_workspace import (
    VersionedWorkspacePolicy,
    VersionedWorkspaceService,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_checkpoint_service(tmp_path: Path) -> tuple[GitCheckpointService, Path]:
    data_root = tmp_path / "data"
    workspace_dir = data_root / "versioned"
    plans_dir = data_root / "plans"
    recommendations_path = data_root / "recommendations" / "inbox.json"
    review_packet_dir = data_root / "reports" / "portfolio_review_packets"

    _write_json(plans_dir / "index.json", {"plans": []})
    _write_json(recommendations_path, {"recommendations": []})
    review_packet_dir.mkdir(parents=True, exist_ok=True)

    workspace_service = VersionedWorkspaceService(
        workspace_dir=workspace_dir,
        plans_dir=plans_dir,
        recommendations_path=recommendations_path,
        review_packet_dir=review_packet_dir,
    )
    return (
        GitCheckpointService(
            workspace_service=workspace_service,
            git_repository=GitRepositoryService(workspace_dir),
        ),
        recommendations_path,
    )


def test_git_checkpoint_initializes_and_commits_materialized_workspace(tmp_path: Path) -> None:
    service, _ = _build_checkpoint_service(tmp_path)

    init_result = service.initialize(VersionedWorkspacePolicy())
    checkpoint = service.checkpoint(policy=VersionedWorkspacePolicy())

    assert init_result["status"] == "initialized"
    assert checkpoint["status"] == "committed"
    assert checkpoint["commit"]["message"] == "Update BuildWealth versioned workspace"
    assert checkpoint["sections"]["recommendations"] == 1


def test_git_checkpoint_reports_nothing_to_commit_after_stable_export(tmp_path: Path) -> None:
    service, _ = _build_checkpoint_service(tmp_path)
    service.initialize(VersionedWorkspacePolicy())
    service.checkpoint(policy=VersionedWorkspacePolicy())

    second = service.checkpoint(policy=VersionedWorkspacePolicy())

    assert second["status"] == "nothing_to_commit"


def test_git_checkpoint_commits_after_source_materially_changes(tmp_path: Path) -> None:
    service, recommendations_path = _build_checkpoint_service(tmp_path)
    service.initialize(VersionedWorkspacePolicy())
    service.checkpoint(policy=VersionedWorkspacePolicy())
    _write_json(
        recommendations_path,
        {
            "recommendations": [
                {
                    "id": "rec-alpha",
                    "title": "Alpha",
                    "status": "proposed",
                }
            ]
        },
    )

    checkpoint = service.checkpoint(policy=VersionedWorkspacePolicy(), event_type="recommendation_created")

    assert checkpoint["status"] == "committed"
    assert checkpoint["sections"]["recommendations"] == 2
