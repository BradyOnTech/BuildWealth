"""Copilot routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

import asyncio
import inspect
import json

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_copilot_context",
    "get_copilot_context_cache_status",
    "reset_copilot_context_cache",
    "list_copilot_conversations",
    "get_copilot_conversation",
    "patch_copilot_conversation_focus",
    "patch_copilot_conversation_llm",
    "get_copilot_llm_options",
    "list_copilot_focus_domains",
    "copilot_chat",
    "copilot_chat_stream",
]


@router.get("/api/copilot/context", response_model=m.CopilotContextResponse)
async def get_copilot_context(
    question: str = "Give me a complete BuildWealth financial context briefing.",
    use_live_snapshot: bool = False,
    plan_id: str | None = None,
    include_research: bool = True,
    include_plan_projection: bool = True,
    force_refresh: bool = False,
    research_symbols: str | None = None,
    research_period: str = "6mo",
    research_interval: str = "1d",
    research_symbol_limit: int = m.DEFAULT_RESEARCH_SYMBOL_LIMIT,
    max_recommendations: int = 10,
    max_plan_decisions: int = 8,
    summary_max_chars: int = m.DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
    detail_level: str = m.DEFAULT_CONTEXT_DETAIL_LEVEL,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "copilot.use")
    symbols_input = [
        item.strip()
        for item in str(research_symbols or "").split(",")
        if item.strip()
    ]
    return await m.assemble_copilot_context_payload(
        question=question,
        use_live_snapshot=use_live_snapshot,
        plan_id=plan_id,
        include_research=include_research,
        force_refresh=force_refresh,
        research_symbols=symbols_input,
        research_period=research_period,
        research_interval=research_interval,
        include_plan_projection=include_plan_projection,
        max_recommendations=max_recommendations,
        max_plan_decisions=max_plan_decisions,
        summary_max_chars=summary_max_chars,
        research_symbol_limit=research_symbol_limit,
        detail_level=detail_level,
        services=services,
    )


@router.get("/api/copilot/context/cache", response_model=m.CopilotContextCacheStatusResponse)
def get_copilot_context_cache_status() -> m.CopilotContextCacheStatusResponse:
    research_stats = m.copilot_context_research_cache.stats()
    projection_stats = m.copilot_context_projection_cache.stats()
    return m.CopilotContextCacheStatusResponse(
        as_of=m.utc_now(),
        enabled=bool(m.settings.copilot_context_cache_enabled),
        stores=[
            {
                "name": "research",
                **research_stats,
            },
            {
                "name": "baseline_projection",
                **projection_stats,
            },
        ],
    )


@router.post("/api/copilot/context/cache/reset", response_model=m.CopilotContextCacheStatusResponse)
def reset_copilot_context_cache(
    target: str = "all",
    reset_metrics: bool = True,
) -> m.CopilotContextCacheStatusResponse:
    target_value = str(target or "all").strip().lower()
    valid_targets = {"all", "research", "baseline_projection"}
    if target_value not in valid_targets:
        raise m.HTTPException(
            status_code=400,
            detail=f"Unsupported cache target '{target}'. Expected one of: all, research, baseline_projection.",
        )

    if target_value in {"all", "research"}:
        m.copilot_context_research_cache.clear(reset_metrics=reset_metrics)
    if target_value in {"all", "baseline_projection"}:
        m.copilot_context_projection_cache.clear(reset_metrics=reset_metrics)

    return m.get_copilot_context_cache_status()


@router.get("/api/copilot/conversations", response_model=list[m.CopilotConversationSummary])
def list_copilot_conversations(
    limit: int = 30,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[m.CopilotConversationSummary]:
    m.require_permission(services.context, "copilot.use")
    summaries = services.conversation_store.list(limit=max(1, min(limit, 200)))
    return [m.CopilotConversationSummary(**summary) for summary in summaries]


@router.get("/api/copilot/conversations/{conversation_id}", response_model=m.CopilotConversationResponse)
def get_copilot_conversation(
    conversation_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CopilotConversationResponse:
    m.require_permission(services.context, "copilot.use")
    try:
        conversation = services.conversation_store.get(conversation_id)
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    workspace_settings = services.settings_store.load_raw()
    resolved_llm = m._resolve_conversation_llm(
        workspace_settings=workspace_settings,
        conversation_llm=conversation.get("llm") if isinstance(conversation, dict) else None,
        request_llm=None,
        settings_store=services.settings_store,
    )
    payload = dict(conversation)
    payload["focus"] = m.public_focus(conversation.get("focus") if isinstance(conversation, dict) else None)
    payload["llm"] = m.ConversationLlm(**resolved_llm)
    return m.CopilotConversationResponse(**payload)


@router.patch("/api/copilot/conversations/{conversation_id}/focus", response_model=m.SessionFocus)
def patch_copilot_conversation_focus(
    conversation_id: str,
    request: m.SessionFocusUpdateRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.SessionFocus:
    m.require_permission(services.context, "copilot.use")
    try:
        conversation = services.conversation_store.get(conversation_id)
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        patch_payload = request.model_dump(exclude_unset=True)
        resolved = m.merge_focus_patch(
            conversation.get("focus") if isinstance(conversation, dict) else None,
            patch_payload,
            set_by="user",
        )
    except m.SessionFocusValidationError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    services.conversation_store.update_focus(conversation_id, m.public_focus(resolved))
    return m.SessionFocus(**m.public_focus(resolved))


@router.patch("/api/copilot/conversations/{conversation_id}/llm", response_model=m.ConversationLlm)
def patch_copilot_conversation_llm(
    conversation_id: str,
    request: m.ConversationLlmUpdateRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ConversationLlm:
    """Set or clear the model used for this conversation (any connected provider)."""
    m.require_permission(services.context, "copilot.use")
    try:
        conversation = services.conversation_store.get(conversation_id)
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    workspace_settings = services.settings_store.load_raw()
    workspace_provider = str(workspace_settings.get("llm_provider") or "openai").strip().lower()
    patch = request.model_dump(exclude_unset=True)
    provider = str(patch.get("provider") or workspace_provider).strip().lower()
    model = str(patch.get("model") or "").strip()
    connected_ids = m._connected_provider_ids(workspace_settings, services.settings_store)
    if model and provider and provider not in connected_ids:
        raise m.HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider}' is not connected. "
                "Add its API key in Settings — you can keep several vendors connected at once."
            ),
        )
    services.conversation_store.update_llm(
        conversation_id,
        {"provider": provider if model else "", "model": model},
    )
    resolved = m._resolve_conversation_llm(
        workspace_settings=workspace_settings,
        conversation_llm={"provider": provider if model else "", "model": model},
        request_llm=None,
        settings_store=services.settings_store,
    )
    return m.ConversationLlm(**resolved)


@router.get("/api/copilot/llm-options")
def get_copilot_llm_options(
    conversation_id: str | None = None,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Catalog of providers/models plus which providers are connected for this workspace."""
    m.require_permission(services.context, "copilot.use")
    workspace_settings = services.settings_store.load_raw()
    conversation_llm = None
    if conversation_id:
        try:
            conversation = services.conversation_store.get(conversation_id)
            if isinstance(conversation, dict) and isinstance(conversation.get("llm"), dict):
                conversation_llm = conversation.get("llm")
        except FileNotFoundError:
            conversation_llm = None
    connected = m._connected_providers_from_settings(workspace_settings, services.settings_store)
    return m.build_llm_options_payload(
        active_provider=str(workspace_settings.get("llm_provider") or "openai"),
        active_model=str(workspace_settings.get("llm_model") or ""),
        connected_providers=connected,
        conversation_llm=conversation_llm if isinstance(conversation_llm, dict) else None,
    )


@router.get("/api/copilot/focus/domains")
def list_copilot_focus_domains(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, list[str]]:
    m.require_permission(services.context, "copilot.use")
    return {"domains": sorted(m.FOCUS_DOMAIN_CATALOG)}


async def _copilot_chat_pipeline(
    request: m.CopilotChatRequest,
    services: m.WorkspaceServices,
    progress: m.Any = None,
) -> dict[str, m.Any]:
    """Shared chat pipeline used by both the blocking and streaming endpoints.

    `progress` (optional callable) receives dict events: stage/round/tool/
    answer_delta. It is forwarded to the copilot runtime only when the runtime
    accepts a progress_cb parameter, so test fakes with narrower signatures
    keep working.
    """
    scoped_services = hasattr(services, "context")
    resolved_services = services if scoped_services else m.resolve_workspace_services(None)
    if scoped_services:
        m.require_permission(resolved_services.context, "copilot.use")
    context_options = request.context_options
    context_symbols = m.normalize_research_symbols(
        context_options.research_symbols,
        max_symbols=context_options.research_symbol_limit,
    )
    token = m.current_copilot_workspace_services.set(resolved_services) if scoped_services else None
    try:
        store = resolved_services.conversation_store
        try:
            conversation = store.get_or_create(
                conversation_id=request.conversation_id,
                first_user_message=request.question,
            )
        except FileNotFoundError as exc:
            raise m.HTTPException(status_code=404, detail=str(exc)) from exc

        workspace_settings = resolved_services.settings_store.load_raw()
        request_llm_payload = (
            request.llm.model_dump(exclude_unset=True) if request.llm is not None else None
        )
        resolved_llm = m._resolve_conversation_llm(
            workspace_settings=workspace_settings,
            conversation_llm=conversation.get("llm") if isinstance(conversation, dict) else None,
            request_llm=request_llm_payload,
            settings_store=resolved_services.settings_store,
        )
        if request.persist_llm and request_llm_payload is not None:
            model_to_store = str(resolved_llm.get("model") or "").strip()
            provider_to_store = str(resolved_llm.get("provider") or "").strip().lower()
            # Persist only true overrides (not identical to workspace default).
            workspace_model = str(workspace_settings.get("llm_model") or "").strip()
            workspace_provider = str(workspace_settings.get("llm_provider") or "").strip().lower()
            is_default = (
                provider_to_store == workspace_provider and model_to_store == workspace_model
            )
            if model_to_store and not is_default:
                conversation = store.update_llm(
                    conversation["id"],
                    {"provider": provider_to_store, "model": model_to_store},
                )
            elif "model" in (request_llm_payload or {}) and not model_to_store:
                conversation = store.update_llm(conversation["id"], {"provider": "", "model": ""})
        turn_llm_client = m._chat_client_for_resolved_llm(
            workspace_settings=workspace_settings,
            resolved=resolved_llm,
            settings_store=resolved_services.settings_store,
        )

        stored_focus = conversation.get("focus") if isinstance(conversation, dict) else None
        request_focus_payload = (
            request.focus.model_dump(mode="json") if request.focus is not None else None
        )
        # Treat empty default focus from the client as "no chip authority" so NL can apply.
        if isinstance(request_focus_payload, dict):
            set_by = str(request_focus_payload.get("set_by") or "default").strip().lower()
            has_lists = any(
                request_focus_payload.get(key)
                for key in (
                    "primary_domains",
                    "secondary_domains",
                    "muted_domains",
                    "pinned_entity_ids",
                    "priority_note",
                )
            )
            if set_by in {"", "default"} and not has_lists and request_focus_payload.get("mode", "balanced") == "balanced":
                request_focus_payload = None
        # UI chips (or entry seeds) win; otherwise apply deterministic NL mute/focus phrases this turn.
        nl_patch = None
        if request_focus_payload is None:
            nl_patch = m.parse_session_focus_utterance(request.question)
        try:
            resolved_focus = m.resolve_turn_focus(
                stored=stored_focus if isinstance(stored_focus, dict) else None,
                request_focus=request_focus_payload,
                nl_patch=nl_patch,
            )
        except m.SessionFocusValidationError as exc:
            raise m.HTTPException(status_code=400, detail=str(exc)) from exc

        resolved_focus_public = m.public_focus(resolved_focus)
        if request.persist_focus and not m.focus_equal(stored_focus, resolved_focus_public):
            conversation = store.update_focus(conversation["id"], resolved_focus_public)
            conversation["focus"] = resolved_focus_public

        conv_token = m.current_copilot_conversation_id.set(str(conversation.get("id") or ""))
        boost_enabled = bool(getattr(m.settings, "copilot_retrieval_focus_boost", True))
        try:
            if progress is not None:
                progress({"type": "stage", "stage": "assembling_context"})
            assembled_context = await m.assemble_copilot_context_payload(
                question=request.question,
                use_live_snapshot=request.use_live_snapshot,
                plan_id=request.plan_id,
                include_research=context_options.include_research,
                include_plan_projection=context_options.include_plan_projection,
                force_refresh=context_options.force_refresh,
                detail_level=context_options.detail_level,
                research_symbols=context_symbols,
                research_period=context_options.research_period,
                research_interval=context_options.research_interval,
                research_symbol_limit=context_options.research_symbol_limit,
                summary_max_chars=context_options.summary_max_chars,
                focus=resolved_focus_public,
                retrieval_focus_boost=boost_enabled,
                services=resolved_services if scoped_services else None,
            )
            intent_for_focus = None
            if isinstance(assembled_context, dict):
                trace_for_intent = assembled_context.get("trace")
                if isinstance(trace_for_intent, dict) and isinstance(trace_for_intent.get("intent"), dict):
                    intent_for_focus = trace_for_intent.get("intent")
            effective_from_assembly = (
                assembled_context.get("effective_focus")
                if isinstance(assembled_context, dict)
                else None
            )
            if isinstance(effective_from_assembly, dict):
                effective_obj = m.EffectiveFocus(
                    mode=str(effective_from_assembly.get("mode") or "balanced"),
                    primary_domains=tuple(effective_from_assembly.get("primary_domains") or ()),
                    secondary_domains=tuple(effective_from_assembly.get("secondary_domains") or ()),
                    muted_domains=tuple(effective_from_assembly.get("muted_domains") or ()),
                    pinned_entity_ids=tuple(effective_from_assembly.get("pinned_entity_ids") or ()),
                    priority_note=str(effective_from_assembly.get("priority_note") or ""),
                    set_by=str(effective_from_assembly.get("set_by") or "default"),
                    retrieval_registry_domains=tuple(
                        effective_from_assembly.get("retrieval_registry_domains") or ()
                    ),
                )
            else:
                effective_obj = m.merge_focus_with_intent(resolved_focus_public, intent_for_focus)
                effective_from_assembly = effective_obj.as_dict()
            contextual_brief = m.build_copilot_prompt_brief(
                assembled_context,
                focus=resolved_focus_public,
                effective_focus=effective_from_assembly,
            )
            context_trace = (
                dict(assembled_context.get("trace"))
                if isinstance(assembled_context, dict) and isinstance(assembled_context.get("trace"), dict)
                else {}
            )
            safety_warnings = (
                assembled_context.get("safety_warnings")
                if isinstance(assembled_context, dict)
                else []
            )
            if not isinstance(safety_warnings, list):
                safety_warnings = context_trace.get("safety_warnings") or []
            context_trace["focus_applied"] = m.focus_applied_brief_and_retrieval(
                effective=effective_obj,
                brief_chars=len(contextual_brief),
                brief_truncated='"brief_truncated":true' in contextual_brief
                or '"brief_truncated": true' in contextual_brief,
                safety_warnings=safety_warnings if isinstance(safety_warnings, list) else [],
                package_sections_included=list(effective_obj.primary_domains)
                + list(effective_obj.secondary_domains),
                package_sections_omitted=list(effective_obj.muted_domains),
                retrieval_focus_boost=boost_enabled,
                detail_level=context_options.detail_level,
            )
            try:
                chat_kwargs: dict[str, m.Any] = dict(
                    question=request.question,
                    conversation=conversation,
                    contextual_brief=contextual_brief,
                    context_trace=context_trace,
                    conversation_store=store,
                    llm_client=turn_llm_client,
                )
                if progress is not None:
                    progress({"type": "stage", "stage": "thinking"})
                    try:
                        accepts_progress = (
                            "progress_cb" in inspect.signature(m.copilot.chat).parameters
                        )
                    except (TypeError, ValueError):
                        accepts_progress = False
                    if accepts_progress:
                        chat_kwargs["progress_cb"] = progress
                result = await m.copilot.chat(**chat_kwargs)
                captured_candidates = resolved_services.context_intelligence_service.detect_chat_context_candidates(
                    message=request.question,
                    conversation_id=str(result.get("conversation_id") or "").strip() or None,
                    message_index=None,
                )
                context_trace = result.get("context_trace") if isinstance(result.get("context_trace"), dict) else {}
                context_trace["focus_applied"] = m.focus_applied_brief_and_retrieval(
                    effective=effective_obj,
                    brief_chars=len(contextual_brief),
                    brief_truncated='"brief_truncated":true' in contextual_brief,
                    safety_warnings=safety_warnings if isinstance(safety_warnings, list) else [],
                    package_sections_included=list(effective_obj.primary_domains)
                    + list(effective_obj.secondary_domains),
                    package_sections_omitted=list(effective_obj.muted_domains),
                    retrieval_focus_boost=boost_enabled,
                    detail_level=context_options.detail_level,
                )
                context_trace["captured_context_candidates"] = [
                    {
                        "id": candidate.get("id"),
                        "target_domain": candidate.get("target_domain"),
                        "target_field": candidate.get("target_field"),
                        "lifecycle_state": candidate.get("lifecycle_state"),
                        "prompt_influence": candidate.get("prompt_influence"),
                        "review_item": candidate.get("review_item"),
                    }
                    for candidate in captured_candidates
                ]
                result["context_trace"] = context_trace
                conversation_id = str(result.get("conversation_id") or conversation.get("id") or "").strip()
                response_focus = resolved_focus_public
                if conversation_id:
                    try:
                        persisted = store.get(conversation_id)
                        response_focus = m.public_focus(
                            persisted.get("focus") if isinstance(persisted, dict) else None
                        )
                    except FileNotFoundError:
                        response_focus = resolved_focus_public
                    store.update_latest_assistant_metadata(
                        conversation_id,
                        {"context_trace": context_trace},
                    )
                result["focus"] = response_focus
                result["llm"] = m.ConversationLlm(**resolved_llm)
            except FileNotFoundError as exc:
                raise m.HTTPException(status_code=404, detail=str(exc)) from exc
            except m.httpx.HTTPStatusError as exc:
                detail = f"LLM provider error: {exc.response.text}"
                raise m.HTTPException(status_code=502, detail=detail) from exc
            except Exception as exc:
                raise m.HTTPException(status_code=500, detail=f"Copilot failed: {exc}") from exc
        finally:
            m.current_copilot_conversation_id.reset(conv_token)
    finally:
        if token is not None:
            m.current_copilot_workspace_services.reset(token)

    return result


@router.post("/api/copilot/chat", response_model=m.CopilotChatResponse)
async def copilot_chat(
    request: m.CopilotChatRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CopilotChatResponse:
    result = await _copilot_chat_pipeline(request, services)
    return m.CopilotChatResponse(**result)


@router.post("/api/copilot/chat/stream")
async def copilot_chat_stream(
    request: m.CopilotChatRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> StreamingResponse:
    """Server-sent-events variant of /api/copilot/chat.

    Emits progress events (stage, round, tool, answer_delta) while the turn
    runs, then a final `result` event with the full CopilotChatResponse
    payload, or an `error` event. Client disconnect cancels the turn.
    """
    queue: asyncio.Queue[dict[str, m.Any] | None] = asyncio.Queue()

    def emit(event: dict[str, m.Any]) -> None:
        queue.put_nowait(event)

    async def run_turn() -> None:
        try:
            result = await _copilot_chat_pipeline(request, services, progress=emit)
            payload = jsonable_encoder(m.CopilotChatResponse(**result))
            emit({"type": "result", "data": payload})
        except m.HTTPException as exc:
            emit({"type": "error", "status": exc.status_code, "detail": str(exc.detail)})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            emit({"type": "error", "status": 500, "detail": f"Copilot failed: {exc}"})
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(run_turn())

    async def event_stream():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if await http_request.is_disconnected():
                        break
                    continue
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
