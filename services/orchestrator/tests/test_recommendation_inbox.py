from pathlib import Path

import pytest

from buildwealth_orchestrator.services.recommendation_inbox import (
    RecommendationInbox,
    RecommendationNotFoundError,
)


def test_recommendation_inbox_create_and_filter(tmp_path: Path) -> None:
    store = RecommendationInbox(tmp_path / "recommendations.json")

    first = store.create(
        title="Review concentrated position",
        detail="Top holding exceeds target allocation.",
        priority="high",
    )
    second = store.create(
        title="Increase HSA contributions",
        detail="Potential tax advantage this year.",
        priority="medium",
        plan_id="plan-2026",
    )

    proposed = store.list(status="proposed")
    assert len(proposed) == 2
    assert {row["id"] for row in proposed} == {first["id"], second["id"]}

    plan_specific = store.list(status="proposed", plan_id="plan-2026")
    assert len(plan_specific) == 1
    assert plan_specific[0]["id"] == second["id"]

    store.set_status(first["id"], status="archived", resolution_note="Handled elsewhere")
    non_archived = store.list()
    assert all(row["id"] != first["id"] for row in non_archived)

    with_archived = store.list(include_archived=True)
    assert any(row["id"] == first["id"] for row in with_archived)


def test_recommendation_inbox_update_and_status_flow(tmp_path: Path) -> None:
    store = RecommendationInbox(tmp_path / "recommendations.json")
    created = store.create(
        title="Initial title",
        detail="Initial detail",
    )

    updated = store.update(
        created["id"],
        updates={
            "title": "Updated title",
            "detail": "Updated detail",
            "priority": "low",
            "recommendation_type": "workflow_action",
            "source": "workflow:risk_concentration_review",
            "plan_id": "plan-a",
            "action_payload": {"workflow_id": "weekly_change_summary"},
        },
    )
    assert updated["title"] == "Updated title"
    assert updated["detail"] == "Updated detail"
    assert updated["priority"] == "low"
    assert updated["recommendation_type"] == "workflow_action"
    assert updated["source"] == "workflow:risk_concentration_review"
    assert updated["plan_id"] == "plan-a"
    assert updated["action_payload"] == {"workflow_id": "weekly_change_summary"}

    applied = store.set_status(created["id"], status="applied", resolution_note="Applied in plan review")
    assert applied["status"] == "applied"
    assert applied["resolution_note"] == "Applied in plan review"
    assert applied["resolved_at"] is not None

    reopened = store.set_status(created["id"], status="proposed")
    assert reopened["status"] == "proposed"
    assert reopened["resolved_at"] is None

    with pytest.raises(RecommendationNotFoundError):
        store.get("missing-recommendation")


def test_recommendation_inbox_list_sort_controls(tmp_path: Path) -> None:
    store = RecommendationInbox(tmp_path / "recommendations.json")
    first = store.create(
        title="First recommendation",
        detail="Created first.",
    )
    second = store.create(
        title="Second recommendation",
        detail="Created second.",
    )

    newest_first = store.list(include_archived=True, sort="created_at_desc")
    assert newest_first[0]["id"] == second["id"]

    oldest_first = store.list(include_archived=True, sort="created_at_asc")
    assert oldest_first[0]["id"] == first["id"]

    unsorted = store.list(limit=None, include_archived=True, sort="none")
    assert [row["id"] for row in unsorted] == [first["id"], second["id"]]
