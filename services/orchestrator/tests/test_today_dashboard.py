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
        inbox_high_priority_count=2,
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
    cards = {card.id: card for card in payload.command_cards}
    assert cards["profile-readiness"].status == "warning"
    assert cards["profile-readiness"].metric_value == "80%"
    assert cards["profile-readiness"].href == "#copilot?intent=complete-context"
    assert cards["data-trust"].status == "warning"
    assert cards["data-trust"].metric_value == "59m old"
    assert cards["plan-posture"].status == "ready"
    assert cards["portfolio-risk"].status == "critical"
    assert cards["portfolio-risk"].metric_value == "40%"
    assert cards["recent-changes"].status == "ready"
    assert cards["recent-changes"].metric_value == "$15,000"
    assert payload.recent_change_usd == 15000
    assert payload.recent_change_percent == 5.2


def test_today_dashboard_payload_surfaces_changes_since_last_review() -> None:
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
            },
            "decisions": [],
            "artifacts": [],
        },
        profile_readiness=ProfileReadinessSummary(
            completion_percent=80.0,
            status="attention",
            next_gap_key="tax_profile",
            next_gap_title="Tax profile",
            next_gap_detail="Set filing status and marginal tax rate.",
            blocking_recommendation_sources=[],
            sections=[],
        ),
        inbox_high_priority_count=2,
        last_review_checkpoint={
            "recorded_at": "2025-12-31T16:00:00+00:00",
            "total_value_usd": 285000,
            "top_holding_symbol": "MSFT",
            "top_holding_percent": 28.0,
            "profile_completion_percent": 70.0,
            "inbox_high_priority_count": 0,
            "active_plan_updated_at": "2025-12-20T12:00:00+00:00",
        },
    )

    cards = {card.id: card for card in payload.command_cards}
    card = cards["what-changed"]
    assert card.status == "warning"
    assert card.title == "What changed"
    assert card.metric_label == "Changes"
    assert card.metric_value == "5"
    assert "Portfolio value is $15,000 higher" in card.detail
    assert "Top holding changed from MSFT to AAPL" in card.detail
    assert "2 high-priority recommendation(s) are now open" in card.detail
    assert card.action_label == "Mark reviewed"
    assert card.href == "#today?review=complete"


def test_today_dashboard_payload_prompts_first_review_checkpoint() -> None:
    payload = build_today_dashboard_payload(
        now=datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc),
        currency="USD",
        state="MN",
        sync_status=_sync_status(),
        latest_snapshot=_snapshot(),
        snapshot_history=_history(),
        active_plan_detail=None,
        last_review_checkpoint=None,
    )

    cards = {card.id: card for card in payload.command_cards}
    card = cards["what-changed"]
    assert card.status == "ready"
    assert card.metric_value == "New"
    assert "No completed daily review checkpoint yet" in card.detail
    assert card.href == "#today?review=complete"


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
    cards = {card.id: card for card in payload.command_cards}
    assert cards["data-trust"].status == "critical"
    assert cards["data-trust"].action_label == "Run sync"
    assert cards["plan-posture"].status == "warning"
    assert cards["plan-posture"].href == "#plan"
