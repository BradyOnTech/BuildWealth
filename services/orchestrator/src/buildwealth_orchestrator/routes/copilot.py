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
from buildwealth_orchestrator.services.copilot_context_reference_adapters import (
    build_workspace_context_reference_lookups,
)
from buildwealth_orchestrator.services.copilot_context_references import (
    ContextReferenceError,
    build_context_references_prompt_block,
    build_context_references_trace,
    resolve_context_references,
)
from buildwealth_orchestrator.services.store_locks import locked_store

router = APIRouter()

_COPILOT_FAILURE_DETAIL = (
    "Copilot could not complete this turn. Your financial data was not changed. "
    "Please try again."
)
_COPILOT_PROVIDER_FAILURE_DETAIL = (
    "The connected model provider could not complete this turn. "
    "Check its connection and try again."
)

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
    "get_copilot_pending_action",
    "apply_copilot_pending_action",
    "reject_copilot_pending_action",
    "copilot_chat",
    "copilot_chat_stream",
]


def _pending_action_http_error(exc: Exception) -> m.HTTPException:
    if isinstance(exc, m.PendingActionNotFoundError):
        return m.HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (
            m.PendingActionExpiredError,
            m.PendingActionStaleError,
            m.PendingActionStateError,
        ),
    ):
        action = getattr(exc, "action", None)
        detail: dict[str, m.Any] = {"message": str(exc)}
        if isinstance(action, m.PendingFinancialAction):
            detail["action"] = m.public_pending_financial_action(action)
        return m.HTTPException(status_code=409, detail=detail)
    return m.HTTPException(status_code=500, detail="Pending action storage failed.")


def _sync_pending_action_snapshot(
    services: m.WorkspaceServices,
    action: m.PendingFinancialAction,
) -> None:
    try:
        services.conversation_store.update_pending_action_snapshot(
            action.conversation_id,
            m.public_pending_financial_action(action),
        )
    except Exception:
        # Lifecycle state remains authoritative in the pending-action store.
        # Conversation metadata is a read-optimized projection and must never
        # make an otherwise successful authoritative action fail.
        pass


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
    include_archived: bool = False,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[m.CopilotConversationSummary]:
    m.require_permission(services.context, "copilot.use")
    summaries = services.conversation_store.list(
        limit=max(1, min(limit, 200)),
        include_archived=include_archived,
    )
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


@router.patch(
    "/api/copilot/conversations/{conversation_id}",
    response_model=m.CopilotConversationResponse,
)
def patch_copilot_conversation(
    conversation_id: str,
    request: m.CopilotConversationUpdateRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CopilotConversationResponse:
    """Rename or archive a Copilot conversation while preserving its durable turns."""
    m.require_permission(services.context, "copilot.use")
    patch = request.model_dump(exclude_unset=True)
    try:
        conversation = services.conversation_store.update_details(
            conversation_id,
            title=patch.get("title"),
            archived=patch.get("archived"),
        )
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    workspace_settings = services.settings_store.load_raw()
    resolved_llm = m._resolve_conversation_llm(
        workspace_settings=workspace_settings,
        conversation_llm=conversation.get("llm") if isinstance(conversation, dict) else None,
        request_llm=None,
        settings_store=services.settings_store,
    )
    payload = dict(conversation)
    payload["focus"] = m.public_focus(conversation.get("focus"))
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
        services.conversation_store.get(conversation_id)
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


@router.get(
    "/api/copilot/pending-actions/{action_id}",
    response_model=m.CopilotPendingActionResponse,
)
def get_copilot_pending_action(
    action_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CopilotPendingActionResponse:
    m.require_permission(services.context, "copilot.use")
    try:
        action = m.pending_financial_action_store(services).get(action_id)
    except Exception as exc:
        raise _pending_action_http_error(exc) from exc
    _sync_pending_action_snapshot(services, action)
    return m.CopilotPendingActionResponse(
        **m.public_pending_financial_action(action, include_payload=True)
    )


@router.post(
    "/api/copilot/pending-actions/{action_id}/reject",
    response_model=m.CopilotPendingActionResponse,
)
def reject_copilot_pending_action(
    action_id: str,
    request: m.CopilotPendingActionRejectRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CopilotPendingActionResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "profile.write")
    try:
        action = m.pending_financial_action_store(services).reject(
            action_id,
            reason=request.reason,
        )
    except Exception as exc:
        raise _pending_action_http_error(exc) from exc
    _sync_pending_action_snapshot(services, action)
    return m.CopilotPendingActionResponse(
        **m.public_pending_financial_action(action)
    )


@router.post(
    "/api/copilot/pending-actions/{action_id}/apply",
    response_model=m.CopilotPendingActionApplyResponse,
)
def apply_copilot_pending_action(
    action_id: str,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CopilotPendingActionApplyResponse:
    """Apply one reviewed action; this endpoint is never a model-facing tool."""

    m.require_csrf(http_request)
    m.require_permission(services.context, "profile.write")
    store = m.pending_financial_action_store(services)
    profile_store = services.financial_profile_store

    # Store methods lock individual JSON files, but an Apply spans the action
    # lifecycle and Canonical Profile files. Hold both locks for the complete
    # compare/write/commit sequence so concurrent clicks or profile edits
    # cannot interleave between validation and the final lifecycle transition.
    with locked_store(store.path), locked_store(profile_store.profile_path):
        try:
            action = store.get(action_id)
        except Exception as exc:
            raise _pending_action_http_error(exc) from exc

        if action.status is m.PendingActionStatus.APPLIED:
            current_profile = m.FinancialProfileResponse(
                **m.get_financial_profile_payload(profile_store)
            ).model_dump(mode="json")
            return m.CopilotPendingActionApplyResponse(
                action=m.CopilotPendingActionResponse(
                    **m.public_pending_financial_action(action)
                ),
                result={"already_applied": True, "profile": current_profile},
            )
        if action.status is not m.PendingActionStatus.PENDING:
            raise _pending_action_http_error(
                m.PendingActionStateError(action, operation="apply")
            )
        if action.tool_name != "draft_financial_profile_update":
            raise m.HTTPException(
                status_code=409,
                detail="This pending action kind is not supported by the profile apply interface.",
            )

        original_profile = profile_store.get()
        current_profile = m.FinancialProfileResponse(
            **m.get_financial_profile_payload(profile_store)
        ).model_dump(mode="json")
        current_fingerprint = m.fingerprint_source_state(current_profile)
        if not m.validate_source_fingerprint(
            action.source_state_fingerprint,
            current_fingerprint,
        ):
            try:
                store.mark_applied(
                    action.action_id,
                    current_source_fingerprint=current_fingerprint,
                )
            except Exception as exc:
                stale_action = getattr(exc, "action", None)
                if isinstance(stale_action, m.PendingFinancialAction):
                    _sync_pending_action_snapshot(services, stale_action)
                raise _pending_action_http_error(exc) from exc

        payload = action.payload
        patch_payload = payload.get("patch_payload")
        if payload.get("kind") != "financial_profile_update" or not isinstance(
            patch_payload,
            dict,
        ):
            raise m.HTTPException(
                status_code=409,
                detail="The reviewed profile proposal is malformed and cannot be applied.",
            )

        draft = m._build_financial_profile_update_draft(
            patch_payload,
            services=services,
        )
        validated = m.FinancialProfileRequest(**draft["proposed_profile"])
        saved = m.save_financial_profile_payload(
            validated,
            source=f"copilot_pending_action:{action.action_id}",
            profile_store=profile_store,
        )
        try:
            applied = store.mark_applied(
                action.action_id,
                current_source_fingerprint=current_fingerprint,
            )
        except Exception as exc:
            # The lifecycle record is the authority for whether Apply
            # committed. Restore the exact pre-write profile if that record
            # cannot be durably advanced, keeping the proposal safely pending.
            try:
                profile_store.replace(original_profile)
            except Exception as rollback_exc:
                raise m.HTTPException(
                    status_code=500,
                    detail=(
                        "The profile write could not be reconciled with its "
                        "pending-action record. Refresh the Profile before "
                        "taking another action."
                    ),
                ) from rollback_exc
            raise _pending_action_http_error(exc) from exc

        # Emit activity and backup side effects only after both authoritative
        # files have committed successfully.
        m._record_profile_update_activity(
            source="copilot_pending_action",
            sections=m._profile_update_sections_from_payload(patch_payload),
            via_copilot=True,
        )
        m._queue_autogit_event("financial_profile_updated")

    _sync_pending_action_snapshot(services, applied)

    return m.CopilotPendingActionApplyResponse(
        action=m.CopilotPendingActionResponse(
            **m.public_pending_financial_action(applied)
        ),
        result={
            "already_applied": False,
            "profile": m.FinancialProfileResponse(**saved).model_dump(mode="json"),
        },
    )


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
    raw_context_references = [
        reference.model_dump(mode="json")
        for reference in request.context_references
    ]
    try:
        resolved_context_references = resolve_context_references(
            raw_context_references,
            workspace_id=str(resolved_services.record.id),
            lookups=build_workspace_context_reference_lookups(resolved_services),
        )
    except ContextReferenceError as exc:
        raise m.HTTPException(status_code=422, detail=exc.to_public_dict()) from exc
    context_reference_trace = build_context_references_trace(
        resolved_context_references
    )
    context_reference_domains = {
        {
            "plan": "plan",
            "recommendation": "recommendation",
            "saved_simulation": "plan",
            "plan_artifact": "plan",
            "holding": "portfolio",
        }[reference.reference_type]
        for reference in resolved_context_references
    }
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
        if (
            request.persist_interaction_mode
            and conversation.get("interaction_mode") != request.interaction_mode
        ):
            if hasattr(store, "update_interaction_mode"):
                conversation = store.update_interaction_mode(
                    conversation["id"],
                    request.interaction_mode,
                )
            else:
                # Compatibility for narrow test/adapter stores; production
                # ConversationStore persists this field durably.
                conversation["interaction_mode"] = request.interaction_mode

        profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
        request_risk_lens = (
            request.risk_lens.model_dump(mode="json") if request.risk_lens is not None else None
        )
        resolved_risk_lens = m.resolve_risk_lens(
            request_risk_lens,
            stored=conversation.get("risk_lens") if isinstance(conversation, dict) else None,
            profile=profile_payload,
        )
        if request.persist_risk_lens and request_risk_lens is not None:
            conversation = store.update_risk_lens(conversation["id"], request_risk_lens)
        compare_all = (
            request.risk_comparison.mode == "all"
            or bool(resolved_risk_lens.get("is_override"))
            or m.question_requests_risk_comparison(request.question)
        )
        risk_comparison = None

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

        try:
            accepts_turn = "turn" in inspect.signature(m.copilot.chat).parameters
        except (TypeError, ValueError):
            accepts_turn = False
        turn = None
        if accepts_turn:
            start_turn_kwargs: dict[str, m.Any] = {
                "conversation": conversation,
                "question": request.question,
                "turn_id": request.turn_id,
            }
            try:
                start_turn_parameters = inspect.signature(store.start_turn).parameters
            except (TypeError, ValueError, AttributeError):
                start_turn_parameters = {}
            if "user_metadata" in start_turn_parameters:
                start_turn_kwargs["user_metadata"] = {
                    "context_references": context_reference_trace["references"],
                }
            turn = store.start_turn(
                **start_turn_kwargs,
            )
            if progress is not None:
                progress(
                    {
                        "type": "turn",
                        "turn_id": turn["id"],
                        "user_message_id": turn.get("user_message_id"),
                        "status": turn.get("status"),
                    }
                )

        if compare_all:
            try:
                holdings_payload = (
                    resolved_services.current_portfolio()
                    if isinstance(resolved_services, m.WorkspaceServices)
                    else resolved_services.portfolio_store.get_holdings()
                )
            except Exception:
                holdings_payload = {}
            risk_comparison = m.build_risk_comparison(
                question=request.question,
                profile=profile_payload,
                holdings=holdings_payload,
                lens=resolved_risk_lens,
                plan_id=request.plan_id or resolved_services.plan_workspace.get_active_plan_id(),
                source_turn_id=str(turn.get("id") or "") if isinstance(turn, dict) else request.turn_id,
            )

        conv_token = m.current_copilot_conversation_id.set(str(conversation.get("id") or ""))
        turn_token = m.current_copilot_turn_id.set(
            str(turn.get("id") or "")
            if isinstance(turn, dict)
            else str(request.turn_id or "")
        )
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
            if risk_comparison is not None:
                contextual_brief += m.risk_comparison_prompt_block(risk_comparison)
            if resolved_context_references:
                contextual_brief += (
                    "\n\n"
                    + build_context_references_prompt_block(
                        resolved_context_references
                    )
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
            interaction_mode = m.InteractionMode(request.interaction_mode)
            intent_domains = (
                intent_for_focus.get("domains")
                if isinstance(intent_for_focus, dict)
                and isinstance(intent_for_focus.get("domains"), list)
                else []
            )
            intent_domains = sorted(
                {str(item) for item in intent_domains}
                | context_reference_domains
            )
            provider_id = str(
                getattr(turn_llm_client, "provider", "")
                or turn_llm_client.__class__.__name__
            ).strip().lower()
            tool_selection = m.resolve_model_tools(
                m.copilot_tool_metadata.values(),
                m.ToolSelectionContext(
                    mode=interaction_mode,
                    intent_domains=frozenset(str(item) for item in intent_domains),
                    primary_domains=frozenset(effective_obj.primary_domains),
                    secondary_domains=frozenset(effective_obj.secondary_domains),
                    muted_domains=frozenset(effective_obj.muted_domains),
                ),
                m.ProviderCapabilities(
                    provider_id=provider_id,
                    tool_calling=True,
                ),
            )
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
            context_trace["tool_policy"] = {
                "policy_version": tool_selection.policy_version,
                "interaction_mode": interaction_mode.value,
                "provider_id": provider_id,
                "selected_tool_names": list(tool_selection.names),
                "selected_tool_count": len(tool_selection.names),
                "excluded_tool_count": len(tool_selection.excluded),
            }
            context_trace["explicit_context_references"] = context_reference_trace
            context_trace["risk_lens_applied"] = {
                **resolved_risk_lens,
                "comparison_available": m.question_supports_risk_comparison(request.question),
                "comparison_generated": risk_comparison is not None,
                "input_fingerprint": risk_comparison.get("input_fingerprint") if risk_comparison else None,
                "comparison_id": risk_comparison.get("id") if risk_comparison else None,
                "comparison_schema_version": risk_comparison.get("schema_version") if risk_comparison else None,
                "policy_version": risk_comparison.get("policy_version") if risk_comparison else None,
                "adapter_versions": risk_comparison.get("adapter_versions") if risk_comparison else {},
                "source_turn_id": risk_comparison.get("source_turn_id") if risk_comparison else request.turn_id,
            }
            try:
                chat_kwargs: dict[str, m.Any] = dict(
                    question=request.question,
                    conversation=conversation,
                    contextual_brief=contextual_brief,
                    context_trace=context_trace,
                    conversation_store=store,
                    llm_client=turn_llm_client,
                )
                try:
                    chat_parameters = inspect.signature(m.copilot.chat).parameters
                except (TypeError, ValueError):
                    chat_parameters = {}
                if "assistant_metadata" in chat_parameters:
                    chat_kwargs["assistant_metadata"] = {
                        "risk_lens": resolved_risk_lens,
                        "risk_comparison": risk_comparison,
                        "risk_replay_context": {
                            "question": request.question,
                            "plan_id": request.plan_id,
                            "use_live_snapshot": request.use_live_snapshot,
                        },
                        "interaction_mode": interaction_mode.value,
                        "tool_policy": context_trace["tool_policy"],
                    }
                if "system_prompt" in chat_parameters:
                    chat_kwargs["system_prompt"] = m.copilot_system_prompt_for_mode(
                        interaction_mode
                    )
                if "allowed_tool_names" in chat_parameters:
                    chat_kwargs["allowed_tool_names"] = tool_selection.names
                if risk_comparison is not None and "fallback_answer" in chat_parameters:
                    chat_kwargs["fallback_answer"] = m.risk_comparison_fallback_answer(risk_comparison)
                if turn is not None:
                    chat_kwargs["turn"] = turn
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
                result["risk_lens"] = resolved_risk_lens
                result["risk_comparison"] = risk_comparison
                result["interaction_mode"] = interaction_mode.value
                if conversation_id:
                    store.update_latest_assistant_metadata(
                        conversation_id,
                        {
                            "risk_lens": resolved_risk_lens,
                            "risk_comparison": risk_comparison,
                            "risk_replay_context": {
                                "question": request.question,
                                "plan_id": request.plan_id,
                                "use_live_snapshot": request.use_live_snapshot,
                            },
                        },
                    )
            except FileNotFoundError as exc:
                raise m.HTTPException(status_code=404, detail=str(exc)) from exc
            except m.httpx.HTTPStatusError as exc:
                raise m.HTTPException(
                    status_code=502,
                    detail=_COPILOT_PROVIDER_FAILURE_DETAIL,
                ) from exc
            except Exception as exc:
                raise m.HTTPException(
                    status_code=500,
                    detail=_COPILOT_FAILURE_DETAIL,
                ) from exc
        except asyncio.CancelledError:
            if turn is not None:
                store.update_turn_status(
                    conversation["id"],
                    str(turn["id"]),
                    "stopped",
                )
            raise
        except m.HTTPException as exc:
            if turn is not None:
                store.update_turn_status(
                    conversation["id"],
                    str(turn["id"]),
                    "failed",
                    error=str(exc.detail),
                )
            raise
        except Exception as exc:
            if turn is not None:
                store.update_turn_status(
                    conversation["id"],
                    str(turn["id"]),
                    "failed",
                    error=_COPILOT_FAILURE_DETAIL,
                )
            raise m.HTTPException(
                status_code=500,
                detail=_COPILOT_FAILURE_DETAIL,
            ) from exc
        finally:
            m.current_copilot_turn_id.reset(turn_token)
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
        except Exception:
            emit({"type": "error", "status": 500, "detail": _COPILOT_FAILURE_DETAIL})
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
