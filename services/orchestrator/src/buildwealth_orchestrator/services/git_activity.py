"""Durable append-only activity feed for BuildWealth Git actions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GitActivityStore:
    def __init__(self, activity_path: Path):
        self.activity_path = activity_path
        self.activity_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event_type: str,
        title: str,
        message: str = "",
        status: str = "ok",
        ref: str | None = None,
        paths: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": f"git-activity-{uuid.uuid4().hex[:12]}",
            "created_at": utc_now_iso(),
            "event_type": str(event_type or "git_event").strip().lower(),
            "title": str(title or "Git activity").strip(),
            "message": str(message or "").strip(),
            "status": str(status or "ok").strip().lower(),
            "ref": str(ref).strip() if ref else None,
            "paths": [
                str(path).strip()
                for path in (paths or [])
                if path is not None and str(path).strip()
            ],
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        with self.activity_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str, sort_keys=True))
            handle.write("\n")
        return event

    def list(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        status: str | None = None,
        ref: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.activity_path.exists():
            return []
        bounded_limit = max(1, min(int(limit), 500))
        cleaned_event_type = str(event_type or "").strip().lower()
        cleaned_status = str(status or "").strip().lower()
        cleaned_ref = str(ref or "").strip()
        rows: list[dict[str, Any]] = []
        for line in reversed(self.activity_path.read_text(encoding="utf-8").splitlines()):
            if len(rows) >= bounded_limit:
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if cleaned_event_type and str(event.get("event_type") or "").lower() != cleaned_event_type:
                continue
            if cleaned_status and str(event.get("status") or "").lower() != cleaned_status:
                continue
            if cleaned_ref and str(event.get("ref") or "") != cleaned_ref:
                continue
            rows.append(event)
        return rows
