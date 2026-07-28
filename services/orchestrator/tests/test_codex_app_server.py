from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services import codex_app_server as module


class FakeTurnProcess:
    instances: list["FakeTurnProcess"] = []

    def __init__(self, *, codex_bin: str, codex_home: Path, cwd: Path, timeout_seconds: float):
        self.codex_bin = codex_bin
        self.codex_home = codex_home
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.notification_handler = None
        self.request_handler = None
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self.__class__.instances.append(self)

    async def start(self) -> None:
        return None

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append((method, params))
        if method == "account/read":
            return {
                "account": {
                    "type": "chatgpt",
                    "email": "household@example.test",
                    "planType": "plus",
                },
                "requiresOpenaiAuth": True,
            }
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        if method == "turn/start":
            assert self.request_handler is not None
            tool_result = await self.request_handler(
                "item/tool/call",
                {
                    "tool": "get_plan_context",
                    "arguments": {"plan_id": "plan-1"},
                    "callId": "call-1",
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                },
            )
            assert tool_result["success"] is True
            assert self.notification_handler is not None
            await self.notification_handler(
                "turn/completed",
                {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [
                            {
                                "id": "message-1",
                                "type": "agentMessage",
                                "phase": "final_answer",
                                "text": "Your plan remains on track.",
                            }
                        ],
                    },
                },
            )
            return {"turn": {"id": "turn-1", "status": "inProgress", "items": []}}
        raise AssertionError(f"Unexpected method: {method}")

    async def close(self) -> None:
        self.closed = True


class FakeDeviceLoginProcess:
    instances: list["FakeDeviceLoginProcess"] = []

    def __init__(self, *, codex_bin: str, codex_home: Path, cwd: Path, timeout_seconds: float):
        self.codex_home = codex_home
        self.notification_handler = None
        self.request_handler = None
        self.account_available = False
        self.closed = False
        self.__class__.instances.append(self)

    async def start(self) -> None:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        (self.codex_home / "auth.json").write_text(
            json.dumps({"tokens": {"access_token": "device-secret"}}),
            encoding="utf-8",
        )

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "account/login/start":
            return {
                "type": "chatgptDeviceCode",
                "loginId": "login-1",
                "verificationUrl": "https://auth.openai.com/codex/device",
                "userCode": "ABCD-EFGH",
            }
        if method == "account/read":
            if not self.account_available:
                return {"account": None, "requiresOpenaiAuth": True}
            return {
                "account": {
                    "type": "chatgpt",
                    "email": "household@example.test",
                    "planType": "plus",
                },
                "requiresOpenaiAuth": True,
            }
        raise AssertionError(f"Unexpected method: {method}")

    async def close(self) -> None:
        self.closed = True


def test_codex_chat_client_bridges_dynamic_tools_and_uses_read_only_thread(monkeypatch):
    FakeTurnProcess.instances.clear()
    monkeypatch.setattr(module, "_AppServerProcess", FakeTurnProcess)
    persisted: list[str] = []
    calls: list[tuple[str, dict[str, Any]]] = []

    async def tool_handler(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return {"ok": True, "result": {"status": "on_track"}, "error": None}

    client = module.CodexAppServerChatClient(
        credential_json=json.dumps({"tokens": {"access_token": "secret"}}),
        model="gpt-test",
        persist_credentials=persisted.append,
    )
    result = asyncio.run(
        client.run_agent(
            messages=[
                {"role": "system", "content": "Use reviewed financial context."},
                {"role": "user", "content": "Am I on track?"},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_plan_context",
                        "description": "Read the active plan.",
                        "parameters": {
                            "type": "object",
                            "properties": {"plan_id": {"type": "string"}},
                        },
                    },
                }
            ],
            tool_handler=tool_handler,
        )
    )

    assert result["message"]["content"] == "Your plan remains on track."
    assert result["provider"] == "codex_subscription"
    assert calls == [("get_plan_context", {"plan_id": "plan-1"})]
    assert persisted and json.loads(persisted[-1])["tokens"]["access_token"] == "secret"
    process = FakeTurnProcess.instances[-1]
    thread_params = next(params for method, params in process.requests if method == "thread/start")
    assert thread_params["sandbox"] == "read-only"
    assert thread_params["approvalPolicy"] == "never"
    assert thread_params["ephemeral"] is True
    assert thread_params["dynamicTools"][0]["name"] == "get_plan_context"
    assert "Do not use shell" in thread_params["baseInstructions"]
    assert process.closed is True


def test_codex_chat_client_rejects_missing_or_invalid_credentials():
    assert module.CodexAppServerChatClient(credential_json="").enabled is False
    assert module.CodexAppServerChatClient(credential_json="not-json").enabled is False
    assert module.CodexAppServerChatClient(credential_json="{}").enabled is True


def test_codex_dynamic_tools_ignore_malformed_entries():
    tools = module.CodexAppServerChatClient._dynamic_tools(
        [
            {"type": "function", "function": {"name": "ok", "description": "Works"}},
            {"type": "function", "function": {}},
            {"type": "other"},
        ]
    )
    assert tools == [
        {
            "type": "function",
            "name": "ok",
            "description": "Works",
            "inputSchema": {"type": "object", "properties": {}},
        }
    ]


def test_device_login_waits_for_account_updated_before_reading_account(monkeypatch):
    FakeDeviceLoginProcess.instances.clear()
    monkeypatch.setattr(module, "_AppServerProcess", FakeDeviceLoginProcess)
    persisted: list[str] = []

    async def run_login() -> module._DeviceLoginSession:
        login = module._DeviceLoginSession(
            workspace_id="ws-test",
            codex_bin="codex",
            persist_credentials=persisted.append,
            timeout_seconds=1.0,
        )
        await login.start()
        process = FakeDeviceLoginProcess.instances[-1]
        assert process.notification_handler is not None
        await process.notification_handler(
            "account/login/completed",
            {"loginId": "login-1", "success": True, "error": None},
        )

        async def publish_account_update() -> None:
            await asyncio.sleep(0.01)
            process.account_available = True
            assert process.notification_handler is not None
            await process.notification_handler(
                "account/updated",
                {"authMode": "chatgpt", "planType": "plus"},
            )

        update_task = asyncio.create_task(publish_account_update())
        assert login._watch_task is not None
        await login._watch_task
        await update_task
        return login

    login = asyncio.run(run_login())

    assert login.state == "connected"
    assert login.error == ""
    assert login.account == {
        "type": "chatgpt",
        "email": "household@example.test",
        "planType": "plus",
    }
    assert persisted and json.loads(persisted[-1])["tokens"]["access_token"] == "device-secret"
