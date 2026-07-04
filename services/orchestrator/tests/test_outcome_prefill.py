"""Outcome prefill: measured suggestions from snapshot history."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _seed_snapshots(store: SnapshotStore) -> None:
    store.write(PortfolioSnapshot(as_of=datetime(2026, 5, 30, tzinfo=timezone.utc), total_value_usd=500_000.0, holdings=[]))
    store.write(PortfolioSnapshot(as_of=datetime(2026, 7, 1, tzinfo=timezone.utc), total_value_usd=520_000.0, holdings=[]))


def _closure(applied_at: str = "2026-06-01T00:00:00+00:00") -> dict:
    return {
        "decision_status": "accepted",
        "applied_at": applied_at,
        "pre_mortem": {"review_date": "2026-06-20T00:00:00+00:00"},
        "expected_outcome": {"delta_future_value_usd": 15_000.0},
    }


@pytest.fixture()
def stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> RecommendationInbox:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    snapshots = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
    _seed_snapshots(snapshots)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "snapshot_store", snapshots)
    return inbox


def test_prefill_measures_change_since_applied(stores: RecommendationInbox) -> None:
    created = stores.create(
        title="Trim the concentrated position",
        detail="Recorded for the outcome-prefill test.",
        priority="medium",
        recommendation_type="workflow_action",
        source="generator:portfolio_risk",
        plan_id="plan-1",
        action_payload={"decision_closure": _closure()},
        status="applied",
    )

    payload = main.build_recommendation_outcome_prefill_payload(created["id"], now=NOW)

    assert payload.status == "ready"
    assert payload.suggested_future_value_delta_usd == 20_000.0
    assert payload.baseline_value_usd == 500_000.0
    assert payload.current_value_usd == 520_000.0
    assert payload.expected_future_value_delta_usd == 15_000.0
    assert payload.observation_window_days == 33
    assert payload.measurement_source == "portfolio_sync"
    assert any("contributions and market moves" in warning for warning in payload.warnings)


def test_prefill_follows_due_review_source_pointer(stores: RecommendationInbox) -> None:
    source = stores.create(
        title="Original decision",
        detail="Recorded for the outcome-prefill test.",
        priority="medium",
        recommendation_type="workflow_action",
        source="generator:portfolio_risk",
        plan_id="plan-1",
        action_payload={"decision_closure": _closure()},
        status="applied",
    )
    review = stores.create(
        title="Outcome review due: Original decision",
        detail="Recorded for the outcome-prefill test.",
        priority="medium",
        recommendation_type="workflow_action",
        source="generator:due_outcome_review",
        plan_id="plan-1",
        action_payload={"evidence": {"source_recommendation_id": source["id"]}},
        status="proposed",
    )

    payload = main.build_recommendation_outcome_prefill_payload(review["id"], now=NOW)

    assert payload.status == "ready"
    assert payload.source_recommendation_id == source["id"]
    assert payload.suggested_future_value_delta_usd == 20_000.0


def test_prefill_unavailable_without_closure_or_history(
    stores: RecommendationInbox,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bare = stores.create(
        title="No closure",
        detail="Recorded for the outcome-prefill test.",
        priority="low",
        recommendation_type="workflow_action",
        source="generator:portfolio_risk",
        plan_id=None,
        action_payload={},
        status="proposed",
    )
    payload = main.build_recommendation_outcome_prefill_payload(bare["id"], now=NOW)
    assert payload.status == "unavailable"
    assert "closure" in payload.detail

    # a single snapshot cannot span a window
    thin = SnapshotStore(snapshot_dir=tmp_path / "thin-snapshots")
    thin.write(PortfolioSnapshot(as_of=datetime(2026, 7, 1, tzinfo=timezone.utc), total_value_usd=1.0, holdings=[]))
    monkeypatch.setattr(main, "snapshot_store", thin)
    closed = stores.create(
        title="Closed decision",
        detail="Recorded for the outcome-prefill test.",
        priority="low",
        recommendation_type="workflow_action",
        source="generator:portfolio_risk",
        plan_id=None,
        action_payload={"decision_closure": _closure()},
        status="applied",
    )
    payload = main.build_recommendation_outcome_prefill_payload(closed["id"], now=NOW)
    assert payload.status == "unavailable"
    assert "snapshot" in payload.detail.lower()
