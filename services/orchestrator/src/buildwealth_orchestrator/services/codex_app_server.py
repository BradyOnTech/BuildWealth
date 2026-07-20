"""ChatGPT-subscription-backed Copilot support through Codex app-server.

Codex app-server is not an OpenAI-compatible HTTP endpoint.  It is a JSON-RPC
agent runtime with its own authentication and tool protocol.  This adapter
keeps those details behind BuildWealth's existing chat-client boundary:

* ChatGPT device authorization works on a headless/cloud host.
* Each workspace's ``auth.json`` is encrypted by ``WorkspaceSecretStore``.
* A fresh temporary ``CODEX_HOME`` is materialized for each turn, so plaintext
  credentials never live in workspace files or backups.
* BuildWealth tools are exposed as app-server dynamic tools.  The Codex thread
  is read-only and explicitly instructed not to use shell, filesystem, or web
  tools for financial answers.

The dynamic-tool surface is currently experimental in Codex.  Protocol errors
are therefore returned clearly instead of silently falling back to a different
provider or credential.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
import shutil
import tempfile
from typing import Any


CODEX_SUBSCRIPTION_PROVIDER = "codex_subscription"
DEFAULT_CODEX_MODEL = "codex-recommended"


class CodexAppServerError(RuntimeError):
    """Raised when the app-server process or JSON-RPC flow fails."""


def _json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CodexAppServerError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CodexAppServerError(f"{label} must contain a JSON object")
    return value


class _AppServerProcess:
    def __init__(
        self,
        *,
        codex_bin: str,
        codex_home: Path,
        cwd: Path,
        timeout_seconds: float,
    ) -> None:
        self.codex_bin = str(codex_bin or "codex")
        self.codex_home = codex_home
        self.cwd = cwd
        self.timeout_seconds = max(5.0, float(timeout_seconds))
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=20)
        self.notification_handler: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None
        self.request_handler: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None

    async def start(self) -> None:
        if self.process is not None:
            return
        resolved = shutil.which(self.codex_bin) if not Path(self.codex_bin).is_absolute() else self.codex_bin
        if not resolved or not Path(resolved).exists():
            raise CodexAppServerError(
                "Codex CLI is not installed on this host. Install it in the service image "
                "or set CODEX_BIN to its absolute path."
            )
        self.codex_home.mkdir(parents=True, exist_ok=True)
        self.cwd.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["CODEX_HOME"] = str(self.codex_home)
        env["CODEX_SQLITE_HOME"] = str(self.codex_home)
        self.process = await asyncio.create_subprocess_exec(
            str(resolved),
            "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd),
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "buildwealth",
                    "title": "BuildWealth Copilot",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self.notify("initialized", {})

    async def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                request_id = message.get("id")
                if request_id is not None and ("result" in message or "error" in message):
                    future = self._pending.pop(int(request_id), None)
                    if future is not None and not future.done():
                        future.set_result(message)
                    continue
                method = str(message.get("method") or "")
                params = message.get("params") if isinstance(message.get("params"), dict) else {}
                if request_id is not None and method:
                    asyncio.create_task(self._handle_server_request(int(request_id), method, params))
                elif method and self.notification_handler is not None:
                    asyncio.create_task(self.notification_handler(method, params))
        finally:
            error = CodexAppServerError(self._process_error("Codex app-server exited"))
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while line := await self.process.stderr.readline():
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                self._stderr_lines.append(text)

    async def _handle_server_request(
        self,
        request_id: int,
        method: str,
        params: dict[str, Any],
    ) -> None:
        if self.request_handler is None:
            await self._send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unsupported server request: {method}"},
                }
            )
            return
        try:
            result = await self.request_handler(method, params)
            await self._send({"id": request_id, "result": result})
        except Exception as exc:
            await self._send(
                {
                    "id": request_id,
                    "error": {"code": -32000, "message": str(exc)[:500]},
                }
            )

    def _process_error(self, prefix: str) -> str:
        detail = "\n".join(self._stderr_lines)
        return f"{prefix}: {detail[-1500:]}" if detail else prefix

    async def _send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None or self.process.returncode is not None:
            raise CodexAppServerError(self._process_error("Codex app-server is not running"))
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        async with self._write_lock:
            self.process.stdin.write(payload)
            await self.process.stdin.drain()

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send({"method": method, "id": request_id, "params": params})
        try:
            response = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise CodexAppServerError(f"Codex app-server timed out during {method}") from exc
        if response.get("error"):
            error = response["error"]
            detail = error.get("message") if isinstance(error, dict) else str(error)
            raise CodexAppServerError(f"Codex app-server {method} failed: {detail}")
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"method": method, "params": params})

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


ToolHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class CodexAppServerChatClient:
    """Chat client that runs one isolated, ephemeral Codex thread per call."""

    provider = CODEX_SUBSCRIPTION_PROVIDER

    def __init__(
        self,
        *,
        credential_json: str,
        model: str = DEFAULT_CODEX_MODEL,
        codex_bin: str = "codex",
        timeout_seconds: float = 180.0,
        persist_credentials: Callable[[str], None] | None = None,
    ) -> None:
        self.credential_json = str(credential_json or "")
        self.model = str(model or DEFAULT_CODEX_MODEL)
        self.codex_bin = str(codex_bin or "codex")
        self.timeout_seconds = max(10.0, float(timeout_seconds))
        self.persist_credentials = persist_credentials

    @property
    def enabled(self) -> bool:
        if not self.credential_json.strip():
            return False
        try:
            _json_object(self.credential_json, label="Stored Codex credential")
        except CodexAppServerError:
            return False
        return True

    @staticmethod
    def _dynamic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for entry in tools:
            function = entry.get("function") if isinstance(entry, dict) else None
            if not isinstance(function, dict) or not function.get("name"):
                continue
            out.append(
                {
                    "type": "function",
                    "name": str(function["name"]),
                    "description": str(function.get("description") or ""),
                    "inputSchema": function.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
        return out

    @staticmethod
    def _split_messages(messages: list[dict[str, Any]]) -> tuple[str, str]:
        system: list[str] = []
        transcript: list[str] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content")
            text = content if isinstance(content, str) else json.dumps(content, default=str)
            if role == "system":
                system.append(text)
            elif role in {"user", "assistant", "tool"} and text:
                transcript.append(f"{role.upper()}:\n{text}")
        return "\n\n".join(system), "\n\n".join(transcript)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if tools:
            raise CodexAppServerError(
                "Codex subscription tool calls must run through FinancialCopilot.run_agent"
            )
        return await self.run_agent(messages=messages, tools=[], tool_handler=None)

    async def run_agent(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_handler: ToolHandler | None,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise CodexAppServerError("Connect a ChatGPT account before using Codex subscription")

        temp_root = Path(tempfile.mkdtemp(prefix="buildwealth-codex-turn-"))
        codex_home = temp_root / "home"
        runtime_cwd = temp_root / "runtime"
        codex_home.mkdir(parents=True, exist_ok=True)
        auth_path = codex_home / "auth.json"
        auth_path.write_text(
            json.dumps(_json_object(self.credential_json, label="Stored Codex credential")),
            encoding="utf-8",
        )
        auth_path.chmod(0o600)
        session = _AppServerProcess(
            codex_bin=self.codex_bin,
            codex_home=codex_home,
            cwd=runtime_cwd,
            timeout_seconds=self.timeout_seconds,
        )
        turn_done: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        completed_messages: list[dict[str, Any]] = []

        async def notification(method: str, params: dict[str, Any]) -> None:
            if method == "item/completed":
                item = params.get("item")
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    completed_messages.append(item)
            elif method == "item/agentMessage/delta" and on_delta is not None:
                # App-server can emit commentary and final-answer deltas on the
                # same channel.  Only stream after a final item is identified;
                # otherwise BuildWealth may show agent narration as the answer.
                pass
            elif method == "turn/completed" and not turn_done.done():
                turn_done.set_result(params)

        async def server_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
            if method != "item/tool/call":
                raise CodexAppServerError(f"Unsupported Codex server request: {method}")
            if tool_handler is None:
                return {
                    "success": False,
                    "contentItems": [
                        {"type": "inputText", "text": "This turn does not expose tools."}
                    ],
                }
            name = str(params.get("tool") or "")
            arguments = params.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {"_raw": arguments}
            payload = await tool_handler(name, arguments)
            text = json.dumps(payload, default=str)
            if len(text) > 12000:
                text = text[:11950] + "..."
            return {
                "success": bool(payload.get("ok", True)),
                "contentItems": [{"type": "inputText", "text": text}],
            }

        session.notification_handler = notification
        session.request_handler = server_request
        try:
            await session.start()
            account = await session.request("account/read", {"refreshToken": True})
            account_payload = account.get("account")
            if not isinstance(account_payload, dict) or account_payload.get("type") != "chatgpt":
                raise CodexAppServerError("Stored Codex session is not a ChatGPT sign-in")

            system, transcript = self._split_messages(messages)
            base_instructions = "\n\n".join(
                chunk
                for chunk in (
                    system,
                    "You are the BuildWealth financial Copilot, not a coding agent. "
                    "Use only the BuildWealth dynamic tools supplied for this thread. "
                    "Do not use shell, filesystem, web, MCP, or delegation tools. "
                    "Never change source files. Treat financial context as private. "
                    "Give a direct final answer and distinguish modeled estimates from facts.",
                )
                if chunk
            )
            thread_params: dict[str, Any] = {
                "cwd": str(runtime_cwd),
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "ephemeral": True,
                "baseInstructions": base_instructions,
                "dynamicTools": self._dynamic_tools(tools),
                "multiAgentMode": "none",
            }
            if self.model and self.model != DEFAULT_CODEX_MODEL:
                thread_params["model"] = self.model
            thread = await session.request("thread/start", thread_params)
            thread_id = str((thread.get("thread") or {}).get("id") or "")
            if not thread_id:
                raise CodexAppServerError("Codex app-server did not return a thread id")
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": transcript or "Respond to the user."}],
            }
            if self.model and self.model != DEFAULT_CODEX_MODEL:
                turn_params["model"] = self.model
            await session.request("turn/start", turn_params)
            completed = await asyncio.wait_for(turn_done, timeout=self.timeout_seconds)
            turn = completed.get("turn") if isinstance(completed.get("turn"), dict) else {}
            if turn.get("status") != "completed":
                error = turn.get("error") if isinstance(turn.get("error"), dict) else {}
                raise CodexAppServerError(
                    str(error.get("message") or f"Codex turn ended with status {turn.get('status')}")
                )
            items = turn.get("items") if isinstance(turn.get("items"), list) else []
            agent_messages = [
                item for item in items if isinstance(item, dict) and item.get("type") == "agentMessage"
            ] or completed_messages
            final_items = [item for item in agent_messages if item.get("phase") == "final_answer"]
            selected = (final_items or agent_messages)[-1] if (final_items or agent_messages) else {}
            answer = str(selected.get("text") or "").strip()
            if not answer:
                raise CodexAppServerError("Codex completed without a final answer")
            if on_delta is not None:
                on_delta(answer)
            return {
                "message": {"role": "assistant", "content": answer, "tool_calls": []},
                "usage": {},
                "model": self.model,
                "provider": self.provider,
                "account": account_payload,
            }
        finally:
            refreshed = ""
            try:
                if auth_path.exists():
                    refreshed = auth_path.read_text(encoding="utf-8")
                    _json_object(refreshed, label="Refreshed Codex credential")
            except Exception:
                refreshed = ""
            await session.close()
            if refreshed and self.persist_credentials is not None:
                self.persist_credentials(refreshed)
            shutil.rmtree(temp_root, ignore_errors=True)


class _DeviceLoginSession:
    def __init__(
        self,
        *,
        workspace_id: str,
        codex_bin: str,
        persist_credentials: Callable[[str], None],
        timeout_seconds: float,
    ) -> None:
        self.workspace_id = workspace_id
        self.codex_bin = codex_bin
        self.persist_credentials = persist_credentials
        self.timeout_seconds = timeout_seconds
        self.temp_root = Path(tempfile.mkdtemp(prefix="buildwealth-codex-login-"))
        self.session = _AppServerProcess(
            codex_bin=codex_bin,
            codex_home=self.temp_root / "home",
            cwd=self.temp_root / "runtime",
            timeout_seconds=timeout_seconds,
        )
        self.state = "starting"
        self.error = ""
        self.login_id = ""
        self.verification_url = ""
        self.user_code = ""
        self.account: dict[str, Any] | None = None
        self._completed: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._watch_task: asyncio.Task[None] | None = None

    async def start(self) -> dict[str, Any]:
        async def notification(method: str, params: dict[str, Any]) -> None:
            if method == "account/login/completed" and not self._completed.done():
                self._completed.set_result(params)

        self.session.notification_handler = notification
        await self.session.start()
        result = await self.session.request(
            "account/login/start",
            {"type": "chatgptDeviceCode"},
        )
        self.login_id = str(result.get("loginId") or "")
        self.verification_url = str(result.get("verificationUrl") or "")
        self.user_code = str(result.get("userCode") or "")
        if not self.login_id or not self.verification_url or not self.user_code:
            await self.close()
            raise CodexAppServerError("Codex did not return a device authorization code")
        self.state = "waiting_for_user"
        self._watch_task = asyncio.create_task(self._watch())
        return self.payload(connected=False)

    async def _watch(self) -> None:
        try:
            result = await asyncio.wait_for(self._completed, timeout=self.timeout_seconds)
            if not result.get("success"):
                raise CodexAppServerError(str(result.get("error") or "ChatGPT sign-in was not completed"))
            account_result = await self.session.request("account/read", {"refreshToken": True})
            account = account_result.get("account")
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                raise CodexAppServerError("ChatGPT sign-in completed without a Codex account")
            auth_path = self.temp_root / "home" / "auth.json"
            credential = auth_path.read_text(encoding="utf-8")
            _json_object(credential, label="Codex credential")
            self.persist_credentials(credential)
            self.account = account
            self.state = "connected"
        except TimeoutError:
            self.state = "expired"
            self.error = "The ChatGPT device code expired. Start a new connection."
        except Exception as exc:
            self.state = "failed"
            self.error = str(exc)
        finally:
            await self.session.close()
            shutil.rmtree(self.temp_root, ignore_errors=True)

    def payload(self, *, connected: bool) -> dict[str, Any]:
        return {
            "provider": CODEX_SUBSCRIPTION_PROVIDER,
            "state": self.state,
            "connected": connected or self.state == "connected",
            "login_id": self.login_id or None,
            "verification_url": self.verification_url or None,
            "user_code": self.user_code or None,
            "account": self.account,
            "error": self.error or None,
        }

    async def close(self) -> None:
        if self.login_id and self.state in {"starting", "waiting_for_user"}:
            try:
                await self.session.request("account/login/cancel", {"loginId": self.login_id})
            except Exception:
                pass
        if self._watch_task is not None and not self._watch_task.done():
            self._watch_task.cancel()
        await self.session.close()
        shutil.rmtree(self.temp_root, ignore_errors=True)


class CodexSubscriptionManager:
    """Tracks short-lived device-login processes, isolated by workspace."""

    def __init__(self) -> None:
        self._sessions: dict[str, _DeviceLoginSession] = {}
        self._lock = asyncio.Lock()

    async def start_login(
        self,
        *,
        workspace_id: str,
        codex_bin: str,
        persist_credentials: Callable[[str], None],
        connected: bool,
        timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        async with self._lock:
            previous = self._sessions.pop(workspace_id, None)
            if previous is not None:
                await previous.close()
            session = _DeviceLoginSession(
                workspace_id=workspace_id,
                codex_bin=codex_bin,
                persist_credentials=persist_credentials,
                timeout_seconds=timeout_seconds,
            )
            self._sessions[workspace_id] = session
            try:
                return await session.start()
            except Exception:
                self._sessions.pop(workspace_id, None)
                raise

    def status(self, *, workspace_id: str, connected: bool) -> dict[str, Any]:
        session = self._sessions.get(workspace_id)
        if session is not None:
            return session.payload(connected=connected)
        return {
            "provider": CODEX_SUBSCRIPTION_PROVIDER,
            "state": "connected" if connected else "disconnected",
            "connected": connected,
            "login_id": None,
            "verification_url": None,
            "user_code": None,
            "account": None,
            "error": None,
        }

    async def disconnect(self, *, workspace_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(workspace_id, None)
            if session is not None:
                await session.close()

    async def close(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await session.close()
