from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.simulation_runs import track_simulation_run


def test_simulation_run_decorator_persists_input_result_and_stable_id(tmp_path) -> None:
    workspace = PlanWorkspace(tmp_path)
    plan = workspace.create_plan(title="Tracked simulation")
    services = SimpleNamespace(plan_workspace=workspace)

    @track_simulation_run("scenario_diff")
    async def run(*, plan_id, request, services):
        return {"plan_id": plan_id, "delta": request["delta"]}

    result = asyncio.run(
        run(plan_id=plan["id"], request={"delta": 12500}, services=services)
    )

    assert result["simulation_run_id"].startswith("simulation-run-")
    stored = workspace.get_simulation_run(plan["id"], result["simulation_run_id"])
    assert stored["status"] == "completed"
    assert stored["input_payload"] == {"delta": 12500}
    assert stored["result_payload"]["delta"] == 12500
    assert stored["result_payload"]["simulation_run_id"] == stored["id"]


def test_simulation_run_decorator_records_failures(tmp_path) -> None:
    workspace = PlanWorkspace(tmp_path)
    plan = workspace.create_plan(title="Failed simulation")
    services = SimpleNamespace(plan_workspace=workspace)

    @track_simulation_run("scenario_branch")
    async def run(*, plan_id, request, services):
        raise ValueError("invalid branch")

    with pytest.raises(ValueError, match="invalid branch"):
        asyncio.run(run(plan_id=plan["id"], request={}, services=services))

    stored = workspace.list_simulation_runs(plan["id"])["runs"][0]
    assert stored["status"] == "failed"
    assert stored["completed_at"]
    assert stored["error"] == "ValueError: invalid branch"
