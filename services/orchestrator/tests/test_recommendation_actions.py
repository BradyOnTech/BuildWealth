import asyncio
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_apply_recommendation_writes_decision_packet_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Decision Packet Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Increase annual contributions",
        detail="Raise annual contributions for stronger baseline outcomes.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id=plan["id"],
        action_payload={
            "plan_settings_updates": {
                "annual_contribution_usd": 25000.0,
            },
            "research_symbols": ["VTI"],
        },
    )

    async def fake_context_payload(**_: object) -> dict[str, object]:
        return {
            "generated_at": "2026-04-14T20:00:00+00:00",
            "scope": {
                "detail_level": "light",
            },
            "quality": {
                "freshness": {
                    "snapshot_stale": False,
                    "snapshot_age_seconds": 1800.0,
                },
                "coverage": {
                    "score_pct": 92.5,
                },
            },
            "warnings": [],
            "summary": "Context summary for decision packet coverage.",
            "research": {
                "symbols": ["VXUS"],
            },
        }

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_buildwealth_context_payload", fake_context_payload)

    response = asyncio.run(
        main.apply_recommendation_with_decision_packet(
            recommendation["id"],
            main.RecommendationApplyRequest(
                rationale="Lock in higher retirement savings.",
                decision_packet_research_symbols=["AAPL"],
            ),
        )
    )

    assert response.recommendation.status == "applied"
    assert response.decision_packet_artifact is not None
    assert response.plan is not None
    assert response.decision_packet_artifact.id in {item.id for item in response.plan.artifacts}

    packet_artifact = workspace.read_artifact(plan["id"], response.decision_packet_artifact.id)
    assert "## Unified Context Snapshot" in packet_artifact["content"]
    assert "## Selected Plan Assumptions" in packet_artifact["content"]
    assert "AAPL" in packet_artifact["content"]
    assert "VTI" in packet_artifact["content"]
    assert "VXUS" in packet_artifact["content"]

    updated_recommendation = inbox.get(recommendation["id"])
    packet_meta = updated_recommendation["action_payload"].get("decision_packet", {})
    assert packet_meta.get("artifact_id") == response.decision_packet_artifact.id
    assert "AAPL" in packet_meta.get("cited_research_symbols", [])


def test_apply_recommendation_can_skip_decision_packet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="No Packet Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review allocation",
        detail="Revisit allocation drift this week.",
        recommendation_type="general",
        plan_id=plan["id"],
    )

    async def should_not_run(**_: object) -> dict[str, object]:
        raise AssertionError("context payload should not be built when packet creation is disabled")

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_buildwealth_context_payload", should_not_run)

    response = asyncio.run(
        main.apply_recommendation_with_decision_packet(
            recommendation["id"],
            main.RecommendationApplyRequest(
                create_decision_packet=False,
            ),
        )
    )

    assert response.recommendation.status == "applied"
    assert response.decision_packet_artifact is None

    artifacts = workspace.get_plan(plan["id"]).get("artifacts", [])
    assert artifacts == []
