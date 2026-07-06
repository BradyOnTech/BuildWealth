"""Per-task LLM routing — one model per job, not one model for everything.

Interactive Copilot chat deserves the strongest configured model; background
summaries and drafts can run on a cheaper or local one. The router resolves a
task class to a chat client, inheriting anything unspecified from the primary
configuration — with no per-task settings saved, every task uses the primary
client exactly as before.

v1 deliberately shares the primary API key across tasks: the split that
matters in practice is "best hosted model for chat, keyless local model
(Ollama/LM Studio via an OpenAI-compatible base URL) for cheap background
work", which needs no new secret plumbing. Routing a task to a different
*keyed* provider will fail its handshake until per-task keys exist.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from buildwealth_orchestrator.services.llm_clients import (
    LLMProviderConfig,
    build_llm_client,
    default_base_url_for_provider,
    default_model_for_provider,
)

# Task classes with a real or near-term consumer. 'chat' is the interactive
# Copilot; 'summarize' covers background summaries and draft preparation.
LLM_TASKS = ("chat", "summarize")

_OVERRIDE_FIELDS = ("provider", "model", "base_url")


def task_setting_key(task: str, field: str) -> str:
    return f"llm_task_{task}_{field}"


def task_routing_setting_keys() -> tuple[str, ...]:
    return tuple(task_setting_key(task, field) for task in LLM_TASKS for field in _OVERRIDE_FIELDS)


def extract_task_overrides(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Pull per-task override fields from a flat settings payload.

    Empty strings mean "inherit from the primary configuration" and are
    dropped here, so an override dict only ever contains real choices.
    """
    overrides: dict[str, dict[str, str]] = {}
    for task in LLM_TASKS:
        fields: dict[str, str] = {}
        for field in _OVERRIDE_FIELDS:
            value = str(payload.get(task_setting_key(task, field)) or "").strip()
            if value:
                fields[field] = value
        if fields:
            overrides[task] = fields
    return overrides


class LLMRouter:
    """Resolves a task class to a chat client, caching one client per task."""

    def __init__(
        self,
        primary_config: LLMProviderConfig,
        task_overrides: dict[str, dict[str, str]] | None = None,
    ):
        self.primary_config = primary_config
        self.task_overrides = {
            task: dict(fields)
            for task, fields in (task_overrides or {}).items()
            if task in LLM_TASKS and fields
        }
        self._clients: dict[str, Any] = {}

    def config_for(self, task: str) -> LLMProviderConfig:
        override = self.task_overrides.get(task)
        if not override:
            return self.primary_config

        provider = override.get("provider") or self.primary_config.provider
        provider_changed = provider != self.primary_config.provider
        # A new provider resets model/base_url to that provider's defaults
        # unless the override names them; same provider inherits the primary's.
        model = override.get("model") or (
            default_model_for_provider(provider) if provider_changed else self.primary_config.model
        )
        base_url = override.get("base_url") or (
            default_base_url_for_provider(provider) if provider_changed else self.primary_config.base_url
        )
        return replace(
            self.primary_config,
            provider=provider,
            model=model,
            base_url=base_url,
        )

    def client_for(self, task: str) -> Any:
        resolved_task = task if task in LLM_TASKS else "chat"
        if resolved_task not in self._clients:
            self._clients[resolved_task] = build_llm_client(self.config_for(resolved_task))
        return self._clients[resolved_task]

    def describe(self) -> list[dict[str, Any]]:
        """Per-task resolution summary for the Settings surface."""
        rows: list[dict[str, Any]] = []
        for task in LLM_TASKS:
            config = self.config_for(task)
            client = self.client_for(task)
            rows.append(
                {
                    "task": task,
                    "provider": config.provider,
                    "model": config.model,
                    "base_url": config.base_url,
                    "inherited": task not in self.task_overrides,
                    "enabled": bool(getattr(client, "enabled", False)),
                }
            )
        return rows
