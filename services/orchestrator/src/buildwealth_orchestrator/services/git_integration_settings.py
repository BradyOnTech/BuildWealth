"""Local settings store for BuildWealth Git integration policy."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GitIntegrationSettingsStore:
    """Read/write non-secret Git integration policy from a local JSON file."""

    DEFAULTS: dict[str, Any] = {
        "enabled": False,
        "workspace_dir": "data/versioned",
        "autogit_enabled": False,
        "auto_push_enabled": False,
        "auto_checkpoint_idle_seconds": 180,
        "remote_name": "origin",
        "include_plans": True,
        "include_recommendations": True,
        "include_review_packets": True,
        "include_snapshot_checkpoints": True,
        "include_financial_profile": False,
    }

    ALLOWED_KEYS = frozenset((*DEFAULTS.keys(), "updated_at"))

    def __init__(self, settings_path: Path, *, default_workspace_dir: Path | None = None):
        self.settings_path = settings_path
        self.default_workspace_dir = default_workspace_dir
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self._write({**self._defaults(), "updated_at": utc_now_iso()})

    def _defaults(self) -> dict[str, Any]:
        defaults = dict(self.DEFAULTS)
        if self.default_workspace_dir is not None:
            defaults["workspace_dir"] = str(self.default_workspace_dir)
        return defaults

    def _write(self, data: dict[str, Any]) -> None:
        self.settings_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def _coerce_bool(cls, value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @classmethod
    def _coerce_idle_seconds(cls, value: Any, *, default: int) -> int:
        try:
            return max(30, min(int(value), 86_400))
        except (TypeError, ValueError):
            return default

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        defaults = self._defaults()
        sanitized = {key: value for key, value in data.items() if key in self.ALLOWED_KEYS}
        for key, value in defaults.items():
            sanitized.setdefault(key, value)

        for key, default in defaults.items():
            if isinstance(default, bool):
                sanitized[key] = self._coerce_bool(sanitized.get(key), default=default)

        sanitized["auto_checkpoint_idle_seconds"] = self._coerce_idle_seconds(
            sanitized.get("auto_checkpoint_idle_seconds"),
            default=int(defaults["auto_checkpoint_idle_seconds"]),
        )
        sanitized["workspace_dir"] = str(sanitized.get("workspace_dir") or defaults["workspace_dir"])
        sanitized["remote_name"] = str(sanitized.get("remote_name") or defaults["remote_name"]).strip()
        if not sanitized["remote_name"]:
            sanitized["remote_name"] = str(defaults["remote_name"])

        if "updated_at" in sanitized and sanitized["updated_at"] is not None:
            sanitized["updated_at"] = str(sanitized["updated_at"])
        return sanitized

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return self._sanitize({**self._defaults(), **data})

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        for key, value in updates.items():
            if key == "updated_at" or key not in self.DEFAULTS:
                continue
            if value is not None:
                current[key] = value

        current["updated_at"] = utc_now_iso()
        current = self._sanitize(current)
        self._write(current)
        return current
