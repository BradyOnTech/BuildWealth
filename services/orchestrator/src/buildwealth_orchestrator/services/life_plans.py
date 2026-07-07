"""The life-plans interview: a few questions about the next chapter of life,
answered in plain words, returned as *draft* dated goals for the household to
review and edit before anything is saved.

Why this exists: the deployment engine treats dated goals inside a few years
as cash to protect, not money to invest. Most people never write those goals
down — not because they have none, but because nothing ever asked. The
interview asks, once, in normal-person language, and every answer explains
what it changes.

Doctrine carried through:
- Drafts, never writes. The service computes; the human applies.
- Defaults are labeled starting points, personalized from the household's own
  numbers where possible (a career break is priced at *their* spending).
- "No plans right now" is a first-class answer, not a nag loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from buildwealth_orchestrator.services.peer_benchmark import _age_from_profile

# Timeframe → (months out, priority). Dates land on the first of the month:
# the month is an honest guess, a precise day would be a fake one.
TIMEFRAMES: dict[str, dict[str, Any]] = {
    "within_2y": {"label": "In the next two years", "months_out": 18, "priority": "high"},
    "in_3_5y": {"label": "In three to five years", "months_out": 48, "priority": "medium"},
    "someday": {"label": "Someday — five-plus years", "months_out": 84, "priority": "low"},
    "not_now": {"label": "Not in the plan", "months_out": None, "priority": None},
}

DOWN_PAYMENT_RATE = 0.20
DEFAULT_HOME_PRICE_USD = 350_000.0
DEFAULT_CHILD_FIRST_YEAR_USD = 18_000.0
DEFAULT_WEDDING_USD = 20_000.0
DEFAULT_EDUCATION_USD = 15_000.0
INCOME_STEP_DOWN_CUSHION_MONTHS = 6
DEFAULT_MONTHLY_INCOME_DROP_USD = 2_000.0
DEFAULT_BIG_PURCHASE_USD = 12_000.0

# Words that mean "this chapter is already written down" per category.
_COVERED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "home": ("home", "house", "down payment", "condo", "apartment"),
    "children": ("child", "kid", "baby"),
    "wedding": ("wedding", "engagement"),
    "education": ("college", "tuition", "school", "education", "degree"),
    "income_change": ("stay at home", "part-time", "sabbatical", "career", "income step"),
    "big_purchase": ("car", "vehicle", "travel", "trip", "relocation", "moving"),
}

DRAFT_NOTES = "From the life-plans interview — starting-point estimate; edit to fit."

# Category → (event_type, explicit impact_type or None for the type's default).
# These are simulation-real semantics, not decoration: the projection engine
# treats "expense" amounts as money leaving in that year, so a home answer
# becomes a modeled outflow the trajectory fan can actually show.
_TIMELINE_EVENT_BY_CATEGORY: dict[str, tuple[str, str | None]] = {
    "home": ("purchase", None),          # purchase defaults to expense
    "wedding": ("purchase", None),
    "education": ("purchase", None),
    "big_purchase": ("purchase", None),
    "children": ("milestone", "expense"),
}


def timeline_event_for_draft(draft: dict[str, Any]) -> dict[str, Any] | None:
    """The Plan-timeline twin of a draft goal: same date, typed so projections
    move the money the way the event actually moves it. One-time drafts spend
    their dollars in the target year; an income step-down bends income monthly
    from the date onward (negative amount, no end — a stay-at-home transition
    is a new normal, not a blip; delete or end-date the event if it isn't)."""
    category = str(draft.get("category") or "")
    if category == "income_change":
        monthly_drop = draft.get("monthly_income_drop_usd")
        if not monthly_drop or not draft.get("target_date"):
            return None
        return {
            "date": draft.get("target_date"),
            "label": draft.get("label"),
            "event_type": "job_change",
            "impact_type": "income",
            "amount_usd": -abs(float(monthly_drop)),
            "recurring_frequency": "monthly",
            "notes": DRAFT_NOTES,
        }
    event_type, impact_type = _TIMELINE_EVENT_BY_CATEGORY.get(category, ("milestone", None))
    event: dict[str, Any] = {
        "date": draft.get("target_date"),
        "label": draft.get("label"),
        "event_type": event_type,
        "amount_usd": draft.get("target_amount_usd"),
        "recurring_frequency": "one_time",
        "notes": DRAFT_NOTES,
    }
    if impact_type:
        event["impact_type"] = impact_type
    return event if event["date"] and event["label"] else None


def _existing_goal_for(category: str, goal_items: list[Any]) -> dict[str, Any] | None:
    keywords = _COVERED_KEYWORDS.get(category, ())
    for goal in goal_items:
        if not isinstance(goal, dict):
            continue
        haystack = f"{goal.get('label') or ''} {goal.get('notes') or ''}".lower()
        if any(keyword in haystack for keyword in keywords):
            return {"goal_id": str(goal.get("id") or ""), "label": str(goal.get("label") or "")}
    return None


def _default_income_drop(monthly_expenses_usd: float | None) -> float:
    if monthly_expenses_usd and monthly_expenses_usd > 0:
        return float(max(500, round(monthly_expenses_usd / 2, -2)))
    return DEFAULT_MONTHLY_INCOME_DROP_USD


def build_life_interview(
    profile_payload: dict[str, Any],
    *,
    monthly_expenses_usd: float | None = None,
    current_year: int,
) -> dict[str, Any]:
    """The question set, tuned to what the household already told us."""
    goal_items = profile_payload.get("goal_items")
    goal_items = goal_items if isinstance(goal_items, list) else []
    members = profile_payload.get("household_members")
    members = members if isinstance(members, list) else []
    age = _age_from_profile(profile_payload, current_year=current_year)
    has_children = any(
        isinstance(m, dict) and str(m.get("relationship") or "") == "child" for m in members
    )

    questions = [
        {
            "id": "home",
            "prompt": "Do you see yourself buying a home — or your next home?",
            "why": "A down payment due inside a few years is cash to protect, not money to invest.",
            "amount_label": "Rough home price",
            "amount_default_usd": DEFAULT_HOME_PRICE_USD,
            "amount_hint": "A rough guess is fine — the date matters more than the number."
            if (age or 99) < 30
            else "Whatever feels realistic for your market.",
        },
        {
            "id": "children",
            "prompt": "Are more children part of the plan?"
            if has_children
            else "Are children part of the plan?",
            "why": "First-year costs land early and all at once; a dated buffer keeps them off the credit card.",
            "amount_label": "First-year buffer",
            "amount_default_usd": DEFAULT_CHILD_FIRST_YEAR_USD,
            "amount_hint": "A common first-year starting point — every family's number differs.",
        },
        {
            "id": "wedding",
            "prompt": "Is a wedding on the horizon — yours or one you'd fund?",
            "why": "Weddings are famous for being paid for twice: once in cash, once in interest.",
            "amount_label": "Rough budget",
            "amount_default_usd": DEFAULT_WEDDING_USD,
            "amount_hint": "Starting point — celebrations scale to taste.",
        },
        {
            "id": "education",
            "prompt": "Any schooling ahead — for you or someone in the household?",
            "why": "Tuition has a date printed on it, which makes it the easiest goal to plan for.",
            "amount_label": "Rough cost",
            "amount_default_usd": DEFAULT_EDUCATION_USD,
            "amount_hint": "A certificate and a degree are different animals — edit freely.",
        },
        {
            "id": "income_change",
            "prompt": (
                "Will household income step down for a stretch — a parent staying home "
                "with kids, going part-time, or taking work you want more that pays less?"
            ),
            "why": (
                "The plan should see income bend before it happens; a cushion banked "
                "first makes the step-down calm instead of tight."
            ),
            "amount_label": "Monthly income drop",
            "amount_default_usd": _default_income_drop(monthly_expenses_usd),
            "amount_hint": "Roughly how much less per month. Raises need no cushion — record those on the Plan timeline.",
        },
        {
            "id": "big_purchase",
            "prompt": "Anything else big — a car, a move, a trip that matters?",
            "why": "Named money gets saved; vague money gets spent.",
            "amount_label": "Rough cost",
            "amount_default_usd": DEFAULT_BIG_PURCHASE_USD,
            "amount_hint": "Give it a name and a number and it becomes real.",
        },
    ]
    for question in questions:
        question["already_covered"] = _existing_goal_for(str(question["id"]), goal_items)

    return {
        "status": "ready",
        "age": age,
        "monthly_expenses_usd": round(monthly_expenses_usd, 2) if monthly_expenses_usd else None,
        "timeframes": [
            {"id": key, "label": value["label"]} for key, value in TIMEFRAMES.items()
        ],
        "questions": questions,
        "not_asked": (
            "Retirement is deliberately absent — it lives on the Plan timeline. "
            "This interview is about the nearer chapters."
        ),
    }


def _target_date(now: datetime, months_out: int) -> str:
    landed = now + timedelta(days=months_out * 30.44)
    return landed.strftime("%Y-%m-01")


def _amount(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def build_life_plan_drafts(
    answers: dict[str, Any],
    *,
    monthly_expenses_usd: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Answers → draft goals. Pure computation; the caller renders a review."""
    now = now or datetime.now(timezone.utc)
    drafts: list[dict[str, Any]] = []
    declined = 0
    considered = 0

    for question_id, answer in (answers or {}).items():
        if not isinstance(answer, dict):
            continue
        timeframe = TIMEFRAMES.get(str(answer.get("timeframe") or ""))
        if timeframe is None:
            continue
        considered += 1
        if timeframe["months_out"] is None:
            declined += 1
            continue
        draft = _draft_for(str(question_id), answer, monthly_expenses_usd)
        if draft is None:
            considered -= 1
            continue
        draft["target_date"] = _target_date(now, timeframe["months_out"])
        draft["priority"] = timeframe["priority"]
        draft["notes"] = DRAFT_NOTES
        draft["target_amount_usd"] = round(draft["target_amount_usd"])
        draft["timeline_event"] = timeline_event_for_draft(draft)
        drafts.append(draft)

    # Every chapter answered "not now": that is an answer, not a failure.
    no_plans = considered > 0 and declined == considered
    return {
        "status": "ready",
        "drafts": drafts,
        "no_plans": no_plans,
        "no_plans_hint": (
            "No plans on the horizon is a real answer. You can pause goal nudges — "
            "the Almanac will stop asking until something changes."
        )
        if no_plans
        else None,
    }


def _draft_for(
    question_id: str, answer: dict[str, Any], monthly_expenses_usd: float | None
) -> dict[str, Any] | None:
    if question_id == "home":
        price = _amount(answer.get("amount_usd"), DEFAULT_HOME_PRICE_USD)
        target = price * DOWN_PAYMENT_RATE
        return {
            "category": "home",
            "label": "Home down payment",
            "target_amount_usd": target,
            "sentence": (
                f"A {DOWN_PAYMENT_RATE:.0%} down payment on a ${price:,.0f} home is "
                f"${target:,.0f}. Dated, it counts as money to hold in cash — "
                "the Almanac won't suggest investing it."
            ),
        }
    if question_id == "children":
        target = _amount(answer.get("amount_usd"), DEFAULT_CHILD_FIRST_YEAR_USD)
        return {
            "category": "children",
            "label": "First year with a child",
            "target_amount_usd": target,
            "sentence": (
                f"A ${target:,.0f} first-year buffer keeps the earliest costs off "
                "the credit card. Starting point — every family's number differs."
            ),
        }
    if question_id == "wedding":
        target = _amount(answer.get("amount_usd"), DEFAULT_WEDDING_USD)
        return {
            "category": "wedding",
            "label": "Wedding",
            "target_amount_usd": target,
            "sentence": f"${target:,.0f} set aside in cash means the celebration is paid for once.",
        }
    if question_id == "education":
        target = _amount(answer.get("amount_usd"), DEFAULT_EDUCATION_USD)
        return {
            "category": "education",
            "label": "Education",
            "target_amount_usd": target,
            "sentence": f"${target:,.0f} toward tuition, dated to when the first bill would arrive.",
        }
    if question_id == "income_change":
        monthly_drop = _amount(answer.get("amount_usd"), _default_income_drop(monthly_expenses_usd))
        target = INCOME_STEP_DOWN_CUSHION_MONTHS * monthly_drop
        return {
            "category": "income_change",
            "label": "Income step-down cushion",
            "target_amount_usd": target,
            "monthly_income_drop_usd": round(monthly_drop),
            "sentence": (
                f"Six months of the ${monthly_drop:,.0f}/month step-down banked first "
                f"(${target:,.0f}) — and the plan models income bending from that date on, "
                "so the trajectory tells the truth about the new normal."
            ),
        }
    if question_id == "big_purchase":
        target = _amount(answer.get("amount_usd"), DEFAULT_BIG_PURCHASE_USD)
        label = str(answer.get("label") or "").strip() or "Big purchase"
        return {
            "category": "big_purchase",
            "label": label,
            "target_amount_usd": target,
            "sentence": f"${target:,.0f} for “{label}” — named money gets saved; vague money gets spent.",
        }
    return None
