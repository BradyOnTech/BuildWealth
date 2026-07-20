"""Unit tests for the curated LLM model catalog and conversation overrides."""

from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.copilot_runtime import ConversationStore
from buildwealth_orchestrator.services.llm_clients import (
    LLMProviderConfig,
    OpenAICompatibleChatClient,
    build_llm_client,
    default_base_url_for_provider,
    default_model_for_provider,
)
from buildwealth_orchestrator.services.codex_app_server import CodexAppServerChatClient
from buildwealth_orchestrator.services.llm_model_catalog import (
    CATALOG_VERSION,
    build_llm_options_payload,
    models_for_provider,
    normalize_conversation_llm,
)
from buildwealth_orchestrator.services.user_settings import LLM_PROVIDER_DEFAULTS


def test_catalog_includes_openrouter_and_cheap_models() -> None:
    models = models_for_provider("openrouter")
    assert models
    assert any(m["id"] == "openrouter/auto" for m in models)
    assert any(m.get("cheap") for m in models)
    assert any(m["cost_band"] == "$" for m in models)
    assert "openrouter" in LLM_PROVIDER_DEFAULTS
    assert LLM_PROVIDER_DEFAULTS["openrouter"]["llm_model"] == "openrouter/auto"


def test_openrouter_client_is_openai_compatible() -> None:
    client = build_llm_client(
        LLMProviderConfig(
            provider="openrouter",
            api_key="sk-or-test",
            model="deepseek/deepseek-chat",
            base_url="https://openrouter.ai/api/v1",
        )
    )
    assert isinstance(client, OpenAICompatibleChatClient)
    assert client.provider == "openrouter"
    assert client.model == "deepseek/deepseek-chat"
    assert default_model_for_provider("openrouter") == "openrouter/auto"
    assert default_base_url_for_provider("openrouter") == "https://openrouter.ai/api/v1"


def test_codex_subscription_uses_app_server_without_an_api_base_url() -> None:
    client = build_llm_client(
        LLMProviderConfig(
            provider="codex_subscription",
            api_key='{"tokens":{"access_token":"test"}}',
            model="codex-recommended",
            base_url="",
        )
    )
    assert isinstance(client, CodexAppServerChatClient)
    assert client.enabled is True
    assert default_model_for_provider("codex_subscription") == "codex-recommended"
    assert default_base_url_for_provider("codex_subscription") == ""
    models = models_for_provider("codex_subscription")
    assert models[0]["id"] == "codex-recommended"


def test_normalize_conversation_llm_prefers_override() -> None:
    resolved = normalize_conversation_llm(
        {"provider": "xai", "model": "grok-4.5"},
        fallback_provider="openai",
        fallback_model="gpt-5.5",
    )
    assert resolved["provider"] == "xai"
    assert resolved["model"] == "grok-4.5"
    assert resolved["source"] == "conversation"
    assert resolved["cost_band"] == "$$$"
    assert resolved["label"] == "Grok 4.5"


def test_normalize_conversation_llm_falls_back_to_workspace() -> None:
    resolved = normalize_conversation_llm(
        None,
        fallback_provider="openrouter",
        fallback_model="openrouter/auto",
    )
    assert resolved["provider"] == "openrouter"
    assert resolved["model"] == "openrouter/auto"
    assert resolved["source"] == "workspace_default"
    assert resolved["cheap"] is True


def test_build_llm_options_marks_connected_provider() -> None:
    payload = build_llm_options_payload(
        active_provider="openrouter",
        active_model="deepseek/deepseek-chat",
        connected_providers=[
            {"id": "openrouter", "connected": True, "is_active_default": True},
            {"id": "openai", "connected": False, "is_active_default": False},
        ],
        conversation_llm={"provider": "openrouter", "model": "openrouter/auto"},
    )
    assert payload["catalog_version"] == CATALOG_VERSION
    assert payload["resolved"]["model"] == "openrouter/auto"
    or_entry = next(p for p in payload["providers"] if p["id"] == "openrouter")
    assert or_entry["connected"] is True
    assert or_entry["models"]


def test_conversation_store_update_llm(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "conversations")
    doc = store.create("Test")
    updated = store.update_llm(doc["id"], {"provider": "openrouter", "model": "deepseek/deepseek-chat"})
    assert updated["llm"]["provider"] == "openrouter"
    assert updated["llm"]["model"] == "deepseek/deepseek-chat"
    reloaded = store.get(doc["id"])
    assert reloaded["llm"]["model"] == "deepseek/deepseek-chat"
