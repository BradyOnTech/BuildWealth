import asyncio
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace


def test_copilot_registry_includes_phase_3_5_tools() -> None:
    required_tools = {
        "get_account_balances",
        "compute_tax",
        "add_timeline_event",
        "compare_withdrawal_strategies",
        "get_asset_allocation",
        "set_contribution_rules",
        "get_buildwealth_context",
    }
    assert required_tools <= set(main.copilot.tools.keys())


def test_copilot_prompt_includes_context_quality_guidance() -> None:
    prompt = str(main.copilot.system_prompt)
    assert "quality.freshness.snapshot_stale" in prompt
    assert "caveat recommendations when context quality is degraded" in prompt


def test_get_buildwealth_context_tool_supports_detail_level_control() -> None:
    tool = main.copilot.tools["get_buildwealth_context"]
    properties = tool.parameters.get("properties", {})
    detail_field = properties.get("detail_level")
    assert isinstance(detail_field, dict)
    assert detail_field.get("enum") == ["light", "full"]


def test_apply_recommendation_tool_supports_decision_packet_controls() -> None:
    tool = main.copilot.tools["apply_recommendation"]
    properties = tool.parameters.get("properties", {})
    assert "create_decision_packet" in properties
    assert "decision_packet_research_symbols" in properties


def test_tool_add_timeline_event_appends_event_and_preserves_retirement_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Timeline Tool Plan")
    workspace.update_plan_timeline(
        plan_id=detail["id"],
        timeline_payload={
            "events": [
                {
                    "id": "event-existing",
                    "date": "2028-01-01",
                    "label": "Existing Event",
                    "event_type": "milestone",
                    "impact_type": "portfolio",
                    "amount_usd": 0,
                    "recurring_frequency": "one_time",
                }
            ],
            "retirement": {
                "target_retirement_age": 60,
                "withdrawal_strategy": "four_percent_rule",
            },
        },
        log_decision=False,
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = asyncio.run(
        main.tool_add_timeline_event(
            {
                "plan_id": detail["id"],
                "date": "2030-03-15",
                "label": "Inheritance",
                "event_type": "windfall",
                "amount_usd": 50_000,
                "recurring_frequency": "one_time",
                "notes": "Family transfer",
            }
        )
    )

    assert payload["plan_id"] == detail["id"]
    assert payload["event"]["label"] == "Inheritance"
    assert payload["event"]["impact_type"] == "income"
    assert payload["event"]["notes"] == "Family transfer"

    timeline = workspace.get_plan_timeline(detail["id"])
    assert len(timeline["events"]) == 2
    assert any(item["label"] == "Existing Event" for item in timeline["events"])
    assert any(item["label"] == "Inheritance" for item in timeline["events"])
    assert timeline["retirement"]["target_retirement_age"] == 60
    assert timeline["retirement"]["withdrawal_strategy"] == "four_percent_rule"


def test_tool_add_timeline_event_uses_active_plan_when_plan_id_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Active Plan")
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = asyncio.run(
        main.tool_add_timeline_event(
            {
                "date": "2031-01-01",
                "label": "Raise",
                "event_type": "job_change",
                "amount_usd": 2_000,
                "recurring_frequency": "monthly",
            }
        )
    )

    assert payload["plan_id"] == detail["id"]
    assert payload["event"]["label"] == "Raise"
    assert payload["event"]["impact_type"] == "income"
    assert payload["event"]["recurring_frequency"] == "monthly"
