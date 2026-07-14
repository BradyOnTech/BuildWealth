from __future__ import annotations

import asyncio
from types import SimpleNamespace

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def _services(tmp_path):
    workspace = PlanWorkspace(tmp_path / "plans")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    return (
        SimpleNamespace(
            context=SimpleNamespace(permissions=frozenset()),
            plan_workspace=workspace,
            recommendation_inbox=inbox,
        ),
        workspace,
        inbox,
    )


def test_applied_recommendation_and_plan_decision_link_each_other(tmp_path) -> None:
    services, workspace, inbox = _services(tmp_path)
    plan = workspace.create_plan(title="Reciprocal links")
    recommendation = inbox.create(
        title="Increase savings",
        detail="Raise annual contributions.",
        recommendation_type="plan_settings_update",
        plan_id=plan["id"],
        action_payload={"plan_settings_updates": {"annual_contribution_usd": 30000}},
    )

    response = main.apply_recommendation(
        recommendation["id"],
        main.RecommendationApplyRequest(capture_scenario_diff=False, create_decision_packet=False),
        services=services,
        scenario_diff_preview={"simulation_run_id": "simulation-run-evidence"},
    )

    assert response.plan_decision is not None
    link = inbox.get(recommendation["id"])["action_payload"]["plan_decision"]
    assert link["decision_id"] == response.plan_decision.id
    assert link["simulation_run_id"] == "simulation-run-evidence"
    decision = next(
        item
        for item in workspace.get_plan(plan["id"])["decisions"]
        if item["id"] == response.plan_decision.id
    )
    assert decision["action_payload"]["recommendation_id"] == recommendation["id"]
    assert decision["action_payload"]["recommendation_resolution"] == "applied"
    assert decision["action_payload"]["simulation_run_id"] == "simulation-run-evidence"


def test_rejected_recommendation_creates_linked_plan_decision(tmp_path, monkeypatch) -> None:
    services, workspace, inbox = _services(tmp_path)
    plan = workspace.create_plan(title="Rejected links")
    recommendation = inbox.create(
        title="Change allocation",
        detail="Move to a more aggressive mix.",
        recommendation_type="general",
        plan_id=plan["id"],
    )

    async def preview(*args, **kwargs):
        return {"status": "captured", "simulation_run_id": "simulation-run-rejected"}

    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", preview)
    response = asyncio.run(
        main.reject_recommendation(
            recommendation["id"],
            reason="Risk is too high.",
            services=services,
        )
    )

    assert response.plan_decision is not None
    link = inbox.get(recommendation["id"])["action_payload"]["plan_decision"]
    assert link["decision_id"] == response.plan_decision.id
    decision = next(
        item
        for item in workspace.get_plan(plan["id"])["decisions"]
        if item["id"] == response.plan_decision.id
    )
    assert decision["status"] == "rejected"
    assert decision["action_payload"]["recommendation_id"] == recommendation["id"]
    assert decision["action_payload"]["recommendation_resolution"] == "rejected"


def test_recommendation_without_plan_uses_active_plan_from_supplied_workspace(
    tmp_path,
    monkeypatch,
) -> None:
    global_workspace = PlanWorkspace(tmp_path / "global-plans")
    global_plan = global_workspace.create_plan(title="Other household")
    services, workspace, inbox = _services(tmp_path / "active-household")
    active_plan = workspace.create_plan(title="Active household")
    recommendation = inbox.create(
        title="Use the active household plan",
        detail="This recommendation intentionally has no explicit plan id.",
        recommendation_type="general",
    )
    monkeypatch.setattr(main, "plan_workspace", global_workspace)

    response = main.apply_recommendation(
        recommendation["id"],
        main.RecommendationApplyRequest(
            capture_scenario_diff=False,
            create_decision_packet=False,
        ),
        services=services,
    )

    assert response.plan is not None
    assert response.plan.id == active_plan["id"]
    assert response.plan.id != global_plan["id"]
    assert len(workspace.get_plan(active_plan["id"])["decisions"]) == 1
    assert global_workspace.get_plan(global_plan["id"])["decisions"] == []
