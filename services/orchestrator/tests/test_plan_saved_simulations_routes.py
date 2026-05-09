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

