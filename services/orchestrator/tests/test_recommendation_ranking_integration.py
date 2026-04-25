from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace


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


def test_recommendation_list_uses_outcome_history_for_calibration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    strong = inbox.create(
        title="Reliable next action",
        detail="Same source has historically matched expected direction.",
        priority="medium",
        recommendation_type="plan_settings_update",
        source="workflow:reliable_review",
    )
    weak = inbox.create(
        title="Noisy next action",
        detail="Same source has historically missed expected direction.",
        priority="medium",
        recommendation_type="plan_settings_update",
        source="workflow:noisy_review",
    )
    for index in range(2):
        created = inbox.create(
            title=f"Reliable measured {index}",
            detail="Measured historical recommendation.",
            priority="medium",
            recommendation_type="plan_settings_update",
            source="workflow:reliable_review",
            action_payload={
                "decision_closure": {
                    "expected_vs_realized": {
                        "status": "measured",
                        "future_value_gap_usd": 500.0,
                        "future_value_direction_match": True,
                    }
                }
            },
        )
        inbox.set_status(created["id"], status="applied")
        created = inbox.create(
            title=f"Noisy measured {index}",
            detail="Measured historical recommendation.",
            priority="medium",
            recommendation_type="plan_settings_update",
            source="workflow:noisy_review",
            action_payload={
                "decision_closure": {
                    "expected_vs_realized": {
                        "status": "measured",
                        "future_value_gap_usd": -500.0,
                        "future_value_direction_match": False,
                    }
                }
            },
        )
        inbox.set_status(created["id"], status="applied")

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    rows = main._recommendation_list(limit=10, status="proposed")
    by_id = {row["id"]: row for row in rows}

    assert rows[0]["id"] == strong["id"]
    assert by_id[strong["id"]]["score"]["calibration"]["confidence_delta"] > 0
    assert by_id[weak["id"]]["score"]["calibration"]["confidence_delta"] < 0


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


def test_build_top_next_actions_scopes_to_plan_and_global(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    target_plan = inbox.create(
        title="Increase annual contributions",
        detail="Raise annual contribution by $4,000.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id="plan-target",
        source="workflow:weekly_review",
    )
    other_plan = inbox.create(
        title="Different plan action",
        detail="Belongs to another plan.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id="plan-other",
        source="workflow:weekly_review",
    )
    global_action = inbox.create(
        title="Global hygiene review",
        detail="Review global assumptions.",
        priority="low",
        recommendation_type="general",
        source="manual-ui",
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    actions = main._build_top_next_actions(plan_id="plan-target", limit=3)

    ids = [item.recommendation_id for item in actions]
    assert target_plan["id"] in ids
    assert global_action["id"] in ids
    assert other_plan["id"] not in ids
    assert ids[0] == target_plan["id"]


def test_get_plan_includes_top_next_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    plan = workspace.create_plan(title="Primary Plan")
    recommendation = inbox.create(
        title="Boost contribution rate",
        detail="Increase annual contribution in plan settings.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id=plan["id"],
        source="workflow:plan_review",
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = main.get_plan(plan["id"])

    assert payload.top_next_actions
    assert payload.top_next_actions[0].recommendation_id == recommendation["id"]
