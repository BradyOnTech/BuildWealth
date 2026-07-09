"""Provider adapters for Copilot chat models with client-side tool use."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_XAI_MODEL = "grok-4.5"
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"

LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_GEMINI = "gemini"
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_XAI = "xai"
LLM_PROVIDER_CUSTOM_OPENAI_COMPATIBLE = "custom_openai_compatible"

OPENAI_COMPATIBLE_PROVIDERS = {
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_GEMINI,
    LLM_PROVIDER_CUSTOM_OPENAI_COMPATIBLE,
}


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float = 60.0
    max_tokens: int = 2048
    parallel_tool_calls: bool = True


class ChatToolClient(Protocol):
    provider: str
    model: str

    @property
    def enabled(self) -> bool: ...

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


ECHO_PROBE_VALUE = 7


def echo_probe_tool_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "echo_tool",
            "description": "Echo a numeric value back to verify client-side tool calling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "The numeric value to echo.",
                    }
                },
                "required": ["value"],
            },
        },
    }


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            return {"_raw": raw_arguments}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if raw_arguments is None:
        return {}
    return {"value": raw_arguments}


def _numeric_probe_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


async def run_tool_call_probe(client: ChatToolClient) -> dict[str, Any]:
    if not client.enabled:
        return {
            "ok": False,
            "provider": getattr(client, "provider", "unknown"),
            "model": getattr(client, "model", None),
            "stage": "configuration",
            "detail": "LLM API key is not configured.",
            "tool_calls": [],
            "answer": "",
        }

    tools = [echo_probe_tool_definition()]
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a provider compatibility probe. You must call echo_tool with "
                f'value {ECHO_PROBE_VALUE}, wait for the tool result, then answer exactly '
                f'"ECHO_VALUE={ECHO_PROBE_VALUE}".'
            ),
        },
        {
            "role": "user",
            "content": f"Call echo_tool with value {ECHO_PROBE_VALUE}, then report the echoed value.",
        },
    ]

    first = await client.complete(messages=messages, tools=tools)
    provider = first.get("provider", getattr(client, "provider", "unknown"))
    model = first.get("model", getattr(client, "model", None))
    assistant_message = first.get("message", {})
    tool_calls = assistant_message.get("tool_calls") or []
    if not tool_calls:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "stage": "tool_call",
            "detail": "The model did not request the probe tool.",
            "tool_calls": [],
            "answer": _message_text(assistant_message.get("content")),
        }

    messages.append(
        {
            "role": "assistant",
            "content": _message_text(assistant_message.get("content")),
            "tool_calls": tool_calls,
        }
    )

    traces: list[dict[str, Any]] = []
    for call in tool_calls:
        function_block = call.get("function", {}) if isinstance(call, dict) else {}
        name = str(function_block.get("name") or "")
        arguments = _parse_tool_arguments(function_block.get("arguments"))
        value = arguments.get("value")
        numeric_value = _numeric_probe_value(value)
        ok = name == "echo_tool" and numeric_value == float(ECHO_PROBE_VALUE)
        tool_payload = {
            "ok": ok,
            "result": {"echo": ECHO_PROBE_VALUE} if ok else {},
            "error": None if ok else f"Unexpected probe tool call: {name}({arguments})",
        }
        traces.append(
            {
                "name": name,
                "arguments": arguments,
                "ok": ok,
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", "") if isinstance(call, dict) else "",
                "content": _safe_json_dumps(tool_payload),
            }
        )

    if not all(trace["ok"] for trace in traces):
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "stage": "tool_arguments",
            "detail": "The model requested an unexpected tool name or argument payload.",
            "tool_calls": traces,
            "answer": "",
        }

    second = await client.complete(messages=messages, tools=tools)
    final_message = second.get("message", {})
    answer = _message_text(final_message.get("content"))
    model = second.get("model", model)
    ok = f"ECHO_VALUE={ECHO_PROBE_VALUE}" in answer
    return {
        "ok": ok,
        "provider": second.get("provider", provider),
        "model": model,
        "stage": "final_answer" if not ok else "complete",
        "detail": "Provider completed a client-side tool call loop." if ok else "Final answer did not include the expected probe value.",
        "tool_calls": traces,
        "answer": answer,
    }


def _coerce_provider(provider: str | None) -> str:
    value = (provider or LLM_PROVIDER_OPENAI).strip().lower()
    supported = {
        LLM_PROVIDER_OPENAI,
        LLM_PROVIDER_GEMINI,
        LLM_PROVIDER_ANTHROPIC,
        LLM_PROVIDER_XAI,
        LLM_PROVIDER_CUSTOM_OPENAI_COMPATIBLE,
    }
    return value if value in supported else LLM_PROVIDER_OPENAI


def default_base_url_for_provider(provider: str) -> str:
    if provider == LLM_PROVIDER_GEMINI:
        return DEFAULT_GEMINI_BASE_URL
    if provider == LLM_PROVIDER_ANTHROPIC:
        return DEFAULT_ANTHROPIC_BASE_URL
    if provider == LLM_PROVIDER_XAI:
        return DEFAULT_XAI_BASE_URL
    return DEFAULT_OPENAI_BASE_URL


def default_model_for_provider(provider: str) -> str:
    if provider == LLM_PROVIDER_GEMINI:
        return DEFAULT_GEMINI_MODEL
    if provider == LLM_PROVIDER_ANTHROPIC:
        return DEFAULT_ANTHROPIC_MODEL
    if provider == LLM_PROVIDER_XAI:
        return DEFAULT_XAI_MODEL
    return DEFAULT_OPENAI_MODEL


def provider_label(provider: str) -> str:
    labels = {
        LLM_PROVIDER_OPENAI: "OpenAI",
        LLM_PROVIDER_GEMINI: "Gemini",
        LLM_PROVIDER_ANTHROPIC: "Anthropic",
        LLM_PROVIDER_XAI: "xAI",
        LLM_PROVIDER_CUSTOM_OPENAI_COMPATIBLE: "Custom OpenAI-compatible",
    }
    return labels.get(provider, provider)


def _safe_json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, default=str)


def _parse_jsonish(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            return {"_raw": value}
    if value is None:
        return {}
    return {"value": value}


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                if item.get("type") in {"text", "output_text", "input_text"} and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
                elif isinstance(item.get("content"), str):
                    chunks.append(item["content"])
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if content is None:
        return ""
    return str(content)


class OpenAICompatibleChatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        provider: str = LLM_PROVIDER_OPENAI,
        timeout_seconds: float = 60.0,
        parallel_tool_calls: bool = True,
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.parallel_tool_calls = parallel_tool_calls

    @property
    def enabled(self) -> bool:
        # Local OpenAI-compatible servers (Ollama, LM Studio, proxies) don't
        # require a bearer token; a custom endpoint with a model and URL is
        # usable keyless. Hosted providers still require their key.
        if self.provider == LLM_PROVIDER_CUSTOM_OPENAI_COMPATIBLE:
            return bool(self.model and self.base_url)
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
            payload["parallel_tool_calls"] = self.parallel_tool_calls

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

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
            "provider": self.provider,
        }


class AnthropicMessagesClient:
    provider = LLM_PROVIDER_ANTHROPIC

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_ANTHROPIC_BASE_URL,
        timeout_seconds: float = 60.0,
        max_tokens: int = 2048,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

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

        payload = self._build_payload(messages=messages, tools=tools)
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return self._normalize_response(data)

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system_chunks: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []

        index = 0
        while index < len(messages):
            message = messages[index]
            role = message.get("role")
            if role == "system":
                text = _message_text(message.get("content"))
                if text:
                    system_chunks.append(text)
                index += 1
                continue
            if role == "tool":
                tool_result_blocks: list[dict[str, Any]] = []
                while index < len(messages) and messages[index].get("role") == "tool":
                    tool_message = messages[index]
                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": str(tool_message.get("tool_call_id") or ""),
                            "content": _message_text(tool_message.get("content")),
                        }
                    )
                    index += 1
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": tool_result_blocks,
                    }
                )
                continue
            if role == "assistant":
                content_blocks = self._assistant_content_blocks(message)
                if content_blocks:
                    anthropic_messages.append({"role": "assistant", "content": content_blocks})
                index += 1
                continue
            if role == "user":
                text = _message_text(message.get("content"))
                anthropic_messages.append({"role": "user", "content": text})
                index += 1
                continue
            index += 1

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }
        if system_chunks:
            payload["system"] = "\n\n".join(system_chunks)
        if tools:
            payload["tools"] = [self._anthropic_tool(tool) for tool in tools]
            payload["tool_choice"] = {"type": "auto"}
        return payload

    @staticmethod
    def _assistant_content_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        text = _message_text(message.get("content"))
        if text:
            blocks.append({"type": "text", "text": text})
        for call in message.get("tool_calls") or []:
            function_block = call.get("function", {}) if isinstance(call, dict) else {}
            blocks.append(
                {
                    "type": "tool_use",
                    "id": str(call.get("id") or "") if isinstance(call, dict) else "",
                    "name": str(function_block.get("name") or ""),
                    "input": _parse_jsonish(function_block.get("arguments")),
                }
            )
        return blocks

    @staticmethod
    def _anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
        function_block = tool.get("function", {}) if isinstance(tool, dict) else {}
        return {
            "name": str(function_block.get("name") or ""),
            "description": str(function_block.get("description") or ""),
            "input_schema": function_block.get("parameters") or {"type": "object", "properties": {}},
        }

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        content = data.get("content") or []
        text_chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text_chunks.append(block["text"])
            if block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or ""),
                            "arguments": _safe_json_dumps(block.get("input") or {}),
                        },
                    }
                )
        return {
            "message": {
                "content": "\n".join(text_chunks).strip(),
                "tool_calls": tool_calls,
            },
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model),
            "provider": self.provider,
        }


class XAIResponsesClient:
    provider = LLM_PROVIDER_XAI

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_XAI_BASE_URL,
        timeout_seconds: float = 60.0,
        max_tokens: int = 2048,
        parallel_tool_calls: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.parallel_tool_calls = parallel_tool_calls
        self._last_response_id: str | None = None

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

        payload = self._build_request_payload(messages=messages, tools=tools)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if data.get("id"):
            self._last_response_id = str(data["id"])
        return self._normalize_response(data)

    def _build_request_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        tool_outputs = self._responses_tool_outputs(messages)
        if self._last_response_id and tool_outputs:
            payload = self._base_payload(input_items=tool_outputs, tools=tools)
            payload["previous_response_id"] = self._last_response_id
            return payload
        self._last_response_id = None
        return self._base_payload(input_items=self._responses_input(messages), tools=tools)

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._base_payload(input_items=self._responses_input(messages), tools=tools)

    def _base_payload(
        self,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "max_output_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = [self._responses_tool(tool) for tool in tools]
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = self.parallel_tool_calls
        return payload

    @staticmethod
    def _responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(message.get("tool_call_id") or ""),
                        "output": _message_text(message.get("content")),
                    }
                )
                continue
            if role == "assistant" and message.get("tool_calls"):
                for call in message.get("tool_calls") or []:
                    function_block = call.get("function", {}) if isinstance(call, dict) else {}
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": str(call.get("id") or "") if isinstance(call, dict) else "",
                            "name": str(function_block.get("name") or ""),
                            "arguments": function_block.get("arguments") or "{}",
                        }
                    )
                text = _message_text(message.get("content"))
                if text:
                    items.append({"role": "assistant", "content": text})
                continue
            if role in {"system", "user", "assistant"}:
                text = _message_text(message.get("content"))
                if text:
                    items.append({"role": role, "content": text})
        return items

    @staticmethod
    def _responses_tool_outputs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trailing_tool_messages: list[dict[str, Any]] = []
        for message in reversed(messages):
            if message.get("role") != "tool":
                break
            trailing_tool_messages.append(message)
        trailing_tool_messages.reverse()
        return [
            {
                "type": "function_call_output",
                "call_id": str(message.get("tool_call_id") or ""),
                "output": _message_text(message.get("content")),
            }
            for message in trailing_tool_messages
        ]

    @staticmethod
    def _responses_tool(tool: dict[str, Any]) -> dict[str, Any]:
        function_block = tool.get("function", {}) if isinstance(tool, dict) else {}
        return {
            "type": "function",
            "name": str(function_block.get("name") or ""),
            "description": str(function_block.get("description") or ""),
            "parameters": function_block.get("parameters") or {"type": "object", "properties": {}},
        }

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        text_chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in {"message", "output_message"}:
                content = item.get("content") or []
                text = _message_text(content)
                if text:
                    text_chunks.append(text)
            if item_type == "output_text" and isinstance(item.get("text"), str):
                text_chunks.append(item["text"])
            if item_type == "function_call":
                tool_calls.append(
                    {
                        "id": str(item.get("call_id") or item.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(item.get("name") or ""),
                            "arguments": item.get("arguments") or "{}",
                        },
                    }
                )
        return {
            "message": {
                "content": "\n".join(text_chunks).strip(),
                "tool_calls": tool_calls,
            },
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model),
            "provider": self.provider,
        }


def build_llm_client(config: LLMProviderConfig) -> ChatToolClient:
    provider = _coerce_provider(config.provider)
    model = config.model or default_model_for_provider(provider)
    base_url = config.base_url or default_base_url_for_provider(provider)
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleChatClient(
            api_key=config.api_key,
            model=model,
            base_url=base_url,
            provider=provider,
            timeout_seconds=config.timeout_seconds,
            parallel_tool_calls=config.parallel_tool_calls,
        )
    if provider == LLM_PROVIDER_ANTHROPIC:
        return AnthropicMessagesClient(
            api_key=config.api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=config.timeout_seconds,
            max_tokens=config.max_tokens,
        )
    if provider == LLM_PROVIDER_XAI:
        return XAIResponsesClient(
            api_key=config.api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=config.timeout_seconds,
            max_tokens=config.max_tokens,
            parallel_tool_calls=config.parallel_tool_calls,
        )
    return OpenAICompatibleChatClient(
        api_key=config.api_key,
        model=model,
        base_url=base_url,
        provider=LLM_PROVIDER_OPENAI,
        timeout_seconds=config.timeout_seconds,
        parallel_tool_calls=config.parallel_tool_calls,
    )
