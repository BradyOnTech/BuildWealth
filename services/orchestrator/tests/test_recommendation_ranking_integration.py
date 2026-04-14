from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_recommendation_list_defaults_to_ranked_sort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    high = inbox.create(
        title="Increase annual contributions",
        detail="Boost annual contributions by $5,000.",
        priority="high",
        recommendation_type="plan_settings_update",
        source="workflow:plan_review",
        action_payload={"plan_settings_updates": {"annual_contribution_usd": 25000.0}},
    )
    low = inbox.create(
        title="Review checklist",
        detail="Read the checklist later.",
        priority="low",
        recommendation_type="general",
        source="manual-ui",
    )
    assert high["id"] != low["id"]

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    rows = main._recommendation_list(limit=10, status="proposed")

    assert rows[0]["id"] == high["id"]
    assert rows[0]["score"]["rank"] == 1
    assert rows[1]["id"] == low["id"]
    assert rows[1]["score"]["rank"] == 2


def test_recommendation_list_supports_created_at_sort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    older = inbox.create(
        title="Older recommendation",
        detail="Created first.",
        priority="high",
    )
    newer = inbox.create(
        title="Newer recommendation",
        detail="Created second.",
        priority="low",
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    rows = main._recommendation_list(limit=10, status="proposed", sort="created_at")

    assert rows[0]["id"] == newer["id"]
    assert rows[1]["id"] == older["id"]
    assert rows[0]["score"]["rank"] is None


def test_create_recommendation_route_includes_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = main.RecommendationCreateRequest(
        title="Increase emergency fund",
        detail="Increase monthly savings transfer to emergency account.",
        priority="medium",
        recommendation_type="plan_settings_update",
        source="manual-ui",
    )
    item = main.create_recommendation(payload)

    assert item.score is not None
    assert item.score.total > 0
    assert item.score.impact > 0
