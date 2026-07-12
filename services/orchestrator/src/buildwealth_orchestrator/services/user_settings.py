"""Legacy single-user settings store for local-only compatibility paths."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services import llm_clients as llm_client_defaults

# Imported lazily in methods that need vault helpers to avoid circular imports
# at module load (llm_provider_vault imports LLM_PROVIDER_DEFAULTS from here).

MASKED_PLACEHOLDER = "••••••••"
VISIBLE_SUFFIX_LEN = 4

# Derived from llm_clients defaults — the single source of truth.
LLM_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "llm_model": llm_client_defaults.DEFAULT_OPENAI_MODEL,
        "llm_base_url": llm_client_defaults.DEFAULT_OPENAI_BASE_URL,
    },
    "gemini": {
        "llm_model": llm_client_defaults.DEFAULT_GEMINI_MODEL,
        "llm_base_url": llm_client_defaults.DEFAULT_GEMINI_BASE_URL,
    },
    "anthropic": {
        "llm_model": llm_client_defaults.DEFAULT_ANTHROPIC_MODEL,
        "llm_base_url": llm_client_defaults.DEFAULT_ANTHROPIC_BASE_URL,
    },
    "xai": {
        "llm_model": llm_client_defaults.DEFAULT_XAI_MODEL,
        "llm_base_url": llm_client_defaults.DEFAULT_XAI_BASE_URL,
    },
    "openrouter": {
        "llm_model": llm_client_defaults.DEFAULT_OPENROUTER_MODEL,
        "llm_base_url": llm_client_defaults.DEFAULT_OPENROUTER_BASE_URL,
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
    "xai": {
        "grok-4-latest",
        "grok-4.20-reasoning",
        "grok-4.20-reasoning-latest",
        "grok-4.20-0309-reasoning",
    },
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

    Multi-vendor: ``llm_provider_api_keys`` maps provider id → API key so several
    vendors can stay connected. ``llm_api_key`` mirrors the active provider.
    """

    SENSITIVE_KEYS = {"openai_api_key", "llm_api_key", "llm_provider_api_keys"}

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
        "llm_provider_api_keys": {},
        "llm_provider_prefs": {},
        # Context-intelligence / embedding provider. Optional; falls back to
        # env defaults set on the Settings object when missing or empty.
        "context_embeddings_enabled": False,
        "context_embedding_provider": "disabled",
        "context_embedding_model": "nomic-embed-text",
        "context_embedding_base_url": "http://localhost:11434",
        "context_embedding_timeout_seconds": 5.0,
        # Per-task LLM routing overrides. Empty = inherit the primary
        # llm_provider/llm_model/llm_base_url above (see llm_routing.py).
        "llm_task_chat_provider": "",
        "llm_task_chat_model": "",
        "llm_task_chat_base_url": "",
        "llm_task_summarize_provider": "",
        "llm_task_summarize_model": "",
        "llm_task_summarize_base_url": "",
        "llm_task_extract_provider": "",
        "llm_task_extract_model": "",
        "llm_task_extract_base_url": "",
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

    @staticmethod
    def _normalize_provider_keys(raw: Any) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for provider, key in raw.items():
            pid = str(provider or "").strip().lower()
            value = str(key or "").strip()
            if pid and value:
                out[pid] = value
        return out

    def get_provider_api_key(self, provider: str) -> str:
        raw = self.load_raw()
        pid = str(provider or "").strip().lower()
        keys = self._normalize_provider_keys(raw.get("llm_provider_api_keys"))
        if pid in keys:
            return keys[pid]
        active = str(raw.get("llm_provider") or "openai").strip().lower()
        if pid == active:
            return str(raw.get("llm_api_key") or "")
        if pid == "openai":
            return str(raw.get("openai_api_key") or "")
        return ""

    def connected_providers_payload(self) -> list[dict[str, Any]]:
        from buildwealth_orchestrator.services.llm_provider_vault import (
            known_llm_providers,
            normalize_provider_prefs,
            prefs_for_provider,
            provider_is_connected,
        )

        raw = self.load_raw()
        active = str(raw.get("llm_provider") or "openai").strip().lower()
        keys = self._normalize_provider_keys(raw.get("llm_provider_api_keys"))
        prefs = normalize_provider_prefs(raw.get("llm_provider_prefs"))
        out: list[dict[str, Any]] = []
        for provider in known_llm_providers():
            pref = prefs_for_provider(prefs, provider)
            has_key = bool(keys.get(provider))
            connected = provider_is_connected(
                provider=provider,
                has_api_key=has_key,
                base_url=pref.get("base_url") or "",
            )
            defaults = LLM_PROVIDER_DEFAULTS.get(provider, {})
            out.append(
                {
                    "id": provider,
                    "label": provider,
                    "connected": connected,
                    "configured": has_key,
                    "last4": (keys[provider][-4:] if has_key and len(keys[provider]) >= 4 else None),
                    "is_active_default": provider == active,
                    "default_model": pref.get("model") or defaults.get("llm_model") or "",
                    "default_base_url": pref.get("base_url") or defaults.get("llm_base_url") or "",
                }
            )
        return out

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

        keys = self._normalize_provider_keys(merged.get("llm_provider_api_keys"))
        active = str(merged.get("llm_provider") or "openai").strip().lower()
        # Migrate single llm_api_key into the multi-vendor map.
        active_key = str(merged.get("llm_api_key") or "").strip()
        if active_key and active not in keys:
            keys[active] = active_key
        openai_key = str(merged.get("openai_api_key") or "").strip()
        if openai_key and "openai" not in keys:
            keys["openai"] = openai_key
        merged["llm_provider_api_keys"] = keys
        merged["llm_api_key"] = keys.get(active) or active_key or ""
        if "openai" in keys:
            merged["openai_api_key"] = keys["openai"]

        from buildwealth_orchestrator.services.llm_provider_vault import normalize_provider_prefs

        merged["llm_provider_prefs"] = normalize_provider_prefs(merged.get("llm_provider_prefs"))
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
        for key in ("openai_api_key", "llm_api_key"):
            if key in masked and masked[key]:
                masked[key] = _mask(masked[key])
                masked[f"{key}_configured"] = True
                value = str(raw.get(key) or "")
                masked[f"{key}_last4"] = value[-VISIBLE_SUFFIX_LEN:] if len(value) >= VISIBLE_SUFFIX_LEN else value
            else:
                masked[f"{key}_configured"] = False
                masked[f"{key}_last4"] = None
        keys = self._normalize_provider_keys(raw.get("llm_provider_api_keys"))
        masked.pop("llm_provider_api_keys", None)
        masked["llm_provider_keys_meta"] = {
            provider: {
                "configured": True,
                "last4": value[-VISIBLE_SUFFIX_LEN:] if len(value) >= VISIBLE_SUFFIX_LEN else value,
            }
            for provider, value in keys.items()
        }
        connected = self.connected_providers_payload()
        try:
            from buildwealth_orchestrator.services.llm_model_catalog import get_provider_entry

            for item in connected:
                entry = get_provider_entry(item["id"]) or {}
                item["label"] = entry.get("label") or item["id"]
                item["hint"] = entry.get("hint") or ""
        except Exception:
            pass
        masked["llm_connected_providers"] = connected
        return masked

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge updates into stored settings. Ignores masked values (unchanged fields).

        Returns the full saved settings (raw, for hot-reload).
        """
        from buildwealth_orchestrator.services.llm_provider_vault import (
            merge_provider_pref,
            normalize_provider_prefs,
            prefs_for_provider,
        )

        current = self.load_raw()
        saved_at = datetime.now(timezone.utc).isoformat()
        requested_provider = str(
            updates.get("llm_provider") or current.get("llm_provider") or "openai"
        ).strip().lower()
        current_provider = str(current.get("llm_provider") or "openai").strip().lower()
        provider_changed = "llm_provider" in updates and requested_provider != current_provider
        keys = self._normalize_provider_keys(current.get("llm_provider_api_keys"))
        prefs = normalize_provider_prefs(current.get("llm_provider_prefs"))

        if provider_changed:
            prefs = merge_provider_pref(
                prefs,
                current_provider,
                model=str(current.get("llm_model") or ""),
                base_url=str(current.get("llm_base_url") or ""),
            )
            next_defaults = LLM_PROVIDER_DEFAULTS.get(requested_provider, LLM_PROVIDER_DEFAULTS["openai"])
            next_prefs = prefs_for_provider(prefs, requested_provider)
            if "llm_model" not in updates and current.get("llm_model") in {
                "",
                *provider_default_model_ids(current_provider),
            }:
                current["llm_model"] = next_prefs.get("model") or next_defaults["llm_model"]
            if "llm_base_url" not in updates and current.get("llm_base_url") in {
                "",
                LLM_PROVIDER_DEFAULTS.get(current_provider, LLM_PROVIDER_DEFAULTS["openai"])["llm_base_url"],
            }:
                current["llm_base_url"] = next_prefs.get("base_url") or next_defaults["llm_base_url"]
            # Multi-vendor: keep other providers' keys; surface the new provider's key.
            if "llm_api_key" not in updates or _is_masked(updates.get("llm_api_key")):
                current["llm_api_key"] = keys.get(requested_provider) or ""

        for key, value in updates.items():
            if key == "updated_at":
                continue
            if key not in self.DEFAULTS:
                continue
            if key == "llm_provider_api_keys":
                if isinstance(value, dict):
                    keys = self._normalize_provider_keys(value)
                continue
            if key == "llm_provider_prefs":
                prefs = normalize_provider_prefs(value)
                continue
            if key in {"openai_api_key", "llm_api_key"} and _is_masked(value):
                continue
            if value is not None:
                current[key] = value

        final_provider = str(current.get("llm_provider") or requested_provider).strip().lower()
        # Apply explicit key write to the target provider slot.
        if "llm_api_key" in updates and not _is_masked(updates.get("llm_api_key")):
            new_key = str(updates.get("llm_api_key") or "").strip()
            if new_key:
                keys[final_provider] = new_key
            else:
                keys.pop(final_provider, None)
        if "openai_api_key" in updates and not _is_masked(updates.get("openai_api_key")):
            new_key = str(updates.get("openai_api_key") or "").strip()
            if new_key:
                keys["openai"] = new_key
            else:
                keys.pop("openai", None)

        prefs = merge_provider_pref(
            prefs,
            final_provider,
            model=str(current.get("llm_model") or ""),
            base_url=str(current.get("llm_base_url") or ""),
        )
        current["llm_provider_api_keys"] = keys
        current["llm_provider_prefs"] = prefs
        current["llm_api_key"] = keys.get(final_provider) or ""
        if "openai" in keys:
            current["openai_api_key"] = keys["openai"]

        if any(key.startswith("llm_") or key.startswith("openai_") for key in updates):
            current["llm_settings_saved_at"] = saved_at
        if any(key.startswith("context_embedding") or key == "context_embeddings_enabled" for key in updates):
            current["context_settings_saved_at"] = saved_at
        current["updated_at"] = saved_at
        current = self._sanitize(current)
        self._write(current)
        return current
