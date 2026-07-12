import asyncio
from pathlib import Path

from buildwealth_orchestrator.services.copilot_runtime import (
    ConversationStore,
    FinancialCopilot,
    OpenAIChatToolClient,
)
from buildwealth_orchestrator.services.llm_clients import (
    AnthropicMessagesClient,
    LLMProviderConfig,
    XAIResponsesClient,
    build_llm_client,
    run_tool_call_probe,
)
from buildwealth_orchestrator.services.user_settings import MASKED_PLACEHOLDER, UserSettingsStore


class FakeToolClient:
    def __init__(self):
        self.enabled = True
        self.model = "fake-model"
        self._calls = 0

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        del messages, tools
        self._calls += 1
        if self._calls == 1:
            return {
                "model": self.model,
                "message": {
                    "content": "Checking your data...",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "echo_tool",
                                "arguments": '{"value": 7}',
                            },
                        }
                    ],
                },
            }

        return {
            "model": self.model,
            "message": {"content": "Your account summary is ready."},
        }


class FakeProbeClient:
    provider = "fake"
    model = "fake-probe-model"
    enabled = True

    def __init__(self, raw_arguments: str = '{"value": 7}'):
        self.calls = 0
        self.raw_arguments = raw_arguments

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        del tools
        self.calls += 1
        if self.calls == 1:
            return {
                "provider": self.provider,
                "model": self.model,
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "echo_tool",
                                "arguments": self.raw_arguments,
                            },
                        }
                    ],
                },
            }
        assert messages[-1]["role"] == "tool"
        return {
            "provider": self.provider,
            "model": self.model,
            "message": {"content": "ECHO_VALUE=7"},
        }


def test_conversation_store_round_trip(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    conversation = store.get_or_create(None, "What should I rebalance first?")
    store.append_message(conversation, role="user", content="What should I rebalance first?")
    store.append_message(
        conversation,
        role="assistant",
        content="Start by reducing concentration in your top holding.",
    )
    store.save(conversation)

    loaded = store.get(conversation["id"])
    assert loaded["id"] == conversation["id"]
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["role"] == "user"
    assert loaded["messages"][1]["role"] == "assistant"

    summaries = store.list(limit=5)
    assert len(summaries) == 1
    assert summaries[0]["id"] == conversation["id"]
    assert "Start by reducing concentration" in summaries[0]["last_message_preview"]


def test_conversation_store_updates_latest_assistant_metadata(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    conversation = store.get_or_create(None, "What context did you use?")
    store.append_message(conversation, role="user", content="What context did you use?")
    store.append_message(
        conversation,
        role="assistant",
        content="I used the plan and profile.",
        metadata={"model": "fake-model"},
    )
    store.save(conversation)

    updated = store.update_latest_assistant_metadata(
        conversation["id"],
        {"context_trace": {"plan_id": "plan-1", "retrieval": {"returned_count": 3}}},
    )

    assert updated is not None
    loaded = store.get(conversation["id"])
    metadata = loaded["messages"][-1]["metadata"]
    assert metadata["model"] == "fake-model"
    assert metadata["context_trace"]["plan_id"] == "plan-1"
    assert metadata["context_trace"]["retrieval"]["returned_count"] == 3


def test_copilot_fallback_mode_persists_conversation(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    llm = OpenAIChatToolClient(api_key="", model="gpt-test", base_url="https://example.com/v1")
    copilot = FinancialCopilot(
        conversation_store=store,
        llm_client=llm,
        max_history_messages=10,
        max_tool_rounds=2,
        system_prompt="System prompt",
    )

    result = asyncio.run(
        copilot.chat(
            question="What is my current stock allocation?",
            conversation_id=None,
            contextual_brief='{"snapshot_summary":"none"}',
        )
    )

    assert "fallback mode" in result["answer"]
    assert result["tool_calls"] == []
    assert result["conversation_id"]

    loaded = store.get(result["conversation_id"])
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["role"] == "user"
    assert loaded["messages"][1]["role"] == "assistant"


def test_copilot_tool_round_trip(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    copilot = FinancialCopilot(
        conversation_store=store,
        llm_client=FakeToolClient(),
        max_history_messages=10,
        max_tool_rounds=3,
        system_prompt="System prompt",
    )

    async def echo_tool(arguments: dict) -> dict:
        return {"echo": arguments.get("value")}

    copilot.register_tool(
        name="echo_tool",
        description="Echo back a number",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
        },
        handler=echo_tool,
    )

    result = asyncio.run(
        copilot.chat(
            question="Run the echo tool",
            conversation_id=None,
            contextual_brief='{"snapshot_summary":"ok"}',
            context_trace={"plan_id": "plan-1", "retrieval": {"returned_count": 2}},
        )
    )

    assert result["answer"] == "Your account summary is ready."
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "echo_tool"
    assert result["tool_calls"][0]["result"] == {"echo": 7}
    assert result["tool_calls"][0]["error"] is None

    loaded = store.get(result["conversation_id"])
    assert loaded["messages"][-1]["metadata"]["tool_calls"][0]["name"] == "echo_tool"
    assert loaded["messages"][-1]["metadata"]["context_trace"]["plan_id"] == "plan-1"
    assert loaded["messages"][-1]["metadata"]["context_trace"]["retrieval"]["returned_count"] == 2


def test_tool_call_probe_runs_two_step_echo_loop() -> None:
    result = asyncio.run(run_tool_call_probe(FakeProbeClient()))

    assert result["ok"] is True
    assert result["stage"] == "complete"
    assert result["provider"] == "fake"
    assert result["tool_calls"] == [{"name": "echo_tool", "arguments": {"value": 7}, "ok": True}]
    assert result["answer"] == "ECHO_VALUE=7"


def test_tool_call_probe_accepts_numeric_string_argument() -> None:
    result = asyncio.run(run_tool_call_probe(FakeProbeClient(raw_arguments='{"value": "7"}')))

    assert result["ok"] is True
    assert result["stage"] == "complete"


def test_build_llm_client_selects_provider_adapters() -> None:
    assert build_llm_client(
        LLMProviderConfig(
            provider="gemini",
            api_key="key",
            model="gemini-3.1-flash-lite",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
    ).provider == "gemini"
    assert isinstance(
        build_llm_client(
            LLMProviderConfig(
                provider="anthropic",
                api_key="key",
                model="claude-opus-4-7",
                base_url="https://api.anthropic.com/v1",
            )
        ),
        AnthropicMessagesClient,
    )
    assert isinstance(
        build_llm_client(
            LLMProviderConfig(
                provider="xai",
                api_key="key",
                model="grok-4",
                base_url="https://api.x.ai/v1",
            )
        ),
        XAIResponsesClient,
    )
    openrouter = build_llm_client(
        LLMProviderConfig(
            provider="openrouter",
            api_key="key",
            model="openrouter/auto",
            base_url="https://openrouter.ai/api/v1",
        )
    )
    assert openrouter.provider == "openrouter"
    assert openrouter.model == "openrouter/auto"


def test_anthropic_adapter_converts_openai_tool_loop_messages() -> None:
    client = AnthropicMessagesClient(api_key="key", model="claude-opus-4-7")
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Run the echo tool"},
        {
            "role": "assistant",
            "content": "Checking.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "echo_tool", "arguments": '{"value": 7}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "echo_tool", "arguments": '{"value": 8}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"ok":true}'},
        {"role": "tool", "tool_call_id": "call_2", "content": '{"ok":true}'},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo_tool",
                "description": "Echo back a number",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                    "required": ["value"],
                },
            },
        }
    ]

    payload = client._build_payload(messages=messages, tools=tools)

    assert payload["system"] == "System prompt"
    assert payload["tools"] == [
        {
            "name": "echo_tool",
            "description": "Echo back a number",
            "input_schema": {
                "type": "object",
                "properties": {"value": {"type": "number"}},
                "required": ["value"],
            },
        }
    ]
    assert payload["messages"][1]["content"][1] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "echo_tool",
        "input": {"value": 7},
    }
    assert payload["messages"][2]["content"][0]["type"] == "tool_result"
    assert payload["messages"][2]["content"][0]["tool_use_id"] == "call_1"
    assert payload["messages"][2]["content"][1]["tool_use_id"] == "call_2"


def test_anthropic_adapter_normalizes_tool_use_response() -> None:
    client = AnthropicMessagesClient(api_key="key", model="claude-opus-4-7")

    result = client._normalize_response(
        {
            "model": "claude-opus-4-7",
            "content": [
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "toolu_1", "name": "echo_tool", "input": {"value": 7}},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )

    assert result["message"]["content"] == "Checking."
    assert result["message"]["tool_calls"] == [
        {
            "id": "toolu_1",
            "type": "function",
            "function": {"name": "echo_tool", "arguments": '{"value": 7}'},
        }
    ]


def test_xai_responses_adapter_converts_openai_tool_loop_messages() -> None:
    client = XAIResponsesClient(api_key="key", model="grok-4")
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Run the echo tool"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "echo_tool", "arguments": '{"value": 7}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"ok":true}'},
    ]

    payload = client._build_payload(
        messages=messages,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "echo_tool",
                    "description": "Echo back a number",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    assert payload["input"][0] == {"role": "system", "content": "System prompt"}
    assert payload["input"][2] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "echo_tool",
        "arguments": '{"value": 7}',
    }
    assert payload["input"][3] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok":true}',
    }
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["name"] == "echo_tool"


def test_xai_responses_adapter_continues_with_previous_response_id() -> None:
    client = XAIResponsesClient(api_key="key", model="grok-4")
    client._last_response_id = "resp_1"

    payload = client._build_request_payload(
        messages=[
            {"role": "system", "content": "System prompt"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_old",
                        "type": "function",
                        "function": {"name": "echo_tool", "arguments": '{"value": 1}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_old", "content": '{"old":true}'},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_new",
                        "type": "function",
                        "function": {"name": "echo_tool", "arguments": '{"value": 2}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_new", "content": '{"new":true}'},
        ],
        tools=[],
    )

    assert payload["previous_response_id"] == "resp_1"
    assert payload["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_new",
            "output": '{"new":true}',
        }
    ]


def test_xai_responses_adapter_normalizes_function_call_response() -> None:
    client = XAIResponsesClient(api_key="key", model="grok-4")

    result = client._normalize_response(
        {
            "model": "grok-4",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Checking."}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "echo_tool",
                    "arguments": '{"value":7}',
                },
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )

    assert result["message"]["content"] == "Checking."
    assert result["message"]["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "echo_tool", "arguments": '{"value":7}'},
        }
    ]


def test_user_settings_migrates_legacy_openai_fields(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"openai_api_key":"sk-test","openai_model":"gpt-4o","openai_base_url":"https://api.openai.com/v1"}',
        encoding="utf-8",
    )

    settings = UserSettingsStore(path).load_raw()

    assert settings["llm_provider"] == "openai"
    assert settings["llm_api_key"] == "sk-test"
    assert settings["llm_model"] == "gpt-4o"
    assert settings["llm_base_url"] == "https://api.openai.com/v1"


def test_new_user_settings_file_does_not_persist_llm_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"

    store = UserSettingsStore(path)

    assert "llm_provider" not in store.load_stored_raw()
    assert store.load_raw()["llm_provider"] == "openai"


def test_user_settings_provider_switch_applies_preset_and_keeps_other_vendor_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    store = UserSettingsStore(path)
    store.save(
        {
            "llm_provider": "openai",
            "llm_api_key": "sk-openai",
            "llm_model": "gpt-5-mini",
            "llm_base_url": "https://api.openai.com/v1",
        }
    )

    saved = store.save(
        {
            "llm_provider": "anthropic",
            "llm_api_key": MASKED_PLACEHOLDER + "enai",
        }
    )

    assert saved["llm_provider"] == "anthropic"
    # Anthropic has no key yet; openai key remains in the multi-vendor map.
    assert saved["llm_api_key"] == ""
    assert saved["llm_provider_api_keys"]["openai"] == "sk-openai"
    assert saved["llm_model"] == "claude-opus-4-8"
    assert saved["llm_base_url"] == "https://api.anthropic.com/v1"
    assert saved["llm_settings_saved_at"]

    # Switching back restores the openai key without re-pasting.
    restored = store.save({"llm_provider": "openai"})
    assert restored["llm_api_key"] == "sk-openai"
    assert restored["llm_provider_api_keys"]["openai"] == "sk-openai"
