"""Settings routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_user_settings",
    "test_llm_settings",
    "test_embedding_settings",
    "get_llm_routing",
    "get_llm_usage",
    "get_context_settings",
]


@router.get("/api/settings")
def get_user_settings(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "settings.read")
    return services.settings_store.load_masked()


@router.post("/api/settings/test-llm")
async def test_llm_settings(
    request: dict[str, m.Any],
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.workspace_services_or_legacy(services)
    m.require_permission(resolved_services.context, "settings.read")
    payload, explicit_keys = m._settings_payload_for_probe(request, resolved_services.settings_store)
    client = m.build_llm_client(
        m._llm_config_from_payload(
            payload,
            explicit_keys=explicit_keys,
        )
    )
    try:
        result = await m.run_tool_call_probe(client)
        if not result.get("ok"):
            raise m.HTTPException(status_code=400, detail=result)
        return result
    except m.HTTPException:
        raise
    except m.httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise m.HTTPException(
            status_code=502,
            detail=m._llm_probe_failure_response(payload, client, "provider_http_error", detail),
        ) from exc
    except Exception as exc:
        raise m.HTTPException(
            status_code=500,
            detail=m._llm_probe_failure_response(payload, client, "provider_error", str(exc)),
        ) from exc


@router.post("/api/settings/test-embedding")
def test_embedding_settings(
    request: dict[str, m.Any],
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Probe the embedding provider with the supplied (or saved) settings.

    Builds a transient settings object, instantiates the embedding client,
    and runs a small embed_text() against a fixed string. Returns the
    provider/model used and the embedded vector length on success.
    """
    m.require_permission(services.context, "settings.read")
    from copy import copy

    probe_settings = copy(m.settings)
    if request.get("context_embeddings_enabled") is not None:
        val = request["context_embeddings_enabled"]
        probe_settings.context_embeddings_enabled = (
            val.strip().lower() in {"true", "1", "yes", "on"}
            if isinstance(val, str) else bool(val)
        )
    if request.get("context_embedding_provider"):
        probe_settings.context_embedding_provider = str(request["context_embedding_provider"])
    if request.get("context_embedding_model"):
        probe_settings.context_embedding_model = str(request["context_embedding_model"])
    if request.get("context_embedding_base_url"):
        probe_settings.context_embedding_base_url = str(request["context_embedding_base_url"])
    if request.get("context_embedding_timeout_seconds") is not None:
        try:
            probe_settings.context_embedding_timeout_seconds = float(request["context_embedding_timeout_seconds"])
        except (TypeError, ValueError):
            pass

    try:
        client = m.build_embedding_client_from_settings(probe_settings)
    except Exception as exc:
        raise m.HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "stage": "build_client",
                "detail": str(exc),
                "provider": probe_settings.context_embedding_provider,
                "model": probe_settings.context_embedding_model,
            },
        ) from exc

    if not getattr(client, "enabled", False):
        return {
            "ok": True,
            "enabled": False,
            "provider": getattr(client, "provider", "disabled"),
            "model": getattr(client, "model", ""),
            "detail": "Embeddings are disabled — narrative search will fall back to structured data.",
        }

    try:
        vector = client.embed_text("BuildWealth handshake probe")
    except Exception as exc:
        raise m.HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "stage": "embed_text",
                "detail": str(exc)[:500],
                "provider": getattr(client, "provider", probe_settings.context_embedding_provider),
                "model": getattr(client, "model", probe_settings.context_embedding_model),
            },
        ) from exc

    return {
        "ok": True,
        "enabled": True,
        "provider": getattr(client, "provider", probe_settings.context_embedding_provider),
        "model": getattr(client, "model", probe_settings.context_embedding_model),
        "vector_length": len(vector) if vector is not None else 0,
        "detail": "Embedding handshake succeeded.",
    }


@router.get("/api/settings/llm-routing")
def get_llm_routing(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Which model serves which task class, after inheritance is resolved."""
    m.require_permission(services.context, "settings.read")
    return {"tasks": m.llm_router.describe()}


@router.get("/api/settings/llm-usage")
def get_llm_usage(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Local token ledger: what the household's key spent, by model and task."""
    m.require_permission(services.context, "settings.read")
    return m.llm_usage_ledger.summary()


@router.get("/api/settings/context")
def get_context_settings(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Read-only summary of context-intelligence + embedding configuration.

    These knobs are env-driven today (CONTEXT_EMBEDDING_*), not user-editable
    via the user_settings store. The v2 Settings page renders this read-only
    so users can see what's configured without needing to know the env-var
    names. Editing is deferred until Slice 6 wires UserSettingsStore support.
    """
    m.require_permission(services.context, "settings.read")
    registry_status = services.context_intelligence_service.get_status()
    # Report the client the workspace actually uses — global settings can lag
    # behind the workspace store after a restart.
    embedding_client = getattr(services.context_intelligence_service, "embedding_client", None)
    client_enabled = bool(getattr(embedding_client, "enabled", False))
    return {
        "context_engine_enabled": True,
        "embeddings_enabled": client_enabled,
        "embedding_provider": (
            str(getattr(embedding_client, "provider", "disabled"))
            if client_enabled
            else m.settings.context_embedding_provider
        ),
        "embedding_model": (
            str(getattr(embedding_client, "model", ""))
            if client_enabled
            else m.settings.context_embedding_model
        ),
        "embedding_base_url": str(
            getattr(embedding_client, "base_url", m.settings.context_embedding_base_url)
        ),
        "embedding_timeout_seconds": float(
            getattr(embedding_client, "timeout_seconds", m.settings.context_embedding_timeout_seconds)
        ),
        "registry": {
            "item_count": int(registry_status.get("item_count", 0) or 0),
            "embedded_count": int(((registry_status.get("embeddings") or {}).get("embedded_count")) or 0),
            "candidate_count": int(((registry_status.get("candidates") or {}).get("candidate_count")) or 0),
            "pending_review_count": int(((registry_status.get("candidates") or {}).get("pending_review_count")) or 0),
            "latest_rebuild_at": registry_status.get("latest_rebuild_at"),
        },
    }
