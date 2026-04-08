from pathlib import Path

import pytest

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
    assert detail["settings"]["annual_contribution_usd"] is None

    context_payload = workspace.get_context_payload()
    assert context_payload["id"] == detail["id"]
    assert "Plan Context" in context_payload["context_excerpt"]
    assert "settings" in context_payload


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
    assert detail["artifacts"] == []

    artifact = workspace.write_artifact(
        plan_id=second["id"],
        title="Risk Concentration Review Report",
        markdown="# Risk Concentration Review Report\n\nGenerated output.",
        kind="risk_concentration_review",
    )
    assert artifact["file_name"].endswith(".md")

    detail_with_artifact = workspace.get_plan(second["id"])
    assert detail_with_artifact["artifacts"][0]["id"] == artifact["id"]

    read_back = workspace.read_artifact(second["id"], artifact["id"])
    assert "Generated output." in read_back["content"]

    activated = workspace.set_active_plan(first["id"])
    assert activated["id"] == first["id"]
    assert activated["is_active"] is True

    refreshed = workspace.get_plan(second["id"])
    assert refreshed["is_active"] is False


def test_plan_workspace_active_plan_id(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    assert workspace.get_active_plan_id() is None

    created = workspace.create_plan(title="Primary Plan")
    assert workspace.get_active_plan_id() == created["id"]


def test_plan_workspace_settings_update_and_validation(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Settings Plan")

    updated = workspace.update_plan_settings(
        plan_id=detail["id"],
        updates={
            "annual_contribution_usd": 22000,
            "years": 22,
            "marginal_tax_rate": 0.24,
            "expected_return_baseline": 0.07,
            "expected_return_optimistic": 0.09,
            "expected_return_conservative": 0.05,
        },
        rationale="Tune assumptions for 2026 plan.",
    )
    assert updated["settings"]["annual_contribution_usd"] == 22000
    assert updated["settings"]["years"] == 22
    assert updated["settings"]["marginal_tax_rate"] == 0.24
    assert "## Plan Settings" in updated["files"]["context_markdown"]
    assert updated["decisions"]
    assert updated["decisions"][0]["summary"].startswith("Updated plan settings:")

    with pytest.raises(ValueError):
        workspace.update_plan_settings(
            plan_id=detail["id"],
            updates={
                "expected_return_baseline": 0.07,
                "expected_return_optimistic": 0.06,
            },
        )
