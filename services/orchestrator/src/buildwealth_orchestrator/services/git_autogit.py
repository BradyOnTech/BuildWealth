"""Domain-event AutoGit debounce and execution state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.git_checkpoint import GitCheckpointService
from buildwealth_orchestrator.services.git_commit_messages import autogit_checkpoint_message
from buildwealth_orchestrator.services.versioned_workspace import VersionedWorkspacePolicy


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _idle_seconds(policy: dict[str, Any]) -> int:
    try:
        return max(30, min(int(policy.get("auto_checkpoint_idle_seconds") or 180), 86_400))
    except (TypeError, ValueError):
        return 180


def _autogit_active(policy: dict[str, Any]) -> bool:
    return bool(policy.get("enabled")) and bool(policy.get("autogit_enabled"))


class GitAutoGitService:
    def __init__(
        self,
        *,
        state_path: Path,
        checkpoint_service: GitCheckpointService,
    ):
        self.state_path = state_path
        self.checkpoint_service = checkpoint_service
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def state(self, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._load()
        if policy is not None:
            state["enabled"] = bool(policy.get("enabled"))
            state["autogit_enabled"] = bool(policy.get("autogit_enabled"))
            state["auto_checkpoint_idle_seconds"] = _idle_seconds(policy)
        return state

    def record_event(
        self,
        *,
        policy: dict[str, Any],
        event_type: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        state = self.state(policy=policy)
        cleaned_event_type = str(event_type or "").strip()
        if not cleaned_event_type:
            return state
        if not _autogit_active(policy):
            return state

        timestamp = now or utc_now()
        pending = state.get("pending_event")
        event_count = 1
        first_seen_at = _iso(timestamp)
        if isinstance(pending, dict):
            event_count = int(pending.get("event_count") or 0) + 1
            first_seen_at = str(pending.get("first_seen_at") or first_seen_at)

        state["pending_event"] = {
            "event_type": cleaned_event_type,
            "event_count": event_count,
            "first_seen_at": first_seen_at,
            "last_seen_at": _iso(timestamp),
            "due_at": _iso(timestamp + timedelta(seconds=_idle_seconds(policy))),
        }
        self._write(state)
        return state

    def run_due(
        self,
        *,
        policy: dict[str, Any],
        workspace_policy: VersionedWorkspacePolicy,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        state = self.state(policy=policy)
        pending = state.get("pending_event")
        if not isinstance(pending, dict):
            state["status"] = "idle"
            return state
        if not _autogit_active(policy):
            state["status"] = "disabled"
            return state

        timestamp = now or utc_now()
        due_at = _parse_iso(pending.get("due_at"))
        if due_at is None or due_at > timestamp:
            state["status"] = "pending"
            return state

        event_type = str(pending.get("event_type") or "domain_event")
        event_count = int(pending.get("event_count") or 1)
        try:
            checkpoint = self.checkpoint_service.checkpoint(
                policy=workspace_policy,
                event_type=f"autogit:{event_type}",
                message=autogit_checkpoint_message(event_type=event_type),
            )
            result = {
                "status": checkpoint.get("status") or "unknown",
                "message": checkpoint.get("message") or "AutoGit checkpoint evaluated.",
                "event_type": event_type,
                "event_count": event_count,
                "ran_at": _iso(timestamp),
                "commit": checkpoint.get("commit"),
            }
        except Exception as exc:
            result = {
                "status": "failed",
                "message": str(exc),
                "event_type": event_type,
                "event_count": event_count,
                "ran_at": _iso(timestamp),
                "commit": None,
            }

        state["pending_event"] = None
        state["last_result"] = result
        state["status"] = result["status"]
        self._write(state)
        return state

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        pending = data.get("pending_event")
        last_result = data.get("last_result")
        return {
            "enabled": False,
            "autogit_enabled": False,
            "auto_checkpoint_idle_seconds": 180,
            "pending_event": pending if isinstance(pending, dict) else None,
            "last_result": last_result if isinstance(last_result, dict) else None,
            "status": str(data.get("status") or "idle"),
        }

    def _write(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
