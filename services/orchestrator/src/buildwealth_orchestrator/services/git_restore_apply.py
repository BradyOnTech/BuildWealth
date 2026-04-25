"""Guarded restore-apply flow for selected versioned workspace artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from buildwealth_orchestrator.services.git_checkpoint import GitCheckpointService
from buildwealth_orchestrator.services.git_repository import GitRepositoryService
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_review_packets import PortfolioReviewPacketStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.versioned_workspace import VersionedWorkspacePolicy


RESTORE_CONFIRMATION_PHRASE = "APPLY_GIT_RESTORE"


class GitRestoreApplyError(ValueError):
    pass


@dataclass(frozen=True)
class RestoreCandidate:
    path: str
    content: str
    artifact_type: str
    artifact_id: str
    action: str
    payload: Any | None = None


class GitRestoreApplyService:
    def __init__(
        self,
        *,
        git_repository: GitRepositoryService,
        checkpoint_service: GitCheckpointService,
        workspace_policy: VersionedWorkspacePolicy,
        plan_workspace: PlanWorkspace,
        recommendation_inbox: RecommendationInbox,
        review_packet_store: PortfolioReviewPacketStore,
    ):
        self.git_repository = git_repository
        self.checkpoint_service = checkpoint_service
        self.workspace_policy = workspace_policy
        self.plan_workspace = plan_workspace
        self.recommendation_inbox = recommendation_inbox
        self.review_packet_store = review_packet_store

    def apply(
        self,
        *,
        ref: str,
        paths: list[str],
        confirmation: str,
        rationale: str | None = None,
        create_checkpoint_before_apply: bool = True,
        create_checkpoint_after_apply: bool = True,
    ) -> dict[str, Any]:
        if confirmation != RESTORE_CONFIRMATION_PHRASE:
            raise GitRestoreApplyError(
                f"Restore apply requires confirmation phrase `{RESTORE_CONFIRMATION_PHRASE}`."
            )

        cleaned_paths = self._clean_paths(paths)
        candidates = [self._candidate_from_ref(ref=ref, path=path) for path in cleaned_paths]
        reason = (rationale or f"Restored selected artifacts from Git checkpoint {ref}.").strip()

        before_checkpoint = None
        if create_checkpoint_before_apply:
            before_checkpoint = self.checkpoint_service.checkpoint(
                policy=self.workspace_policy,
                event_type="git_restore_pre_apply",
                message="Checkpoint before Git restore apply",
            )

        applied = [self._apply_candidate(candidate, rationale=reason) for candidate in candidates]

        after_checkpoint = None
        if create_checkpoint_after_apply:
            after_checkpoint = self.checkpoint_service.checkpoint(
                policy=self.workspace_policy,
                event_type="git_restore_apply",
                message="Apply selected Git restore",
            )

        return {
            "status": "applied",
            "message": f"Applied {len(applied)} selected artifact(s) from Git history through BuildWealth services.",
            "ref": ref,
            "applied_files": len(applied),
            "files": applied,
            "before_checkpoint": before_checkpoint,
            "after_checkpoint": after_checkpoint,
            "warnings": [
                "Restore apply used selected historical file content; it did not run git checkout.",
                "Unsupported exported paths are intentionally rejected until a validated service-layer flow exists.",
            ],
        }

    def _candidate_from_ref(self, *, ref: str, path: str) -> RestoreCandidate:
        content = self.git_repository.file_at_ref(ref=ref, path=path)
        if content is None:
            raise GitRestoreApplyError(
                f"Cannot restore `{path}` because it does not exist at the selected checkpoint."
            )
        return self._build_candidate(path=path, content=content)

    def _build_candidate(self, *, path: str, content: str) -> RestoreCandidate:
        parts = PurePosixPath(path).parts
        if len(parts) >= 3 and parts[0] == "plans":
            return self._plan_candidate(path=path, content=content, parts=parts)
        if len(parts) == 2 and parts[0] == "recommendations" and parts[1] != "index.json":
            payload = self._load_json(content, path)
            recommendation_id = str(payload.get("id") or PurePosixPath(parts[1]).stem).strip()
            if not recommendation_id:
                raise GitRestoreApplyError(f"Recommendation restore payload is missing an id: `{path}`.")
            payload["id"] = recommendation_id
            return RestoreCandidate(
                path=path,
                content=content,
                artifact_type="recommendation",
                artifact_id=recommendation_id,
                action="restore_recommendation",
                payload=payload,
            )
        if (
            len(parts) == 3
            and parts[0] == "reports"
            and parts[1] == "portfolio_review_packets"
            and PurePosixPath(parts[2]).suffix in {".json", ".md"}
        ):
            packet_id = PurePosixPath(parts[2]).stem
            payload = self._load_json(content, path) if path.endswith(".json") else None
            return RestoreCandidate(
                path=path,
                content=content,
                artifact_type="portfolio_review_packet",
                artifact_id=packet_id,
                action="restore_review_packet_file",
                payload=payload,
            )
        raise GitRestoreApplyError(
            f"Restore apply does not support `{path}` yet. Use plan files/settings, recommendation JSON, or review packets."
        )

    def _plan_candidate(self, *, path: str, content: str, parts: tuple[str, ...]) -> RestoreCandidate:
        if len(parts) != 3:
            raise GitRestoreApplyError(f"Restore apply supports top-level exported plan files only: `{path}`.")
        plan_id = parts[1]
        file_name = parts[2]
        json_actions = {
            "settings.json": "restore_plan_settings",
            "timeline.json": "restore_plan_timeline",
            "contribution_rules.json": "restore_plan_contribution_rules",
            "assumption_sets.json": "restore_plan_assumption_sets",
            "branch_templates.json": "restore_plan_branch_templates",
        }
        if file_name in {"plan.md", "tasks.md"}:
            return RestoreCandidate(
                path=path,
                content=content,
                artifact_type="plan",
                artifact_id=plan_id,
                action=f"restore_{file_name.replace('.', '_')}",
            )
        if file_name in json_actions:
            return RestoreCandidate(
                path=path,
                content=content,
                artifact_type="plan",
                artifact_id=plan_id,
                action=json_actions[file_name],
                payload=self._load_json(content, path),
            )
        raise GitRestoreApplyError(
            f"Restore apply does not support `{path}` yet. Plan context, decisions, YAML, and artifacts remain preview-only."
        )

    def _apply_candidate(self, candidate: RestoreCandidate, *, rationale: str) -> dict[str, str]:
        if candidate.action == "restore_plan_md":
            self.plan_workspace.update_plan_files(
                candidate.artifact_id,
                plan_markdown=candidate.content,
            )
        elif candidate.action == "restore_tasks_md":
            self.plan_workspace.update_plan_files(
                candidate.artifact_id,
                tasks_markdown=candidate.content,
            )
        elif candidate.action == "restore_plan_settings":
            self.plan_workspace.update_plan_settings(
                candidate.artifact_id,
                candidate.payload if isinstance(candidate.payload, dict) else {},
                rationale=rationale,
                status="accepted",
            )
        elif candidate.action == "restore_plan_timeline":
            self.plan_workspace.update_plan_timeline(
                candidate.artifact_id,
                candidate.payload if isinstance(candidate.payload, dict) else {},
                rationale=rationale,
                status="accepted",
            )
        elif candidate.action == "restore_plan_contribution_rules":
            self.plan_workspace.update_plan_contribution_rules(
                candidate.artifact_id,
                candidate.payload if isinstance(candidate.payload, dict) else {},
                rationale=rationale,
                status="accepted",
            )
        elif candidate.action == "restore_plan_assumption_sets":
            self.plan_workspace.update_plan_assumption_sets(
                candidate.artifact_id,
                candidate.payload if isinstance(candidate.payload, dict) else {},
                rationale=rationale,
                status="accepted",
            )
        elif candidate.action == "restore_plan_branch_templates":
            self.plan_workspace.update_plan_branch_templates(
                candidate.artifact_id,
                candidate.payload if isinstance(candidate.payload, dict) else {},
                rationale=rationale,
                status="accepted",
            )
        elif candidate.action == "restore_recommendation":
            payload = candidate.payload if isinstance(candidate.payload, dict) else {}
            self.recommendation_inbox.restore(payload)
        elif candidate.action == "restore_review_packet_file":
            self.review_packet_store.restore_file(
                file_name=PurePosixPath(candidate.path).name,
                content=candidate.content,
            )
        else:
            raise GitRestoreApplyError(f"Unsupported restore action: {candidate.action}")

        return {
            "path": candidate.path,
            "status": "applied",
            "artifact_type": candidate.artifact_type,
            "artifact_id": candidate.artifact_id,
            "action": candidate.action,
        }

    @staticmethod
    def _clean_paths(paths: list[str]) -> list[str]:
        if not paths:
            raise GitRestoreApplyError("At least one restore path is required.")
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_path in paths:
            path = str(raw_path or "").strip().replace("\\", "/").strip("/")
            if not path or path.startswith(".") or "/../" in f"/{path}/":
                raise GitRestoreApplyError(f"Invalid restore path: `{raw_path}`.")
            if path not in seen:
                cleaned.append(path)
                seen.add(path)
        if len(cleaned) > 50:
            raise GitRestoreApplyError("Restore apply is limited to 50 selected paths at a time.")
        return cleaned

    @staticmethod
    def _load_json(content: str, path: str) -> dict[str, Any]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GitRestoreApplyError(f"Historical content for `{path}` is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise GitRestoreApplyError(f"Historical content for `{path}` must be a JSON object.")
        return payload
