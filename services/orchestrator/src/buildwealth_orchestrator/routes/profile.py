"""Profile routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_life_plans_interview",
    "post_life_plans_drafts",
    "get_financial_profile",
    "update_financial_profile",
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
