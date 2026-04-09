from datetime import datetime, timedelta, timezone

import pytest

from buildwealth_orchestrator.schemas import GoalItem
from buildwealth_orchestrator.services.goal_tracker import compute_goal_progress

NOW = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)


def _goal(label="House Down Payment", target=80000, months_away=None, priority="high"):
    target_date = None
    if months_away is not None:
        target_date = NOW + timedelta(days=int(months_away * 30.44))
    return GoalItem(id=f"g-{label[:4].lower()}", label=label, target_amount_usd=target, target_date=target_date, priority=priority)


def _progress(goals, surplus=3000, portfolio=50000):
    return compute_goal_progress(goals=goals, monthly_surplus_usd=surplus, portfolio_value_usd=portfolio, now=NOW)


class TestAchievedGoal:
    def test_goal_already_met(self):
        r = _progress([_goal(target=40000)], portfolio=50000)
        assert r.goals[0].status == "achieved"
        assert r.goals[0].progress_pct == 100.0
        assert r.goals[0].remaining_usd == 0

    def test_exactly_met(self):
        r = _progress([_goal(target=50000)], portfolio=50000)
        assert r.goals[0].status == "achieved"


class TestOnTrack:
    def test_on_track_with_deadline(self):
        # Need 30k more, deadline in 12 months, surplus = 3000/month → need 2500/month
        r = _progress([_goal(target=80000, months_away=12)], surplus=3000, portfolio=50000)
        g = r.goals[0]
        assert g.status in ("on_track", "ahead")
        assert g.required_monthly_usd is not None
        assert g.required_monthly_usd == pytest.approx(30000 / 12, abs=100)

    def test_ahead_of_schedule(self):
        # Need 10k more, deadline in 12 months, surplus = 3000/month → way ahead
        r = _progress([_goal(target=60000, months_away=12)], surplus=3000, portfolio=50000)
        assert r.goals[0].status == "ahead"


class TestBehind:
    def test_behind_insufficient_savings(self):
        # Need 70k more, deadline in 6 months, surplus = 3000/month → need ~11.7k/month
        r = _progress([_goal(target=120000, months_away=6)], surplus=3000, portfolio=50000)
        g = r.goals[0]
        assert g.status == "behind"
        assert "short" in g.status_detail.lower() or "need" in g.status_detail.lower()

    def test_behind_deadline_passed(self):
        r = _progress([_goal(target=80000, months_away=-2)], surplus=3000, portfolio=50000)
        assert r.goals[0].status == "behind"
        assert "passed" in r.goals[0].status_detail.lower()

    def test_behind_no_surplus(self):
        r = _progress([_goal(target=80000, months_away=12)], surplus=0, portfolio=50000)
        assert r.goals[0].status == "behind"


class TestNoDeadline:
    def test_no_deadline_with_surplus(self):
        # 30k remaining, 3000/month → 10 months
        r = _progress([_goal(target=80000)], surplus=3000, portfolio=50000)
        g = r.goals[0]
        assert g.status == "no_deadline"
        assert g.months_to_target == pytest.approx(10, abs=0.5)

    def test_no_deadline_no_surplus(self):
        r = _progress([_goal(target=80000)], surplus=0, portfolio=50000)
        assert r.goals[0].status == "no_deadline"
        assert r.goals[0].months_to_target is None


class TestGoalSeeking:
    def test_required_monthly_calculated(self):
        # 50k remaining, 24 months → need ~2083/month
        r = _progress([_goal(target=100000, months_away=24)], surplus=3000, portfolio=50000)
        g = r.goals[0]
        assert g.required_monthly_usd is not None
        assert g.required_monthly_usd == pytest.approx(50000 / 24, abs=100)

    def test_required_monthly_none_when_no_deadline(self):
        r = _progress([_goal(target=100000)])
        assert r.goals[0].required_monthly_usd is None


class TestMultipleGoals:
    def test_priority_ordering(self):
        goals = [
            _goal("Vacation", target=5000, priority="low"),
            _goal("Emergency Fund", target=20000, priority="high"),
            _goal("Car", target=30000, priority="medium"),
        ]
        r = _progress(goals, portfolio=10000)
        assert r.goals[0].priority == "high"
        assert r.goals[1].priority == "medium"
        assert r.goals[2].priority == "low"

    def test_goal_count(self):
        goals = [_goal("A", target=10000), _goal("B", target=20000)]
        r = _progress(goals)
        assert r.goal_count == 2


class TestSummary:
    def test_no_goals(self):
        r = _progress([])
        assert "no goals" in r.summary.lower()

    def test_all_achieved(self):
        r = _progress([_goal(target=10000), _goal(target=20000)], portfolio=50000)
        assert "achieved" in r.summary.lower()

    def test_behind_summary(self):
        r = _progress([_goal(target=200000, months_away=3)], surplus=1000, portfolio=50000)
        assert "behind" in r.summary.lower()


class TestProgressPct:
    def test_partial_progress(self):
        r = _progress([_goal(target=100000)], portfolio=25000)
        assert r.goals[0].progress_pct == 25.0

    def test_over_100_capped(self):
        r = _progress([_goal(target=10000)], portfolio=50000)
        assert r.goals[0].progress_pct == 100.0


class TestEdgeCases:
    def test_zero_target_skipped(self):
        r = _progress([GoalItem(id="g1", label="Nothing", target_amount_usd=0)])
        assert r.goal_count == 0

    def test_negative_surplus(self):
        r = _progress([_goal(target=80000, months_away=12)], surplus=-500, portfolio=50000)
        g = r.goals[0]
        assert g.monthly_savings_available_usd == 0
        assert g.status == "behind"
