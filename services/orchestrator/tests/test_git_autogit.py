from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.git_autogit import GitAutoGitService
from buildwealth_orchestrator.services.versioned_workspace import VersionedWorkspacePolicy


class FakeCheckpointService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def checkpoint(
        self,
        *,
        policy: VersionedWorkspacePolicy,
        event_type: str,
        message: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"policy": policy, "event_type": event_type, "message": message})
        return {
            "status": "committed",
            "message": "Versioned workspace checkpoint committed.",
            "workspace_dir": "/tmp/versioned",
            "files_written": 3,
            "files_removed": 0,
            "sections": {"plans": 1},
            "commit": {
                "hash": "abc123",
                "short_hash": "abc123",
                "date": "2026-04-24T12:00:00+00:00",
                "message": "AutoGit checkpoint: plan_updated",
            },
        }


def test_autogit_debounces_events_until_idle(tmp_path: Path) -> None:
    checkpoint_service = FakeCheckpointService()
    service = GitAutoGitService(
        state_path=tmp_path / "autogit_state.json",
        checkpoint_service=checkpoint_service,
    )
    policy = {
        "enabled": True,
        "autogit_enabled": True,
        "auto_checkpoint_idle_seconds": 30,
    }
    workspace_policy = VersionedWorkspacePolicy()
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)

    first = service.record_event(policy=policy, event_type="plan_updated", now=now)
    second = service.record_event(
        policy=policy,
        event_type="plan_updated",
        now=now + timedelta(seconds=10),
    )
    early = service.run_due(
        policy=policy,
        workspace_policy=workspace_policy,
        now=now + timedelta(seconds=39),
    )
    assert checkpoint_service.calls == []

    due = service.run_due(
        policy=policy,
        workspace_policy=workspace_policy,
        now=now + timedelta(seconds=40),
    )

    assert first["pending_event"]["event_count"] == 1
    assert second["pending_event"]["event_count"] == 2
    assert second["pending_event"]["due_at"] == "2026-04-24T12:00:40+00:00"
    assert early["status"] == "pending"
    assert due["status"] == "committed"
    assert due["pending_event"] is None
    assert due["last_result"]["event_type"] == "plan_updated"
    assert due["last_result"]["event_count"] == 2
    assert checkpoint_service.calls[0]["event_type"] == "autogit:plan_updated"
