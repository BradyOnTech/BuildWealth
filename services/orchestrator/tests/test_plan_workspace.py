from pathlib import Path
import json

import pytest

from buildwealth_orchestrator.schemas import PlanTimelineUpdateRequest
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace


def test_plan_workspace_create_and_get_context(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)

    detail = workspace.create_plan(
        title="Retirement Acceleration 2026",
        description="Increase annual savings while keeping liquidity.",
    )

    assert detail["title"] == "Retirement Acceleration 2026"
    assert detail["is_active"] is True
    assert detail["schema_version"] == 2
    assert "## Goal" in detail["files"]["plan_markdown"]
    assert detail["files"]["plan_yaml"].startswith("currency: USD")
    assert '"events": []' in detail["files"]["timeline_json"]
    assert '"rules": []' in detail["files"]["contribution_rules_json"]
    assert '"templates": [' in detail["files"]["branch_templates_json"]
    assert detail["settings"]["annual_contribution_usd"] is None
    assert detail["settings"]["schema_version"] == 2

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
            "filing_status": "single",
            "withdrawal_strategy": "4_percent_rule",
        },
        rationale="Tune assumptions for 2026 plan.",
    )
    assert updated["settings"]["annual_contribution_usd"] == 22000
    assert updated["settings"]["years"] == 22
    assert updated["settings"]["marginal_tax_rate"] == 0.24
    assert updated["settings"]["filing_status"] == "single"
    assert updated["settings"]["withdrawal_strategy"] == "4_percent_rule"
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


def test_plan_workspace_migrates_legacy_index_and_settings(tmp_path: Path) -> None:
    (tmp_path / "index.json").write_text(
        """
{
  "active_plan_id": "plan-legacy",
  "plans": [{
    "id": "plan-legacy",
    "title": "Legacy Plan",
    "description": "",
    "created_at": "2026-04-09T00:00:00+00:00",
    "updated_at": "2026-04-09T00:00:00+00:00"
  }]
}
        """.strip(),
        encoding="utf-8",
    )
    plan_dir = tmp_path / "plan-legacy"
    plan_dir.mkdir(parents=True)
    (plan_dir / "artifacts").mkdir()
    (plan_dir / "plan.md").write_text("# Legacy Plan", encoding="utf-8")
    (plan_dir / "plan.yaml").write_text("currency: USD\n", encoding="utf-8")
    (plan_dir / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (plan_dir / "context.md").write_text("", encoding="utf-8")
    (plan_dir / "decisions.jsonl").write_text("", encoding="utf-8")
    (plan_dir / "settings.json").write_text(
        """
{
  "annual_contribution_usd": 10000
}
        """.strip(),
        encoding="utf-8",
    )

    workspace = PlanWorkspace(tmp_path)
    detail = workspace.get_plan("plan-legacy")

    assert detail["schema_version"] == 2
    assert detail["settings"]["schema_version"] == 2
    assert detail["settings"]["annual_contribution_usd"] == 10000
    assert '"events": []' in detail["files"]["timeline_json"]
    assert '"rules": []' in detail["files"]["contribution_rules_json"]
    assert '"templates": [' in detail["files"]["branch_templates_json"]


def test_plan_workspace_updates_timeline(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Timeline Plan")

    updated_timeline = workspace.update_plan_timeline(
        plan_id=detail["id"],
        timeline_payload={
            "events": [
                {
                    "id": "event-1",
                    "date": "2028-06-01",
                    "label": "Buy House",
                    "event_type": "purchase",
                    "impact_type": "expense",
                    "amount_usd": 80000,
                    "recurring_frequency": "one_time",
                }
            ],
            "retirement": {
                "target_retirement_age": 60,
                "withdrawal_strategy": "4_percent_rule",
                "social_security_claiming_age": 67,
                "social_security_fra_monthly_benefit_usd": 2800,
                "rmd_birth_year": 1960,
                "rmd_start_age": 75,
            },
        },
    )

    assert len(updated_timeline["events"]) == 1
    assert updated_timeline["events"][0]["label"] == "Buy House"
    assert updated_timeline["retirement"]["target_retirement_age"] == 60
    assert updated_timeline["retirement"]["social_security_claiming_age"] == 67
    assert updated_timeline["retirement"]["social_security_fra_monthly_benefit_usd"] == 2800.0
    assert updated_timeline["retirement"]["rmd_birth_year"] == 1960
    assert updated_timeline["retirement"]["rmd_start_age"] == 75

    loaded = workspace.get_plan_timeline(detail["id"])
    assert len(loaded["events"]) == 1
    assert loaded["events"][0]["event_type"] == "purchase"

    refreshed = workspace.get_plan(detail["id"])
    timeline_json = json.loads(refreshed["files"]["timeline_json"])
    assert len(timeline_json["events"]) == 1
    assert refreshed["decisions"]
    assert "Updated plan timeline" in refreshed["decisions"][0]["summary"]


def test_plan_workspace_timeline_defaults_impact_type_by_event(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Timeline Defaults")

    updated_timeline = workspace.update_plan_timeline(
        plan_id=detail["id"],
        timeline_payload={
            "events": [
                {
                    "id": "event-purchase",
                    "date": "2029-01-01",
                    "label": "Home Down Payment",
                    "event_type": "purchase",
                    "amount_usd": 50000,
                },
                {
                    "id": "event-windfall",
                    "date": "2030-01-01",
                    "label": "Inheritance",
                    "event_type": "windfall",
                    "amount_usd": 25000,
                },
            ],
        },
    )

    assert len(updated_timeline["events"]) == 2
    assert updated_timeline["events"][0]["impact_type"] == "expense"
    assert updated_timeline["events"][1]["impact_type"] == "income"


def test_timeline_schema_defaults_impact_type_by_event() -> None:
    parsed = PlanTimelineUpdateRequest.model_validate(
        {
            "events": [
                {
                    "id": "event-retire",
                    "date": "2055-01-01",
                    "label": "Retire",
                    "event_type": "retirement",
                    "amount_usd": 12000,
                }
            ]
        }
    )

    assert parsed.events
    assert parsed.events[0].impact_type == "contribution"


def test_plan_workspace_contribution_rules_round_trip(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Contribution Rules Plan")

    defaults = workspace.get_plan_contribution_rules(detail["id"])
    assert defaults["base_rule"]["type"] == "save"
    assert defaults["rules"] == []
    assert defaults["employer_match_target_usd"] == pytest.approx(6000.0)
    assert defaults["age"] == 35

    updated = workspace.update_plan_contribution_rules(
        plan_id=detail["id"],
        contribution_rules_payload={
            "base_rule": {"type": "spend"},
            "rules": [
                {
                    "id": "rule-1",
                    "accountId": "acct-401k",
                    "rank": 1,
                    "amount": {"type": "dollarAmount", "dollarAmount": 10000},
                    "employerMatch": 6000,
                }
            ],
            "profile_id": "custom_profile",
            "employer_match_target_usd": 6500.0,
            "age": 40,
        },
        rationale="Tune contribution rules for matching-first strategy.",
    )
    assert updated["base_rule"]["type"] == "spend"
    assert len(updated["rules"]) == 1
    assert updated["profile_id"] == "custom_profile"
    assert updated["employer_match_target_usd"] == pytest.approx(6500.0)
    assert updated["age"] == 40

    refreshed = workspace.get_plan(detail["id"])
    assert refreshed["decisions"]
    assert refreshed["decisions"][0]["summary"].startswith("Updated contribution rules:")
    contribution_rules_json = json.loads(refreshed["files"]["contribution_rules_json"])
    assert contribution_rules_json["base_rule"]["type"] == "spend"
    assert contribution_rules_json["age"] == 40


def test_plan_workspace_contribution_rules_validation(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Contribution Rules Validation Plan")

    with pytest.raises(ValueError, match="base_rule.type"):
        workspace.update_plan_contribution_rules(
            plan_id=detail["id"],
            contribution_rules_payload={
                "base_rule": {"type": "invalid"},
                "rules": [],
            },
        )

    with pytest.raises(ValueError, match="rules must be a list"):
        workspace.update_plan_contribution_rules(
            plan_id=detail["id"],
            contribution_rules_payload={
                "base_rule": {"type": "save"},
                "rules": {},
            },
        )

    with pytest.raises(ValueError, match="age must be between 0 and 120"):
        workspace.update_plan_contribution_rules(
            plan_id=detail["id"],
            contribution_rules_payload={
                "base_rule": {"type": "save"},
                "rules": [],
                "age": 150,
            },
        )


def test_plan_workspace_assumption_sets_round_trip(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Assumption Sets Plan")

    defaults = workspace.get_plan_assumption_sets(detail["id"])
    default_ids = {item["id"] for item in defaults["sets"]}
    assert defaults["active_assumption_set_id"] == "default"
    assert {"default", "historical_average", "conservative", "stagflation", "japan_scenario"} <= default_ids

    updated = workspace.update_plan_assumption_sets(
        plan_id=detail["id"],
        assumption_sets_payload={
            "active_assumption_set_id": "StagFlation",
            "sets": [
                {
                    "id": "default",
                    "name": "Default",
                    "expected_return_baseline": None,
                    "expected_return_optimistic": None,
                    "expected_return_conservative": None,
                    "inflation_rate": None,
                    "marginal_tax_rate": None,
                },
                {
                    "id": "stagflation",
                    "name": "Stagflation",
                    "expected_return_baseline": 0.04,
                    "expected_return_optimistic": 0.05,
                    "expected_return_conservative": 0.02,
                    "inflation_rate": 0.05,
                    "marginal_tax_rate": 0.27,
                },
                {
                    "id": "custom_growth",
                    "name": "Custom Growth",
                    "expected_return_baseline": 0.065,
                    "expected_return_optimistic": 0.08,
                    "expected_return_conservative": 0.045,
                    "inflation_rate": 0.028,
                    "marginal_tax_rate": 0.24,
                },
            ],
        },
        rationale="Assumption set calibration for plan sensitivity analysis.",
    )

    assert updated["active_assumption_set_id"] == "stagflation"
    assert len(updated["sets"]) == 3
    custom = next(item for item in updated["sets"] if item["id"] == "custom_growth")
    assert custom["expected_return_baseline"] == pytest.approx(0.065)
    assert custom["inflation_rate"] == pytest.approx(0.028)

    refreshed = workspace.get_plan(detail["id"])
    assert refreshed["decisions"]
    assert refreshed["decisions"][0]["summary"].startswith("Updated assumption sets:")
    assumption_sets_json = json.loads(refreshed["files"]["assumption_sets_json"])
    assert assumption_sets_json["active_assumption_set_id"] == "stagflation"


def test_plan_workspace_assumption_sets_validation(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Assumption Validation Plan")

    with pytest.raises(ValueError, match="must be unique"):
        workspace.update_plan_assumption_sets(
            plan_id=detail["id"],
            assumption_sets_payload={
                "active_assumption_set_id": "duplicate",
                "sets": [
                    {
                        "id": "duplicate",
                        "name": "Duplicate A",
                        "expected_return_baseline": 0.06,
                        "expected_return_optimistic": 0.08,
                        "expected_return_conservative": 0.04,
                    },
                    {
                        "id": "duplicate",
                        "name": "Duplicate B",
                        "expected_return_baseline": 0.05,
                        "expected_return_optimistic": 0.06,
                        "expected_return_conservative": 0.03,
                    },
                ],
            },
        )

    with pytest.raises(ValueError, match="optimistic return must be >= baseline return"):
        workspace.update_plan_assumption_sets(
            plan_id=detail["id"],
            assumption_sets_payload={
                "active_assumption_set_id": "broken",
                "sets": [
                    {
                        "id": "broken",
                        "name": "Broken",
                        "expected_return_baseline": 0.07,
                        "expected_return_optimistic": 0.06,
                        "expected_return_conservative": 0.05,
                        "inflation_rate": 0.03,
                        "marginal_tax_rate": 0.24,
                    }
                ],
            },
        )


def test_plan_workspace_branch_templates_round_trip(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Branch Templates Plan")

    defaults = workspace.get_plan_branch_templates(detail["id"])
    assert defaults["default_template_id"] == "job_loss_6_months"
    default_ids = {item["id"] for item in defaults["templates"]}
    assert {"job_loss_6_months", "raise_20_percent", "new_child_costs"} <= default_ids

    updated = workspace.update_plan_branch_templates(
        plan_id=detail["id"],
        branch_templates_payload={
            "default_template_id": "custom_branch",
            "templates": [
                {
                    "id": "custom_branch",
                    "name": "Custom Branch",
                    "description": "Custom what-if setup",
                    "branch_name": "Custom Branch Run",
                    "assumption_set_id": "conservative",
                    "compare_settings": {
                        "annual_contribution_usd": 18000,
                        "expected_return_baseline": 0.06,
                        "expected_return_optimistic": 0.075,
                        "expected_return_conservative": 0.045,
                    },
                    "branch_events": [
                        {
                            "label": "Temporary Cost Spike",
                            "event_type": "milestone",
                            "impact_type": "expense",
                            "amount_usd": 950.0,
                            "recurring_frequency": "monthly",
                            "start_year_offset": 1,
                            "duration_months": 18,
                        }
                    ],
                }
            ],
        },
        rationale="Preset branch templates for rapid scenario analysis.",
    )
    assert updated["default_template_id"] == "custom_branch"
    assert len(updated["templates"]) == 1
    template = updated["templates"][0]
    assert template["id"] == "custom_branch"
    assert template["compare_settings"]["annual_contribution_usd"] == 18000
    assert template["branch_events"][0]["start_year_offset"] == 1

    refreshed = workspace.get_plan(detail["id"])
    assert refreshed["decisions"]
    assert refreshed["decisions"][0]["summary"].startswith("Updated branch templates:")
    branch_templates_json = json.loads(refreshed["files"]["branch_templates_json"])
    assert branch_templates_json["default_template_id"] == "custom_branch"


def test_plan_workspace_branch_templates_validation(tmp_path: Path) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Branch Template Validation Plan")

    with pytest.raises(ValueError, match="must be unique"):
        workspace.update_plan_branch_templates(
            plan_id=detail["id"],
            branch_templates_payload={
                "default_template_id": "dup",
                "templates": [
                    {
                        "id": "dup",
                        "name": "Dup A",
                        "branch_events": [
                            {
                                "label": "Event A",
                                "event_type": "milestone",
                                "impact_type": "expense",
                                "amount_usd": 100.0,
                                "start_year_offset": 0,
                            }
                        ],
                    },
                    {
                        "id": "dup",
                        "name": "Dup B",
                        "branch_events": [
                            {
                                "label": "Event B",
                                "event_type": "milestone",
                                "impact_type": "expense",
                                "amount_usd": 200.0,
                                "start_year_offset": 0,
                            }
                        ],
                    },
                ],
            },
        )

    with pytest.raises(ValueError, match="must include branch_events and/or compare_settings"):
        workspace.update_plan_branch_templates(
            plan_id=detail["id"],
            branch_templates_payload={
                "default_template_id": "empty-template",
                "templates": [
                    {
                        "id": "empty-template",
                        "name": "Empty",
                        "branch_events": [],
                        "compare_settings": {},
                    }
                ],
            },
        )
