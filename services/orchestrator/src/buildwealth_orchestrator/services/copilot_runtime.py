from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx
from buildwealth_orchestrator.services.store_locks import synchronized_store


CONVERSATION_SCHEMA_VERSION = 2
TURN_STATUSES = {"running", "completed", "stopped", "failed", "incomplete"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


@synchronized_store('base_dir')
class ConversationStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id: str) -> Path:
        return self.base_dir / f"{conversation_id}.json"

    def _new_conversation(self, title: str) -> dict[str, Any]:
        now = utc_now_iso()
        return {
            "schema_version": CONVERSATION_SCHEMA_VERSION,
            "id": uuid.uuid4().hex,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
            "focus": {
                "mode": "balanced",
                "primary_domains": [],
                "secondary_domains": [],
                "muted_domains": [],
                "pinned_entity_ids": [],
                "priority_note": "",
                "set_by": "default",
                "updated_at": None,
                "schema_version": 1,
            },
            # Optional per-conversation model override. Empty = workspace default.
            "llm": {
                "provider": "",
                "model": "",
            },
            "risk_lens": {
                "mode": "profile",
                "posture": None,
                "schema_version": 1,
            },
            "messages": [],
            "turns": [],
        }

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _legacy_id(conversation_id: str, kind: str, index: int) -> str:
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"buildwealth:conversation:{conversation_id}:{kind}:{index}",
        ).hex

    def _normalize_conversation(self, conversation: dict[str, Any]) -> dict[str, Any]:
        """Upgrade legacy conversation documents in memory without losing content."""
        conversation["schema_version"] = CONVERSATION_SCHEMA_VERSION
        conversation.setdefault("archived_at", None)
        risk_lens = conversation.get("risk_lens")
        if not isinstance(risk_lens, dict):
            risk_lens = {"mode": "profile", "posture": None, "schema_version": 1}
        conversation["risk_lens"] = risk_lens
        messages = conversation.get("messages")
        if not isinstance(messages, list):
            messages = []
            conversation["messages"] = messages
        turns = conversation.get("turns")
        if not isinstance(turns, list):
            turns = []
            conversation["turns"] = turns

        now = utc_now_iso()
        turns_by_id: dict[str, dict[str, Any]] = {}
        conversation_id = str(conversation.get("id") or "legacy")
        for turn_index, raw_turn in enumerate(turns):
            if not isinstance(raw_turn, dict):
                continue
            turn_id = str(
                raw_turn.get("id") or self._legacy_id(conversation_id, "turn", turn_index)
            )
            raw_turn["id"] = turn_id
            status = str(raw_turn.get("status") or "incomplete")
            raw_turn["status"] = status if status in TURN_STATUSES else "incomplete"
            raw_turn.setdefault("created_at", conversation.get("created_at") or now)
            raw_turn.setdefault("updated_at", raw_turn["created_at"])
            raw_turn.setdefault("user_message_id", None)
            raw_turn.setdefault("assistant_message_id", None)
            raw_turn.setdefault("error", None)
            turns_by_id[turn_id] = raw_turn

        normalized_turns = list(turns_by_id.values())
        conversation["turns"] = normalized_turns
        active_legacy_turn: dict[str, Any] | None = None

        for message_index, raw_message in enumerate(messages):
            if not isinstance(raw_message, dict):
                continue
            created_at = str(raw_message.get("created_at") or conversation.get("created_at") or now)
            message_id = str(
                raw_message.get("id")
                or self._legacy_id(conversation_id, "message", message_index)
            )
            raw_message["id"] = message_id
            raw_message["created_at"] = created_at
            raw_message.setdefault("updated_at", created_at)
            raw_message.setdefault("metadata", {})
            raw_message.setdefault("status", "complete")

            turn_id = str(raw_message.get("turn_id") or "").strip()
            role = str(raw_message.get("role") or "")
            if not turn_id and role == "user":
                turn_id = self._legacy_id(conversation_id, "message-turn", message_index)
                active_legacy_turn = {
                    "id": turn_id,
                    "status": "incomplete",
                    "user_message_id": message_id,
                    "assistant_message_id": None,
                    "error": None,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
                normalized_turns.append(active_legacy_turn)
                turns_by_id[turn_id] = active_legacy_turn
            elif not turn_id and role == "assistant" and active_legacy_turn is not None:
                turn_id = str(active_legacy_turn["id"])
            elif turn_id:
                active_legacy_turn = turns_by_id.get(turn_id)

            raw_message["turn_id"] = turn_id or None
            if not turn_id:
                continue
            turn = turns_by_id.get(turn_id)
            if turn is None:
                turn = {
                    "id": turn_id,
                    "status": "incomplete",
                    "user_message_id": None,
                    "assistant_message_id": None,
                    "error": None,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
                normalized_turns.append(turn)
                turns_by_id[turn_id] = turn
            if role == "user":
                turn["user_message_id"] = message_id
            elif role == "assistant":
                turn["assistant_message_id"] = message_id
                if turn.get("status") == "incomplete":
                    turn["status"] = "completed"
                turn["updated_at"] = raw_message["updated_at"]

        return conversation

    def create(self, title: str = "New Conversation") -> dict[str, Any]:
        doc = self._new_conversation(title=title)
        self.save(doc)
        return doc

    def get(self, conversation_id: str) -> dict[str, Any]:
        path = self._path(conversation_id)
        if not path.exists():
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")

        return self._normalize_conversation(json.loads(path.read_text(encoding="utf-8")))

    def save(self, conversation: dict[str, Any]) -> None:
        self._normalize_conversation(conversation)
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
        *,
        turn_id: str | None = None,
        status: str = "complete",
    ) -> dict[str, Any]:
        conversation.setdefault("messages", [])
        now = utc_now_iso()
        message = {
            "id": self._new_id(),
            "turn_id": turn_id,
            "role": role,
            "content": content,
            "created_at": now,
            "updated_at": now,
            "status": status,
            "metadata": metadata or {},
        }
        conversation["messages"].append(message)
        return message

    def start_turn(
        self,
        conversation: dict[str, Any],
        question: str,
        turn_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or resume one durable Copilot turn and persist it immediately."""
        self._normalize_conversation(conversation)
        requested_id = str(turn_id or "").strip()
        existing = next(
            (turn for turn in conversation["turns"] if turn.get("id") == requested_id),
            None,
        ) if requested_id else None
        now = utc_now_iso()
        if existing is not None:
            if existing.get("status") != "completed":
                existing["status"] = "running"
                existing["error"] = None
                existing["updated_at"] = now
                self.save(conversation)
            return existing

        durable_turn_id = requested_id or self._new_id()
        user_message = self.append_message(
            conversation,
            role="user",
            content=question,
            turn_id=durable_turn_id,
        )
        turn = {
            "id": durable_turn_id,
            "status": "running",
            "user_message_id": user_message["id"],
            "assistant_message_id": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        conversation["turns"].append(turn)
        self.save(conversation)
        return turn

    def set_turn_status(
        self,
        conversation: dict[str, Any],
        turn_id: str,
        status: str,
        *,
        assistant_message_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if status not in TURN_STATUSES:
            raise ValueError(f"Unsupported Copilot turn status: {status}")
        self._normalize_conversation(conversation)
        turn = next(
            (item for item in conversation["turns"] if item.get("id") == turn_id),
            None,
        )
        if turn is None:
            raise KeyError(f"Copilot turn not found: {turn_id}")
        turn["status"] = status
        turn["updated_at"] = utc_now_iso()
        turn["error"] = error
        if assistant_message_id is not None:
            turn["assistant_message_id"] = assistant_message_id
        return turn

    def update_turn_status(
        self,
        conversation_id: str,
        turn_id: str,
        status: str,
        *,
        assistant_message_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        conversation = self.get(conversation_id)
        turn = self.set_turn_status(
            conversation,
            turn_id,
            status,
            assistant_message_id=assistant_message_id,
            error=error,
        )
        self.save(conversation)
        return turn

    def update_latest_assistant_metadata(
        self,
        conversation_id: str,
        metadata_patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        conversation = self.get(conversation_id)
        messages = conversation.get("messages")
        if not isinstance(messages, list):
            return None

        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            metadata = message.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.update(metadata_patch)
            message["metadata"] = metadata
            self.save(conversation)
            return message
        return None

    def update_focus(
        self,
        conversation_id: str,
        focus: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist Session Focus on a conversation document and return the updated doc."""
        conversation = self.get(conversation_id)
        conversation["focus"] = focus
        self.save(conversation)
        return conversation

    def update_llm(
        self,
        conversation_id: str,
        llm: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist per-conversation LLM override (provider + model)."""
        conversation = self.get(conversation_id)
        provider = str(llm.get("provider") or "").strip().lower()
        model = str(llm.get("model") or "").strip()
        conversation["llm"] = {"provider": provider, "model": model}
        self.save(conversation)
        return conversation

    def update_risk_lens(
        self,
        conversation_id: str,
        risk_lens: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist only the reversible Copilot lens, never Profile risk tolerance."""
        conversation = self.get(conversation_id)
        mode = str(risk_lens.get("mode") or "profile").strip().lower()
        posture = str(risk_lens.get("posture") or "").strip().lower() or None
        conversation["risk_lens"] = {
            "mode": "override" if mode == "override" else "profile",
            "posture": posture,
            "schema_version": 1,
        }
        self.save(conversation)
        return conversation

    def update_details(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """Rename or archive a conversation without touching its message history."""
        conversation = self.get(conversation_id)
        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValueError("Conversation title cannot be empty")
            conversation["title"] = clean_title
        if archived is not None:
            conversation["archived_at"] = utc_now_iso() if archived else None
        self.save(conversation)
        return conversation

    def list(self, limit: int = 20, *, include_archived: bool = False) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []

        for path in self.base_dir.glob("*.json"):
            try:
                doc = self._normalize_conversation(json.loads(path.read_text(encoding="utf-8")))
                if include_archived or not doc.get("archived_at"):
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
                    "archived_at": doc.get("archived_at"),
                    "last_message_preview": last_message_preview,
                    "message_count": len(messages),
                    "last_turn_status": str((doc.get("turns") or [{}])[-1].get("status") or ""),
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
        conversation_id: str | None = None,
        *,
        conversation: dict[str, Any] | None = None,
        turn: dict[str, Any] | None = None,
        turn_id: str | None = None,
        contextual_brief: str,
        context_trace: dict[str, Any] | None = None,
        conversation_store: ConversationStore | None = None,
        llm_client: ChatToolClient | None = None,
        progress_cb: Any = None,
        assistant_metadata: dict[str, Any] | None = None,
        fallback_answer: str | None = None,
    ) -> dict[str, Any]:
        store = conversation_store or self.conversation_store
        client = llm_client or self.llm_client

        def _emit(event: dict[str, Any]) -> None:
            if progress_cb is None:
                return
            try:
                progress_cb(event)
            except Exception:  # progress reporting must never break the turn
                pass

        if conversation is None:
            conversation = store.get_or_create(
                conversation_id=conversation_id,
                first_user_message=question,
            )
        # The route may create the turn before context assembly so failures and
        # cancellations remain visible in history. Direct callers start it here.
        if turn is None:
            turn = store.start_turn(conversation, question=question, turn_id=turn_id)
        durable_turn_id = str(turn["id"])

        tool_traces: list[dict[str, Any]] = []
        answer = ""
        model_name = client.model if client.enabled else None

        if client.enabled:
            messages = self._build_messages(
                conversation=conversation,
                contextual_brief=contextual_brief,
            )

            agent_client = hasattr(client, "run_agent")
            if agent_client:
                _emit({"type": "round", "round": 1})

                async def handle_agent_tool(
                    name: str,
                    arguments: dict[str, Any],
                ) -> dict[str, Any]:
                    _emit({"type": "tool", "name": name, "status": "start"})
                    result, error = await self._execute_tool(name=name, arguments=arguments)
                    _emit(
                        {
                            "type": "tool",
                            "name": name,
                            "status": "error" if error else "done",
                        }
                    )
                    tool_traces.append(
                        {
                            "name": name,
                            "arguments": arguments,
                            "result": result,
                            "error": error,
                        }
                    )
                    return {
                        "ok": error is None,
                        "result": result,
                        "error": error,
                    }

                completion = await client.run_agent(
                    messages=messages,
                    tools=self._tool_definitions(),
                    tool_handler=handle_agent_tool,
                    on_delta=(
                        (lambda text: _emit({"type": "answer_delta", "text": text}))
                        if progress_cb is not None
                        else None
                    ),
                )
                model_name = completion.get("model", model_name)
                assistant_message = completion.get("message", {})
                answer = self._message_text(assistant_message.get("content")).strip()

            for round_index in ([] if agent_client else range(self.max_tool_rounds)):
                _emit({"type": "round", "round": round_index + 1})
                if progress_cb is not None and hasattr(client, "complete_stream"):
                    completion = await client.complete_stream(
                        messages=messages,
                        tools=self._tool_definitions(),
                        on_delta=lambda text: _emit({"type": "answer_delta", "text": text}),
                    )
                else:
                    completion = await client.complete(
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

                        _emit({"type": "tool", "name": name, "status": "start"})
                        result, error = await self._execute_tool(name=name, arguments=arguments)
                        _emit(
                            {
                                "type": "tool",
                                "name": name,
                                "status": "error" if error else "done",
                            }
                        )

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
            answer = fallback_answer or (
                "Copilot is running in fallback mode because an LLM API key is not configured. "
                "I can still use direct endpoints for sync/import/planning, but conversational reasoning is limited."
            )

        message_metadata = {
            "tool_calls": tool_traces,
            "model": model_name,
            "context_trace": context_trace or {},
        }
        if isinstance(assistant_metadata, dict):
            message_metadata.update(assistant_metadata)
        assistant_message = store.append_message(
            conversation,
            role="assistant",
            content=answer,
            metadata=message_metadata,
            turn_id=durable_turn_id,
        )
        store.set_turn_status(
            conversation,
            durable_turn_id,
            "completed",
            assistant_message_id=str(assistant_message["id"]),
        )
        store.save(conversation)

        return {
            "conversation_id": conversation["id"],
            "turn_id": durable_turn_id,
            "user_message_id": turn.get("user_message_id"),
            "assistant_message_id": assistant_message["id"],
            "turn_status": "completed",
            "answer": answer,
            "tool_calls": tool_traces,
            "model": model_name,
            "context_trace": context_trace or {},
            "created_at": utc_now(),
        }
