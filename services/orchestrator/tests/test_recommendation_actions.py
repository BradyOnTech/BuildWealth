import asyncio
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.recommendation_factory import generate_plan_tracking_recommendations
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
    assert closure.get("expected_outcome", {}).get("status") == "captured"
    assert closure.get("expected_vs_realized", {}).get("status") == "pending_realized"


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
    assert response.decision_closure.get("expected_outcome", {}).get("status") in {"captured", "unavailable"}
    assert response.decision_closure.get("expected_vs_realized", {}).get("status") in {"pending_realized", "unavailable"}

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


def test_apply_watchlist_thesis_review_refreshes_watchlist_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Watchlist Thesis Plan")
    portfolio = PortfolioStore(tmp_path / "portfolio")
    portfolio.upsert_watchlist_item(
        symbol="NVDA",
        thesis="AI compute thesis.",
        thesis_reference_price_usd=800.0,
        target_price_usd=1200.0,
        tags=["ai"],
    )
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review NVDA thesis after a material price move",
        detail="NVDA moved enough to review the saved thesis.",
        recommendation_type="workflow_action",
        source="generator:watchlist_research",
        plan_id=plan["id"],
        action_payload={
            "suggested_action": {
                "kind": "review_research_thesis",
                "symbol": "NVDA",
                "reason": "material_price_change",
            },
            "evidence": {
                "symbol": "NVDA",
                "current_price_usd": 980.0,
                "reference_price_usd": 800.0,
            },
        },
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "portfolio_store", portfolio)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = asyncio.run(
        main.apply_recommendation_with_decision_packet(
            recommendation["id"],
            main.RecommendationApplyRequest(
                create_decision_packet=False,
                capture_scenario_diff=False,
                pin_research_bridge=False,
                rationale="Thesis still fits after review.",
            ),
        )
    )

    item = portfolio.list_watchlist()[0]
    assert item["symbol"] == "NVDA"
    assert item["thesis_reference_price_usd"] == pytest.approx(980.0)
    assert item["thesis_reviewed_at"]
    assert item["thesis_expires_at"]
    assert item["updated_at"] == item["thesis_reviewed_at"]

    payload = inbox.get(recommendation["id"])["action_payload"]
    thesis_review = payload["thesis_review"]
    assert thesis_review["status"] == "refreshed"
    assert thesis_review["target"] == "watchlist"
    assert thesis_review["symbol"] == "NVDA"
    assert thesis_review["reference_price_usd"] == pytest.approx(980.0)
    assert response.recommendation.status == "applied"


def test_apply_saved_dossier_thesis_review_writes_artifact_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Dossier Thesis Plan")
    artifact = workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - MSFT vs VTI",
        markdown="# Research Dossier: MSFT vs VTI\n\n## Thesis\n\nCompare MSFT against broad-market exposure.\n",
        kind="research_dossier",
    )
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Refresh stale research thesis for MSFT / VTI",
        detail="The saved dossier thesis is past its review window.",
        recommendation_type="workflow_action",
        source="generator:research_thesis_expiration",
        plan_id=plan["id"],
        action_payload={
            "suggested_action": {
                "kind": "review_research_thesis",
                "artifact_id": artifact["id"],
                "plan_id": plan["id"],
                "symbols": ["MSFT", "VTI"],
            },
            "evidence": {
                "artifact_id": artifact["id"],
                "plan_id": plan["id"],
                "symbols": ["MSFT", "VTI"],
                "current_price_usd": 410.0,
            },
        },
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = asyncio.run(
        main.apply_recommendation_with_decision_packet(
            recommendation["id"],
            main.RecommendationApplyRequest(
                create_decision_packet=False,
                capture_scenario_diff=False,
                pin_research_bridge=False,
                rationale="Dossier thesis reviewed.",
            ),
        )
    )

    refreshed_artifact = workspace.read_artifact(plan["id"], artifact["id"])
    assert "## Thesis Review Metadata" in refreshed_artifact["content"]
    assert "- Reviewed at:" in refreshed_artifact["content"]
    assert "- Expires at:" in refreshed_artifact["content"]
    assert "- Reference price USD: `410.0`" in refreshed_artifact["content"]

    lookup = main.build_research_dossier_lookup_payload(
        plan_id=plan["id"],
        limit=5,
        include_content=True,
    )
    assert lookup["items"][0]["thesis_review"]["status"] == "current"
    assert lookup["items"][0]["thesis_review"]["reference_price_usd"] == pytest.approx(410.0)

    payload = inbox.get(recommendation["id"])["action_payload"]
    thesis_review = payload["thesis_review"]
    assert thesis_review["status"] == "refreshed"
    assert thesis_review["target"] == "dossier"
    assert thesis_review["artifact_id"] == artifact["id"]
    assert response.recommendation.status == "applied"


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
    assert response.decision_closure.get("expected_outcome", {}).get("status") in {"captured", "unavailable"}
    assert response.decision_closure.get("expected_vs_realized", {}).get("status") in {"pending_realized", "unavailable"}


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


def test_generated_plan_tracking_contribution_recommendation_previews_and_applies_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Factory Action Plan")
    workspace.update_plan_settings(
        plan["id"],
        {"annual_contribution_usd": 18_000.0, "hsa_extra_contribution_usd": 0.0},
        log_decision=False,
    )
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    factory_result = generate_plan_tracking_recommendations(
        plan_tracking_payload={
            "plan_id": plan["id"],
            "plan_title": "Factory Action Plan",
            "status": "behind",
            "status_detail": "Contribution pace is behind target.",
            "tracking_window_days": 90,
            "window_start": "2026-01-25T12:00:00+00:00",
            "window_end": "2026-04-25T12:00:00+00:00",
            "starting_value_usd": 100_000.0,
            "current_value_usd": 102_000.0,
            "projected_value_usd": 104_000.0,
            "value_drift_usd": -2_000.0,
            "value_drift_pct": -1.92,
            "actual_annualized_return_pct": 4.5,
            "expected_annualized_return_pct": 6.5,
            "return_drift_pct": -2.0,
            "actual_return_method": "snapshot_delta",
            "expected_return_method": "plan_setting",
            "actual_contributions_usd": 1_000.0,
            "expected_contributions_usd": 4_500.0,
            "contribution_pace_pct": 22.2,
            "market_growth_usd": 1_000.0,
            "snapshot_count": 3,
            "plan_settings": {
                "annual_contribution_usd": 18_000.0,
                "hsa_extra_contribution_usd": 0.0,
            },
        },
        existing_recommendations=[],
        dry_run=True,
        limit=1,
    )
    candidate = factory_result.candidates[0]
    proposed_annual_contribution = candidate["action_payload"]["plan_settings_updates"]["annual_contribution_usd"]
    recommendation = inbox.create(
        title=candidate["title"],
        detail=candidate["detail"],
        priority=candidate["priority"],
        recommendation_type=candidate["recommendation_type"],
        source=candidate["source"],
        plan_id=candidate["plan_id"],
        action_payload=candidate["action_payload"],
    )

    async def fake_preview(recommendation_payload: dict[str, object], **kwargs: object) -> dict[str, object]:
        assert recommendation_payload["action_payload"]["plan_settings_updates"] == {
            "annual_contribution_usd": proposed_annual_contribution
        }
        assert kwargs.get("request_updates") == {}
        return {
            "status": "captured",
            "compare_settings": {"annual_contribution_usd": proposed_annual_contribution},
            "scenario_deltas": [{"label": "baseline", "delta_future_value_usd": 1500.0}],
        }

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "build_recommendation_scenario_diff_preview", fake_preview)

    preview = asyncio.run(
        main.preview_recommendation(
            recommendation["id"],
            main.RecommendationPreviewRequest(),
        )
    )

    assert preview.preview["status"] == "captured"
    assert preview.preview["action_preview"]["kind"] == "plan_settings_update"
    assert preview.preview["action_preview"]["proposed_plan_settings_updates"] == {
        "annual_contribution_usd": proposed_annual_contribution
    }

    applied = main.apply_recommendation(
        recommendation["id"],
        main.RecommendationApplyRequest(create_decision_packet=False, capture_scenario_diff=False),
    )

    assert applied.recommendation.status == "applied"
    updated_plan = workspace.get_plan(plan["id"])
    assert updated_plan["settings"]["annual_contribution_usd"] == proposed_annual_contribution
