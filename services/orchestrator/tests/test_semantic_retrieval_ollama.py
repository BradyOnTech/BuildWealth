"""End-to-end semantic retrieval against a real local Ollama.

Skips cleanly when Ollama (or the embedding model) isn't available, so CI
stays green; on dev machines with Ollama running it proves the full path:
index rebuild -> embedding rebuild -> semantic scores in search results.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from buildwealth_orchestrator.services.embedding_clients import OllamaEmbeddingClient

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"


def _ollama_available() -> bool:
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
        return any(name.startswith(EMBED_MODEL) for name in models)
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not _ollama_available(),
    reason=f"local Ollama with {EMBED_MODEL} not available",
)


@requires_ollama
def test_semantic_search_scores_with_real_ollama(tmp_path: Path) -> None:
    from test_context_intelligence import _build_service

    client = OllamaEmbeddingClient(model=EMBED_MODEL, base_url=OLLAMA_URL)
    service = _build_service(tmp_path, embedding_client=client)

    service.rebuild_registry()
    embed_result = service.rebuild_embeddings()
    # rebuild_registry embeds eligible items when the client is enabled, so a
    # follow-up rebuild reports them as reused — either way they're indexed.
    indexed = embed_result.get("embedded_count", 0) + embed_result.get("reused_count", 0)
    assert indexed > 0
    assert embed_result.get("failed_count") == 0

    result = service.search_context(query="what is my marginal tax rate", limit=10)
    semantic = result.get("semantic") or {}
    assert semantic.get("enabled") is True
    assert semantic.get("provider") == "ollama"
    assert semantic.get("matched_count", 0) > 0

    # The tax-rate profile item should rank near the top on a tax query.
    top_ids = [item.get("field_path") or item.get("id") for item in result["items"][:5]]
    assert any("marginal_tax_rate" in str(x) for x in top_ids), top_ids
