"""Track progress toward financial goals using current savings capacity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from buildwealth_orchestrator.schemas import (
    GoalItem,
    GoalProgressItem,
    GoalProgressResponse,
)


def _months_between(start: datetime, end: datetime) -> float:
    delta = end - start
    return max(0.0, delta.total_seconds() / (30.44 * 86400))


def _add_months(dt: datetime, months: float) -> datetime:
    total_days = months * 30.44
    from datetime import timedelta
    return dt + timedelta(days=total_days)


def compute_goal_progress(
    *,
    goals: list[GoalItem],
    monthly_surplus_usd: float,
    portfolio_value_usd: float,
    now: datetime | None = None,
) -> GoalProgressResponse:
    now = now or datetime.now(timezone.utc)
    items: list[GoalProgressItem] = []

    # Savings available is the monthly surplus (could be negative)
    savings_available = max(0.0, monthly_surplus_usd)

    for goal in goals:
        target = goal.target_amount_usd
        if target <= 0:
            continue

        # Current savings toward this goal = proportion of portfolio by priority weight
        # Simple heuristic: portfolio value is the savings pool for all goals
        # For single-goal users this is exact; for multi-goal we show total pool
        current_savings = portfolio_value_usd
        progress_pct = min(100.0, (current_savings / target) * 100.0) if target > 0 else 100.0
        remaining = max(0.0, target - current_savings)

        # Already achieved
        if remaining <= 0:
            items.append(GoalProgressItem(
                goal_id=goal.id,
                label=goal.label,
                target_amount_usd=target,
                target_date=goal.target_date,
                priority=goal.priority,
                current_savings_usd=round(current_savings, 2),
                progress_pct=round(progress_pct, 1),
                remaining_usd=0.0,
                monthly_savings_available_usd=round(savings_available, 2),
                months_to_target=0.0,
                estimated_completion_date=now,
                required_monthly_usd=0.0,
                status="achieved",
                status_detail=f"Goal of ${target:,.0f} has been reached.",
            ))
            continue

        # Time to target at current savings rate
        months_to_target: float | None = None
        estimated_completion: datetime | None = None
        if savings_available > 0:
            months_to_target = remaining / savings_available
            estimated_completion = _add_months(now, months_to_target)

        # Required monthly savings if deadline exists
        required_monthly: float | None = None
        months_until_deadline: float | None = None
        status: Literal["on_track", "ahead", "behind", "achieved", "no_deadline"]
        status_detail: str

        if goal.target_date is not None:
            deadline = goal.target_date
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            months_until_deadline = _months_between(now, deadline)

            if months_until_deadline <= 0:
                # Deadline passed
                status = "behind"
                status_detail = f"Deadline has passed. Still ${remaining:,.0f} short of ${target:,.0f} goal."
                required_monthly = None
            else:
                required_monthly = remaining / months_until_deadline

                if savings_available <= 0:
                    status = "behind"
                    status_detail = (
                        f"No monthly surplus available. Need ${required_monthly:,.0f}/month "
                        f"to reach ${target:,.0f} by {goal.target_date.strftime('%Y-%m-%d')}."
                    )
                elif savings_available >= required_monthly:
                    # Can meet the deadline
                    margin = savings_available - required_monthly
                    if margin > required_monthly * 0.2:
                        status = "ahead"
                        status_detail = (
                            f"On pace to reach ${target:,.0f} "
                            f"{(months_until_deadline - (months_to_target or 0)):.0f} months early."
                        )
                    else:
                        status = "on_track"
                        status_detail = (
                            f"Current savings rate covers the ${required_monthly:,.0f}/month needed "
                            f"to reach ${target:,.0f} by {goal.target_date.strftime('%Y-%m-%d')}."
                        )
                else:
                    shortfall = required_monthly - savings_available
                    status = "behind"
                    status_detail = (
                        f"Need ${required_monthly:,.0f}/month but only ${savings_available:,.0f}/month available. "
                        f"Short by ${shortfall:,.0f}/month to meet deadline."
                    )
        else:
            # No deadline
            if savings_available > 0 and months_to_target is not None:
                status = "no_deadline"
                years = months_to_target / 12
                if years < 1:
                    status_detail = f"At current pace, ${target:,.0f} goal reachable in {months_to_target:.0f} months."
                else:
                    status_detail = f"At current pace, ${target:,.0f} goal reachable in {years:.1f} years."
            else:
                status = "no_deadline"
                status_detail = f"${remaining:,.0f} remaining toward ${target:,.0f}. Add savings capacity to project a timeline."

        items.append(GoalProgressItem(
            goal_id=goal.id,
            label=goal.label,
            target_amount_usd=target,
            target_date=goal.target_date,
            priority=goal.priority,
            current_savings_usd=round(current_savings, 2),
            progress_pct=round(progress_pct, 1),
            remaining_usd=round(remaining, 2),
            monthly_savings_available_usd=round(savings_available, 2),
            months_to_target=round(months_to_target, 1) if months_to_target is not None else None,
            estimated_completion_date=estimated_completion,
            required_monthly_usd=round(required_monthly, 2) if required_monthly is not None else None,
            status=status,
            status_detail=status_detail,
        ))

    # Sort by priority (high first), then by remaining amount
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda g: (priority_order.get(g.priority, 1), g.remaining_usd))

    # Summary
    achieved = sum(1 for g in items if g.status == "achieved")
    behind = sum(1 for g in items if g.status == "behind")
    total = len(items)

    if total == 0:
        summary = "No goals configured. Add goals in your financial profile to track progress."
    elif achieved == total:
        summary = f"All {total} goal(s) achieved."
    elif behind > 0:
        summary = f"{behind} of {total} goal(s) behind pace. Review savings allocation or adjust targets."
    else:
        summary = f"Tracking {total} goal(s) — {achieved} achieved, {total - achieved} in progress."

    return GoalProgressResponse(
        generated_at=now,
        monthly_surplus_usd=round(monthly_surplus_usd, 2),
        goal_count=total,
        goals=items,
        summary=summary,
    )
