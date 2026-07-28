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
    "patch_financial_profile",
    "update_financial_profile_section",
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


@router.patch("/api/financial-profile", response_model=m.FinancialProfileResponse)
def patch_financial_profile(
    request: m.FinancialProfileRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    source: str | None = None,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.FinancialProfileResponse:
    """Update only fields present in the request body.

    FinancialProfileRequest carries defaults for full-profile editors. The
    shared save helper uses ``exclude_unset`` so a PATCH containing only
    ``income_items`` cannot clear expenses, debt, assets, or other Canonical
    State.
    """
    return update_financial_profile(
        request=request,
        http_request=http_request,
        source=source or "profile_patch",
        services=services,
    )


@router.patch(
    "/api/financial-profile/sections/{section_key}",
    response_model=m.FinancialProfileResponse,
)
def update_financial_profile_section(
    section_key: str,
    request: m.ProfileSectionUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.FinancialProfileResponse:
    """Replace or merge exactly one list section with optimistic concurrency."""
    from buildwealth_orchestrator.schemas import (
        BenefitItem,
        DebtItem,
        ExpenseItem,
        GoalItem,
        HouseholdMemberItem,
        IncomeItem,
        InsurancePolicyItem,
        PhysicalAssetItem,
    )

    section_models = {
        "household_members": HouseholdMemberItem,
        "income_items": IncomeItem,
        "expense_items": ExpenseItem,
        "debt_items": DebtItem,
        "goal_items": GoalItem,
        "physical_assets": PhysicalAssetItem,
        "insurance_policies": InsurancePolicyItem,
        "benefit_items": BenefitItem,
    }
    model = section_models.get(str(section_key or "").strip())
    if model is None:
        raise m.HTTPException(status_code=404, detail="Unknown profile section.")

    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "profile.write")
    store = services.financial_profile_store
    current = store.get()

    expected = request.expected_updated_at
    current_updated_at = str(current.get("updated_at") or "")
    if expected is not None:
        expected_text = expected.isoformat().replace("+00:00", "Z")
        normalized_current = current_updated_at.replace("+00:00", "Z")
        if expected_text != normalized_current:
            raise m.HTTPException(
                status_code=409,
                detail={
                    "message": "This profile changed after you opened it. Review the latest section before replacing it.",
                    "current_updated_at": current_updated_at,
                },
            )

    incoming = [
        model.model_validate(item).model_dump(mode="json")
        for item in request.items
    ]
    if request.mode == "merge":
        existing = [
            dict(item)
            for item in current.get(section_key, [])
            if isinstance(item, dict)
        ]
        by_id = {str(item.get("id") or ""): index for index, item in enumerate(existing)}
        for item in incoming:
            item_id = str(item.get("id") or "")
            if item_id and item_id in by_id:
                existing[by_id[item_id]] = item
            else:
                existing.append(item)
        next_items = existing
    else:
        next_items = incoming

    updates: dict[str, m.Any] = {section_key: next_items}
    if request.mode == "replace":
        kept_ids = {str(item.get("id") or "") for item in next_items}
        removed_ids = {
            str(item.get("id") or "")
            for item in current.get(section_key, [])
            if isinstance(item, dict)
        } - kept_ids

        def _clear_links(target_section: str, field: str) -> None:
            if not removed_ids:
                return
            rows = current.get(target_section, [])
            if not isinstance(rows, list):
                return
            cleaned = [
                {
                    **item,
                    field: None,
                }
                if isinstance(item, dict) and str(item.get(field) or "") in removed_ids
                else item
                for item in rows
            ]
            if cleaned != rows:
                updates[target_section] = cleaned

        if section_key == "physical_assets":
            _clear_links("debt_items", "linked_asset_id")
            _clear_links("expense_items", "linked_asset_id")
            _clear_links("income_items", "linked_asset_id")
            _clear_links("insurance_policies", "linked_asset_id")
        elif section_key == "debt_items":
            _clear_links("expense_items", "linked_debt_id")
        elif section_key == "expense_items":
            _clear_links("insurance_policies", "premium_expense_id")
        elif section_key == "household_members":
            _clear_links("income_items", "owner_member_id")
            _clear_links("expense_items", "related_member_id")
            _clear_links("physical_assets", "owner_member_id")
            _clear_links("insurance_policies", "insured_member_id")
            _clear_links("benefit_items", "owner_member_id")

    saved = store.save(
        updates,
        metadata_source=f"profile_section_{request.mode}",
    )
    m._record_profile_update_activity(
        source=f"profile_section_{request.mode}",
        sections=list(updates),
        via_copilot=False,
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
