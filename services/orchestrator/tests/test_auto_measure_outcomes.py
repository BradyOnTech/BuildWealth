"""The outcome loop closes itself: due, measurable outcomes get recorded
automatically — labeled as auto-measured, editable, and never nagging."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _closure(review_date: str = "2026-06-20T00:00:00+00:00") -> dict:
    return {
        "decision_status": "accepted",
        "applied_at": "2026-06-01T00:00:00+00:00",
        "pre_mortem": {"review_date": review_date},
        "expected_outcome": {"delta_future_value_usd": 15_000.0},
    }


def _applied(inbox: RecommendationInbox, *, title: str = "Trim the concentrated position", closure: dict | None = None) -> dict:
    return inbox.create(
        title=title,
        detail="Recorded for the auto-measure test.",
        priority="medium",
        recommendation_type="workflow_action",
        source="generator:portfolio_risk",
        action_payload={"decision_closure": closure or _closure()},
        status="applied",
    )


@pytest.fixture()
def stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> RecommendationInbox:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    snapshots = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
    snapshots.write(PortfolioSnapshot(as_of=datetime(2026, 5, 30, tzinfo=timezone.utc), total_value_usd=500_000.0, holdings=[]))
    snapshots.write(PortfolioSnapshot(as_of=datetime(2026, 7, 1, tzinfo=timezone.utc), total_value_usd=520_000.0, holdings=[]))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "snapshot_store", snapshots)
    return inbox


def test_due_measurable_outcome_is_recorded_automatically(stores: RecommendationInbox) -> None:
    created = _applied(stores)

    assert main.sweep_auto_measure_outcomes(now=NOW) == 1

    closure = stores.get(created["id"])["action_payload"]["decision_closure"]
    realized = closure["realized_outcome"]
    assert realized["realized_delta_future_value_usd"] == 20_000.0
    assert realized["measurement_source"] == "auto:portfolio_sync"
    assert "Measured automatically" in realized["note"]
    assert "Edit the outcome" in realized["note"]
    # Expected-vs-realized calibration data materializes with it.
    assert isinstance(closure.get("expected_vs_realized"), dict)

    # Idempotent: a measured outcome is never re-measured.
    assert main.sweep_auto_measure_outcomes(now=NOW) == 0


def test_future_review_dates_are_left_alone(stores: RecommendationInbox) -> None:
    _applied(stores, closure=_closure(review_date="2026-08-15T00:00:00+00:00"))
    assert main.sweep_auto_measure_outcomes(now=NOW) == 0


def test_unmeasurable_outcomes_are_skipped_not_faked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    empty_snapshots = SnapshotStore(snapshot_dir=tmp_path / "snapshots-empty")
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "snapshot_store", empty_snapshots)
    created = _applied(inbox)

    assert main.sweep_auto_measure_outcomes(now=NOW) == 0
    closure = inbox.get(created["id"])["action_payload"]["decision_closure"]
    assert "realized_outcome" not in closure


def test_auto_measured_decisions_never_become_review_nags(stores: RecommendationInbox) -> None:
    _applied(stores)

    # Heartbeat order: measure first, then the review sweep — nothing left to nag.
    assert main.sweep_auto_measure_outcomes(now=NOW) == 1
    assert main.sweep_due_outcome_reviews() == 0
    review_entries = [
        row
        for row in stores.list(limit=None, status=None, sort="none")
        if str(row.get("source") or "") == "generator:due_outcome_review"
    ]
    assert review_entries == []
