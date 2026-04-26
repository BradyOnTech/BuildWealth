from datetime import datetime, timezone

from buildwealth_orchestrator.schemas import (
    Holding,
    PortfolioSnapshot,
    ProfileReadinessSummary,
    SnapshotHistoryPoint,
    SnapshotHistoryResponse,
    SyncStatusResponse,
)
from buildwealth_orchestrator.services.today_dashboard import build_today_dashboard_payload


def _sync_status() -> SyncStatusResponse:
    return SyncStatusResponse(
        running=False,
        runs_total=4,
        runs_failed=0,
        last_trigger="manual",
        last_started_at=datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc),
        last_completed_at=datetime(2026, 1, 1, 15, 1, tzinfo=timezone.utc),
        last_error=None,
        last_snapshot_path=None,
        last_ignidash_payload_path=None,
    )


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime(2026, 1, 1, 15, 1, tzinfo=timezone.utc),
        base_currency="USD",
        total_value_usd=300000,
        total_investment_usd=250000,
        net_performance_usd=50000,
        net_performance_percent=0.2,
        holdings=[
            Holding(symbol="AAPL", name="Apple", value_usd=120000, allocation_percent=40),
            Holding(symbol="VTI", name="VTI", value_usd=90000, allocation_percent=30),
            Holding(symbol="VXUS", name="VXUS", value_usd=90000, allocation_percent=30),
        ],
    )


def _history() -> SnapshotHistoryResponse:
    return SnapshotHistoryResponse(
        points=[
            SnapshotHistoryPoint(
                as_of=datetime(2026, 1, 1, 15, 1, tzinfo=timezone.utc),
                total_value_usd=300000,
                net_performance_usd=50000,
                net_performance_percent=0.2,
                holdings_count=3,
            ),
            SnapshotHistoryPoint(
                as_of=datetime(2025, 12, 1, 15, 1, tzinfo=timezone.utc),
                total_value_usd=285000,
                net_performance_usd=43000,
                net_performance_percent=0.17,
                holdings_count=3,
            ),
        ],
        window_points=2,
        latest_as_of=datetime(2026, 1, 1, 15, 1, tzinfo=timezone.utc),
        oldest_as_of=datetime(2025, 12, 1, 15, 1, tzinfo=timezone.utc),
        delta_total_value_usd=15000,
        delta_total_value_percent=5.2,
        delta_net_performance_usd=7000,
    )


def test_today_dashboard_payload_with_active_plan() -> None:
    payload = build_today_dashboard_payload(
        now=datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc),
        currency="USD",
        state="MN",
        sync_status=_sync_status(),
        latest_snapshot=_snapshot(),
        snapshot_history=_history(),
        active_plan_detail={
            "id": "plan-1",
            "title": "Primary Plan",
            "updated_at": "2026-01-01T15:05:00+00:00",
            "settings": {
                "annual_contribution_usd": 22000,
                "years": 25,
                "expected_return_baseline": 0.07,
                "expected_return_optimistic": 0.09,
                "expected_return_conservative": 0.05,
            },
            "decisions": [
                {"created_at": "2026-01-01T15:10:00+00:00", "summary": "Decision 1"},
            ],
            "artifacts": [{"id": "a1"}],
        },
        profile_readiness=ProfileReadinessSummary(
            completion_percent=80.0,
            status="attention",
            next_gap_key="tax_profile",
            next_gap_title="Tax profile",
            next_gap_detail="Set filing status and marginal tax rate.",
            blocking_recommendation_sources=["profile_completeness", "tax_planning"],
            sections=[],
        ),
    )

    assert payload.total_value_usd == 300000
    assert payload.active_plan is not None
    assert payload.active_plan.title == "Primary Plan"
    assert payload.concentration_risk == "high"
    assert payload.context_state == "warning"
    assert any("financial profile is incomplete" in note.lower() for note in payload.context_notes)
    assert payload.recommendations
    assert payload.checklist
    assert payload.workflow_steps
    assert payload.profile_readiness is not None
    assert payload.profile_readiness.next_gap_key == "tax_profile"
    assert "Profile readiness: next gap is Tax profile." in payload.context_notes


def test_today_dashboard_payload_without_snapshot_or_plan() -> None:
    payload = build_today_dashboard_payload(
        now=datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc),
        currency="USD",
        state="MN",
        sync_status=_sync_status(),
        latest_snapshot=None,
        snapshot_history=SnapshotHistoryResponse(points=[], window_points=0),
        active_plan_detail=None,
    )

    assert payload.total_value_usd is None
    assert payload.active_plan is None
    assert payload.context_state == "critical"
    assert any("no portfolio snapshot" in note.lower() for note in payload.context_notes)
    assert any(item.id == "sync-first-snapshot" for item in payload.checklist)
    assert any(item.id == "create-plan" for item in payload.recommendations)
