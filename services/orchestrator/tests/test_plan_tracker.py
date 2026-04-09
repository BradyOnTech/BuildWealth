from datetime import datetime, timedelta, timezone

import pytest

from buildwealth_orchestrator.schemas import (
    PlanSettings,
    PlanTrackingResponse,
    PortfolioSnapshot,
)
from buildwealth_orchestrator.services.plan_tracker import compute_plan_tracking

NOW = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)

DEFAULTS = {
    "annual_contribution_usd": 18000.0,
    "expected_return_baseline": 0.065,
    "hsa_extra_contribution_usd": 1000.0,
}


def _snap(days_ago: int, total_value: float, total_investment: float) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=NOW - timedelta(days=days_ago),
        total_value_usd=total_value,
        total_investment_usd=total_investment,
        net_performance_usd=total_value - total_investment,
        net_performance_percent=((total_value - total_investment) / total_investment * 100) if total_investment else 0,
    )


def _track(settings: PlanSettings | None = None, snapshots: list[PortfolioSnapshot] | None = None) -> PlanTrackingResponse:
    return compute_plan_tracking(
        plan_id="plan-1",
        plan_title="Test Plan",
        plan_settings=settings or PlanSettings(),
        planner_defaults=DEFAULTS,
        snapshots=snapshots or [],
    )


class TestInsufficientData:
    def test_no_snapshots(self):
        result = _track(snapshots=[])
        assert result.status == "insufficient_data"
        assert result.snapshot_count == 0

    def test_one_snapshot(self):
        result = _track(snapshots=[_snap(0, 100000, 80000)])
        assert result.status == "insufficient_data"
        assert result.snapshot_count == 1
        assert result.current_value_usd == 100000

    def test_short_window(self):
        snaps = [_snap(0, 101000, 80500), _snap(3, 100000, 80000)]
        result = _track(snapshots=snaps)
        assert result.status == "insufficient_data"
        assert result.tracking_window_days == 3


class TestReturnComparison:
    def test_on_track_returns(self):
        """Portfolio grew roughly at the expected rate."""
        # 90 days, 6.5% annual = ~1.57% for the period
        start_val = 100000
        expected_growth = start_val * ((1.065 ** (90 / 365)) - 1)
        end_val = start_val + expected_growth
        snaps = [_snap(0, end_val, 80000), _snap(90, start_val, 80000)]
        result = _track(
            settings=PlanSettings(expected_return_baseline=0.065),
            snapshots=snaps,
        )
        assert result.status == "on_track"
        assert abs(result.return_drift_pct) < 2.0

    def test_ahead_returns(self):
        """Portfolio grew much faster than expected."""
        snaps = [_snap(0, 120000, 80000), _snap(90, 100000, 80000)]
        result = _track(
            settings=PlanSettings(expected_return_baseline=0.065),
            snapshots=snaps,
        )
        assert result.status == "ahead"
        assert result.return_drift_pct > 0
        assert result.actual_annualized_return_pct > result.expected_annualized_return_pct

    def test_behind_returns(self):
        """Portfolio shrank while plan assumed growth."""
        snaps = [_snap(0, 95000, 80000), _snap(90, 100000, 80000)]
        result = _track(
            settings=PlanSettings(expected_return_baseline=0.065),
            snapshots=snaps,
        )
        assert result.status == "behind"
        assert result.return_drift_pct < 0


class TestContributionTracking:
    def test_contributions_on_pace(self):
        """Contributions match plan rate."""
        # 90 days at $19k/year (18k + 1k HSA) = ~$4,685 expected
        annual = 18000 + 1000
        expected = annual * (90 / 365)
        snaps = [_snap(0, 104685, 80000 + expected), _snap(90, 100000, 80000)]
        result = _track(snapshots=snaps)
        assert result.contribution_pace_pct == pytest.approx(100.0, abs=1.0)

    def test_contributions_below_pace(self):
        """Contributions are behind plan."""
        snaps = [_snap(0, 101000, 81000), _snap(90, 100000, 80000)]
        result = _track(snapshots=snaps)
        assert result.contribution_pace_pct < 100.0
        assert result.actual_contributions_usd == 1000.0

    def test_zero_plan_contributions(self):
        """Plan has no contribution target - pace should be 0."""
        snaps = [_snap(0, 102000, 81000), _snap(90, 100000, 80000)]
        result = _track(
            settings=PlanSettings(annual_contribution_usd=0, hsa_extra_contribution_usd=0),
            snapshots=snaps,
        )
        assert result.contribution_pace_pct == 0.0


class TestProjectedValue:
    def test_projected_vs_actual(self):
        """Projected value uses plan return + expected contributions."""
        start = 100000
        snaps = [_snap(0, 110000, 85000), _snap(90, start, 80000)]
        result = _track(
            settings=PlanSettings(expected_return_baseline=0.065, annual_contribution_usd=18000),
            snapshots=snaps,
        )
        assert result.projected_value_usd > 0
        assert result.value_drift_usd == pytest.approx(
            result.current_value_usd - result.projected_value_usd, abs=0.01
        )

    def test_value_drift_pct(self):
        snaps = [_snap(0, 110000, 85000), _snap(90, 100000, 80000)]
        result = _track(snapshots=snaps)
        if result.projected_value_usd > 0:
            expected_pct = (result.value_drift_usd / result.projected_value_usd) * 100
            assert result.value_drift_pct == pytest.approx(expected_pct, abs=0.01)


class TestMarketGrowth:
    def test_market_growth_calculation(self):
        """Market growth = value change - contributions."""
        snaps = [_snap(0, 115000, 85000), _snap(90, 100000, 80000)]
        result = _track(snapshots=snaps)
        contributions = 85000 - 80000  # 5000
        value_change = 115000 - 100000  # 15000
        assert result.market_growth_usd == value_change - contributions


class TestDefaultFallback:
    def test_uses_planner_defaults_when_settings_empty(self):
        """Empty plan settings should fall back to planner defaults."""
        snaps = [_snap(0, 102000, 81000), _snap(90, 100000, 80000)]
        result = _track(settings=PlanSettings(), snapshots=snaps)
        assert result.expected_annualized_return_pct == pytest.approx(6.5, abs=0.01)

    def test_uses_plan_settings_when_set(self):
        snaps = [_snap(0, 102000, 81000), _snap(90, 100000, 80000)]
        result = _track(
            settings=PlanSettings(expected_return_baseline=0.08),
            snapshots=snaps,
        )
        assert result.expected_annualized_return_pct == pytest.approx(8.0, abs=0.01)


class TestMetadata:
    def test_window_fields(self):
        snaps = [_snap(0, 102000, 81000), _snap(60, 100000, 80000)]
        result = _track(snapshots=snaps)
        assert result.tracking_window_days == 60
        assert result.snapshot_count == 2
        assert result.plan_id == "plan-1"
        assert result.plan_title == "Test Plan"
