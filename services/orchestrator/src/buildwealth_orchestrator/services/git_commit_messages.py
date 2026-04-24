"""Commit message helpers for BuildWealth Git checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def manual_checkpoint_message() -> str:
    return "Update BuildWealth versioned workspace"


def autogit_checkpoint_message(*, event_type: str) -> str:
    event_label = event_type.replace("_", " ").strip().title() or "Domain Event"
    return f"AutoGit checkpoint: {event_label}"


def checkpoint_commit_body(*, event_type: str = "manual_checkpoint") -> str:
    return "\n".join(
        [
            f"Event: {event_type}",
            f"Generated-At: {utc_now_iso()}",
        ]
    )
