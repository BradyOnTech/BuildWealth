from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class ConversationStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id: str) -> Path:
        return self.base_dir / f"{conversation_id}.json"

    def _new_conversation(self, title: str) -> dict[str, Any]:
        now = utc_now_iso()
        return {
            "id": uuid.uuid4().hex,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }

    def create(self, title: str = "New Conversation") -> dict[str, Any]:
        doc = self._new_conversation(title=title)
        self.save(doc)
        return doc

    def get(self, conversation_id: str) -> dict[str, Any]:
        path = self._path(conversation_id)
        if not path.exists():
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")

        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, conversation: dict[str, Any]) -> None:
        conversation["updated_at"] = utc_now_iso()
        path = self._path(conversation["id"])
        path.write_text(json.dumps(conversation, indent=2), encoding="utf-8")

    def get_or_create(
        self,
        conversation_id: str | None,
        first_user_message: str,
    ) -> dict[str, Any]:
        if conversation_id:
            return self.get(conversation_id)

        title = (first_user_message or "New Conversation").strip()
        if len(title) > 64:
            title = f"{title[:61]}..."

        return self.create(title=title or "New Conversation")

    def append_message(
        self,
        conversation: dict[str, Any],
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conversation.setdefault("messages", [])
        conversation["messages"].append(
            {
                "role": role,
                "content": content,
                "created_at": utc_now_iso(),
                "metadata": metadata or {},
            }
        )

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []

        for path in self.base_dir.glob("*.json"):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                docs.append(doc)
            except Exception:
                continue

        docs.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

        summaries: list[dict[str, Any]] = []
        for doc in docs[:limit]:
            messages = doc.get("messages", [])
            last_message_preview = ""
            for message in reversed(messages):
                if message.get("role") == "assistant":
                    last_message_preview = str(message.get("content", ""))
                    break
            if len(last_message_preview) > 120:
                last_message_preview = f"{last_message_preview[:117]}..."

            summaries.append(
                {
                    "id": doc.get("id"),
                    "title": doc.get("title", "Conversation"),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                    "last_message_preview": last_message_preview,
                }
            )

        return summaries


class OpenAIChatToolClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM API key is not configured")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tool_choice": "auto",
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice.get("message", {})

        return {
            "message": message,
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model),
        }


class ChatToolClient(Protocol):
    model: str

    @property
    def enabled(self) -> bool: ...

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


@dataclass
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class FinancialCopilot:
    def __init__(
        self,
        conversation_store: ConversationStore,
        llm_client: ChatToolClient,
        max_history_messages: int,
        max_tool_rounds: int,
        system_prompt: str,
    ):
        self.conversation_store = conversation_store
        self.llm_client = llm_client
        self.max_history_messages = max_history_messages
        self.max_tool_rounds = max_tool_rounds
        self.system_prompt = system_prompt
        self.tools: dict[str, RegisteredTool] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        self.tools[name] = RegisteredTool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools.values()
        ]

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        chunks.append(item["text"])
                    elif isinstance(item.get("content"), str):
                        chunks.append(item["content"])
                elif isinstance(item, str):
                    chunks.append(item)
            return "\n".join([chunk for chunk in chunks if chunk]).strip()
        if content is None:
            return ""
        return str(content)

    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        tool = self.tools.get(name)
        if not tool:
            return {}, f"Unknown tool: {name}"

        try:
            result = await tool.handler(arguments)
            return result, None
        except Exception as exc:
            return {}, str(exc)

    @staticmethod
    def _safe_tool_content(payload: dict[str, Any]) -> str:
        text = json.dumps(payload, default=str)
        if len(text) > 12000:
            text = f"{text[:11950]}..."
        return text

    def _build_messages(
        self,
        conversation: dict[str, Any],
        contextual_brief: str,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": f"{self.system_prompt}\n\nFinancial Context:\n{contextual_brief}",
            }
        ]

        history = conversation.get("messages", [])[-self.max_history_messages :]
        for message in history:
            role = message.get("role")
            content = str(message.get("content", ""))
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        return messages

    async def chat(
        self,
        question: str,
        conversation_id: str | None,
        contextual_brief: str,
        context_trace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conversation = self.conversation_store.get_or_create(
            conversation_id=conversation_id,
            first_user_message=question,
        )
        self.conversation_store.append_message(
            conversation,
            role="user",
            content=question,
        )

        tool_traces: list[dict[str, Any]] = []
        answer = ""
        model_name = self.llm_client.model if self.llm_client.enabled else None

        if self.llm_client.enabled:
            messages = self._build_messages(
                conversation=conversation,
                contextual_brief=contextual_brief,
            )

            for _ in range(self.max_tool_rounds):
                completion = await self.llm_client.complete(
                    messages=messages,
                    tools=self._tool_definitions(),
                )
                model_name = completion.get("model", model_name)
                assistant_message = completion.get("message", {})
                content = self._message_text(assistant_message.get("content"))
                tool_calls = assistant_message.get("tool_calls") or []

                if tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": tool_calls,
                        }
                    )

                    for call in tool_calls:
                        function_block = call.get("function", {})
                        name = function_block.get("name", "")
                        raw_arguments = function_block.get("arguments") or "{}"

                        try:
                            arguments = (
                                json.loads(raw_arguments)
                                if isinstance(raw_arguments, str)
                                else dict(raw_arguments)
                            )
                        except Exception:
                            arguments = {"_raw": raw_arguments}

                        result, error = await self._execute_tool(name=name, arguments=arguments)

                        trace = {
                            "name": name,
                            "arguments": arguments,
                            "result": result,
                            "error": error,
                        }
                        tool_traces.append(trace)

                        tool_payload = {
                            "ok": error is None,
                            "result": result,
                            "error": error,
                        }
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", ""),
                                "content": self._safe_tool_content(tool_payload),
                            }
                        )

                    continue

                answer = content.strip()
                if answer:
                    break

            if not answer:
                answer = (
                    "I reviewed your request but could not produce a final response. "
                    "Try asking a narrower question or run a portfolio sync first."
                )
        else:
            answer = (
                "Copilot is running in fallback mode because an LLM API key is not configured. "
                "I can still use direct endpoints for sync/import/planning, but conversational reasoning is limited."
            )

        self.conversation_store.append_message(
            conversation,
            role="assistant",
            content=answer,
            metadata={
                "tool_calls": tool_traces,
                "model": model_name,
                "context_trace": context_trace or {},
            },
        )
        self.conversation_store.save(conversation)

        return {
            "conversation_id": conversation["id"],
            "answer": answer,
            "tool_calls": tool_traces,
            "model": model_name,
            "context_trace": context_trace or {},
            "created_at": utc_now(),
        }
