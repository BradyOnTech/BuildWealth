from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class EmbeddingClient(Protocol):
    provider: str
    model: str
    enabled: bool

    def embed_text(self, text: str) -> list[float] | None: ...


@dataclass(frozen=True)
class DisabledEmbeddingClient:
    provider: str = "disabled"
    model: str = "disabled"
    enabled: bool = False

    def embed_text(self, text: str) -> list[float] | None:
        return None


@dataclass(frozen=True)
class OllamaEmbeddingClient:
    model: str
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 5.0
    provider: str = "ollama"
    enabled: bool = True

    def embed_text(self, text: str) -> list[float] | None:
        cleaned_text = str(text or "").strip()
        if not cleaned_text:
            return None

        response = httpx.post(
            f"{self.base_url.rstrip('/')}/api/embeddings",
            json={"model": self.model, "prompt": cleaned_text},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload.get("embedding")
        if not isinstance(embedding, list):
            return None
        return _normalize_embedding_vector(embedding)


def build_embedding_client_from_settings(settings: Any) -> EmbeddingClient:
    enabled = bool(getattr(settings, "context_embeddings_enabled", False))
    provider = str(getattr(settings, "context_embedding_provider", "disabled") or "disabled").strip().lower()
    if not enabled or provider in {"", "disabled", "none", "off"}:
        return DisabledEmbeddingClient(provider="disabled", model="disabled")

    model = str(getattr(settings, "context_embedding_model", "") or "").strip()
    if provider == "ollama" and model:
        return OllamaEmbeddingClient(
            model=model,
            base_url=str(getattr(settings, "context_embedding_base_url", "http://localhost:11434") or ""),
            timeout_seconds=float(getattr(settings, "context_embedding_timeout_seconds", 5.0) or 5.0),
        )

    return DisabledEmbeddingClient(provider="disabled", model="disabled")


def _normalize_embedding_vector(values: list[Any]) -> list[float] | None:
    vector: list[float] = []
    for value in values:
        try:
            vector.append(float(value))
        except (TypeError, ValueError):
            return None
    return vector or None
