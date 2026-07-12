"""System routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_release_readiness",
    "record_release_workflow_verification",
    "preview_secret_key_rotation",
    "apply_secret_key_rotation",
    "get_service_status",
    "get_runtime_telemetry",
    "list_workflow_templates",
    "run_workflow",
    "chat",
]


@router.get("/api/release-readiness", response_model=m.ReleaseReadinessResponse)
def get_release_readiness(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ReleaseReadinessResponse:
    resolved_services = m.route_workspace_services(services, permission="backup.read")
    return m.build_release_readiness_response(services=resolved_services)


@router.post("/api/release-readiness/workflow-verification", response_model=m.GitActivityEvent)
def record_release_workflow_verification(
    request: m.ReleaseWorkflowVerificationRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.GitActivityEvent:
    resolved_services = m.route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    activity_store = (
        m._git_activity_store(resolved_services)
        if hasattr(services, "context")
        else m._git_activity_store()
    )
    workflow = str(request.workflow or "product_testing").strip() or "product_testing"
    failed_count = int(request.failed_count or 0)
    passed_count = int(request.passed_count or 0)
    status = request.status
    title_status = "passed" if status == "passed" and failed_count == 0 else status
    event = activity_store.record(
        event_type="product_workflow_verification",
        title=f"Product workflow verification {title_status}",
        message=str(request.notes or "").strip(),
        status=status,
        metadata={
            "workflow": workflow,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "checklist_path": request.checklist_path or m.RELEASE_READINESS_PRODUCT_TESTING_CHECKLIST,
        },
    )
    return m.GitActivityEvent.model_validate(event)


@router.get("/api/security/secrets/rotation/preview")
def preview_secret_key_rotation(
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_permission(context, "workspace.manage")
    return m.workspace_service_factory.preview_secret_key_rotation()


@router.post("/api/security/secrets/rotation/apply")
def apply_secret_key_rotation(
    request: m.Request,
    payload: dict[str, m.Any],
    context: m.RequestContext = m.Depends(m.get_request_context),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(context, "workspace.manage")
    if str(payload.get("confirm") or "").strip().lower() != "rotate":
        raise m.HTTPException(status_code=400, detail='Type "rotate" to confirm secret key rotation')
    try:
        result = m.workspace_service_factory.rotate_secret_key()
    except m.SecretKeyRotationUnavailable as exc:
        raise m.HTTPException(status_code=409, detail=str(exc)) from exc
    m.control_plane_store.record_audit_event(
        action="security.workspace_secret_key_rotated",
        actor_user_id=context.user_id,
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        target_type="secret_key",
        target_id="workspace_secret_key",
        metadata_json=m.json.dumps(
            {
                "workspace_count": result.get("workspace_count"),
                "secret_count": result.get("secret_count"),
            }
        ),
    )
    return result


@router.get("/api/services/status", response_model=m.ServiceStatusResponse)
async def get_service_status(refresh: bool = False) -> m.ServiceStatusResponse:
    return m.build_native_service_status()


@router.get("/api/telemetry/runtime", response_model=m.RuntimeTelemetryResponse)
def get_runtime_telemetry() -> m.RuntimeTelemetryResponse:
    return m._build_runtime_telemetry_response()


@router.get("/api/workflows/templates", response_model=list[m.WorkflowTemplateResponse])
def list_workflow_templates() -> list[m.WorkflowTemplateResponse]:
    templates = m.workflow_runner.templates()
    return [m.WorkflowTemplateResponse(**item) for item in templates]


@router.post("/api/workflows/run", response_model=m.WorkflowRunResponse)
async def run_workflow(
    request: m.WorkflowRunRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.WorkflowRunResponse:
    requires_write = bool(request.save_to_plan or request.create_recommendations)
    resolved_services = m.route_workspace_services(
        services,
        permission="plan.write" if requires_write else "portfolio.read",
        http_request=http_request,
        require_write_token=requires_write,
    )
    snapshot, previous_snapshot = await m.resolve_snapshots_for_workflow(
        use_live_snapshot=request.use_live_snapshot,
        services=resolved_services,
    )

    try:
        result = m.workflow_runner.run(
            workflow_id=request.workflow_id,
            snapshot=snapshot,
            params=request.params,
            previous_snapshot=previous_snapshot,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_plan_id = request.plan_id or resolved_services.plan_workspace.get_active_plan_id()

    artifact_payload: dict[str, object] | None = None
    if request.save_to_plan:
        if resolved_plan_id:
            try:
                artifact_payload = resolved_services.plan_workspace.write_artifact(
                    plan_id=resolved_plan_id,
                    title=f"{request.workflow_id.replace('_', ' ').title()} Report",
                    markdown=result.get("report_markdown", ""),
                    kind=request.workflow_id,
                )
            except m.PlanNotFoundError as exc:
                raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    result["artifact"] = artifact_payload
    if request.create_recommendations:
        result["recommendations"] = m.create_recommendations_from_workflow_result(
            workflow_id=request.workflow_id,
            result=result,
            plan_id=resolved_plan_id,
            inbox=resolved_services.recommendation_inbox,
        )
    else:
        result["recommendations"] = []
    return m.WorkflowRunResponse(**result)


@router.post("/api/chat", response_model=m.ChatResponse)
async def chat(request: m.ChatRequest) -> m.ChatResponse:
    if request.refresh_snapshot:
        snapshot = await m.build_live_snapshot()
        m.snapshot_store.write(snapshot)
    else:
        try:
            snapshot = m.snapshot_store.latest()
        except FileNotFoundError:
            snapshot = await m.build_live_snapshot()
            m.snapshot_store.write(snapshot)

    planning = m.scenario_engine.run(current_portfolio_value_usd=snapshot.total_value_usd).model_dump()
    research = None

    if any(token in request.question.lower() for token in ["option", "options", "chain", "research"]):
        # Default demo symbol until a ticker is requested explicitly.
        research = m.research_service.options_chain("AAPL").model_dump()

    return m.coordinator.answer(
        question=request.question,
        snapshot=snapshot,
        planning=planning,
        research=research,
    )
