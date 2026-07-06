from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from buildwealth_orchestrator.services.llm_clients import LLMProviderConfig
from buildwealth_orchestrator.services.llm_routing import (
    LLM_TASKS,
    LLMRouter,
    extract_task_overrides,
    task_routing_setting_keys,
)
from buildwealth_orchestrator.services.workspace_settings import (
    WorkspaceSecretStore,
    WorkspaceSettingsStore,
    load_or_create_local_secret_key,
)


def _primary() -> LLMProviderConfig:
    return LLMProviderConfig(
        provider="anthropic",
        api_key="sk-primary",
        model="claude-opus-4-7",
        base_url="https://api.anthropic.com/v1",
        timeout_seconds=45.0,
        max_tokens=1024,
        parallel_tool_calls=False,
    )


def test_no_overrides_every_task_uses_the_primary_config() -> None:
    router = LLMRouter(_primary())
    for task in LLM_TASKS:
        assert router.config_for(task) == _primary()
    assert all(row["inherited"] for row in router.describe())


def test_unknown_task_falls_back_to_chat() -> None:
    router = LLMRouter(_primary())
    assert router.client_for("nonsense") is router.client_for("chat")


def test_model_only_override_inherits_provider_and_key() -> None:
    router = LLMRouter(_primary(), {"summarize": {"model": "claude-haiku-4-5-20251001"}})
    config = router.config_for("summarize")
    assert config.provider == "anthropic"
    assert config.model == "claude-haiku-4-5-20251001"
    assert config.base_url == "https://api.anthropic.com/v1"
    assert config.api_key == "sk-primary"
    # Chat is untouched.
    assert router.config_for("chat") == _primary()


def test_provider_change_resets_model_and_base_url_to_provider_defaults() -> None:
    router = LLMRouter(
        _primary(),
        {"summarize": {"provider": "custom_openai_compatible", "base_url": "http://localhost:11434/v1", "model": "llama3.2"}},
    )
    config = router.config_for("summarize")
    assert config.provider == "custom_openai_compatible"
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434/v1"
    # Timeout/token limits stay household-wide.
    assert config.timeout_seconds == 45.0
    assert config.max_tokens == 1024


def test_clients_are_cached_per_task() -> None:
    router = LLMRouter(_primary(), {"summarize": {"model": "claude-haiku-4-5-20251001"}})
    assert router.client_for("chat") is router.client_for("chat")
    assert router.client_for("summarize") is router.client_for("summarize")
    assert router.client_for("chat") is not router.client_for("summarize")


def test_keyless_local_endpoint_is_enabled() -> None:
    # The point of routing background work to a local model: Ollama/LM Studio
    # via an OpenAI-compatible URL need no API key and must count as enabled.
    router = LLMRouter(
        _primary(),
        {"summarize": {"provider": "custom_openai_compatible", "base_url": "http://localhost:11434/v1", "model": "llama3.2"}},
    )
    keyless = LLMRouter(
        replace(_primary(), api_key=""),
        {"summarize": {"provider": "custom_openai_compatible", "base_url": "http://localhost:11434/v1", "model": "llama3.2"}},
    )
    assert router.client_for("summarize").enabled is True
    assert keyless.client_for("summarize").enabled is True
    # Hosted providers still require their key.
    assert keyless.client_for("chat").enabled is False


def test_extract_task_overrides_drops_blanks() -> None:
    overrides = extract_task_overrides(
        {
            "llm_task_summarize_model": "  llama3.2  ",
            "llm_task_summarize_provider": "",
            "llm_task_chat_model": None,
            "unrelated_key": "x",
        }
    )
    assert overrides == {"summarize": {"model": "llama3.2"}}


def test_routing_keys_round_trip_through_workspace_settings(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "secret.key")
    store = WorkspaceSettingsStore(
        tmp_path / "workspace_settings.json",
        WorkspaceSecretStore(tmp_path / "secrets.json", key),
    )
    for setting_key in task_routing_setting_keys():
        assert setting_key in store.DEFAULTS

    store.save({"llm_task_summarize_provider": "custom_openai_compatible", "llm_task_summarize_model": "llama3.2"})
    saved = store.load_raw()
    assert saved["llm_task_summarize_provider"] == "custom_openai_compatible"
    assert saved["llm_task_summarize_model"] == "llama3.2"
    assert extract_task_overrides(saved) == {
        "summarize": {"provider": "custom_openai_compatible", "model": "llama3.2"}
    }
