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


def test_update_recommendation_outcome_records_investment_process_calibration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review NVDA fit",
        detail="Copilot drafted an investment-fit review.",
        recommendation_type="workflow_action",
        source="copilot:investment_fit",
        status="applied",
        action_payload={
            "evidence": {
                "symbol": "NVDA",
                "research_evidence_packet_id": "research-evidence:yfinance:NVDA:6mo:1d",
            },
            "quality": {
                "actionability": "review_only",
                "calibration": {"domain": "investment_research", "track_process_outcome": True},
            },
            "decision_closure": {
                "decision_status": "accepted",
                "expected_outcome": {
                    "expected_delta_context_quality": "research_or_fit_reviewed",
                    "expected_next_safe_action": "review_portfolio_fit",
                },
                "expected_vs_realized": {"status": "unavailable"},
            },
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = main.update_recommendation_outcome(
        recommendation["id"],
        main.RecommendationOutcomeUpdateRequest(
            process_outcome="useful_review",
            evidence_sufficiency="sufficient",
            measurement_source="copilot investment review",
            note="The review clarified concentration risk before acting.",
        ),
    )

    calibration = response.decision_closure.get("decision_process_calibration", {})
    assert calibration["domain"] == "investment_research"
    assert calibration["process_outcome"] == "useful_review"
    assert calibration["evidence_sufficiency"] == "sufficient"
    assert calibration["symbol"] == "NVDA"
    assert calibration["research_evidence_packet_id"] == "research-evidence:yfinance:NVDA:6mo:1d"
    assert response.decision_closure.get("expected_vs_realized", {}).get("status") == "unavailable"

    payload = main.build_recommendation_closure_analytics_payload(
        limit=200,
        statuses=["applied", "rejected"],
        include_pending_realized=True,
    )
    assert payload["process_calibration_summary"]["count"] == 1
    assert payload["process_calibration_summary"]["useful_count"] == 1
    assert payload["process_calibration_by_outcome"][0]["key"] == "useful_review"
    assert payload["items"][0]["process_outcome"] == "useful_review"


def test_update_recommendation_outcome_includes_thesis_revision_calibration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review NVDA thesis",
        detail="Copilot revised a watchlist thesis during the investment-fit review.",
        recommendation_type="workflow_action",
        source="copilot:investment_fit",
        status="applied",
        action_payload={
            "evidence": {
                "symbol": "NVDA",
                "fit_status": "review_needed",
                "research_evidence_packet_id": "research-evidence:yfinance:NVDA:6mo:1d",
            },
            "quality": {
                "actionability": "review_only",
                "calibration": {"domain": "investment_research", "track_process_outcome": True},
            },
            "thesis_revision": {
                "event_id": "thesis-revision:watchlist:abc123",
                "target_type": "watchlist",
                "symbol": "NVDA",
                "source": "copilot_review",
                "reviewed_at": "2026-04-29T12:00:00+00:00",
                "revised_thesis_hash": "abc123def456",
                "evidence_gaps": ["tax lot impact not reviewed"],
                "warnings": ["Review-only; not an action instruction."],
            },
            "decision_closure": {
                "decision_status": "accepted",
                "expected_outcome": {
                    "expected_delta_context_quality": "thesis_revised",
                    "expected_next_safe_action": "review_portfolio_fit",
                },
                "expected_vs_realized": {"status": "unavailable"},
            },
        },
    )
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = main.update_recommendation_outcome(
        recommendation["id"],
        main.RecommendationOutcomeUpdateRequest(
            process_outcome="useful_review",
            evidence_sufficiency="sufficient",
            measurement_source="copilot thesis review",
            note="The revised thesis made the fit concern clearer.",
        ),
    )

    calibration = response.decision_closure["decision_process_calibration"]
    assert calibration["thesis_revision"]["event_id"] == "thesis-revision:watchlist:abc123"
    assert calibration["thesis_revision"]["target_type"] == "watchlist"
    assert calibration["thesis_revision"]["revised_thesis_hash"] == "abc123def456"
    assert calibration["thesis_revision"]["evidence_gaps"] == ["tax lot impact not reviewed"]
    assert calibration["quality_effects"]["decision_clarity"] == "improved"
    assert calibration["quality_effects"]["evidence_sufficiency"] == "sufficient"
    assert calibration["quality_effects"]["blocking_gaps"] == "not_blocking"
    analytics = main.build_recommendation_closure_analytics_payload(
        limit=200,
        statuses=["applied", "rejected"],
        include_pending_realized=True,
    )
    assert analytics["process_calibration_summary"]["thesis_revision_count"] == 1
    assert analytics["process_calibration_summary"]["useful_thesis_revision_count"] == 1
    assert analytics["items"][0]["thesis_revision_event_id"] == "thesis-revision:watchlist:abc123"


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
                "pre_mortem": {
                    "expected_benefit": "Retirement baseline improves.",
                    "main_risk": "Cash runway gets too tight.",
                    "disconfirming_signal": "Savings rate turns negative.",
                    "monitoring_plan": "Review cash runway.",
                    "review_date": "2026-06-30",
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
    assert summary["pre_mortem_count"] == 1
    assert summary["pre_mortem_realized_count"] == 1
    assert summary["pre_mortem_pending_count"] == 0
    assert summary["measured_count"] == 2
    assert summary["pending_realized_count"] == 1
    assert summary["future_value_gap_total_usd"] == 250.0
    assert summary["future_value_direction_match_rate_pct"] == 50.0
    assert payload["calibration_model_version"] == "calibration_v1"
    assert payload["pre_mortem_summary"] == {
        "count": 1,
        "realized_count": 1,
        "pending_count": 0,
        "coverage_pct": 33.33,
        "realized_coverage_pct": 100.0,
    }

    calibration_summary = payload["calibration_summary"]
    assert calibration_summary["count"] == 3
    assert calibration_summary["pre_mortem_count"] == 1
    assert calibration_summary["pre_mortem_realized_count"] == 1
    assert calibration_summary["measured_count"] == 2
    assert calibration_summary["future_value_direction_match_rate_pct"] == 50.0
    assert calibration_summary["mean_future_value_abs_error_usd"] == 325.0
    assert calibration_summary["future_value_bias"] == "underestimated"

    by_type = {row["key"]: row for row in payload["calibration_by_type"]}
    assert by_type["plan_settings_update"]["future_value_direction_match_rate_pct"] == 100.0
    assert by_type["workflow_action"]["future_value_direction_match_rate_pct"] == 0.0
    assert by_type["general"]["pending_realized_count"] == 1
    assert by_type["general"]["measured_count"] == 0

    by_source = {row["key"]: row for row in payload["calibration_by_source"]}
    assert by_source["copilot"]["measured_count"] == 2
    assert by_source["workflow:daily_review"]["pending_realized_count"] == 1

    windows = {row["window"]: row for row in payload["calibration_windows"]}
    assert windows["all"]["count"] == 3
    assert windows["all"]["measured_count"] == 2

    measured_only = main.build_recommendation_closure_analytics_payload(
        limit=200,
        statuses=["applied", "rejected"],
        include_pending_realized=False,
    )
    assert measured_only["count"] == 2


def test_build_recommendation_closure_analytics_payload_filters_by_plan_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    inbox.create(
        title="Plan A Action",
        detail="Measured in plan A.",
        recommendation_type="plan_settings_update",
        source="copilot",
        plan_id="plan-a",
        status="applied",
        action_payload={
            "decision_closure": {
                "expected_outcome": {"expected_delta_future_value_usd": 1000.0},
                "realized_outcome": {"realized_delta_future_value_usd": 900.0},
                "expected_vs_realized": {"status": "measured", "future_value_gap_usd": -100.0},
            }
        },
    )
    inbox.create(
        title="Plan B Action",
        detail="Measured in plan B.",
        recommendation_type="general",
        source="manual-ui",
        plan_id="plan-b",
        status="rejected",
        action_payload={
            "decision_closure": {
                "expected_outcome": {"expected_delta_future_value_usd": -300.0},
                "realized_outcome": {"realized_delta_future_value_usd": -250.0},
                "expected_vs_realized": {"status": "measured", "future_value_gap_usd": 50.0},
            }
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    payload = main.build_recommendation_closure_analytics_payload(
        limit=200,
        statuses=["applied", "rejected"],
        include_pending_realized=True,
        plan_id="plan-a",
    )

    assert payload["plan_id"] == "plan-a"
    assert payload["count"] == 1
    assert payload["items"][0]["title"] == "Plan A Action"


def test_create_plan_recommendation_closure_summary_writes_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Closure Summary Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    inbox.create(
        title="Measured Applied",
        detail="Measured recommendation for plan closure summary.",
        recommendation_type="plan_settings_update",
        source="copilot",
        plan_id=plan["id"],
        status="applied",
        action_payload={
            "decision_closure": {
                "expected_outcome": {"expected_delta_future_value_usd": 1200.0},
                "realized_outcome": {"realized_delta_future_value_usd": 900.0},
                "expected_vs_realized": {
                    "status": "measured",
                    "future_value_gap_usd": -300.0,
                    "future_value_direction_match": True,
                },
            }
        },
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = main.create_plan_recommendation_closure_summary(
        plan_id=plan["id"],
        request=main.PlanRecommendationClosureSummaryRequest(
            limit=200,
            statuses=["applied", "rejected"],
            include_pending_realized=True,
            write_artifact=True,
        ),
    )

    assert response.plan_id == plan["id"]
    assert response.analytics.plan_id == plan["id"]
    assert response.analytics.count == 1
    assert response.artifact is not None
    assert response.decision_summary.startswith("Generated recommendation closure analytics summary")

    artifact = workspace.read_artifact(plan["id"], response.artifact.id)
    assert "Recommendation Closure Analytics" in artifact["title"]
    assert "Calibration by Type" in artifact["content"]

    refreshed_plan = workspace.get_plan(plan["id"])
    assert any(
        str(decision.get("summary") or "").startswith("Generated recommendation closure analytics summary")
        for decision in refreshed_plan.get("decisions", [])
    )
