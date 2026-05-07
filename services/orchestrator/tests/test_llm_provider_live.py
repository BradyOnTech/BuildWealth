import asyncio
import os

import pytest

from buildwealth_orchestrator.services.llm_clients import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_XAI_BASE_URL,
    DEFAULT_XAI_MODEL,
    LLMProviderConfig,
    build_llm_client,
    run_tool_call_probe,
)


def _provider_cases() -> list[tuple[str, str, str, str, str]]:
    return [
        ("openai", "OPENAI_API_KEY", DEFAULT_OPENAI_MODEL, DEFAULT_OPENAI_BASE_URL, "OpenAI"),
        ("gemini", "GEMINI_API_KEY", DEFAULT_GEMINI_MODEL, DEFAULT_GEMINI_BASE_URL, "Gemini"),
        ("anthropic", "ANTHROPIC_API_KEY", DEFAULT_ANTHROPIC_MODEL, DEFAULT_ANTHROPIC_BASE_URL, "Anthropic"),
        ("xai", "XAI_API_KEY", DEFAULT_XAI_MODEL, DEFAULT_XAI_BASE_URL, "xAI"),
    ]


def _generic_provider_case() -> tuple[str, str, str] | None:
    provider = os.getenv("LLM_PROVIDER")
    api_key = os.getenv("LLM_API_KEY")
    if not provider or not api_key:
        return None
    defaults = {
        "openai": (DEFAULT_OPENAI_MODEL, DEFAULT_OPENAI_BASE_URL),
        "gemini": (DEFAULT_GEMINI_MODEL, DEFAULT_GEMINI_BASE_URL),
        "anthropic": (DEFAULT_ANTHROPIC_MODEL, DEFAULT_ANTHROPIC_BASE_URL),
        "xai": (DEFAULT_XAI_MODEL, DEFAULT_XAI_BASE_URL),
    }
    model, base_url = defaults.get(provider, (os.getenv("LLM_MODEL", ""), os.getenv("LLM_BASE_URL", "")))
    return (
        provider,
        os.getenv("LLM_MODEL", model),
        os.getenv("LLM_BASE_URL", base_url),
    )


@pytest.mark.parametrize(
    ("provider", "env_key", "model", "base_url", "label"),
    _provider_cases(),
)
def test_live_provider_tool_call_probe(provider: str, env_key: str, model: str, base_url: str, label: str) -> None:
    api_key = os.getenv(env_key)
    if not api_key:
        pytest.skip(f"{env_key} is not configured")

    client = build_llm_client(
        LLMProviderConfig(
            provider=provider,
            api_key=api_key,
            model=os.getenv(f"{env_key.removesuffix('_API_KEY')}_MODEL", model),
            base_url=os.getenv(f"{env_key.removesuffix('_API_KEY')}_BASE_URL", base_url),
            timeout_seconds=90.0,
            max_tokens=512,
        )
    )

    result = asyncio.run(run_tool_call_probe(client))

    assert result["ok"], f"{label} probe failed: {result}"
    assert result["tool_calls"], f"{label} did not produce a tool call: {result}"
    assert "ECHO_VALUE=7" in result["answer"]


def test_live_generic_llm_tool_call_probe() -> None:
    generic = _generic_provider_case()
    if generic is None:
        pytest.skip("LLM_PROVIDER and LLM_API_KEY are not configured")
    provider, model, base_url = generic

    client = build_llm_client(
        LLMProviderConfig(
            provider=provider,
            api_key=os.environ["LLM_API_KEY"],
            model=model,
            base_url=base_url,
            timeout_seconds=90.0,
            max_tokens=512,
        )
    )

    result = asyncio.run(run_tool_call_probe(client))

    assert result["ok"], f"Generic LLM probe failed: {result}"
    assert result["tool_calls"], f"Generic LLM did not produce a tool call: {result}"
    assert "ECHO_VALUE=7" in result["answer"]
