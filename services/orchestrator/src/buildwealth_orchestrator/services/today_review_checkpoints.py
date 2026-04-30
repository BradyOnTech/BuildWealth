from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TodayReviewCheckpointStore:
    """Persist the latest Today review checkpoint in local JSON storage."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def latest(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict) and isinstance(payload.get("latest"), dict):
            return dict(payload["latest"])
        if isinstance(payload, dict):
            return dict(payload)
        return None

    def save(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        cleaned = {key: value for key, value in checkpoint.items() if value is not None}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"latest": cleaned}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return cleaned
