from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace


def _override_plan_workspace(workspace: PlanWorkspace):
    services = SimpleNamespace(
        context=SimpleNamespace(permissions=ControlPlaneStore.OWNER_PERMISSIONS),
        plan_workspace=workspace,
        snapshot_store=main.snapshot_store,
        portfolio_store=main.portfolio_store,
        recommendation_inbox=main.recommendation_inbox,
    )
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    return services


def test_plan_saved_simulation_routes(monkeypatch, tmp_path) -> None:
    workspace = PlanWorkspace(tmp_path)
    plan = workspace.create_plan(title="Saved Simulation Route Plan")
    monkeypatch.setattr(main, "plan_workspace", workspace)
    _override_plan_workspace(workspace)

    try:
        with TestClient(main.app) as client:
            create_response = client.post(
                f"/api/plans/{plan['id']}/simulations/saved",
                json={
                    "title": "Market stress",
                    "source": "scenario_branch",
                    "summary": "Market stress reduced projected ending value.",
                    "input_payload": {"branch_template_id": "market_stress"},
                    "result_payload": {"scenario_deltas": [{"label": "baseline"}]},
                },
            )
            assert create_response.status_code == 200
            saved = create_response.json()
            assert saved["title"] == "Market stress"
            assert saved["immutable"] is True

            list_response = client.get(f"/api/plans/{plan['id']}/simulations/saved")
            assert list_response.status_code == 200
            assert list_response.json()["simulations"][0]["id"] == saved["id"]

            detail_response = client.get(f"/api/plans/{plan['id']}/simulations/saved/{saved['id']}")
            assert detail_response.status_code == 200
            assert detail_response.json()["summary"] == "Market stress reduced projected ending value."

            decision_response = client.post(
                f"/api/plans/{plan['id']}/simulations/saved/{saved['id']}/decision",
                json={"status": "proposed"},
            )
            assert decision_response.status_code == 200
            decision = decision_response.json()["decision"]
            assert decision["summary"].startswith("Reviewed saved simulation")
            assert decision["action_payload"]["plan_id"] == plan["id"]
            assert decision["action_payload"]["saved_simulation_id"] == saved["id"]
            assert decision["action_payload"]["saved_simulation_title"] == "Market stress"

            explain_response = client.post(
                f"/api/plans/{plan['id']}/simulation-explain",
                json={
                    "source": "scenario_branch",
                    "input_payload": {"branch_template_id": "market_stress"},
                    "result_payload": {
                        "base_settings": {"expected_return_baseline": 0.06},
                        "branch_settings": {"expected_return_baseline": 0.04},
                        "scenario_deltas": [
                            {
                                "label": "baseline",
                                "delta_future_value_usd": -60_000,
                                "delta_real_value_usd": -45_000,
                            }
                        ],
                    },
                },
            )
            assert explain_response.status_code == 200
            explained = explain_response.json()
            assert explained["source"] == "What-if simulation"
            assert explained["outcome_label"] == "worse"
            assert explained["assumption_traces"][0]["label"] == "Expected return"

            review_response = client.post(
                f"/api/plans/{plan['id']}/what-if-review-level",
                json={
                    "source": "scenario_branch",
                    "input_payload": {"branch_template_id": "market_stress"},
                    "result_payload": {
                        "base_settings": {"expected_return_baseline": 0.06},
                        "branch_settings": {"expected_return_baseline": 0.04},
                        "scenario_deltas": [
                            {
                                "label": "baseline",
                                "base_future_value_usd": 900_000,
                                "candidate_future_value_usd": 840_000,
                                "delta_future_value_usd": -60_000,
                                "delta_real_value_usd": -45_000,
                            }
                        ],
                    },
                    "explanation_payload": explained,
                },
            )
            assert review_response.status_code == 200
            review = review_response.json()
            assert review["source"] == "What-if simulation"
            assert review["review_level"] == "high"
            assert review["stage_one"]["name"] == "Change size"
            assert review["stage_two"]["name"] == "Result trust"
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)

def test_plan_saved_simulation_copilot_tools(monkeypatch, tmp_path) -> None:
    workspace = PlanWorkspace(tmp_path)
    plan = workspace.create_plan(
        title="Saved Simulation Tool Plan",
    )
    workspace.update_plan_settings(
        plan_id=plan["id"],
        updates={"annual_contribution_usd": 24_000},
        log_decision=False,
    )
    saved = workspace.save_simulation(
        plan_id=plan["id"],
        simulation_payload={
            "title": "Contribution lift",
            "source": "scenario_diff",
            "summary": "Contribution lift increased the projection.",
            "input_payload": {"annual_contribution_usd": 30_000},
            "result_payload": {
                "base_settings": {"annual_contribution_usd": 20_000},
                "candidate_settings": {"annual_contribution_usd": 30_000},
                "scenario_deltas": [{"label": "baseline", "delta_future_value_usd": 40_000}],
            },
        },
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)
    _override_plan_workspace(workspace)

    try:
        listed = asyncio.run(main.tool_list_plan_saved_simulations({"plan_id": plan["id"], "limit": 5}))
        assert listed["simulations"][0]["id"] == saved["id"]

        detail = asyncio.run(
            main.tool_get_plan_saved_simulation_context(
                {"plan_id": plan["id"], "saved_simulation_id": saved["id"]}
            )
        )
        assert detail["saved_simulation"]["title"] == "Contribution lift"

        comparison = asyncio.run(
            main.tool_compare_plan_saved_simulation_current(
                {"plan_id": plan["id"], "saved_simulation_id": saved["id"]}
            )
        )
        assert comparison["changed_since_saved"] is True
        assert comparison["setting_differences"][0]["field"] == "annual_contribution_usd"
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)


def test_plan_saved_simulation_compare_and_rerun_routes(monkeypatch, tmp_path) -> None:
    workspace = PlanWorkspace(tmp_path)
    plan = workspace.create_plan(title="Saved Simulation Compare Plan")
    workspace.update_plan_settings(
        plan_id=plan["id"],
        updates={"annual_contribution_usd": 24_000, "expected_return_baseline": 0.06},
        log_decision=False,
    )
    saved = workspace.save_simulation(
        plan_id=plan["id"],
        simulation_payload={
            "title": "Contribution increase",
            "source": "scenario_diff",
            "summary": "Increasing contributions improved the active plan.",
            "input_payload": {"compare_settings": {"annual_contribution_usd": 30_000}},
            "result_payload": {
                "base_settings": {
                    "annual_contribution_usd": 20_000,
                    "expected_return_baseline": 0.06,
                },
                "candidate_settings": {
                    "annual_contribution_usd": 30_000,
                    "expected_return_baseline": 0.06,
                },
                "scenario_deltas": [
                    {
                        "label": "baseline",
                        "delta_future_value_usd": 80_000,
                        "delta_real_value_usd": 50_000,
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)
    _override_plan_workspace(workspace)

    class FakeScenarioDiffResponse:
        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "plan_id": plan["id"],
                "base_settings": {"annual_contribution_usd": 24_000},
                "candidate_settings": {"annual_contribution_usd": 30_000},
                "scenario_deltas": [
                    {
                        "label": "baseline",
                        "delta_future_value_usd": 60_000,
                        "delta_real_value_usd": 40_000,
                    }
                ],
            }

    async def fake_run_plan_scenario_diff(plan_id: str, request, services=None):
        assert plan_id == plan["id"]
        assert services is not None
        assert request.compare_settings.annual_contribution_usd == 30_000
        return FakeScenarioDiffResponse()

    monkeypatch.setattr(main, "run_plan_scenario_diff", fake_run_plan_scenario_diff)

    try:
        with TestClient(main.app) as client:
            compare_response = client.get(
                f"/api/plans/{plan['id']}/simulations/saved/{saved['id']}/compare-current"
            )
            assert compare_response.status_code == 200
            comparison = compare_response.json()
            assert comparison["changed_since_saved"] is True
            assert comparison["setting_differences"][0]["label"] == "Annual contribution"
            assert comparison["rerun_payload"]["compare_settings"]["annual_contribution_usd"] == 30_000

            rerun_response = client.post(
                f"/api/plans/{plan['id']}/simulations/saved/{saved['id']}/rerun",
                json={"save_result": True, "title": "Contribution increase rerun"},
            )
            assert rerun_response.status_code == 200
            rerun = rerun_response.json()
            assert rerun["source"] == "scenario_diff"
            assert rerun["result_payload"]["scenario_deltas"][0]["delta_future_value_usd"] == 60_000
            assert rerun["saved_simulation"]["title"] == "Contribution increase rerun"
    finally:
        main.app.dependency_overrides.pop(main.get_workspace_services, None)
