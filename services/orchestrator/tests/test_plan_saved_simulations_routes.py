from __future__ import annotations

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace


def test_plan_saved_simulation_routes(monkeypatch, tmp_path) -> None:
    workspace = PlanWorkspace(tmp_path)
    plan = workspace.create_plan(title="Saved Simulation Route Plan")
    monkeypatch.setattr(main, "plan_workspace", workspace)

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
        assert decision_response.json()["decision"]["summary"].startswith("Reviewed saved simulation")

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
