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


class WorkspaceSettingsStore:
    """Workspace settings with sensitive provider keys delegated to WorkspaceSecretStore."""

    SENSITIVE_KEYS = {"openai_api_key", "llm_api_key"}

    DEFAULTS: dict[str, Any] = {
        "llm_provider": "openai",
        "llm_model": "gpt-5.5",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_timeout_seconds": 60.0,
        "llm_max_tokens": 2048,
        "llm_parallel_tool_calls": True,
        "openai_model": "gpt-5.5",
        "openai_base_url": "https://api.openai.com/v1",
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
        return {
            key: value
            for key, value in data.items()
            if key in self.ALLOWED_KEYS and key not in self.SENSITIVE_KEYS
        }

    def load_raw(self) -> dict[str, Any]:
        stored = self.load_stored_raw()
        merged = {**self.DEFAULTS, **stored}
        llm_secret = self.secret_store.get_secret("llm_api_key")
        openai_secret = self.secret_store.get_secret("openai_api_key")
        merged["llm_api_key"] = llm_secret or openai_secret or ""
        merged["openai_api_key"] = openai_secret or llm_secret or ""
        return merged

    def load_masked(self) -> dict[str, Any]:
        raw = self.load_raw()
        masked = dict(raw)
        for key in self.SENSITIVE_KEYS:
            metadata = self.secret_store.secret_metadata(key)
            if metadata.get("configured"):
                masked[key] = _mask_suffix(str(metadata.get("last4") or ""))
            else:
                masked[key] = ""
            masked[f"{key}_configured"] = bool(metadata.get("configured"))
            masked[f"{key}_last4"] = metadata.get("last4")
            masked[f"{key}_updated_at"] = metadata.get("updated_at")
        return masked

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.load_raw()
        stored = self.load_stored_raw()
        saved_at = utc_now_iso()
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
            if "llm_base_url" not in updates and current.get("llm_base_url") in {
                "",
                previous_defaults["llm_base_url"],
            }:
                current["llm_base_url"] = next_defaults["llm_base_url"]
            if "llm_api_key" not in updates or _is_masked(updates.get("llm_api_key")):
                self.secret_store.remove_secret("llm_api_key")
                current["llm_api_key"] = ""

        for key, value in updates.items():
            if key == "updated_at" or key not in self.ALLOWED_KEYS:
                continue
            if key in self.SENSITIVE_KEYS:
                if _is_masked(value):
                    continue
                if value:
                    self.secret_store.set_secret(key, str(value))
                else:
                    self.secret_store.remove_secret(key)
                continue
            if value is not None:
                current[key] = value

        for key in self.DEFAULTS:
            if key in current:
                stored[key] = current[key]

        if any(key.startswith("llm_") or key.startswith("openai_") for key in updates):
            stored["llm_settings_saved_at"] = saved_at
        if any(key.startswith("context_embedding") or key == "context_embeddings_enabled" for key in updates):
            stored["context_settings_saved_at"] = saved_at
        stored["updated_at"] = saved_at
        self._write(stored)
        return self.load_raw()
