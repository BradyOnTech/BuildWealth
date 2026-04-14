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

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {"status": "captured", "scenario_deltas": [{"label": "baseline", "delta_future_value_usd": 1000.0}]}

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_buildwealth_context_payload", fake_context_payload)
    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)

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
    assert response.decision_closure_artifact is not None
    assert response.plan is not None
    assert response.decision_packet_artifact.id in {item.id for item in response.plan.artifacts}
    assert response.decision_closure_artifact.id in {item.id for item in response.plan.artifacts}

    packet_artifact = workspace.read_artifact(plan["id"], response.decision_packet_artifact.id)
    assert "## Unified Context Snapshot" in packet_artifact["content"]
    assert "## Selected Plan Assumptions" in packet_artifact["content"]
    assert "AAPL" in packet_artifact["content"]
    assert "VTI" in packet_artifact["content"]
    assert "VXUS" in packet_artifact["content"]
    closure_artifact = workspace.read_artifact(plan["id"], response.decision_closure_artifact.id)
    assert "## Scenario Preview" in closure_artifact["content"]
    assert "baseline" in closure_artifact["content"]

    updated_recommendation = inbox.get(recommendation["id"])
    packet_meta = updated_recommendation["action_payload"].get("decision_packet", {})
    assert packet_meta.get("artifact_id") == response.decision_packet_artifact.id
    assert "AAPL" in packet_meta.get("cited_research_symbols", [])
    closure_artifact_meta = updated_recommendation["action_payload"].get("decision_closure_artifact", {})
    assert closure_artifact_meta.get("artifact_id") == response.decision_closure_artifact.id
    closure = updated_recommendation["action_payload"].get("decision_closure", {})
    assert closure.get("scenario_diff_preview", {}).get("status") == "captured"


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

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {"status": "captured"}

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_buildwealth_context_payload", should_not_run)
    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)

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
    assert response.decision_closure_artifact is not None
    assert response.decision_closure.get("scenario_diff_preview", {}).get("status") == "captured"

    artifacts = workspace.get_plan(plan["id"]).get("artifacts", [])
    assert len(artifacts) == 1
    assert artifacts[0].get("id") == response.decision_closure_artifact.id


def test_apply_recommendation_updates_research_bridge_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Bridge Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Evaluate tech concentration",
        detail="Run a branch with watchlist research context.",
        recommendation_type="general",
        plan_id=plan["id"],
        action_payload={"research_symbols": ["VTI"]},
    )

    async def should_not_run(**_: object) -> dict[str, object]:
        raise AssertionError("context payload should not be built when decision packet creation is disabled")

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {"status": "captured"}

    def fake_pin(plan_id: str, request: main.PlanResearchBridgeRequest) -> main.PlanResearchBridgeResponse:
        assert plan_id == plan["id"]
        assert request.symbols == ["VTI"]
        return main.PlanResearchBridgeResponse(
            plan_id=plan_id,
            template_id="research_watchlist_bridge",
            template_name="Research Watchlist Thesis",
            pinned_symbols=["VTI"],
            pinned_items=[
                main.PlanResearchBridgePinnedItem(
                    symbol="VTI",
                    data_source="OPENBB",
                    thesis="Core market thesis",
                )
            ],
            branch_templates=main.PlanScenarioBranchTemplatesResponse(
                schema_version=2,
                default_template_id="research_watchlist_bridge",
                templates=[],
            ),
        )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_buildwealth_context_payload", should_not_run)
    monkeypatch.setattr(main, "pin_watchlist_research_bridge", fake_pin)
    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)

    response = asyncio.run(
        main.apply_recommendation_with_decision_packet(
            recommendation["id"],
            main.RecommendationApplyRequest(
                create_decision_packet=False,
                pin_research_bridge=True,
            ),
        )
    )

    assert response.recommendation.status == "applied"
    assert response.decision_packet_artifact is None
    assert response.decision_closure_artifact is not None
    assert response.research_bridge.get("status") == "pinned"
    assert response.suggested_research_symbols == ["VTI"]
    assert response.decision_closure.get("scenario_diff_preview", {}).get("status") == "captured"

    updated_recommendation = inbox.get(recommendation["id"])
    bridge_meta = updated_recommendation["action_payload"].get("research_bridge", {})
    assert bridge_meta.get("status") == "pinned"
    assert bridge_meta.get("template_id") == "research_watchlist_bridge"
    assert bridge_meta.get("pinned_symbols") == ["VTI"]
    closure_artifact_meta = updated_recommendation["action_payload"].get("decision_closure_artifact", {})
    assert closure_artifact_meta.get("artifact_id") == response.decision_closure_artifact.id


def test_reject_recommendation_returns_suggested_research_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Pause momentum trade",
        detail="Reject this for now.",
        recommendation_type="general",
        action_payload={"research_symbols": ["qqq", "VTI", "QQQ"]},
    )
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {"status": "captured", "scenario_deltas": []}

    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)
    response = asyncio.run(main.reject_recommendation(recommendation["id"], reason="Not aligned this month."))

    assert response.recommendation.status == "rejected"
    assert response.suggested_research_symbols == ["QQQ", "VTI"]
    assert response.decision_closure.get("scenario_diff_preview", {}).get("status") == "captured"


def test_reject_recommendation_persists_closure_artifact_when_plan_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Reject Closure Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Delay contribution increase",
        detail="Reject now and revisit in six months.",
        recommendation_type="plan_settings_update",
        plan_id=plan["id"],
        action_payload={
            "plan_settings_updates": {
                "annual_contribution_usd": 25000.0,
            }
        },
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {
            "status": "captured",
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "delta_future_value_usd": 1250.0,
                    "delta_real_value_usd": 900.0,
                }
            ],
        }

    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)
    response = asyncio.run(main.reject_recommendation(recommendation["id"], reason="Revisit after annual review."))

    assert response.recommendation.status == "rejected"
    assert response.plan is not None
    assert response.decision_closure_artifact is not None
    assert response.decision_closure.get("decision_status") == "rejected"

    decision_summaries = [item.summary for item in response.plan.decisions]
    assert any(summary.startswith("Recommendation closure:") for summary in decision_summaries)
    assert response.decision_closure_artifact.id in {item.id for item in response.plan.artifacts}

    updated_recommendation = inbox.get(recommendation["id"])
    closure_artifact_meta = updated_recommendation["action_payload"].get("decision_closure_artifact", {})
    assert closure_artifact_meta.get("artifact_id") == response.decision_closure_artifact.id


def test_reject_recommendation_can_write_decision_packet_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Reject Decision Packet Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Skip aggressive contribution bump",
        detail="Reject this recommendation for now.",
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
            "generated_at": "2026-04-14T21:00:00+00:00",
            "scope": {
                "detail_level": "light",
            },
            "quality": {
                "freshness": {
                    "snapshot_stale": False,
                    "snapshot_age_seconds": 900.0,
                },
                "coverage": {
                    "score_pct": 95.0,
                },
            },
            "warnings": [],
            "summary": "Context summary for reject decision packet.",
            "research": {
                "symbols": ["VXUS"],
            },
        }

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {"status": "captured", "scenario_deltas": [{"label": "baseline", "delta_future_value_usd": -800.0}]}

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_buildwealth_context_payload", fake_context_payload)
    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)

    response = asyncio.run(
        main.reject_recommendation(
            recommendation["id"],
            reason="Need to protect short-term liquidity.",
            create_decision_packet=True,
            decision_packet_research_symbols=["AAPL"],
        )
    )

    assert response.recommendation.status == "rejected"
    assert response.plan is not None
    assert response.decision_packet_artifact is not None
    assert response.decision_closure_artifact is not None
    assert response.decision_packet_artifact.id in {item.id for item in response.plan.artifacts}

    packet_artifact = workspace.read_artifact(plan["id"], response.decision_packet_artifact.id)
    assert "## Unified Context Snapshot" in packet_artifact["content"]
    assert "- Decision Status: `rejected`" in packet_artifact["content"]
    assert "AAPL" in packet_artifact["content"]
    assert "VTI" in packet_artifact["content"]
    assert "VXUS" in packet_artifact["content"]

    updated_recommendation = inbox.get(recommendation["id"])
    packet_meta = updated_recommendation["action_payload"].get("decision_packet", {})
    assert packet_meta.get("artifact_id") == response.decision_packet_artifact.id
    assert packet_meta.get("decision_status") == "rejected"
    assert "AAPL" in packet_meta.get("cited_research_symbols", [])


def test_preview_recommendation_plan_settings_update_captures_scenario(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Preview Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Increase savings",
        detail="Raise annual contributions.",
        recommendation_type="plan_settings_update",
        plan_id=plan["id"],
        action_payload={"plan_settings_updates": {"annual_contribution_usd": 26000.0}},
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    async def fake_preview(*_: object, **__: object) -> dict[str, object]:
        return {
            "status": "captured",
            "scenario_deltas": [{"label": "baseline", "delta_future_value_usd": 1500.0}],
        }

    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)
    response = asyncio.run(
        main.preview_recommendation(
            recommendation["id"],
            main.RecommendationPreviewRequest(),
        )
    )

    assert response.recommendation.status == "proposed"
    assert response.preview["status"] == "captured"
    assert response.preview["scenario_diff_preview"]["status"] == "captured"
    assert response.preview["action_preview"]["kind"] == "plan_settings_update"
    assert response.preview["action_preview"]["updates_count"] == 1
    assert response.preview["plan_id"] == plan["id"]

    unchanged = inbox.get(recommendation["id"])
    assert unchanged["status"] == "proposed"


def test_preview_recommendation_general_returns_advisory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review spending categories",
        detail="Quick housekeeping recommendation.",
        recommendation_type="general",
    )
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = asyncio.run(
        main.preview_recommendation(
            recommendation["id"],
            main.RecommendationPreviewRequest(),
        )
    )

    assert response.recommendation.status == "proposed"
    assert response.preview["status"] == "advisory"
    assert response.preview["action_preview"]["kind"] == "general"
    assert response.preview["scenario_diff_preview"]["status"] == "skipped"
