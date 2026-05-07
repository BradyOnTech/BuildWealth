from pathlib import Path
import asyncio

import httpx
import pytest
from fastapi import HTTPException
import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.user_settings import MASKED_PLACEHOLDER, UserSettingsStore


def test_settings_probe_payload_clears_masked_key_on_provider_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save(
        {
            "llm_provider": "openai",
            "llm_api_key": "sk-openai",
            "llm_model": "gpt-5-mini",
            "llm_base_url": "https://api.openai.com/v1",
        }
    )
    monkeypatch.setattr(main, "user_settings_store", store)

    payload, explicit_keys = main._settings_payload_for_probe(
        {
            "llm_provider": "anthropic",
            "llm_api_key": MASKED_PLACEHOLDER + "enai",
        }
    )

    assert payload["llm_provider"] == "anthropic"
    assert payload["llm_api_key"] == ""
    assert payload["llm_base_url"] == "https://api.anthropic.com/v1"
    assert payload["llm_model"] == "claude-opus-4-7"
    assert "llm_base_url" in explicit_keys


def test_settings_probe_payload_replaces_stale_provider_default_base_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save(
        {
            "llm_provider": "openai",
            "llm_api_key": "sk-openai",
            "llm_model": "gpt-5-mini",
            "llm_base_url": "https://api.openai.com/v1",
        }
    )
    monkeypatch.setattr(main, "user_settings_store", store)

    payload, explicit_keys = main._settings_payload_for_probe(
        {
            "llm_provider": "anthropic",
            "llm_api_key": "sk-ant",
            "llm_model": "gpt-5-mini",
            "llm_base_url": "https://api.openai.com/v1",
        }
    )
    config = main._llm_config_from_payload(payload, explicit_keys=explicit_keys)

    assert config.provider == "anthropic"
    assert config.model == "claude-opus-4-7"
    assert config.base_url == "https://api.anthropic.com/v1"
    assert config.api_key == "sk-ant"


def test_settings_probe_payload_keeps_custom_openai_compatible_base_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save(
        {
            "llm_provider": "custom_openai_compatible",
            "llm_api_key": "sk-custom",
            "llm_model": "custom-model",
            "llm_base_url": "http://localhost:11434/v1",
        }
    )
    monkeypatch.setattr(main, "user_settings_store", store)

    payload, explicit_keys = main._settings_payload_for_probe({})
    config = main._llm_config_from_payload(payload, explicit_keys=explicit_keys)

    assert config.provider == "custom_openai_compatible"
    assert config.model == "custom-model"
    assert config.base_url == "http://localhost:11434/v1"


def test_test_llm_settings_returns_probe_success(monkeypatch) -> None:
    async def fake_probe(_client):
        return {
            "ok": True,
            "provider": "openai",
            "model": "gpt-5.5",
            "stage": "complete",
            "detail": "ok",
            "tool_calls": [{"name": "echo_tool"}],
            "answer": "ECHO_VALUE=7",
        }

    monkeypatch.setattr(main, "run_tool_call_probe", fake_probe)

    result = asyncio.run(main.test_llm_settings({"llm_api_key": "sk-test"}))

    assert result["ok"] is True
    assert result["stage"] == "complete"


def test_test_llm_settings_raises_400_for_probe_failure(monkeypatch) -> None:
    async def fake_probe(_client):
        return {
            "ok": False,
            "provider": "openai",
            "model": "gpt-5.5",
            "stage": "tool_call",
            "detail": "The model did not request the probe tool.",
            "tool_calls": [],
            "answer": "",
        }

    monkeypatch.setattr(main, "run_tool_call_probe", fake_probe)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.test_llm_settings({"llm_api_key": "sk-test"}))

    assert exc.value.status_code == 400
    assert exc.value.detail["stage"] == "tool_call"


def test_test_llm_settings_raises_502_for_provider_http_error(monkeypatch) -> None:
    async def fake_probe(_client):
        request = httpx.Request("POST", "https://api.example.test/v1/chat/completions")
        response = httpx.Response(401, request=request, text="bad key")
        raise httpx.HTTPStatusError("bad key", request=request, response=response)

    monkeypatch.setattr(main, "run_tool_call_probe", fake_probe)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.test_llm_settings({"llm_api_key": "sk-test"}))

    assert exc.value.status_code == 502
    assert exc.value.detail["stage"] == "provider_http_error"
    assert "bad key" in exc.value.detail["detail"]
