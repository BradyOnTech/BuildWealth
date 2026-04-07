import asyncio
from pathlib import Path

from buildwealth_orchestrator.services.copilot_runtime import (
    ConversationStore,
    FinancialCopilot,
    OpenAIChatToolClient,
)


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
        )
    )

    assert result["answer"] == "Your account summary is ready."
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "echo_tool"
    assert result["tool_calls"][0]["result"] == {"echo": 7}
    assert result["tool_calls"][0]["error"] is None

    loaded = store.get(result["conversation_id"])
    assert loaded["messages"][-1]["metadata"]["tool_calls"][0]["name"] == "echo_tool"
