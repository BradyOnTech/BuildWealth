"""Context routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.profile_candidate_apply import apply_candidate_to_profile
from buildwealth_orchestrator.services.profile_inference import build_profile_inference_candidates

router = APIRouter()

__all__ = [
    "get_context_registry_status",
    "rebuild_context_registry",
    "rebuild_context_embeddings",
    "search_context_endpoint",
    "list_context_candidates",
    "draft_context_candidate",
    "detect_chat_context_candidates",
    "summarize_conversation_context_candidate",
    "infer_profile_context_candidates",
    "apply_context_candidate_to_profile",
    "update_context_candidate_lifecycle",
    "list_context_candidate_events",
]


@router.get("/api/context/registry/status")
def get_context_registry_status(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(services, permission="copilot.use")
    return resolved_services.context_intelligence_service.get_status()


@router.post("/api/context/registry/rebuild")
def rebuild_context_registry(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    return resolved_services.context_intelligence_service.rebuild_registry()


@router.post("/api/context/embeddings/rebuild")
def rebuild_context_embeddings(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    return resolved_services.context_intelligence_service.rebuild_embeddings()


@router.get("/api/context/search")
def search_context_endpoint(
    q: str = "",
    domain: str | None = None,
    domains: str | None = None,
    plan_id: str | None = None,
    symbol: str | None = None,
    symbols: str | None = None,
    recommendation_status: str | None = None,
    entity_type: str | None = None,
    entity_types: str | None = None,
    field_path: str | None = None,
    limit: int = 20,
    rebuild_if_empty: bool = True,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(services, permission="copilot.use")
    return resolved_services.context_intelligence_service.search_context(
        query=q,
        domains=m._context_filter_values(domains, domain),
        plan_id=plan_id,
        symbols=m._context_filter_values(symbols, symbol),
        entity_types=m._context_filter_values(entity_types, entity_type),
        recommendation_status=recommendation_status,
        field_path=field_path,
        limit=max(1, min(int(limit), 100)),
        rebuild_if_empty=rebuild_if_empty,
    )


@router.get("/api/context/candidates")
def list_context_candidates(
    lifecycle_state: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(services, permission="copilot.use")
    return {
        "items": resolved_services.context_intelligence_service.list_context_candidates(
            lifecycle_state=lifecycle_state,
            include_archived=include_archived,
            limit=max(1, min(int(limit), 5000)),
        )
    }


@router.post("/api/context/candidates")
def draft_context_candidate(
    request: dict[str, m.Any],
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    return resolved_services.context_intelligence_service.draft_context_candidate(
        source_domain=str(request.get("source_domain") or "manual"),
        source_ref=str(request.get("source_ref") or "manual/context_candidate"),
        extracted_claim=str(request.get("extracted_claim") or ""),
        target_domain=str(request.get("target_domain") or "conversation"),
        target_area=str(request.get("target_area") or "general"),
        target_field=(
            str(request.get("target_field") or "").strip()
            if request.get("target_field") is not None
            else None
        ),
        target_value=request.get("target_value"),
        confidence=str(request.get("confidence") or "medium"),
        metadata=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
        lifecycle_state=str(request.get("lifecycle_state") or "pending_review"),
        prompt_influence=(
            str(request.get("prompt_influence") or "").strip()
            if request.get("prompt_influence") is not None
            else None
        ),
    )


@router.post("/api/context/candidates/detect-chat")
def detect_chat_context_candidates(
    request: dict[str, m.Any],
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    items = resolved_services.context_intelligence_service.detect_chat_context_candidates(
        message=str(request.get("message") or ""),
        conversation_id=str(request.get("conversation_id") or "").strip() or None,
        message_index=(
            m._coerce_int(request.get("message_index"), 0)
            if request.get("message_index") is not None
            else None
        ),
    )
    return {"count": len(items), "items": items}


@router.post("/api/context/candidates/conversation-summary")
def summarize_conversation_context_candidate(
    request: dict[str, m.Any],
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    conversation_id = str(request.get("conversation_id") or "").strip()
    if conversation_id:
        try:
            conversation = resolved_services.conversation_store.get(conversation_id)
        except FileNotFoundError as exc:
            raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        conversation = request.get("conversation")
        if not isinstance(conversation, dict):
            raise m.HTTPException(status_code=400, detail="conversation or conversation_id is required")
    candidate = resolved_services.context_intelligence_service.summarize_conversation_candidate(
        conversation=conversation,
        min_messages=max(1, min(m._coerce_int(request.get("min_messages"), 8), 100)),
    )
    return {"created": candidate is not None, "candidate": candidate}


@router.post("/api/context/candidates/infer-profile")
def infer_profile_context_candidates(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Infer-and-confirm sweep: draft profile candidates (marginal bracket from
    income, statement suggestions for empty sections). Nothing touches the
    profile until the user applies a candidate."""
    resolved_services = m.route_workspace_services(
        services,
        permission="profile.write",
        http_request=http_request,
        require_write_token=True,
    )
    profile_payload = resolved_services.financial_profile_store.get()
    try:
        statement_reports = resolved_services.import_workbench_store.list_reports(limit=20)
    except Exception:
        statement_reports = []
    try:
        portfolio_transactions = resolved_services.portfolio_store.list_transactions(limit=2000)
    except Exception:
        portfolio_transactions = []
    drafts = build_profile_inference_candidates(
        profile_payload=profile_payload,
        statement_reports=statement_reports,
        portfolio_transactions=portfolio_transactions,
    )
    created: list[str] = []
    skipped = 0
    for draft in drafts:
        stored = resolved_services.context_intelligence_service.draft_context_candidate(**draft)
        # Upsert preserves terminal states — a re-drafted candidate the user
        # already resolved counts as skipped, not created.
        if str(stored.get("lifecycle_state") or "") in {"applied", "rejected", "superseded", "archived"}:
            skipped += 1
        else:
            created.append(str(stored.get("id") or ""))
    return {"created": created, "skipped": skipped}


@router.post("/api/context/candidates/{candidate_id}/apply")
def apply_context_candidate_to_profile(
    candidate_id: str,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Write a confirmed candidate's target_value into the financial profile,
    then mark the candidate applied/authoritative."""
    resolved_services = m.route_workspace_services(
        services,
        permission="profile.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        candidate = resolved_services.context_intelligence_service.get_context_candidate(candidate_id)
    except KeyError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    apply_result = apply_candidate_to_profile(
        candidate,
        resolved_services.financial_profile_store,
    )
    if not apply_result.get("applied"):
        raise m.HTTPException(
            status_code=400,
            detail=str(apply_result.get("reason") or "This capture cannot be applied to the profile."),
        )
    updated = resolved_services.context_intelligence_service.update_context_candidate_lifecycle(
        candidate_id,
        lifecycle_state="applied",
        prompt_influence="authoritative",
        metadata_patch={
            "review_action": "applied_to_profile",
            "resolution_state": "resolved_by_apply",
            "applied_sections": list(apply_result.get("sections") or []),
        },
    )
    return {"candidate": updated, "apply_result": apply_result}


@router.patch("/api/context/candidates/{candidate_id}/lifecycle")
def update_context_candidate_lifecycle(
    candidate_id: str,
    request: dict[str, m.Any],
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        return resolved_services.context_intelligence_service.update_context_candidate_lifecycle(
            candidate_id,
            lifecycle_state=str(request.get("lifecycle_state") or "pending_review"),
            prompt_influence=(
                str(request.get("prompt_influence") or "").strip()
                if request.get("prompt_influence") is not None
                else None
            ),
            metadata_patch=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
        )
    except KeyError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/context/candidates/{candidate_id}/events")
def list_context_candidate_events(
    candidate_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(services, permission="copilot.use")
    return {"items": resolved_services.context_intelligence_service.list_context_candidate_events(candidate_id)}
