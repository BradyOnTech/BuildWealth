from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from buildwealth_orchestrator.services.llm_routing import MeteredChatClient
from buildwealth_orchestrator.services.llm_usage_ledger import (
    LLMUsageLedger,
    estimate_cost_usd,
    normalize_usage,
)


def test_normalize_usage_reads_openai_and_anthropic_shapes() -> None:
    assert normalize_usage({"prompt_tokens": 120, "completion_tokens": 45}) == (120, 45)
    assert normalize_usage({"input_tokens": 200, "output_tokens": 80}) == (200, 80)
    assert normalize_usage({}) == (0, 0)
    assert normalize_usage(None) == (0, 0)
    assert normalize_usage({"prompt_tokens": "nan"}) == (0, 0)


def test_estimate_cost_uses_longest_prefix_and_zero_for_unknown() -> None:
    # gpt-5-mini must match its own price, not the shorter gpt-5 prefix.
    mini = estimate_cost_usd("gpt-5-mini", 1_000_000, 0)
    full = estimate_cost_usd("gpt-5.5", 1_000_000, 0)
    assert mini == 0.25
    assert full == 1.25
    # Local and unknown models cost nothing.
    assert estimate_cost_usd("llama3.2", 5_000_000, 5_000_000) == 0.0


def test_ledger_aggregates_by_month_and_key(tmp_path: Path) -> None:
    ledger = LLMUsageLedger(tmp_path / "ledger.json")
    january = datetime(2026, 1, 10, tzinfo=timezone.utc)
    ledger.record(provider="openai", model="gpt-5.5", task="chat", usage={"prompt_tokens": 100, "completion_tokens": 50}, now=january)
    ledger.record(provider="openai", model="gpt-5.5", task="chat", usage={"prompt_tokens": 300, "completion_tokens": 150}, now=january)
    ledger.record(provider="custom_openai_compatible", model="llama3.2", task="summarize", usage={"prompt_tokens": 900, "completion_tokens": 400}, now=january)

    summary = ledger.summary(now=january)
    assert summary["month"] == "2026-01"
    current = summary["current"]
    assert current["requests"] == 3
    assert current["prompt_tokens"] == 1300
    chat_row = next(row for row in current["rows"] if row["task"] == "chat")
    assert chat_row["requests"] == 2
    assert chat_row["prompt_tokens"] == 400
    assert chat_row["completion_tokens"] == 200
    assert chat_row["estimated_cost_usd"] > 0
    local_row = next(row for row in current["rows"] if row["task"] == "summarize")
    assert local_row["estimated_cost_usd"] == 0.0

    # A new month starts a fresh bucket; the old one stays recorded.
    february = datetime(2026, 2, 1, tzinfo=timezone.utc)
    ledger.record(provider="openai", model="gpt-5.5", task="chat", usage={"prompt_tokens": 10, "completion_tokens": 5}, now=february)
    feb = ledger.summary(now=february)
    assert feb["current"]["requests"] == 1
    assert feb["months_recorded"] == ["2026-02", "2026-01"]


class _FakeInner:
    provider = "openai"
    model = "gpt-5.5"
    enabled = True

    async def complete(self, messages, tools):
        return {
            "message": {"content": "hi"},
            "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            "model": "gpt-5.5",
            "provider": "openai",
        }


def test_metered_client_records_and_passes_through(tmp_path: Path) -> None:
    ledger = LLMUsageLedger(tmp_path / "ledger.json")
    client = MeteredChatClient(_FakeInner(), task="chat", ledger=ledger)
    assert client.enabled is True
    assert client.model == "gpt-5.5"

    completion = asyncio.run(client.complete([], []))
    assert completion["message"]["content"] == "hi"

    current = ledger.summary()["current"]
    assert current["requests"] == 1
    assert current["prompt_tokens"] == 42
    assert current["completion_tokens"] == 7


class _BrokenLedger:
    def record(self, **kwargs):
        raise RuntimeError("disk full")


def test_metering_failure_never_breaks_the_completion() -> None:
    client = MeteredChatClient(_FakeInner(), task="chat", ledger=_BrokenLedger())
    completion = asyncio.run(client.complete([], []))
    assert completion["message"]["content"] == "hi"


def test_summary_includes_history_and_provider_rollup(tmp_path: Path) -> None:
    ledger = LLMUsageLedger(tmp_path / "ledger.json")
    january = datetime(2026, 1, 10, tzinfo=timezone.utc)
    february = datetime(2026, 2, 10, tzinfo=timezone.utc)
    ledger.record(provider="openai", model="gpt-5.5", task="chat", usage={"prompt_tokens": 100, "completion_tokens": 50}, now=january)
    ledger.record(provider="anthropic", model="claude-opus-4-8", task="chat", usage={"prompt_tokens": 200, "completion_tokens": 80}, now=february)
    ledger.record(provider="openai", model="gpt-5.5", task="summarize", usage={"prompt_tokens": 50, "completion_tokens": 10}, now=february)

    summary = ledger.summary(now=february)

    history = summary["history"]
    assert [row["month"] for row in history] == ["2026-02", "2026-01"]
    feb_row = history[0]
    assert feb_row["requests"] == 2
    assert feb_row["prompt_tokens"] == 250
    jan_row = history[1]
    assert jan_row["requests"] == 1

    providers = summary["providers"]
    assert {row["provider"] for row in providers} == {"openai", "anthropic"}
    openai_row = next(row for row in providers if row["provider"] == "openai")
    assert openai_row["requests"] == 1
    assert openai_row["prompt_tokens"] == 50


class _FakeStreamingInner:
    provider = "openai"
    model = "gpt-5.5"
    enabled = True

    async def complete(self, messages, tools):
        return {"message": {"content": "hi"}, "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "gpt-5.5", "provider": "openai"}

    async def complete_stream(self, messages, tools, on_delta=None):
        if on_delta:
            on_delta("hi")
        return {"message": {"content": "hi"}, "usage": {"prompt_tokens": 5, "completion_tokens": 2}, "model": "gpt-5.5", "provider": "openai"}


def test_metered_wrapper_preserves_streaming_capability(tmp_path: Path) -> None:
    import asyncio

    from buildwealth_orchestrator.services.llm_routing import metered_chat_client

    ledger = LLMUsageLedger(tmp_path / "ledger.json")

    streaming = metered_chat_client(_FakeStreamingInner(), task="chat", ledger=ledger)
    assert hasattr(streaming, "complete_stream")
    deltas: list[str] = []
    asyncio.run(streaming.complete_stream([], [], on_delta=deltas.append))
    assert deltas == ["hi"]

    non_streaming = metered_chat_client(_FakeInner(), task="chat", ledger=ledger)
    assert not hasattr(non_streaming, "complete_stream")

    summary = ledger.summary()
    row = summary["current"]["rows"][0]
    assert row["prompt_tokens"] == 5
    assert row["completion_tokens"] == 2
