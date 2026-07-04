"""Due-outcome-review factory: due pre-mortem promises become Inbox entries."""

from datetime import datetime, timezone
from pathlib import Path

from buildwealth_orchestrator.services.recommendation_factory import (
    DUE_OUTCOME_REVIEW_SOURCE,
    generate_due_outcome_review_recommendations,
)
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _applied_recommendation(
    *,
    rec_id: str = "rec-1",
    review_date: str = "2026-06-20T00:00:00+00:00",
    decision_status: str = "accepted",
    measured: bool = False,
    source: str = "generator:portfolio_risk",
) -> dict:
    closure: dict = {
        "decision_status": decision_status,
        "applied_at": "2026-05-01T00:00:00+00:00",
        "pre_mortem": {
            "expected_benefit": "Concentration drops below the cap.",
            "main_risk": "Sold into a rally.",
            "disconfirming_signal": "Top holding still above 30% of portfolio.",
            "monitoring_plan": "Check concentration monthly.",
            "review_date": review_date,
        },
        "expected_vs_realized": {"status": "measured" if measured else "pending_realized"},
    }
    if measured:
        closure["realized_outcome"] = {
            "realized_delta_future_value_usd": 1200.0,
            "observed_at": "2026-06-25T00:00:00+00:00",
        }
    return {
        "id": rec_id,
        "title": "Trim the concentrated position",
        "status": "applied",
        "plan_id": "plan-1",
        "source": source,
        "action_payload": {"decision_closure": closure},
    }


def test_due_review_generates_candidate_with_evidence() -> None:
    result = generate_due_outcome_review_recommendations(
        existing_recommendations=[_applied_recommendation()],
        dry_run=True,
        now=NOW,
    )

    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["source"] == DUE_OUTCOME_REVIEW_SOURCE
    assert candidate["title"] == "Outcome review due: Trim the concentrated position"
    assert candidate["priority"] == "medium"  # 14 days overdue
    assert candidate["plan_id"] == "plan-1"

    payload = candidate["action_payload"]
    assert payload["generator"]["dedupe_key"] == "due_outcome_review:rec-1"
    assert payload["evidence"]["days_overdue"] == 14
    assert payload["evidence"]["disconfirming_signal"] == "Top holding still above 30% of portfolio."
    assert payload["suggested_action"]["kind"] == "capture_decision_outcome"
    assert payload["quality"]["actionability"] == "review_only"
    assert "Disconfirming signal to check" in candidate["detail"]


def test_long_overdue_review_is_high_priority() -> None:
    result = generate_due_outcome_review_recommendations(
        existing_recommendations=[_applied_recommendation(review_date="2026-05-01T00:00:00+00:00")],
        dry_run=True,
        now=NOW,
    )
    assert result.candidates[0]["priority"] == "high"


def test_non_qualifying_closures_generate_nothing() -> None:
    cases = [
        _applied_recommendation(measured=True),
        _applied_recommendation(review_date="2026-09-01T00:00:00+00:00"),
        _applied_recommendation(decision_status="rejected"),
        _applied_recommendation(source=DUE_OUTCOME_REVIEW_SOURCE),
        {"id": "rec-x", "title": "No closure at all", "action_payload": {}},
    ]
    result = generate_due_outcome_review_recommendations(
        existing_recommendations=cases,
        dry_run=True,
        now=NOW,
    )
    assert result.generated_count == 0
    assert result.candidates == []


def test_apply_run_creates_then_dedupes(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    source = _applied_recommendation()

    first = generate_due_outcome_review_recommendations(
        existing_recommendations=[source, *inbox.list(limit=None, include_archived=True, sort="none")],
        creator=inbox,
        dry_run=False,
        now=NOW,
    )
    assert first.generated_count == 1
    assert len(first.created) == 1

    second = generate_due_outcome_review_recommendations(
        existing_recommendations=[source, *inbox.list(limit=None, include_archived=True, sort="none")],
        creator=inbox,
        dry_run=False,
        now=NOW,
    )
    assert second.generated_count == 0
    assert {item["reason"] for item in second.skipped} == {"active_duplicate"}
