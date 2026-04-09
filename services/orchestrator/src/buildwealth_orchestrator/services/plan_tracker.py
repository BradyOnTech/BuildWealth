"""Compare plan assumptions against actual portfolio performance from snapshot history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from buildwealth_orchestrator.schemas import (
    PlanSettings,
    PlanTrackingResponse,
    PortfolioSnapshot,
)
from buildwealth_orchestrator.services.portfolio_performance import (
    calculate_modified_dietz_return,
    filter_transaction_cash_flows,
)

MIN_WINDOW_DAYS = 7
DRIFT_THRESHOLD_PCT = 2.0  # +/- 2% annualized return drift = on_track
ASSET_CLASS_EXPECTED_RETURNS = {
    "us_stocks": 0.07,
    "international_stocks": 0.072,
    "emerging_markets": 0.078,
    "us_bonds": 0.04,
    "international_bonds": 0.038,
    "cash": 0.025,
    "reit": 0.065,
    "reits": 0.065,
    "commodities": 0.045,
    "crypto": 0.10,
}


def _resolve_setting(plan: PlanSettings, key: str, defaults: dict[str, Any]) -> float | None:
    """Return the plan setting if set, otherwise fall back to planner defaults."""
    value = getattr(plan, key, None)
    if value is not None:
        return float(value)
    return defaults.get(key)


def _annualize_return(total_return: float, days: int) -> float:
    """Convert a total return over N days to an annualized rate."""
    if days <= 0:
        return 0.0
    if total_return <= -1.0:
        return -1.0
    return (1.0 + total_return) ** (365.0 / days) - 1.0


def _normalize_asset_class(value: str | None) -> str:
    text = (value or "").strip().lower()
    return text.replace(" ", "_").replace("-", "_")


def _infer_expected_return_from_asset_mix(snapshot: PortfolioSnapshot | None) -> float | None:
    if snapshot is None:
        return None

    weighted_sum = 0.0
    weighted_value = 0.0
    for holding in snapshot.holdings:
        value = float(holding.value_usd or 0.0)
        if value <= 0:
            continue
        normalized_asset_class = _normalize_asset_class(holding.asset_class)
        expected_return = ASSET_CLASS_EXPECTED_RETURNS.get(normalized_asset_class)
        if expected_return is None:
            continue
        weighted_sum += value * expected_return
        weighted_value += value

    if weighted_value <= 0:
        return None

    return weighted_sum / weighted_value


def compute_plan_tracking(
    *,
    plan_id: str,
    plan_title: str,
    plan_settings: PlanSettings,
    planner_defaults: dict[str, Any],
    snapshots: list[PortfolioSnapshot],
    transactions: list[dict[str, Any]] | None = None,
) -> PlanTrackingResponse:
    """Build a plan-vs-actual tracking comparison from plan settings and snapshot history.

    ``snapshots`` should be ordered newest-first (as returned by SnapshotStore.recent).
    """
    now = datetime.now(timezone.utc)

    if len(snapshots) < 2:
        plan_expected = _resolve_setting(plan_settings, "expected_return_baseline", {})
        expected_return_method: Literal["plan_setting", "asset_mix_inferred", "planner_default"] = (
            "plan_setting" if plan_expected is not None else "planner_default"
        )
        return PlanTrackingResponse(
            plan_id=plan_id,
            plan_title=plan_title,
            status="insufficient_data",
            status_detail="Need at least 2 snapshots to compute tracking. Run sync to build history.",
            tracking_window_days=0,
            window_start=now,
            window_end=now,
            starting_value_usd=snapshots[0].total_value_usd if snapshots else 0.0,
            current_value_usd=snapshots[0].total_value_usd if snapshots else 0.0,
            projected_value_usd=0.0,
            value_drift_usd=0.0,
            value_drift_pct=0.0,
            actual_annualized_return_pct=0.0,
            expected_annualized_return_pct=plan_expected or (planner_defaults.get("expected_return_baseline") or 0.065),
            return_drift_pct=0.0,
            actual_return_method="snapshot_delta",
            expected_return_method=expected_return_method,
            actual_contributions_usd=0.0,
            expected_contributions_usd=0.0,
            contribution_pace_pct=0.0,
            market_growth_usd=0.0,
            snapshot_count=len(snapshots),
        )

    latest = snapshots[0]
    oldest = snapshots[-1]

    delta = latest.as_of - oldest.as_of
    window_days = max(1, int(delta.total_seconds() / 86400))
    tracking_flows = (
        filter_transaction_cash_flows(
            transactions=transactions or [],
            start_date=oldest.as_of,
            end_date=latest.as_of,
        )
        if transactions
        else []
    )

    # -- Contribution tracking --
    actual_contributions = sum(amount for _, amount in tracking_flows)
    actual_return_method: Literal["modified_dietz", "snapshot_delta"] = "modified_dietz"
    if not tracking_flows:
        actual_contributions = latest.total_investment_usd - oldest.total_investment_usd
        actual_return_method = "snapshot_delta"
    plan_annual_contribution = _resolve_setting(plan_settings, "annual_contribution_usd", planner_defaults) or 0.0
    hsa_extra = _resolve_setting(plan_settings, "hsa_extra_contribution_usd", planner_defaults) or 0.0
    total_annual_contribution = plan_annual_contribution + hsa_extra
    expected_contributions = total_annual_contribution * (window_days / 365.0)
    contribution_pace = (actual_contributions / expected_contributions * 100.0) if expected_contributions > 0 else 0.0

    # -- Market growth (value change minus contributions) --
    value_change = latest.total_value_usd - oldest.total_value_usd
    market_growth = value_change - actual_contributions

    # -- Actual return --
    if tracking_flows and window_days >= MIN_WINDOW_DAYS:
        period_return, annualized_return = calculate_modified_dietz_return(
            start_value=oldest.total_value_usd,
            end_value=latest.total_value_usd,
            start_date=oldest.as_of,
            end_date=latest.as_of,
            cash_flows=tracking_flows,
        )
        if period_return is None or annualized_return is None:
            actual_return_method = "snapshot_delta"
            avg_base = (oldest.total_value_usd + latest.total_value_usd) / 2.0
            if avg_base > 0:
                period_return = market_growth / avg_base
                actual_annual_return = _annualize_return(period_return, window_days)
            else:
                period_return = 0.0
                actual_annual_return = 0.0
        else:
            actual_annual_return = annualized_return
    else:
        avg_base = (oldest.total_value_usd + latest.total_value_usd) / 2.0
        if avg_base > 0 and window_days >= MIN_WINDOW_DAYS:
            period_return = market_growth / avg_base
            actual_annual_return = _annualize_return(period_return, window_days)
        else:
            period_return = 0.0
            actual_annual_return = 0.0

    # -- Expected return from plan --
    plan_expected_return = plan_settings.expected_return_baseline
    inferred_expected_return = _infer_expected_return_from_asset_mix(latest)
    if plan_expected_return is not None:
        expected_annual_return = float(plan_expected_return)
        expected_return_method: Literal["plan_setting", "asset_mix_inferred", "planner_default"] = "plan_setting"
    elif inferred_expected_return is not None:
        expected_annual_return = inferred_expected_return
        expected_return_method = "asset_mix_inferred"
    else:
        expected_annual_return = _resolve_setting(plan_settings, "expected_return_baseline", planner_defaults) or 0.065
        expected_return_method = "planner_default"

    return_drift = actual_annual_return - expected_annual_return

    # -- Projected value (where should we be if plan assumptions held?) --
    expected_period_return = (1.0 + expected_annual_return) ** (window_days / 365.0) - 1.0
    projected_value = oldest.total_value_usd * (1.0 + expected_period_return) + expected_contributions
    value_drift = latest.total_value_usd - projected_value
    value_drift_pct = (value_drift / projected_value * 100.0) if projected_value > 0 else 0.0

    # -- Status assessment --
    if window_days < MIN_WINDOW_DAYS:
        status: Literal["on_track", "ahead", "behind", "insufficient_data"] = "insufficient_data"
        status_detail = f"Only {window_days} day(s) of data. Need at least {MIN_WINDOW_DAYS} days for meaningful tracking."
    elif return_drift > DRIFT_THRESHOLD_PCT / 100.0:
        status = "ahead"
        status_detail = (
            f"Actual annualized return ({actual_annual_return:.1%}) is "
            f"{abs(return_drift):.1%} ahead of plan assumption ({expected_annual_return:.1%})."
        )
    elif return_drift < -DRIFT_THRESHOLD_PCT / 100.0:
        status = "behind"
        status_detail = (
            f"Actual annualized return ({actual_annual_return:.1%}) is "
            f"{abs(return_drift):.1%} behind plan assumption ({expected_annual_return:.1%})."
        )
    else:
        status = "on_track"
        status_detail = (
            f"Actual annualized return ({actual_annual_return:.1%}) is within "
            f"{DRIFT_THRESHOLD_PCT}% of plan assumption ({expected_annual_return:.1%})."
        )

    return PlanTrackingResponse(
        plan_id=plan_id,
        plan_title=plan_title,
        status=status,
        status_detail=status_detail,
        tracking_window_days=window_days,
        window_start=oldest.as_of,
        window_end=latest.as_of,
        starting_value_usd=oldest.total_value_usd,
        current_value_usd=latest.total_value_usd,
        projected_value_usd=round(projected_value, 2),
        value_drift_usd=round(value_drift, 2),
        value_drift_pct=round(value_drift_pct, 2),
        actual_annualized_return_pct=round(actual_annual_return * 100, 2),
        expected_annualized_return_pct=round(expected_annual_return * 100, 2),
        return_drift_pct=round(return_drift * 100, 2),
        actual_return_method=actual_return_method,
        expected_return_method=expected_return_method,
        actual_contributions_usd=round(actual_contributions, 2),
        expected_contributions_usd=round(expected_contributions, 2),
        contribution_pace_pct=round(contribution_pace, 1),
        market_growth_usd=round(market_growth, 2),
        snapshot_count=len(snapshots),
    )
