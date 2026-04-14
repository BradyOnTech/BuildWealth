from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_update_recommendation_outcome_records_realized_metrics_and_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Outcome Tracking Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Increase annual contributions",
        detail="Apply contribution increase and track outcome.",
        priority="high",
        recommendation_type="plan_settings_update",
        source="copilot",
        plan_id=plan["id"],
        status="applied",
        action_payload={
            "decision_closure": {
                "decision_status": "accepted",
                "applied_at": "2026-04-14T00:00:00+00:00",
                "expected_outcome": {
                    "status": "captured",
                    "expected_delta_future_value_usd": 1000.0,
                    "expected_delta_real_value_usd": 700.0,
                },
                "expected_vs_realized": {
                    "status": "pending_realized",
                },
            }
        },
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = main.update_recommendation_outcome(
        recommendation["id"],
        main.RecommendationOutcomeUpdateRequest(
            plan_id=plan["id"],
            realized_delta_future_value_usd=1350.0,
            realized_delta_real_value_usd=900.0,
            observation_window_days=45,
            measurement_source="manual-review",
            note="Outcome exceeded baseline expectation.",
        ),
    )

    assert response.recommendation.status == "applied"
    assert response.decision_closure_artifact is not None
    assert response.decision_closure.get("expected_vs_realized", {}).get("status") == "measured"
    assert response.decision_closure.get("expected_vs_realized", {}).get("future_value_gap_usd") == 350.0
    assert response.decision_closure.get("expected_vs_realized", {}).get("real_value_gap_usd") == 200.0

    updated = inbox.get(recommendation["id"])
    closure = updated["action_payload"]["decision_closure"]
    assert closure["realized_outcome"]["realized_delta_future_value_usd"] == 1350.0
    assert closure["realized_outcome"]["measurement_source"] == "manual-review"


def test_build_recommendation_closure_analytics_payload_summarizes_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    inbox.create(
        title="Measured Applied",
        detail="Measured outcome.",
        recommendation_type="plan_settings_update",
        source="copilot",
        status="applied",
        action_payload={
            "decision_closure": {
                "decision_status": "accepted",
                "expected_outcome": {
                    "expected_delta_future_value_usd": 1000.0,
                    "expected_delta_real_value_usd": 700.0,
                },
                "realized_outcome": {
                    "realized_delta_future_value_usd": 800.0,
                    "realized_delta_real_value_usd": 650.0,
                },
                "expected_vs_realized": {
                    "status": "measured",
                    "future_value_gap_usd": -200.0,
                    "real_value_gap_usd": -50.0,
                    "future_value_direction_match": True,
                },
            }
        },
    )
    inbox.create(
        title="Pending Rejected",
        detail="Pending realized capture.",
        recommendation_type="general",
        source="workflow:daily_review",
        status="rejected",
        action_payload={
            "decision_closure": {
                "decision_status": "rejected",
                "expected_outcome": {
                    "expected_delta_future_value_usd": -500.0,
                },
                "expected_vs_realized": {
                    "status": "pending_realized",
                },
            }
        },
    )
    inbox.create(
        title="Measured Rejected",
        detail="Measured but direction mismatch.",
        recommendation_type="workflow_action",
        source="copilot",
        status="rejected",
        action_payload={
            "decision_closure": {
                "decision_status": "rejected",
                "expected_outcome": {
                    "expected_delta_future_value_usd": -300.0,
                },
                "realized_outcome": {
                    "realized_delta_future_value_usd": 150.0,
                },
                "expected_vs_realized": {
                    "status": "measured",
                    "future_value_gap_usd": 450.0,
                    "future_value_direction_match": False,
                },
            }
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = main.build_recommendation_closure_analytics_payload(
        limit=200,
        statuses=["applied", "rejected"],
        include_pending_realized=True,
    )

    assert payload["count"] == 3
    summary = payload["summary"]
    assert summary["with_expected_count"] == 3
    assert summary["with_realized_count"] == 2
    assert summary["measured_count"] == 2
    assert summary["pending_realized_count"] == 1
    assert summary["future_value_gap_total_usd"] == 250.0
    assert summary["future_value_direction_match_rate_pct"] == 50.0

    measured_only = main.build_recommendation_closure_analytics_payload(
        limit=200,
        statuses=["applied", "rejected"],
        include_pending_realized=False,
    )
    assert measured_only["count"] == 2
