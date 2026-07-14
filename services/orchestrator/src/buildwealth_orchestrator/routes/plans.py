"""Plans routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.simulation_runs import track_simulation_run

router = APIRouter()

__all__ = [
    "list_plans",
    "create_plan",
    "get_plan",
    "update_plan",
    "update_plan_settings",
    "get_plan_timeline",
    "update_plan_timeline",
    "get_plan_contribution_rules",
    "update_plan_contribution_rules",
    "get_plan_assumption_sets",
    "update_plan_assumption_sets",
    "get_plan_branch_templates",
    "update_plan_branch_templates",
    "explain_plan_simulation_result",
    "classify_plan_what_if_review_level",
    "list_plan_simulation_runs",
    "get_plan_simulation_run",
    "list_plan_saved_simulations",
    "create_plan_saved_simulation",
    "get_plan_saved_simulation",
    "compare_plan_saved_simulation_to_current",
    "rerun_plan_saved_simulation",
    "create_plan_saved_simulation_decision",
    "pin_watchlist_research_to_plan_branch_template",
    "run_plan_scenario_diff",
    "compare_plan_withdrawal_strategies",
    "run_plan_scenario_branch",
    "get_plan_tracking",
    "activate_plan",
    "create_plan_recommendation_closure_summary_route",
    "append_plan_decision",
    "refresh_plan_context",
    "read_plan_artifact",
    "save_plan_artifact_thesis_revision",
]


@router.get("/api/plans/{plan_id}/simulations/runs", response_model=m.PlanSimulationRunsResponse)
def list_plan_simulation_runs(
    plan_id: str,
    limit: int = 50,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSimulationRunsResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.list_simulation_runs(plan_id, limit=limit)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanSimulationRunsResponse(**payload)


@router.get("/api/plans/{plan_id}/simulations/runs/{simulation_run_id}", response_model=m.PlanSimulationRun)
def get_plan_simulation_run(
    plan_id: str,
    simulation_run_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSimulationRun:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_simulation_run(plan_id, simulation_run_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanSimulationRun(**payload)


@router.get("/api/plans", response_model=list[m.PlanSummary])
def list_plans(
    limit: int = 100,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[m.PlanSummary]:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    summaries = resolved_services.plan_workspace.list_plans(limit=max(1, min(limit, 500)))
    return [m.PlanSummary(**summary) for summary in summaries]


@router.post("/api/plans", response_model=m.PlanDetailResponse)
def create_plan(
    request: m.PlanCreateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanDetailResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        detail = resolved_services.plan_workspace.create_plan(title=request.title, description=request.description)
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_created")
    return m._build_plan_detail_response(detail, inbox=resolved_services.recommendation_inbox)


@router.get("/api/plans/{plan_id}", response_model=m.PlanDetailResponse)
def get_plan(
    plan_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanDetailResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m._build_plan_detail_response(detail, inbox=resolved_services.recommendation_inbox)


@router.put("/api/plans/{plan_id}", response_model=m.PlanDetailResponse)
def update_plan(
    plan_id: str,
    request: m.PlanUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanDetailResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        detail = resolved_services.plan_workspace.update_plan_files(
            plan_id=plan_id,
            plan_markdown=request.plan_markdown,
            tasks_markdown=request.tasks_markdown,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_updated")
    return m._build_plan_detail_response(detail, inbox=resolved_services.recommendation_inbox)


@router.patch("/api/plans/{plan_id}/settings", response_model=m.PlanDetailResponse)
def update_plan_settings(
    plan_id: str,
    request: m.PlanSettingsUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanDetailResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise m.HTTPException(status_code=400, detail="Provide at least one settings field to update")

    try:
        detail = resolved_services.plan_workspace.update_plan_settings(
            plan_id=plan_id,
            updates=updates,
            rationale="Updated via Plan Workspace settings.",
            status="accepted",
            log_decision=True,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_settings_updated")
    return m._build_plan_detail_response(detail, inbox=resolved_services.recommendation_inbox)


@router.get("/api/plans/{plan_id}/timeline", response_model=m.PlanTimelineResponse)
def get_plan_timeline(
    plan_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanTimelineResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        timeline = resolved_services.plan_workspace.get_plan_timeline(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanTimelineResponse(**timeline)


@router.put("/api/plans/{plan_id}/timeline", response_model=m.PlanTimelineResponse)
def update_plan_timeline(
    plan_id: str,
    request: m.PlanTimelineUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanTimelineResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        timeline = resolved_services.plan_workspace.update_plan_timeline(
            plan_id=plan_id,
            timeline_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace timeline editor.",
            status="accepted",
            log_decision=True,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_timeline_updated")
    return m.PlanTimelineResponse(**timeline)


@router.get("/api/plans/{plan_id}/contribution-rules", response_model=m.PlanContributionRulesResponse)
def get_plan_contribution_rules(
    plan_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanContributionRulesResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_plan_contribution_rules(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_contribution_rules_updated")
    return m.PlanContributionRulesResponse(**payload)


@router.put("/api/plans/{plan_id}/contribution-rules", response_model=m.PlanContributionRulesResponse)
def update_plan_contribution_rules(
    plan_id: str,
    request: m.PlanContributionRulesUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanContributionRulesResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.update_plan_contribution_rules(
            plan_id=plan_id,
            contribution_rules_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace contribution rules editor.",
            status="accepted",
            log_decision=True,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.PlanContributionRulesResponse(**payload)


@router.get("/api/plans/{plan_id}/assumption-sets", response_model=m.PlanAssumptionSetsResponse)
def get_plan_assumption_sets(
    plan_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanAssumptionSetsResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_plan_assumption_sets(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_assumption_sets_updated")
    return m.PlanAssumptionSetsResponse(**payload)


@router.put("/api/plans/{plan_id}/assumption-sets", response_model=m.PlanAssumptionSetsResponse)
def update_plan_assumption_sets(
    plan_id: str,
    request: m.PlanAssumptionSetsUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanAssumptionSetsResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.update_plan_assumption_sets(
            plan_id=plan_id,
            assumption_sets_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace assumption sets editor.",
            status="accepted",
            log_decision=True,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.PlanAssumptionSetsResponse(**payload)


@router.get("/api/plans/{plan_id}/branch-templates", response_model=m.PlanScenarioBranchTemplatesResponse)
def get_plan_branch_templates(
    plan_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanScenarioBranchTemplatesResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_plan_branch_templates(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_branch_templates_updated")
    return m.PlanScenarioBranchTemplatesResponse(**payload)


@router.put("/api/plans/{plan_id}/branch-templates", response_model=m.PlanScenarioBranchTemplatesResponse)
def update_plan_branch_templates(
    plan_id: str,
    request: m.PlanScenarioBranchTemplatesUpdateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanScenarioBranchTemplatesResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.update_plan_branch_templates(
            plan_id=plan_id,
            branch_templates_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace branch templates editor.",
            status="accepted",
            log_decision=True,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.PlanScenarioBranchTemplatesResponse(**payload)


@router.post("/api/plans/{plan_id}/simulation-explain", response_model=m.PlanSimulationExplainResponse)
def explain_plan_simulation_result(
    plan_id: str,
    request: m.PlanSimulationExplainRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSimulationExplainResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        resolved_services.plan_workspace.get_plan(plan_id)
        payload = m.explain_plan_simulation(
            plan_id=plan_id,
            source=request.source,
            input_payload=request.input_payload,
            result_payload=request.result_payload,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanSimulationExplainResponse(**payload)


@router.post("/api/plans/{plan_id}/what-if-review-level", response_model=m.PlanWhatIfReviewLevelResponse)
def classify_plan_what_if_review_level(
    plan_id: str,
    request: m.PlanWhatIfReviewLevelRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanWhatIfReviewLevelResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        resolved_services.plan_workspace.get_plan(plan_id)
        payload = m.classify_plan_lever_impact(
            plan_id=plan_id,
            source=request.source,
            input_payload=request.input_payload,
            result_payload=request.result_payload,
            explanation_payload=request.explanation_payload,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanWhatIfReviewLevelResponse(**payload)


@router.get("/api/plans/{plan_id}/simulations/saved", response_model=m.PlanSavedSimulationsResponse)
def list_plan_saved_simulations(
    plan_id: str,
    limit: int = 50,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSavedSimulationsResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.list_saved_simulations(plan_id=plan_id, limit=limit)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanSavedSimulationsResponse(**payload)


@router.post("/api/plans/{plan_id}/simulations/saved", response_model=m.PlanSavedSimulation)
def create_plan_saved_simulation(
    plan_id: str,
    request: m.PlanSavedSimulationCreateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSavedSimulation:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        linked_run = None
        if request.simulation_run_id:
            linked_run = resolved_services.plan_workspace.get_simulation_run(
                plan_id,
                request.simulation_run_id,
            )
            if linked_run.get("status") != "completed":
                raise ValueError("Only a completed Simulation Run can be saved.")
        payload = resolved_services.plan_workspace.save_simulation(
            plan_id=plan_id,
            simulation_payload=request.model_dump(mode="json"),
        )
        if linked_run is not None:
            resolved_services.plan_workspace.finish_simulation_run(
                plan_id,
                request.simulation_run_id or "",
                status="completed",
                result_payload=(
                    linked_run.get("result_payload")
                    if isinstance(linked_run.get("result_payload"), dict)
                    else {}
                ),
                saved_simulation_id=str(payload.get("id") or ""),
            )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_saved_simulation_created")
    return m.PlanSavedSimulation(**payload)


@router.get("/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}", response_model=m.PlanSavedSimulation)
def get_plan_saved_simulation(
    plan_id: str,
    saved_simulation_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSavedSimulation:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanSavedSimulation(**payload)


@router.get(
    "/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/compare-current",
    response_model=m.PlanSavedSimulationCompareResponse,
)
def compare_plan_saved_simulation_to_current(
    plan_id: str,
    saved_simulation_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSavedSimulationCompareResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
        simulation = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
        settings_payload = detail.get("settings")
        current_settings = settings_payload if isinstance(settings_payload, dict) else {}
        payload = m.compare_saved_simulation_to_current_plan(
            plan_id=plan_id,
            saved_simulation=simulation,
            current_settings=current_settings,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.PlanSavedSimulationCompareResponse(**payload)


@router.post(
    "/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/rerun",
    response_model=m.PlanSavedSimulationRerunResponse,
)
async def rerun_plan_saved_simulation(
    plan_id: str,
    saved_simulation_id: str,
    request: m.PlanSavedSimulationRerunRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSavedSimulationRerunResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write" if request.save_result else "plan.read",
        http_request=http_request,
        require_write_token=request.save_result,
    )
    try:
        simulation = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
        source = str(simulation.get("source") or "").strip().lower()
        input_payload = simulation.get("input_payload") if isinstance(simulation.get("input_payload"), dict) else {}

        if source == "scenario_diff":
            result_model = await m.run_plan_scenario_diff(
                plan_id,
                m.PlanScenarioDiffRequest(**input_payload),
                services=resolved_services,
            )
            result_payload = result_model.model_dump(mode="json")
            explanation = m.explain_plan_simulation(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
            )
            review_level = m.classify_plan_lever_impact(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
                explanation_payload=explanation,
            )
        elif source == "scenario_branch":
            result_model = await m.run_plan_scenario_branch(
                plan_id,
                m.PlanScenarioBranchRequest(**input_payload),
                services=resolved_services,
            )
            result_payload = result_model.model_dump(mode="json")
            explanation = m.explain_plan_simulation(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
            )
            review_level = m.classify_plan_lever_impact(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
                explanation_payload=explanation,
            )
        elif source == "withdrawal_strategy":
            result_model = await m.compare_plan_withdrawal_strategies(
                plan_id,
                m.PlanWithdrawalStrategyCompareRequest(**input_payload),
                services=resolved_services,
            )
            result_payload = result_model.model_dump(mode="json")
            explanation = result_payload.get("explanation") if isinstance(result_payload.get("explanation"), dict) else {}
            review_level = {}
        else:
            raise ValueError("Only simulation, what-if, and strategy comparison Saved Simulations can be rerun.")

        saved_payload = None
        if request.save_result:
            summary = str(explanation.get("summary") or "").strip() if isinstance(explanation, dict) else ""
            saved_payload = resolved_services.plan_workspace.save_simulation(
                plan_id=plan_id,
                simulation_payload={
                    "title": str(request.title or "").strip() or f"Rerun: {simulation.get('title') or saved_simulation_id}",
                    "source": source,
                    "summary": summary,
                    "notes": request.notes,
                    "input_payload": input_payload,
                    "result_payload": result_payload,
                    "simulation_run_id": result_payload.get("simulation_run_id"),
                },
            )
            rerun_id = str(result_payload.get("simulation_run_id") or "").strip()
            if rerun_id:
                resolved_services.plan_workspace.finish_simulation_run(
                    plan_id,
                    rerun_id,
                    status="completed",
                    result_payload=result_payload,
                    saved_simulation_id=str(saved_payload.get("id") or ""),
                )
            m._queue_autogit_event("plan_saved_simulation_rerun_saved")
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    return m.PlanSavedSimulationRerunResponse(
        plan_id=plan_id,
        saved_simulation_id=saved_simulation_id,
        source=source,
        input_payload=input_payload,
        result_payload=result_payload,
        explanation=explanation if isinstance(explanation, dict) else {},
        review_level=review_level if isinstance(review_level, dict) else {},
        saved_simulation=m.PlanSavedSimulation(**saved_payload) if isinstance(saved_payload, dict) else None,
    )


@router.post(
    "/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/decision",
    response_model=m.PlanSavedSimulationDecisionResponse,
)
def create_plan_saved_simulation_decision(
    plan_id: str,
    saved_simulation_id: str,
    request: m.PlanSavedSimulationDecisionRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSavedSimulationDecisionResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        simulation = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
        summary = (
            str(request.summary or "").strip()
            or f"Reviewed saved simulation: {simulation.get('title') or saved_simulation_id}"
        )
        rationale = (
            str(request.rationale or "").strip()
            or str(simulation.get("summary") or "").strip()
            or "Saved simulation reviewed before changing the active plan."
        )
        decision = resolved_services.plan_workspace.append_decision(
            plan_id=plan_id,
            summary=summary,
            rationale=f"{rationale} Saved simulation id: {saved_simulation_id}.",
            status=request.status,
            action_payload={
                "plan_id": plan_id,
                "saved_simulation_id": saved_simulation_id,
                "saved_simulation_title": simulation.get("title"),
                "source": "saved_simulation_decision",
            },
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_saved_simulation_decision_added")
    return m.PlanSavedSimulationDecisionResponse(
        plan_id=plan_id,
        saved_simulation_id=saved_simulation_id,
        simulation=m.PlanSavedSimulation(**simulation),
        decision=decision,
    )


@router.post("/api/plans/{plan_id}/branch-templates/pin-watchlist", response_model=m.PlanResearchBridgeResponse)
def pin_watchlist_research_to_plan_branch_template(
    plan_id: str,
    request: m.PlanResearchBridgeRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanResearchBridgeResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        return m.pin_watchlist_research_bridge(plan_id=plan_id, request=request, services=resolved_services)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/plans/{plan_id}/scenario-diff", response_model=m.PlanScenarioDiffResponse)
@track_simulation_run("scenario_diff")
async def run_plan_scenario_diff(
    plan_id: str,
    request: m.PlanScenarioDiffRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanScenarioDiffResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    m.require_permission(resolved_services.context, "profile.read")
    m.require_permission(resolved_services.context, "portfolio.read")
    profile_payload = m.get_financial_profile_payload(resolved_services.financial_profile_store)
    planning_accounts = m.build_planning_accounts_from_portfolio(resolved_services.portfolio_store)
    compare_updates = request.compare_settings.model_dump(exclude_unset=True)

    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    timeline_payload = m.resolve_plan_timeline_payload(detail)
    retirement_age = m.resolve_timeline_retirement_age(timeline_payload)
    timeline_withdrawal_strategy = m.resolve_timeline_withdrawal_strategy(timeline_payload)
    timeline_drawdown_order = m.resolve_timeline_drawdown_order(timeline_payload)
    assumption_sets_payload = m.resolve_plan_assumption_sets(detail)
    requested_assumption_set_id = str(request.assumption_set_id or "").strip() or None
    requested_candidate_assumption_set_id = str(request.candidate_assumption_set_id or "").strip() or None
    base_settings_raw = detail.get("settings", {})
    if not isinstance(base_settings_raw, dict):
        base_settings_raw = {}
    base_settings, base_assumption_set = m.apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=requested_assumption_set_id,
    )
    candidate_set_id = requested_candidate_assumption_set_id or requested_assumption_set_id
    candidate_base_settings, candidate_assumption_set = m.apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=candidate_set_id,
    )
    candidate_settings = m.merge_plan_settings(candidate_base_settings, compare_updates)
    base_income_projection = m.build_income_projection_for_plan_settings(
        base_settings, profile_payload=profile_payload
    )
    candidate_income_projection = m.build_income_projection_for_plan_settings(
        candidate_settings, profile_payload=profile_payload
    )
    base_expense_projection = m.build_expense_projection_for_plan_settings(
        base_settings, profile_payload=profile_payload
    )
    candidate_expense_projection = m.build_expense_projection_for_plan_settings(
        candidate_settings, profile_payload=profile_payload
    )
    base_debt_projection = m.build_debt_projection_for_plan_settings(
        base_settings, profile_payload=profile_payload
    )
    candidate_debt_projection = m.build_debt_projection_for_plan_settings(
        candidate_settings, profile_payload=profile_payload
    )
    base_timeline_projection = m.build_timeline_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
    )
    candidate_timeline_projection = m.build_timeline_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
    )
    contribution_rules_payload = m.resolve_plan_contribution_rules(detail)
    base_contribution_allocation = m.build_contribution_allocation_for_plan_settings(
        plan_settings=base_settings,
        contribution_rules_payload=contribution_rules_payload,
        accounts_override=planning_accounts,
    )
    candidate_contribution_allocation = m.build_contribution_allocation_for_plan_settings(
        plan_settings=candidate_settings,
        contribution_rules_payload=contribution_rules_payload,
        accounts_override=planning_accounts,
    )
    base_social_security_projection = m.build_social_security_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        income_projection=base_income_projection,
        start_year=m.utc_now().year,
    )
    candidate_social_security_projection = m.build_social_security_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
        income_projection=candidate_income_projection,
        start_year=m.utc_now().year,
    )
    base_rmd_projection = m.build_rmd_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        start_year=m.utc_now().year,
        accounts_override=planning_accounts,
    )
    candidate_rmd_projection = m.build_rmd_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
        start_year=m.utc_now().year,
        accounts_override=planning_accounts,
    )

    try:
        current_value = m.resolve_portfolio_value(
            request.current_portfolio_value_usd,
            store=resolved_services.snapshot_store,
            portfolio=resolved_services.portfolio_store,
        )
        base_result = await m.run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_value,
            plan_settings=base_settings,
            income_projection=base_income_projection,
            expense_projection=base_expense_projection,
            debt_projection=base_debt_projection,
            timeline_projection=base_timeline_projection,
            contribution_allocation=base_contribution_allocation,
            social_security_projection=base_social_security_projection,
            rmd_projection=base_rmd_projection,
            assumption_set=base_assumption_set,
            retirement_age=retirement_age,
            timeline_withdrawal_strategy=timeline_withdrawal_strategy,
            timeline_drawdown_order=timeline_drawdown_order,
            profile_payload=profile_payload,
            planning_accounts_override=planning_accounts,
        )
        candidate_result = await m.run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_value,
            plan_settings=candidate_settings,
            income_projection=candidate_income_projection,
            expense_projection=candidate_expense_projection,
            debt_projection=candidate_debt_projection,
            timeline_projection=candidate_timeline_projection,
            contribution_allocation=candidate_contribution_allocation,
            social_security_projection=candidate_social_security_projection,
            rmd_projection=candidate_rmd_projection,
            assumption_set=candidate_assumption_set,
            retirement_age=retirement_age,
            timeline_withdrawal_strategy=timeline_withdrawal_strategy,
            timeline_drawdown_order=timeline_drawdown_order,
            profile_payload=profile_payload,
            planning_accounts_override=planning_accounts,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    scenario_deltas, monte_carlo_delta, simulation_delta = m.build_scenario_diff_payload(
        base_result,
        candidate_result,
    )

    return m.PlanScenarioDiffResponse(
        plan_id=plan_id,
        current_portfolio_value_usd=current_value,
        base_settings=m.PlanSettings(**base_settings),
        candidate_settings=m.PlanSettings(**candidate_settings),
        base_assumption_set=base_assumption_set,
        candidate_assumption_set=candidate_assumption_set,
        base_result=base_result,
        candidate_result=candidate_result,
        scenario_deltas=[m.ScenarioComparisonRow(**item) for item in scenario_deltas],
        monte_carlo_delta=monte_carlo_delta,
        simulation_delta=simulation_delta,
    )


@router.post(
    "/api/plans/{plan_id}/withdrawal-strategy-compare",
    response_model=m.PlanWithdrawalStrategyCompareResponse,
)
@track_simulation_run("withdrawal_strategy")
async def compare_plan_withdrawal_strategies(
    plan_id: str,
    request: m.PlanWithdrawalStrategyCompareRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanWithdrawalStrategyCompareResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    arguments: dict[str, m.Any] = {
        "plan_id": plan_id,
        "current_portfolio_value_usd": request.current_portfolio_value_usd,
        "assumption_set_id": request.assumption_set_id,
        "strategies": request.strategies,
        "include_raw_results": request.include_raw_results,
    }
    try:
        token = m.current_copilot_workspace_services.set(resolved_services)
        try:
            payload = await m.tool_compare_withdrawal_strategies(arguments)
        finally:
            m.current_copilot_workspace_services.reset(token)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    except m.HTTPException:
        raise
    except Exception as exc:
        raise m.HTTPException(
            status_code=500,
            detail=f"Withdrawal strategy comparison failed: {exc}",
        ) from exc
    return m.PlanWithdrawalStrategyCompareResponse(**payload)


@router.post("/api/plans/{plan_id}/scenario-branch", response_model=m.PlanScenarioBranchResponse)
@track_simulation_run("scenario_branch")
async def run_plan_scenario_branch(
    plan_id: str,
    request: m.PlanScenarioBranchRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanScenarioBranchResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    compare_updates = request.compare_settings.model_dump(exclude_unset=True)
    raw_branch_events = [item.model_dump(mode="json") for item in request.branch_events]

    try:
        payload = await m.compute_plan_scenario_branch(
            plan_id=plan_id,
            branch_name=str(request.branch_name or "").strip() or "What-If Branch",
            current_portfolio_value_usd=request.current_portfolio_value_usd,
            assumption_set_id=str(request.assumption_set_id or "").strip() or None,
            branch_template_id=str(request.branch_template_id or "").strip() or None,
            compare_updates=compare_updates,
            raw_branch_events=raw_branch_events,
            services=resolved_services,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    return m.PlanScenarioBranchResponse(**payload)


@router.get("/api/plans/{plan_id}/tracking", response_model=m.PlanTrackingResponse)
def get_plan_tracking(
    plan_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanTrackingResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    plan_settings = m.PlanSettings(**detail.get("settings", {}))
    snapshots = resolved_services.snapshot_store.recent(limit=90)
    transactions = resolved_services.portfolio_store.list_transactions(limit=10_000)

    planner_defaults = {
        "annual_contribution_usd": m.settings.planner_annual_contribution_usd,
        "expected_return_baseline": m.settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": m.settings.planner_hsa_delta_default,
    }

    return m.compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    )


@router.post("/api/plans/{plan_id}/activate", response_model=m.PlanSummary)
def activate_plan(
    plan_id: str,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanSummary:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        summary = resolved_services.plan_workspace.set_active_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    m._queue_autogit_event("plan_activated")
    return m.PlanSummary(**summary)


@router.post(
    "/api/plans/{plan_id}/recommendation-closure-summary",
    response_model=m.PlanRecommendationClosureSummaryResponse,
)
def create_plan_recommendation_closure_summary_route(
    plan_id: str,
    request: m.PlanRecommendationClosureSummaryRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanRecommendationClosureSummaryResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write" if request.write_artifact else "plan.read",
        http_request=http_request,
        require_write_token=request.write_artifact,
    )
    try:
        response = m.create_plan_recommendation_closure_summary(
            plan_id=plan_id,
            request=request,
            services=resolved_services,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_recommendation_closure_summary_created")
    return response


@router.post("/api/plans/{plan_id}/decisions", response_model=m.PlanDetailResponse)
def append_plan_decision(
    plan_id: str,
    request: m.PlanDecisionCreateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanDetailResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        resolved_services.plan_workspace.append_decision(
            plan_id=plan_id,
            summary=request.summary,
            rationale=request.rationale,
            status=request.status,
            action_payload=request.action_payload,
        )
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("plan_decision_added")
    return m._build_plan_detail_response(detail, inbox=resolved_services.recommendation_inbox)


@router.post("/api/plans/{plan_id}/refresh-context", response_model=m.PlanDetailResponse)
def refresh_plan_context(
    plan_id: str,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanDetailResponse:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        resolved_services.plan_workspace.refresh_context(plan_id)
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    m._queue_autogit_event("plan_context_refreshed")
    return m._build_plan_detail_response(detail, inbox=resolved_services.recommendation_inbox)


@router.get("/api/plans/{plan_id}/artifacts/{artifact_id}", response_model=m.PlanArtifactResponse)
def read_plan_artifact(
    plan_id: str,
    artifact_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PlanArtifactResponse:
    resolved_services = m.route_workspace_services(services, permission="plan.read")
    try:
        artifact = resolved_services.plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    if str(artifact.get("title") or "").lower().startswith("research dossier") or "-research-dossier-" in str(artifact.get("file_name") or ""):
        artifact.update(m._extract_thesis_review_metadata_from_markdown(artifact.get("content")))
        artifact["thesis_review"] = m.research_thesis_review_metadata(artifact)
        artifact["thesis_revision_history"] = m._extract_thesis_revision_history(artifact.get("content"))
    return m.PlanArtifactResponse(**artifact)


@router.put("/api/plans/{plan_id}/artifacts/{artifact_id}/thesis")
def save_plan_artifact_thesis_revision(
    plan_id: str,
    artifact_id: str,
    request: dict[str, m.Any],
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    thesis = str(request.get("thesis") or request.get("proposed_thesis") or "").strip()
    if not thesis:
        raise m.HTTPException(status_code=400, detail="thesis is required")

    reference_raw = (
        request.get("reference_price_usd")
        if request.get("reference_price_usd") is not None
        else request.get("thesis_reference_price_usd")
    )
    reference_value = m._coerce_optional_float(reference_raw)
    if reference_raw not in (None, "", "null") and reference_value is None:
        raise m.HTTPException(status_code=400, detail="reference_price_usd must be a number")
    if reference_value is not None and reference_value <= 0:
        raise m.HTTPException(status_code=400, detail="reference_price_usd must be greater than 0")

    try:
        review_window_days = max(1, min(int(request.get("review_window_days") or m.TODAY_THESIS_REVIEW_DAYS), 3650))
    except (TypeError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail="review_window_days must be an integer") from exc

    reviewed_at_dt = m.utc_now()
    reviewed_at = reviewed_at_dt.isoformat()
    expires_at = str(request.get("expires_at") or "").strip() or (reviewed_at_dt + m.timedelta(days=review_window_days)).isoformat()

    try:
        artifact = resolved_services.plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
        previous_thesis = m._extract_markdown_section(artifact.get("content"), "Thesis")
        revision_event = m._compact_thesis_revision_event(
            target_type="dossier",
            plan_id=plan_id,
            artifact_id=artifact_id,
            previous_thesis=previous_thesis,
            revised_thesis=thesis,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
            review_window_days=review_window_days,
            request=request,
        )
        updated = m._replace_markdown_section(str(artifact.get("content") or ""), "Thesis", thesis)
        updated = m._replace_thesis_revision_notes_section(updated, str(request.get("rationale") or ""))
        updated = m._replace_thesis_review_metadata_section(
            updated,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
        )
        updated = m._replace_thesis_revision_history_section(updated, revision_event)
        saved = resolved_services.plan_workspace.update_artifact_content(
            plan_id=plan_id,
            artifact_id=artifact_id,
            markdown=updated,
        )
        m._link_thesis_revision_to_recommendation(
            request.get("recommendation_id"),
            revision_event,
            inbox=resolved_services.recommendation_inbox,
        )
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    history_lines = m._extract_thesis_revision_history_lines(saved.get("content"))
    review = m.research_thesis_review_metadata(
        {
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "reference_price_usd": reference_value,
        }
    )
    return {
        "artifact": saved,
        "thesis_review": {
            "status": review.get("status") or "current",
            "target": "dossier",
            "plan_id": plan_id,
            "artifact_id": saved.get("id") or artifact_id,
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "reference_price_usd": reference_value,
            "age_days": review.get("age_days"),
        },
        "thesis_revision_history": [
            revision_event,
            *({"summary": line} for line in history_lines[1:m.THESIS_REVISION_HISTORY_LIMIT]),
        ],
    }
