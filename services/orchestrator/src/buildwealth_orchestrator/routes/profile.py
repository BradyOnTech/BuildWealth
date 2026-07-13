"""Profile routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.profile_document_vision import (
    ALLOWED_MEDIA_TYPES,
    MAX_IMAGE_BYTES,
    apply_document_suggestions,
    extract_profile_document,
)

router = APIRouter()

__all__ = [
    "get_profile_defaults",
    "get_life_plans_interview",
    "post_life_plans_drafts",
    "get_financial_profile",
    "update_financial_profile",
    "extract_profile_document_image",
    "apply_profile_document_vision",
]


@router.get("/api/life-plans/interview")
def get_life_plans_interview(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """The life-plans interview: a few questions about the next chapter,
    tuned to what the household already recorded."""
    resolved_services = m.route_workspace_services(services, permission="profile.read")
    profile, monthly_expenses = m._life_interview_context(resolved_services)
    return m.build_life_interview(
        profile,
        monthly_expenses_usd=monthly_expenses,
        current_year=m.datetime.now(m.timezone.utc).year,
    )


@router.post("/api/life-plans/drafts")
def post_life_plans_drafts(
    body: m.LifePlanDraftRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Interview answers → draft dated goals. Computation only — nothing is
    saved until the household reviews and applies through the profile."""
    resolved_services = m.route_workspace_services(services, permission="profile.read")
    _, monthly_expenses = m._life_interview_context(resolved_services)
    return m.build_life_plan_drafts(
        body.answers,
        monthly_expenses_usd=monthly_expenses,
    )


@router.get("/api/profile/defaults")
def get_profile_defaults(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Labeled suggestions for every estimable profile field — the UI never
    shows a blank the app can estimate."""
    from buildwealth_orchestrator.services.profile_defaults import (
        build_profile_default_suggestions,
    )

    resolved_services = m.route_workspace_services(services, permission="profile.read")
    profile = resolved_services.financial_profile_store.get()
    return {
        "generated_at": m.utc_now(),
        "suggestions": build_profile_default_suggestions(profile),
    }


@router.get("/api/financial-profile", response_model=m.FinancialProfileResponse)
def get_financial_profile(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.FinancialProfileResponse:
    m.require_permission(services.context, "profile.read")
    return m.FinancialProfileResponse(**m.get_financial_profile_payload(services.financial_profile_store))


@router.put("/api/financial-profile", response_model=m.FinancialProfileResponse)
def update_financial_profile(
    request: m.FinancialProfileRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    source: str | None = None,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.FinancialProfileResponse:
    scoped_services = hasattr(services, "context")
    if http_request is not None:
        m.require_csrf(http_request)
    if scoped_services:
        m.require_permission(services.context, "profile.write")
    source_label = str(source or "profile_editor").strip() or "profile_editor"
    saved = m.save_financial_profile_payload(
        request,
        source=source_label,
        profile_store=services.financial_profile_store if scoped_services else m.financial_profile_store,
    )
    m._record_profile_update_activity(
        source=source_label,
        sections=m._profile_update_sections_from_payload(request),
        via_copilot=source_label.startswith("copilot"),
    )
    m._queue_autogit_event("financial_profile_updated")
    return m.FinancialProfileResponse(**saved)


@router.post("/api/profile/document-vision")
async def extract_profile_document_image(
    file: m.UploadFile = m.File(...),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Read a paystub/W-2/mortgage/insurance photo with the 'extract' vision
    model and return reviewable profile suggestions — nothing is saved until
    the user applies them through /api/profile/document-vision/apply."""
    m.require_permission(services.context, "profile.read")
    image_bytes = await file.read()
    media_type = str(file.content_type or "").strip().lower()
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise m.HTTPException(
            status_code=400,
            detail=(
                f"Unsupported image type {media_type or 'unknown'}. Use PNG, JPEG, WebP, "
                "or GIF; for a PDF, screenshot the page."
            ),
        )
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise m.HTTPException(status_code=400, detail="Image is larger than 8 MB — crop or downscale it.")

    result = await extract_profile_document(
        image_bytes,
        media_type,
        llm_client=m.llm_router.client_for("extract"),
    )
    return {
        "status": result.status,
        "detail": result.detail,
        "file_name": file.filename,
        "document_type": result.document_type,
        "confidence": result.confidence,
        "suggestions": result.suggestions,
        "warnings": result.warnings,
        "review_note": (
            "Read by AI from your photo — check every number against the document "
            "before applying. Nothing is saved until you apply."
        ),
    }


@router.post("/api/profile/document-vision/apply")
def apply_profile_document_vision(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Apply a reviewed (possibly user-edited) document-vision suggestions
    patch to the financial profile. Lists append with dedupe; only known
    sections and fields are honored."""
    resolved_services = m.route_workspace_services(
        services,
        permission="profile.write",
        http_request=http_request,
        require_write_token=True,
    )
    result = apply_document_suggestions(request, resolved_services.financial_profile_store)
    if result.get("applied_sections"):
        m._queue_autogit_event("financial_profile_updated")
    return result
