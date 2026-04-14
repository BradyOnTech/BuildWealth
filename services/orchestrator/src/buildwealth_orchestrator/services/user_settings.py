"""Single-user settings store for API keys and service configuration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MASKED_PLACEHOLDER = "••••••••"
VISIBLE_SUFFIX_LEN = 4


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= VISIBLE_SUFFIX_LEN:
        return MASKED_PLACEHOLDER
    return f"{MASKED_PLACEHOLDER}{value[-VISIBLE_SUFFIX_LEN:]}"


def _is_masked(value: str | None) -> bool:
    """Return True if the value looks like a masked placeholder (user didn't change it)."""
    if not value:
        return False
    return value.startswith(MASKED_PLACEHOLDER)


class UserSettingsStore:
    """Read/write user settings from a local JSON file.

    Keys are stored in plaintext (single-user, local-only app).
    API responses mask sensitive values.
    """

    SENSITIVE_KEYS = {"openai_api_key"}

    DEFAULTS: dict[str, Any] = {
        "openai_api_key": "",
        "openai_model": "gpt-5-mini",
        "openai_base_url": "https://api.openai.com/v1",
    }

    ALLOWED_KEYS = frozenset((*DEFAULTS.keys(), "updated_at"))

    def __init__(self, settings_path: Path):
        self.settings_path = settings_path
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self._write({**self.DEFAULTS, "updated_at": datetime.now(timezone.utc).isoformat()})

    def _write(self, data: dict[str, Any]) -> None:
        self.settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def _sanitize(cls, data: dict[str, Any]) -> dict[str, Any]:
        sanitized = {
            key: value
            for key, value in data.items()
            if key in cls.ALLOWED_KEYS
        }
        for key, value in cls.DEFAULTS.items():
            sanitized.setdefault(key, value)
        return sanitized

    def load_raw(self) -> dict[str, Any]:
        """Load settings with real values (for internal use by services)."""
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        merged = self._sanitize({**self.DEFAULTS, **data})
        return merged

    def load_masked(self) -> dict[str, Any]:
        """Load settings with sensitive values masked (for API responses)."""
        raw = self.load_raw()
        masked = dict(raw)
        for key in self.SENSITIVE_KEYS:
            if key in masked and masked[key]:
                masked[key] = _mask(masked[key])
        return masked

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge updates into stored settings. Ignores masked values (unchanged fields).

        Returns the full saved settings (raw, for hot-reload).
        """
        current = self.load_raw()

        for key, value in updates.items():
            if key == "updated_at":
                continue
            if key not in self.DEFAULTS:
                continue
            if key in self.SENSITIVE_KEYS and _is_masked(value):
                # User didn't change this field — keep the existing value
                continue
            if value is not None:
                current[key] = value

        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        current = self._sanitize(current)
        self._write(current)
        return current
