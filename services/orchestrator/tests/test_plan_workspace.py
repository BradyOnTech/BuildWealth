from pathlib import Path

from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace


def test_plan_workspace_create_and_get_context(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)

    detail = workspace.create_plan(
        title="Retirement Acceleration 2026",
        description="Increase annual savings while keeping liquidity.",
    )

    assert detail["title"] == "Retirement Acceleration 2026"
    assert detail["is_active"] is True
    assert "## Goal" in detail["files"]["plan_markdown"]
    assert detail["files"]["plan_yaml"].startswith("currency: USD")

    context_payload = workspace.get_context_payload()
    assert context_payload["id"] == detail["id"]
    assert "Plan Context" in context_payload["context_excerpt"]


def test_plan_workspace_updates_and_decisions(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    first = workspace.create_plan(title="Plan One")
    second = workspace.create_plan(title="Plan Two")

    assert workspace.list_plans(limit=10)[0]["id"] == second["id"]

    updated = workspace.update_plan_files(
        plan_id=second["id"],
        plan_markdown="# Plan Two\n\nUpdated strategy.",
        tasks_markdown="# Tasks\n\n- [ ] Run scenario diff",
    )
    assert "Updated strategy." in updated["files"]["plan_markdown"]
    assert "Run scenario diff" in updated["files"]["tasks_markdown"]

    decision = workspace.append_decision(
        plan_id=second["id"],
        summary="Increase HSA contribution by $1,000",
        rationale="Tax-efficient additional savings.",
        status="approved",
    )
    assert decision["status"] == "approved"

    detail = workspace.get_plan(second["id"])
    assert detail["decisions"][0]["summary"] == "Increase HSA contribution by $1,000"

    activated = workspace.set_active_plan(first["id"])
    assert activated["id"] == first["id"]
    assert activated["is_active"] is True

    refreshed = workspace.get_plan(second["id"])
    assert refreshed["is_active"] is False
