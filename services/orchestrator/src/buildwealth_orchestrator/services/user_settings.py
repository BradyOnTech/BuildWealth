"""Legacy single-user settings store for local-only compatibility paths."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MASKED_PLACEHOLDER = "••••••••"
VISIBLE_SUFFIX_LEN = 4

LLM_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "llm_model": "gpt-5.5",
        "llm_base_url": "https://api.openai.com/v1",
    },
    "gemini": {
        "llm_model": "gemini-3.1-flash-lite",
        "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    "anthropic": {
        "llm_model": "claude-opus-4-7",
        "llm_base_url": "https://api.anthropic.com/v1",
    },
    "xai": {
        "llm_model": "grok-4.20-reasoning-latest",
        "llm_base_url": "https://api.x.ai/v1",
    },
    "custom_openai_compatible": {
        "llm_model": "",
        "llm_base_url": "",
    },
}

LEGACY_LLM_PROVIDER_DEFAULT_MODELS: dict[str, set[str]] = {
    "openai": {"gpt-5-mini"},
    "gemini": {"gemini-2.5-flash"},
    "anthropic": {"claude-sonnet-4-5"},
    "xai": {"grok-4-latest", "grok-4.20-reasoning"},
}


def provider_default_model_ids(provider: str) -> set[str]:
    defaults = LLM_PROVIDER_DEFAULTS.get(provider, LLM_PROVIDER_DEFAULTS["openai"])
    models = {str(defaults["llm_model"])}
    models.update(LEGACY_LLM_PROVIDER_DEFAULT_MODELS.get(provider, set()))
    return models


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

    Keys are stored in plaintext for legacy single-user paths only. Workspace
    Settings flows use WorkspaceSettingsStore and encrypted workspace secrets.
    API responses mask sensitive values.
    """

    SENSITIVE_KEYS = {"openai_api_key", "llm_api_key"}

    DEFAULTS: dict[str, Any] = {
        "llm_provider": "openai",
        "llm_api_key": "",
        "llm_model": "gpt-5.5",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_timeout_seconds": 60.0,
        "llm_max_tokens": 2048,
        "llm_parallel_tool_calls": True,
        "openai_api_key": "",
        "openai_model": "gpt-5.5",
        "openai_base_url": "https://api.openai.com/v1",
        # Context-intelligence / embedding provider. Optional; falls back to
        # env defaults set on the Settings object when missing or empty.
        "context_embeddings_enabled": False,
        "context_embedding_provider": "disabled",
        "context_embedding_model": "nomic-embed-text",
        "context_embedding_base_url": "http://localhost:11434",
        "context_embedding_timeout_seconds": 5.0,
    }

    ALLOWED_KEYS = frozenset((*DEFAULTS.keys(), "updated_at", "llm_settings_saved_at", "context_settings_saved_at"))

    def __init__(self, settings_path: Path):
        self.settings_path = settings_path
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self._write({"updated_at": datetime.now(timezone.utc).isoformat()})

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
        data = self.load_stored_raw()
        merged = self._sanitize({**self.DEFAULTS, **data})
        if "llm_api_key" not in data and merged.get("openai_api_key"):
            merged["llm_api_key"] = merged["openai_api_key"]
        if "llm_model" not in data and merged.get("openai_model"):
            merged["llm_model"] = merged["openai_model"]
        if "llm_base_url" not in data and merged.get("openai_base_url"):
            merged["llm_base_url"] = merged["openai_base_url"]
        return merged

    def load_stored_raw(self) -> dict[str, Any]:
        """Load only values actually persisted in the local settings file."""
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            key: value
            for key, value in data.items()
            if key in self.ALLOWED_KEYS
        }

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
        saved_at = datetime.now(timezone.utc).isoformat()
        requested_provider = str(updates.get("llm_provider") or current.get("llm_provider") or "openai")
        current_provider = str(current.get("llm_provider") or "openai")
        provider_changed = "llm_provider" in updates and requested_provider != current_provider

        if provider_changed:
            previous_defaults = LLM_PROVIDER_DEFAULTS.get(current_provider, LLM_PROVIDER_DEFAULTS["openai"])
            next_defaults = LLM_PROVIDER_DEFAULTS.get(requested_provider, LLM_PROVIDER_DEFAULTS["openai"])
            if "llm_model" not in updates and current.get("llm_model") in {
                "",
                *provider_default_model_ids(current_provider),
            }:
                current["llm_model"] = next_defaults["llm_model"]
            if "llm_base_url" not in updates and current.get("llm_base_url") in {"", previous_defaults["llm_base_url"]}:
                current["llm_base_url"] = next_defaults["llm_base_url"]
            if "llm_api_key" not in updates or _is_masked(updates.get("llm_api_key")):
                current["llm_api_key"] = ""

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

        if any(key.startswith("llm_") or key.startswith("openai_") for key in updates):
            current["llm_settings_saved_at"] = saved_at
        if any(key.startswith("context_embedding") or key == "context_embeddings_enabled" for key in updates):
            current["context_settings_saved_at"] = saved_at
        current["updated_at"] = saved_at
        current = self._sanitize(current)
        self._write(current)
        return current
