from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.llm_provider_vault import (
    LEGACY_LLM_API_KEY,
    LEGACY_OPENAI_API_KEY,
    known_llm_providers,
    merge_provider_pref,
    normalize_provider_prefs,
    prefs_for_provider,
    provider_api_key_secret_name,
    provider_id_from_secret_name,
    provider_is_connected,
)
from buildwealth_orchestrator.services.user_settings import (
    LLM_PROVIDER_DEFAULTS,
    MASKED_PLACEHOLDER,
    provider_default_model_ids,
)


VISIBLE_SUFFIX_LEN = 4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_or_create_local_secret_key(secret_key_path: Path) -> bytes:
    secret_key_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_key_path.exists():
        raw = secret_key_path.read_text(encoding="utf-8").strip()
        try:
            return base64.urlsafe_b64decode(raw.encode("ascii"))
        except Exception:
            pass
    key = secrets.token_bytes(32)
    secret_key_path.write_text(base64.urlsafe_b64encode(key).decode("ascii"), encoding="utf-8")
    try:
        os.chmod(secret_key_path, 0o600)
    except OSError:
        pass
    return key


def write_local_secret_key(secret_key_path: Path, secret_key: bytes) -> None:
    secret_key_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = secret_key_path.with_suffix(secret_key_path.suffix + ".tmp")
    temp_path.write_text(base64.urlsafe_b64encode(secret_key).decode("ascii"), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(secret_key_path)


def _is_masked(value: str | None) -> bool:
    return bool(value and value.startswith(MASKED_PLACEHOLDER))


def _mask_suffix(value: str | None) -> str | None:
    if not value:
        return None
    suffix = value[-VISIBLE_SUFFIX_LEN:]
    return f"{MASKED_PLACEHOLDER}{suffix}" if suffix else MASKED_PLACEHOLDER


class WorkspaceSecretStore:
    """Workspace-scoped encrypted secret store.

    This avoids plaintext provider keys in workspace settings. It uses a local
    authenticated stream built from HMAC-SHA256 so the implementation remains
    dependency-light for the current proof of concept. Before hosted beta this
    should be replaced with a standard audited primitive or deployment KMS.
    """

    def __init__(self, secrets_path: Path, secret_key: bytes):
        self.secrets_path = secrets_path
        self.secret_key = secret_key
        self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.secrets_path.exists():
            self._write({"schema_version": 1, "secrets": {}})

    def _write(self, payload: dict[str, Any]) -> None:
        self.secrets_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.secrets_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            payload = {"schema_version": 1, "secrets": {}}
        if not isinstance(payload, dict):
            payload = {"schema_version": 1, "secrets": {}}
        if not isinstance(payload.get("secrets"), dict):
            payload["secrets"] = {}
        return payload

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        blocks: list[bytes] = []
        counter = 0
        while sum(len(block) for block in blocks) < length:
            counter_bytes = counter.to_bytes(4, "big")
            blocks.append(hmac.new(self.secret_key, nonce + counter_bytes, hashlib.sha256).digest())
            counter += 1
        return b"".join(blocks)[:length]

    def _encrypt(self, value: str) -> dict[str, str]:
        return self._encrypt_with_key(value, self.secret_key)

    @classmethod
    def _encrypt_with_key(cls, value: str, secret_key: bytes) -> dict[str, str]:
        nonce = secrets.token_bytes(16)
        plaintext = value.encode("utf-8")
        keystream = cls._keystream_for(secret_key, nonce, len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream, strict=True))
        tag = hmac.new(secret_key, nonce + ciphertext, hashlib.sha256).digest()
        return {
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            "tag": base64.urlsafe_b64encode(tag).decode("ascii"),
        }

    @staticmethod
    def _keystream_for(secret_key: bytes, nonce: bytes, length: int) -> bytes:
        blocks: list[bytes] = []
        counter = 0
        while sum(len(block) for block in blocks) < length:
            counter_bytes = counter.to_bytes(4, "big")
            blocks.append(hmac.new(secret_key, nonce + counter_bytes, hashlib.sha256).digest())
            counter += 1
        return b"".join(blocks)[:length]

    def _decrypt(self, payload: dict[str, Any]) -> str | None:
        try:
            nonce = base64.urlsafe_b64decode(str(payload["nonce"]).encode("ascii"))
            ciphertext = base64.urlsafe_b64decode(str(payload["ciphertext"]).encode("ascii"))
            tag = base64.urlsafe_b64decode(str(payload["tag"]).encode("ascii"))
        except Exception:
            return None
        expected = hmac.new(self.secret_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            return None
        keystream = self._keystream(nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream, strict=True))
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def set_secret(self, key: str, value: str) -> None:
        payload = self._read()
        encrypted = self._encrypt(value)
        payload["secrets"][key] = {
            **encrypted,
            "last4": value[-VISIBLE_SUFFIX_LEN:] if len(value) >= VISIBLE_SUFFIX_LEN else value,
            "updated_at": utc_now_iso(),
        }
        self._write(payload)

    def get_secret(self, key: str) -> str:
        payload = self._read()
        entry = payload.get("secrets", {}).get(key)
        if not isinstance(entry, dict):
            return ""
        return self._decrypt(entry) or ""

    def remove_secret(self, key: str) -> None:
        payload = self._read()
        payload.get("secrets", {}).pop(key, None)
        self._write(payload)

    def export_plaintext_secrets(self) -> dict[str, str]:
        payload = self._read()
        exported: dict[str, str] = {}
        for key, entry in payload.get("secrets", {}).items():
            if not isinstance(entry, dict):
                continue
            value = self._decrypt(entry)
            if value is None:
                raise ValueError(f"secret could not be decrypted: {key}")
            exported[str(key)] = value
        return exported

    def rotate_key(self, new_secret_key: bytes) -> dict[str, Any]:
        exported = self.export_plaintext_secrets()
        payload = self._read()
        rotated = {"schema_version": payload.get("schema_version", 1), "secrets": {}}
        now = utc_now_iso()
        for key, value in exported.items():
            rotated["secrets"][key] = {
                **self._encrypt_with_key(value, new_secret_key),
                "last4": value[-VISIBLE_SUFFIX_LEN:] if len(value) >= VISIBLE_SUFFIX_LEN else value,
                "updated_at": now,
                "rotated_at": now,
            }
        self._write(rotated)
        self.secret_key = new_secret_key
        return {"rotated": True, "secret_count": len(exported), "rotated_at": now}

    def secret_metadata(self, key: str) -> dict[str, Any]:
        payload = self._read()
        entry = payload.get("secrets", {}).get(key)
        if not isinstance(entry, dict):
            return {"configured": False, "last4": None, "updated_at": None}
        return {
            "configured": True,
            "last4": entry.get("last4"),
            "updated_at": entry.get("updated_at"),
        }

    def list_secret_keys(self) -> list[str]:
        payload = self._read()
        return [str(key) for key in (payload.get("secrets") or {})]


class WorkspaceSettingsStore:
    """Workspace settings with sensitive provider keys delegated to WorkspaceSecretStore."""

    SENSITIVE_KEYS = {LEGACY_OPENAI_API_KEY, LEGACY_LLM_API_KEY}

    DEFAULTS: dict[str, Any] = {
        "llm_provider": "openai",
        "llm_model": "gpt-5.5",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_timeout_seconds": 60.0,
        "llm_max_tokens": 2048,
        "llm_parallel_tool_calls": True,
        "openai_model": "gpt-5.5",
        "openai_base_url": "https://api.openai.com/v1",
        # Per-provider last model/base_url so switching vendors restores prefs.
        "llm_provider_prefs": {},
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

    ALLOWED_KEYS = frozenset(
        (
            *DEFAULTS.keys(),
            *SENSITIVE_KEYS,
            "updated_at",
            "llm_settings_saved_at",
            "context_settings_saved_at",
        )
    )

    def __init__(self, settings_path: Path, secret_store: WorkspaceSecretStore):
        self.settings_path = settings_path
        self.secret_store = secret_store
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self._write({"updated_at": utc_now_iso()})

    def _write(self, data: dict[str, Any]) -> None:
        self.settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_stored_raw(self) -> dict[str, Any]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        out = {
            key: value
            for key, value in data.items()
            if key in self.ALLOWED_KEYS and key not in self.SENSITIVE_KEYS
        }
        if "llm_provider_prefs" in out:
            out["llm_provider_prefs"] = normalize_provider_prefs(out.get("llm_provider_prefs"))
        return out

    def _migrate_legacy_provider_secret(self, active_provider: str) -> None:
        """One-time copy of legacy llm_api_key into a per-provider vault slot.

        Never re-attribute a legacy key to a newly selected provider once any
        per-provider slot already exists — that would leak vendor A’s key onto B.
        """
        active = str(active_provider or "openai").strip().lower()
        active_slot = provider_api_key_secret_name(active)
        if self.secret_store.get_secret(active_slot):
            return
        has_any_provider_slot = any(
            provider_id_from_secret_name(name) for name in self.secret_store.list_secret_keys()
        )
        if has_any_provider_slot:
            return
        legacy = self.secret_store.get_secret(LEGACY_LLM_API_KEY) or self.secret_store.get_secret(
            LEGACY_OPENAI_API_KEY
        )
        if legacy:
            self.secret_store.set_secret(active_slot, legacy)

    def _has_any_provider_secret_slot(self) -> bool:
        return any(
            provider_id_from_secret_name(name) for name in self.secret_store.list_secret_keys()
        )

    def get_provider_api_key(self, provider: str, *, active_provider: str | None = None) -> str:
        pid = str(provider or "").strip().lower()
        if not pid:
            return ""
        value = self.secret_store.get_secret(provider_api_key_secret_name(pid))
        if value:
            return value
        # Once multi-vendor slots exist, never fall back to the shared legacy
        # llm_api_key mirror — it may belong to a different vendor.
        if self._has_any_provider_secret_slot():
            if pid == "openai":
                # openai_api_key is vendor-specific, safe to use as openai fallback.
                return self.secret_store.get_secret(LEGACY_OPENAI_API_KEY)
            return ""
        if pid == "openai":
            openai_legacy = self.secret_store.get_secret(LEGACY_OPENAI_API_KEY)
            if openai_legacy:
                return openai_legacy
        # Pre-migration: single shared key applies only to the active provider.
        active = str(
            active_provider
            if active_provider is not None
            else (self.load_stored_raw().get("llm_provider") or self.DEFAULTS["llm_provider"])
        ).strip().lower()
        if pid == active:
            return self.secret_store.get_secret(LEGACY_LLM_API_KEY)
        return ""

    def set_provider_api_key(self, provider: str, value: str) -> None:
        pid = str(provider or "").strip().lower()
        if not pid:
            return
        slot = provider_api_key_secret_name(pid)
        if value:
            self.secret_store.set_secret(slot, value)
        else:
            self.secret_store.remove_secret(slot)

    def provider_api_keys_map(self, *, active_provider: str | None = None) -> dict[str, str]:
        active = str(
            active_provider
            if active_provider is not None
            else (self.load_stored_raw().get("llm_provider") or "openai")
        ).strip().lower()
        keys: dict[str, str] = {}
        for provider in known_llm_providers():
            value = self.get_provider_api_key(provider, active_provider=active)
            if value:
                keys[provider] = value
        # Include any extra vault slots not in the catalog defaults.
        for secret_name in self.secret_store.list_secret_keys():
            pid = provider_id_from_secret_name(secret_name)
            if pid and pid not in keys:
                value = self.secret_store.get_secret(secret_name)
                if value:
                    keys[pid] = value
        return keys

    def provider_keys_metadata(self, *, active_provider: str | None = None) -> dict[str, dict[str, Any]]:
        active = str(
            active_provider
            if active_provider is not None
            else (self.load_stored_raw().get("llm_provider") or "openai")
        ).strip().lower()
        meta: dict[str, dict[str, Any]] = {}
        for provider in known_llm_providers():
            slot = provider_api_key_secret_name(provider)
            entry = self.secret_store.secret_metadata(slot)
            if not entry.get("configured") and provider == "openai":
                legacy = self.secret_store.secret_metadata(LEGACY_OPENAI_API_KEY)
                if legacy.get("configured"):
                    entry = legacy
            meta[provider] = entry
        if active and not meta.get(active, {}).get("configured"):
            legacy = self.secret_store.secret_metadata(LEGACY_LLM_API_KEY)
            if legacy.get("configured"):
                meta[active] = legacy
        return meta

    def connected_providers_payload(self) -> list[dict[str, Any]]:
        stored = self.load_stored_raw()
        active = str(stored.get("llm_provider") or "openai").strip().lower()
        prefs = normalize_provider_prefs(stored.get("llm_provider_prefs"))
        meta = self.provider_keys_metadata(active_provider=active)
        out: list[dict[str, Any]] = []
        for provider in known_llm_providers():
            entry_meta = meta.get(provider) or {}
            pref = prefs_for_provider(prefs, provider)
            has_key = bool(entry_meta.get("configured")) or bool(
                self.get_provider_api_key(provider, active_provider=active)
            )
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
                    "last4": entry_meta.get("last4") if has_key else None,
                    "updated_at": entry_meta.get("updated_at") if has_key else None,
                    "is_active_default": provider == active,
                    "default_model": pref.get("model") or defaults.get("llm_model") or "",
                    "default_base_url": pref.get("base_url") or defaults.get("llm_base_url") or "",
                }
            )
        return out

    def load_raw(self) -> dict[str, Any]:
        stored = self.load_stored_raw()
        merged = {**self.DEFAULTS, **stored}
        active = str(merged.get("llm_provider") or "openai").strip().lower()
        self._migrate_legacy_provider_secret(active)
        prefs = normalize_provider_prefs(merged.get("llm_provider_prefs"))
        merged["llm_provider_prefs"] = prefs
        provider_keys = self.provider_api_keys_map(active_provider=active)
        merged["llm_provider_api_keys"] = provider_keys
        active_key = provider_keys.get(active) or ""
        openai_key = provider_keys.get("openai") or ""
        merged["llm_api_key"] = active_key
        merged["openai_api_key"] = openai_key or (active_key if active == "openai" else "")
        return merged

    def load_masked(self) -> dict[str, Any]:
        raw = self.load_raw()
        masked = dict(raw)
        active = str(raw.get("llm_provider") or "openai").strip().lower()
        meta = self.provider_keys_metadata()
        active_meta = meta.get(active) or {"configured": False, "last4": None, "updated_at": None}
        if active_meta.get("configured"):
            masked["llm_api_key"] = _mask_suffix(str(active_meta.get("last4") or ""))
        else:
            masked["llm_api_key"] = ""
        masked["llm_api_key_configured"] = bool(active_meta.get("configured"))
        masked["llm_api_key_last4"] = active_meta.get("last4") if active_meta.get("configured") else None
        masked["llm_api_key_updated_at"] = (
            active_meta.get("updated_at") if active_meta.get("configured") else None
        )

        openai_meta = meta.get("openai") or self.secret_store.secret_metadata(LEGACY_OPENAI_API_KEY)
        if openai_meta.get("configured"):
            masked["openai_api_key"] = _mask_suffix(str(openai_meta.get("last4") or ""))
        else:
            masked["openai_api_key"] = ""
        masked["openai_api_key_configured"] = bool(openai_meta.get("configured"))
        masked["openai_api_key_last4"] = openai_meta.get("last4") if openai_meta.get("configured") else None
        masked["openai_api_key_updated_at"] = (
            openai_meta.get("updated_at") if openai_meta.get("configured") else None
        )

        # Never expose plaintext multi-key map over the API.
        masked.pop("llm_provider_api_keys", None)
        keys_meta = {
            provider: {
                "configured": bool(entry.get("configured")),
                "last4": entry.get("last4") if entry.get("configured") else None,
                "updated_at": entry.get("updated_at") if entry.get("configured") else None,
            }
            for provider, entry in meta.items()
        }
        masked["llm_provider_keys_meta"] = keys_meta
        connected = self.connected_providers_payload()
        # Attach human labels from catalog when available.
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
        current = self.load_raw()
        stored = self.load_stored_raw()
        saved_at = utc_now_iso()
        requested_provider = str(
            updates.get("llm_provider") or current.get("llm_provider") or "openai"
        ).strip().lower()
        current_provider = str(current.get("llm_provider") or "openai").strip().lower()
        provider_changed = "llm_provider" in updates and requested_provider != current_provider
        prefs = normalize_provider_prefs(current.get("llm_provider_prefs"))

        if provider_changed:
            # Remember the outgoing provider's model/base_url, keep its key.
            prefs = merge_provider_pref(
                prefs,
                current_provider,
                model=str(current.get("llm_model") or ""),
                base_url=str(current.get("llm_base_url") or ""),
            )
            next_defaults = LLM_PROVIDER_DEFAULTS.get(requested_provider, LLM_PROVIDER_DEFAULTS["openai"])
            next_prefs = prefs_for_provider(prefs, requested_provider)
            if "llm_model" not in updates:
                if current.get("llm_model") in {
                    "",
                    *provider_default_model_ids(current_provider),
                } or next_prefs.get("model"):
                    current["llm_model"] = next_prefs.get("model") or next_defaults["llm_model"]
            if "llm_base_url" not in updates:
                previous_defaults = LLM_PROVIDER_DEFAULTS.get(
                    current_provider, LLM_PROVIDER_DEFAULTS["openai"]
                )
                if current.get("llm_base_url") in {
                    "",
                    previous_defaults["llm_base_url"],
                } or next_prefs.get("base_url"):
                    current["llm_base_url"] = (
                        next_prefs.get("base_url") or next_defaults["llm_base_url"]
                    )
            # Load the vault key for the *new* provider — do not wipe others.
            if "llm_api_key" not in updates or _is_masked(updates.get("llm_api_key")):
                current["llm_api_key"] = self.get_provider_api_key(requested_provider)

        for key, value in updates.items():
            if key == "updated_at" or key not in self.ALLOWED_KEYS:
                continue
            if key == "llm_provider_prefs":
                prefs = normalize_provider_prefs(value)
                continue
            if key in self.SENSITIVE_KEYS:
                if _is_masked(value):
                    continue
                # Write into the active (or requested) provider vault slot.
                target_provider = requested_provider
                if key == LEGACY_OPENAI_API_KEY:
                    target_provider = "openai"
                if value:
                    self.set_provider_api_key(target_provider, str(value))
                    # Keep legacy mirror in sync for active provider / openai readers.
                    if target_provider == requested_provider:
                        self.secret_store.set_secret(LEGACY_LLM_API_KEY, str(value))
                    if target_provider == "openai":
                        self.secret_store.set_secret(LEGACY_OPENAI_API_KEY, str(value))
                else:
                    self.set_provider_api_key(target_provider, "")
                    if target_provider == requested_provider:
                        self.secret_store.remove_secret(LEGACY_LLM_API_KEY)
                    if target_provider == "openai":
                        self.secret_store.remove_secret(LEGACY_OPENAI_API_KEY)
                continue
            if value is not None:
                current[key] = value

        # Persist prefs for the provider we just saved.
        final_provider = str(current.get("llm_provider") or requested_provider).strip().lower()
        # Keep legacy llm_api_key mirror aligned with the active provider only.
        active_key = self.get_provider_api_key(final_provider)
        if active_key:
            self.secret_store.set_secret(LEGACY_LLM_API_KEY, active_key)
        else:
            self.secret_store.remove_secret(LEGACY_LLM_API_KEY)
        current["llm_api_key"] = active_key
        prefs = merge_provider_pref(
            prefs,
            final_provider,
            model=str(current.get("llm_model") or ""),
            base_url=str(current.get("llm_base_url") or ""),
        )
        current["llm_provider_prefs"] = prefs

        for key in self.DEFAULTS:
            if key in current:
                stored[key] = current[key]
        stored["llm_provider_prefs"] = prefs

        if any(key.startswith("llm_") or key.startswith("openai_") for key in updates):
            stored["llm_settings_saved_at"] = saved_at
        if any(key.startswith("context_embedding") or key == "context_embeddings_enabled" for key in updates):
            stored["context_settings_saved_at"] = saved_at
        stored["updated_at"] = saved_at
        self._write(stored)
        return self.load_raw()
