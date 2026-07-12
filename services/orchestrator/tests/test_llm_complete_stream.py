from __future__ import annotations

import asyncio
import json

from buildwealth_orchestrator.services import llm_clients


class _FakeStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200):
        self._lines = lines
        self.status_code = status_code

    async def aread(self) -> bytes:
        return b""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    lines: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, headers=None, json=None):
        return _FakeStreamContext(_FakeStreamResponse(type(self).lines))


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload)


def test_complete_stream_accumulates_content_and_tool_calls(monkeypatch):
    _FakeAsyncClient.lines = [
        _sse({"model": "gpt-test", "choices": [{"delta": {"content": "Hel"}}]}),
        _sse({"choices": [{"delta": {"content": "lo"}}]}),
        _sse(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {"name": "get_profile", "arguments": '{"a"'},
                                }
                            ]
                        }
                    }
                ]
            }
        ),
        _sse(
            {
                "choices": [
                    {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": 1}"}}]}}
                ]
            }
        ),
        "data: [DONE]",
    ]
    monkeypatch.setattr(llm_clients.httpx, "AsyncClient", _FakeAsyncClient)

    client = llm_clients.OpenAICompatibleChatClient(
        api_key="sk-test",
        model="gpt-test",
        base_url="https://api.test/v1",
    )
    deltas: list[str] = []
    completion = asyncio.run(
        client.complete_stream(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            on_delta=deltas.append,
        )
    )

    assert deltas == ["Hel", "lo"]
    message = completion["message"]
    assert message["content"] == "Hello"
    assert message["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_profile", "arguments": '{"a": 1}'},
        }
    ]
    assert completion["model"] == "gpt-test"


def test_complete_stream_ignores_malformed_chunks(monkeypatch):
    _FakeStreamResponse_lines = [
        "data: not-json",
        ": comment line",
        _sse({"choices": [{"delta": {"content": "ok"}}]}),
        "data: [DONE]",
    ]
    _FakeAsyncClient.lines = _FakeStreamResponse_lines
    monkeypatch.setattr(llm_clients.httpx, "AsyncClient", _FakeAsyncClient)

    client = llm_clients.OpenAICompatibleChatClient(
        api_key="sk-test",
        model="gpt-test",
        base_url="https://api.test/v1",
    )
    completion = asyncio.run(
        client.complete_stream(messages=[{"role": "user", "content": "hi"}], tools=[])
    )
    assert completion["message"]["content"] == "ok"
