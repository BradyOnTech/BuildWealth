"""Multi-vendor provider vault: several keys connected at once."""

from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.llm_provider_vault import (
    provider_api_key_secret_name,
    provider_is_connected,
)
from buildwealth_orchestrator.services.user_settings import MASKED_PLACEHOLDER, UserSettingsStore
from buildwealth_orchestrator.services.workspace_settings import (
    WorkspaceSecretStore,
    WorkspaceSettingsStore,
    load_or_create_local_secret_key,
)


def test_workspace_store_keeps_multiple_provider_keys(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "local_secret.key")
    secret_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)
    store = WorkspaceSettingsStore(tmp_path / "workspace_settings.json", secret_store)

    store.save(
        {
            "llm_provider": "openai",
            "llm_api_key": "sk-openai-1111",
            "llm_model": "gpt-5.5",
            "llm_base_url": "https://api.openai.com/v1",
        }
    )
    store.save(
        {
            "llm_provider": "xai",
            "llm_api_key": "sk-xai-2222",
            "llm_model": "grok-4.5",
            "llm_base_url": "https://api.x.ai/v1",
        }
    )
    store.save(
        {
            "llm_provider": "openrouter",
            "llm_api_key": "sk-or-3333",
            "llm_model": "openrouter/auto",
            "llm_base_url": "https://openrouter.ai/api/v1",
        }
    )

    raw = store.load_raw()
    assert raw["llm_provider"] == "openrouter"
    assert raw["llm_api_key"] == "sk-or-3333"
    assert raw["llm_provider_api_keys"]["openai"] == "sk-openai-1111"
    assert raw["llm_provider_api_keys"]["xai"] == "sk-xai-2222"
    assert raw["llm_provider_api_keys"]["openrouter"] == "sk-or-3333"

    # Switching default back to xai restores that vendor's key + prefs.
    restored = store.save({"llm_provider": "xai"})
    assert restored["llm_provider"] == "xai"
    assert restored["llm_api_key"] == "sk-xai-2222"
    assert restored["llm_model"] == "grok-4.5"
    assert restored["llm_provider_api_keys"]["openai"] == "sk-openai-1111"

    masked = store.load_masked()
    assert masked["llm_api_key_configured"] is True
    connected = [p for p in masked["llm_connected_providers"] if p["connected"]]
    ids = {p["id"] for p in connected}
    assert ids >= {"openai", "xai", "openrouter"}
    assert masked["llm_provider_keys_meta"]["openai"]["configured"] is True
    assert "sk-openai-1111" not in (tmp_path / "workspace_secrets.json").read_text(encoding="utf-8")


def test_workspace_store_provider_switch_with_masked_key_does_not_wipe_vault(
    tmp_path: Path,
) -> None:
    key = load_or_create_local_secret_key(tmp_path / "local_secret.key")
    secret_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)
    store = WorkspaceSettingsStore(tmp_path / "workspace_settings.json", secret_store)

    store.save({"llm_provider": "openai", "llm_api_key": "sk-openai-abcd"})
    saved = store.save(
        {
            "llm_provider": "anthropic",
            "llm_api_key": MASKED_PLACEHOLDER + "abcd",
        }
    )
    assert saved["llm_provider"] == "anthropic"
    assert saved["llm_api_key"] == ""
    assert saved["llm_provider_api_keys"]["openai"] == "sk-openai-abcd"
    assert secret_store.get_secret(provider_api_key_secret_name("openai")) == "sk-openai-abcd"


def test_workspace_store_migrates_legacy_llm_api_key_slot(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "local_secret.key")
    secret_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)
    secret_store.set_secret("llm_api_key", "sk-legacy-9999")
    store = WorkspaceSettingsStore(tmp_path / "workspace_settings.json", secret_store)
    store.save({"llm_provider": "openai", "llm_model": "gpt-5.5"})

    raw = store.load_raw()
    assert raw["llm_api_key"] == "sk-legacy-9999"
    assert raw["llm_provider_api_keys"]["openai"] == "sk-legacy-9999"
    assert secret_store.get_secret(provider_api_key_secret_name("openai")) == "sk-legacy-9999"


def test_user_settings_multi_vendor_map(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save({"llm_provider": "openai", "llm_api_key": "sk-oai"})
    store.save({"llm_provider": "openrouter", "llm_api_key": "sk-or"})
    raw = store.load_raw()
    assert raw["llm_provider_api_keys"]["openai"] == "sk-oai"
    assert raw["llm_provider_api_keys"]["openrouter"] == "sk-or"
    connected = [p for p in store.connected_providers_payload() if p["connected"]]
    assert {p["id"] for p in connected} >= {"openai", "openrouter"}


def test_provider_is_connected_custom_keyless() -> None:
    assert provider_is_connected(
        provider="custom_openai_compatible",
        has_api_key=False,
        base_url="http://localhost:11434/v1",
    )
    assert not provider_is_connected(
        provider="openai",
        has_api_key=False,
        base_url="https://api.openai.com/v1",
    )


def test_resolve_conversation_llm_allows_connected_cross_provider(tmp_path: Path) -> None:
    import buildwealth_orchestrator.main as main

    key = load_or_create_local_secret_key(tmp_path / "local_secret.key")
    secret_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)
    store = WorkspaceSettingsStore(tmp_path / "workspace_settings.json", secret_store)
    store.save({"llm_provider": "openai", "llm_api_key": "sk-oai", "llm_model": "gpt-5.5"})
    store.save({"llm_provider": "xai", "llm_api_key": "sk-xai", "llm_model": "grok-4.5"})
    # Leave default as xai; conversation wants openai model.
    settings = store.load_raw()
    resolved = main._resolve_conversation_llm(
        workspace_settings=settings,
        conversation_llm={"provider": "openai", "model": "gpt-4o-mini"},
        request_llm=None,
        settings_store=store,
    )
    assert resolved["provider"] == "openai"
    assert resolved["model"] == "gpt-4o-mini"
    assert resolved["source"] == "conversation"

    client = main._chat_client_for_resolved_llm(
        workspace_settings=settings,
        resolved=resolved,
        settings_store=store,
    )
    assert client.provider == "openai"
    assert client.model == "gpt-4o-mini"
    assert client.enabled is True


def test_connected_chatgpt_subscription_is_default_but_explicit_provider_still_wins(
    tmp_path: Path,
) -> None:
    import json

    import buildwealth_orchestrator.main as main

    key = load_or_create_local_secret_key(tmp_path / "local_secret.key")
    secret_store = WorkspaceSecretStore(tmp_path / "workspace_secrets.json", key)
    store = WorkspaceSettingsStore(tmp_path / "workspace_settings.json", secret_store)
    store.save({"llm_provider": "openai", "llm_api_key": "sk-oai", "llm_model": "gpt-5.5"})
    store.set_provider_api_key(
        "codex_subscription",
        json.dumps({"tokens": {"access_token": "subscription-token"}}),
    )
    settings = store.load_raw()

    default = main._resolve_conversation_llm(
        workspace_settings=settings,
        conversation_llm=None,
        request_llm=None,
        settings_store=store,
    )
    assert default["provider"] == "codex_subscription"
    assert default["model"] == "codex-recommended"

    explicit = main._resolve_conversation_llm(
        workspace_settings=settings,
        conversation_llm={"provider": "openai", "model": "gpt-5.5"},
        request_llm=None,
        settings_store=store,
    )
    assert explicit["provider"] == "openai"
    assert explicit["model"] == "gpt-5.5"

    provider_only = main._resolve_conversation_llm(
        workspace_settings=settings,
        conversation_llm=None,
        request_llm={"provider": "openai"},
        settings_store=store,
    )
    assert provider_only["provider"] == "openai"
    assert provider_only["model"] == "gpt-5.5"

    store.set_provider_api_key("codex_subscription", "")
    fallback = main._resolve_conversation_llm(
        workspace_settings=store.load_raw(),
        conversation_llm=None,
        request_llm=None,
        settings_store=store,
    )
    assert fallback["provider"] == "openai"
    assert fallback["model"] == "gpt-5.5"
