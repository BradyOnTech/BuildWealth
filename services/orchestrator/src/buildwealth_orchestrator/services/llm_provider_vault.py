"""Multi-vendor LLM provider credentials.

Auth is per *provider* (one API key each). Several providers can stay connected
at once so Copilot can switch models across vendors without re-saving keys.

Secret names in the encrypted workspace store:
  llm_api_key__{provider}   — per-provider key (source of truth)
  llm_api_key               — legacy / active-provider mirror for older readers

Non-secret prefs live in settings JSON as ``llm_provider_prefs``:
  { "xai": {"model": "grok-4.5", "base_url": "https://api.x.ai/v1"}, ... }
"""

from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.services.user_settings import LLM_PROVIDER_DEFAULTS

PROVIDER_SECRET_PREFIX = "llm_api_key__"
LEGACY_LLM_API_KEY = "llm_api_key"
LEGACY_OPENAI_API_KEY = "openai_api_key"


def known_llm_providers() -> list[str]:
    return list(LLM_PROVIDER_DEFAULTS.keys())


def provider_api_key_secret_name(provider: str) -> str:
    pid = str(provider or "").strip().lower()
    return f"{PROVIDER_SECRET_PREFIX}{pid}"


def is_provider_secret_name(key: str) -> bool:
    return str(key or "").startswith(PROVIDER_SECRET_PREFIX)


def provider_id_from_secret_name(key: str) -> str | None:
    raw = str(key or "")
    if not raw.startswith(PROVIDER_SECRET_PREFIX):
        return None
    return raw[len(PROVIDER_SECRET_PREFIX) :].strip().lower() or None


def normalize_provider_prefs(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for provider, entry in raw.items():
        pid = str(provider or "").strip().lower()
        if not pid or not isinstance(entry, dict):
            continue
        model = str(entry.get("model") or "").strip()
        base_url = str(entry.get("base_url") or "").strip()
        if model or base_url:
            out[pid] = {"model": model, "base_url": base_url}
    return out


def prefs_for_provider(
    prefs: dict[str, dict[str, str]] | None,
    provider: str,
) -> dict[str, str]:
    pid = str(provider or "").strip().lower()
    entry = (prefs or {}).get(pid) if isinstance(prefs, dict) else None
    if not isinstance(entry, dict):
        defaults = LLM_PROVIDER_DEFAULTS.get(pid, {})
        return {
            "model": str(defaults.get("llm_model") or ""),
            "base_url": str(defaults.get("llm_base_url") or ""),
        }
    defaults = LLM_PROVIDER_DEFAULTS.get(pid, {})
    return {
        "model": str(entry.get("model") or defaults.get("llm_model") or ""),
        "base_url": str(entry.get("base_url") or defaults.get("llm_base_url") or ""),
    }


def merge_provider_pref(
    prefs: dict[str, dict[str, str]],
    provider: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> dict[str, dict[str, str]]:
    pid = str(provider or "").strip().lower()
    if not pid:
        return dict(prefs)
    next_prefs = {k: dict(v) for k, v in prefs.items()}
    current = dict(next_prefs.get(pid) or {})
    if model is not None:
        current["model"] = str(model or "").strip()
    if base_url is not None:
        current["base_url"] = str(base_url or "").strip()
    if current.get("model") or current.get("base_url"):
        next_prefs[pid] = {
            "model": str(current.get("model") or ""),
            "base_url": str(current.get("base_url") or ""),
        }
    elif pid in next_prefs:
        del next_prefs[pid]
    return next_prefs


def provider_is_connected(
    *,
    provider: str,
    has_api_key: bool,
    base_url: str = "",
) -> bool:
    """Custom OpenAI-compatible can be keyless when a base URL is set."""
    pid = str(provider or "").strip().lower()
    if pid == "custom_openai_compatible":
        return has_api_key or bool(str(base_url or "").strip())
    return has_api_key
