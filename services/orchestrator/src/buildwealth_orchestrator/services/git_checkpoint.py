"""Checkpoint orchestration for BuildWealth versioned workspaces."""

from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.git_commit_messages import (
    checkpoint_commit_body,
    manual_checkpoint_message,
)
from buildwealth_orchestrator.services.git_repository import GitRepositoryService
from buildwealth_orchestrator.services.versioned_workspace import (
    VersionedWorkspacePolicy,
    VersionedWorkspaceService,
)


class GitCheckpointService:
    def __init__(
        self,
        *,
        workspace_service: VersionedWorkspaceService,
        git_repository: GitRepositoryService,
    ):
        self.workspace_service = workspace_service
        self.git_repository = git_repository

    def initialize(self, policy: VersionedWorkspacePolicy) -> dict[str, Any]:
        self.workspace_service.materialize(policy)
        return self.git_repository.init_repo()

    def checkpoint(
        self,
        *,
        policy: VersionedWorkspacePolicy,
        event_type: str = "manual_checkpoint",
        message: str | None = None,
    ) -> dict[str, Any]:
        export_result = self.workspace_service.materialize(policy)
        commit_result = self.git_repository.commit(
            message=message or manual_checkpoint_message(),
            body=checkpoint_commit_body(event_type=event_type),
        )
        return {
            "status": commit_result["status"],
            "message": commit_result["message"],
            "workspace_dir": export_result.workspace_dir,
            "files_written": export_result.files_written,
            "files_removed": export_result.files_removed,
            "sections": export_result.sections,
            "commit": commit_result.get("commit"),
        }
