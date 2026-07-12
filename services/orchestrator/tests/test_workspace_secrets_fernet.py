from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets as pysecrets
from pathlib import Path

import pytest

from buildwealth_orchestrator.services.workspace_settings import (
    SECRET_KEY_ENV_VAR,
    SECRET_KEY_FILE_ENV_VAR,
    WorkspaceSecretStore,
    load_or_create_local_secret_key,
    resolve_local_secret_key_with_source,
)


def _legacy_encrypt(secret_key: bytes, value: str) -> dict[str, str]:
    """Reproduce the retired HMAC-keystream cipher to seed legacy entries."""
    nonce = pysecrets.token_bytes(16)
    plaintext = value.encode("utf-8")
    blocks: list[bytes] = []
    counter = 0
    while sum(len(b) for b in blocks) < len(plaintext):
        blocks.append(hmac.new(secret_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    keystream = b"".join(blocks)[: len(plaintext)]
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream, strict=True))
    tag = hmac.new(secret_key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        "tag": base64.urlsafe_b64encode(tag).decode("ascii"),
    }


def test_new_secrets_are_fernet_tokens(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "key")
    store = WorkspaceSecretStore(tmp_path / "secrets.json", key)
    store.set_secret("llm_api_key", "sk-test-abcd1234")

    raw = json.loads((tmp_path / "secrets.json").read_text())
    entry = raw["secrets"]["llm_api_key"]
    assert "token" in entry
    assert "ciphertext" not in entry
    assert "sk-test-abcd1234" not in json.dumps(raw)
    assert store.get_secret("llm_api_key") == "sk-test-abcd1234"


def test_legacy_hmac_entries_migrate_to_fernet_on_load(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "key")
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "secrets": {
                    "llm_api_key": {
                        **_legacy_encrypt(key, "sk-legacy-value-9876"),
                        "last4": "9876",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                },
            }
        )
    )

    store = WorkspaceSecretStore(secrets_path, key)
    assert store.get_secret("llm_api_key") == "sk-legacy-value-9876"

    migrated = json.loads(secrets_path.read_text())
    entry = migrated["secrets"]["llm_api_key"]
    assert "token" in entry
    assert "ciphertext" not in entry
    assert entry["last4"] == "9876"
    assert entry["migrated_at"]
    assert migrated["schema_version"] == 2


def test_rotation_reencrypts_with_fernet(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "key")
    store = WorkspaceSecretStore(tmp_path / "secrets.json", key)
    store.set_secret("llm_api_key", "sk-rotate-me-4321")

    new_key = b"2" * 32
    result = store.rotate_key(new_key)
    assert result["rotated"] is True

    rotated_store = WorkspaceSecretStore(tmp_path / "secrets.json", new_key)
    assert rotated_store.get_secret("llm_api_key") == "sk-rotate-me-4321"
    entry = json.loads((tmp_path / "secrets.json").read_text())["secrets"]["llm_api_key"]
    assert "token" in entry


def test_secret_key_env_var_wins_and_must_be_valid(tmp_path: Path) -> None:
    key_bytes = b"3" * 32
    env = {SECRET_KEY_ENV_VAR: base64.urlsafe_b64encode(key_bytes).decode("ascii")}
    key, source = resolve_local_secret_key_with_source(tmp_path / "unused-key", env=env)
    assert key == key_bytes
    assert source == "env"
    assert not (tmp_path / "unused-key").exists()

    with pytest.raises(ValueError):
        resolve_local_secret_key_with_source(tmp_path / "k", env={SECRET_KEY_ENV_VAR: "not-b64!!"})
    with pytest.raises(ValueError):
        resolve_local_secret_key_with_source(
            tmp_path / "k",
            env={SECRET_KEY_ENV_VAR: base64.urlsafe_b64encode(b"short").decode("ascii")},
        )


def test_secret_key_file_override(tmp_path: Path) -> None:
    override = tmp_path / "outside" / "key"
    env = {SECRET_KEY_FILE_ENV_VAR: str(override)}
    key, source = resolve_local_secret_key_with_source(tmp_path / "data-key", env=env)
    assert source == "file_override"
    assert override.exists()
    assert not (tmp_path / "data-key").exists()
    key_again, _ = resolve_local_secret_key_with_source(tmp_path / "data-key", env=env)
    assert key_again == key
