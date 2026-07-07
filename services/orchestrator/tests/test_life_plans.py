"""The life-plans interview — questions that adapt, drafts that stay honest."""

from __future__ import annotations

from datetime import datetime, timezone

from buildwealth_orchestrator.services.life_plans import (
    build_life_interview,
    build_life_plan_drafts,
)

NOW = datetime(2026, 7, 7, tzinfo=timezone.utc)


def _profile(*, birth_year: int | None = 2004, children: int = 0, goals: list | None = None) -> dict:
    members = []
    if birth_year is not None:
        members.append({"id": "m1", "display_name": "Me", "relationship": "self", "birth_year": birth_year})
    for index in range(children):
        members.append({"id": f"c{index}", "display_name": f"Kid {index}", "relationship": "child"})
    return {"household_members": members, "goal_items": goals or []}


def test_interview_asks_six_questions_with_reasons() -> None:
    payload = build_life_interview(_profile(), monthly_expenses_usd=4_200.0, current_year=2026)
    assert payload["status"] == "ready"
    assert payload["age"] == 22
    ids = [q["id"] for q in payload["questions"]]
    assert ids == ["home", "children", "wedding", "education", "career_break", "big_purchase"]
    # Every question explains what answering changes.
    assert all(q["why"] for q in payload["questions"])
    # The career-break question is priced at the household's own spending.
    career = next(q for q in payload["questions"] if q["id"] == "career_break")
    assert "$4,200" in career["why"]
    # Retirement is deliberately out of scope, and says so.
    assert "Plan timeline" in payload["not_asked"]


def test_interview_respects_goals_already_on_file() -> None:
    goals = [{"id": "goal_1", "label": "House down payment", "target_amount_usd": 60_000}]
    payload = build_life_interview(_profile(goals=goals), current_year=2026)
    home = next(q for q in payload["questions"] if q["id"] == "home")
    assert home["already_covered"] == {"goal_id": "goal_1", "label": "House down payment"}
    wedding = next(q for q in payload["questions"] if q["id"] == "wedding")
    assert wedding["already_covered"] is None


def test_interview_adapts_children_prompt_to_existing_children() -> None:
    payload = build_life_interview(_profile(children=1), current_year=2026)
    children = next(q for q in payload["questions"] if q["id"] == "children")
    assert children["prompt"].startswith("Are more children")


def test_drafts_map_timeframes_to_dates_and_priorities() -> None:
    result = build_life_plan_drafts(
        {
            "home": {"timeframe": "in_3_5y", "amount_usd": 400_000},
            "wedding": {"timeframe": "within_2y"},
            "education": {"timeframe": "someday"},
        },
        now=NOW,
    )
    drafts = {d["category"]: d for d in result["drafts"]}
    # Home: 20% of the stated price, medium priority ~4 years out.
    assert drafts["home"]["target_amount_usd"] == 80_000
    assert drafts["home"]["priority"] == "medium"
    assert drafts["home"]["target_date"].startswith("2030-")
    assert drafts["home"]["target_date"].endswith("-01")
    # Wedding: near-term goals are high priority.
    assert drafts["wedding"]["priority"] == "high"
    assert drafts["wedding"]["target_amount_usd"] == 20_000
    # Someday goals still get written down, at low priority.
    assert drafts["education"]["priority"] == "low"
    # Every draft explains itself and admits it is a starting point.
    assert all(d["sentence"] for d in result["drafts"])
    assert all("starting-point" in d["notes"] for d in result["drafts"])
    assert result["no_plans"] is False


def test_career_break_is_priced_at_household_spending() -> None:
    result = build_life_plan_drafts(
        {"career_break": {"timeframe": "within_2y", "months": 6}},
        monthly_expenses_usd=4_200.0,
        now=NOW,
    )
    draft = result["drafts"][0]
    assert draft["target_amount_usd"] == 25_200
    assert "$4,200/month" in draft["sentence"]


def test_career_break_without_expenses_uses_labeled_placeholder() -> None:
    result = build_life_plan_drafts(
        {"career_break": {"timeframe": "within_2y", "months": 6}},
        monthly_expenses_usd=None,
        now=NOW,
    )
    draft = result["drafts"][0]
    assert draft["target_amount_usd"] == 15_000
    assert "placeholder" in draft["sentence"]


def test_all_not_now_is_an_answer_not_a_failure() -> None:
    result = build_life_plan_drafts(
        {
            "home": {"timeframe": "not_now"},
            "children": {"timeframe": "not_now"},
        },
        now=NOW,
    )
    assert result["drafts"] == []
    assert result["no_plans"] is True
    assert "pause goal nudges" in result["no_plans_hint"]


def test_junk_answers_are_ignored_not_fatal() -> None:
    result = build_life_plan_drafts(
        {
            "home": {"timeframe": "eventually?"},
            "unknown_question": {"timeframe": "within_2y"},
            "wedding": "not-a-dict",
            "children": {"timeframe": "within_2y", "amount_usd": -50},
        },
        now=NOW,
    )
    # Only the valid answer survives; the negative amount falls back to default.
    assert len(result["drafts"]) == 1
    assert result["drafts"][0]["category"] == "children"
    assert result["drafts"][0]["target_amount_usd"] == 18_000
    assert result["no_plans"] is False


def test_drafts_carry_timeline_event_twins() -> None:
    result = build_life_plan_drafts(
        {
            "home": {"timeframe": "in_3_5y", "amount_usd": 400_000},
            "career_break": {"timeframe": "within_2y", "months": 6},
        },
        monthly_expenses_usd=4_000.0,
        now=NOW,
    )
    events = {d["category"]: d["timeline_event"] for d in result["drafts"]}
    # A home is a purchase: the projection engine subtracts it as an expense.
    home = events["home"]
    assert home["event_type"] == "purchase"
    assert "impact_type" not in home  # purchase already defaults to expense
    assert home["amount_usd"] == 80_000
    assert home["date"].endswith("-01")
    assert home["recurring_frequency"] == "one_time"
    # A career break is a milestone with explicit expense impact — job_change
    # would ADD income; the break spends the banked runway instead.
    career = events["career_break"]
    assert career["event_type"] == "milestone"
    assert career["impact_type"] == "expense"
    assert career["amount_usd"] == 24_000
