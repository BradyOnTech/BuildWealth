"""Heartbeat scheduling: staleness-aware sync decisions."""

from datetime import timedelta

from buildwealth_orchestrator.main import (
    scheduled_sync_is_due,
    snapshot_age_seconds,
    utc_now,
)
from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore
from buildwealth_orchestrator.settings import Settings


def test_scheduled_sync_is_due_semantics() -> None:
    day = 1440 * 60
    assert scheduled_sync_is_due(None, day) is True  # no snapshot yet: bootstrap
    assert scheduled_sync_is_due(day + 1, day) is True
    assert scheduled_sync_is_due(float(day), day) is True
    assert scheduled_sync_is_due(day - 60, day) is False
    assert scheduled_sync_is_due(0.0, day) is False


def test_snapshot_age_seconds_reads_latest_snapshot(tmp_path) -> None:
    store = SnapshotStore(snapshot_dir=tmp_path)
    assert snapshot_age_seconds(store) is None

    stale_time = utc_now() - timedelta(hours=30)
    store.write(PortfolioSnapshot(as_of=stale_time, total_value_usd=1000.0, holdings=[]))
    age = snapshot_age_seconds(store)
    assert age is not None
    assert 29 * 3600 < age < 31 * 3600


def test_sync_interval_defaults_to_daily(monkeypatch) -> None:
    monkeypatch.delenv("SYNC_INTERVAL_MINUTES", raising=False)
    assert Settings().sync_interval_minutes == 1440.0


def test_restore_sync_state_from_disk(tmp_path) -> None:
    from buildwealth_orchestrator import main

    saved = dict(main.sync_state)
    try:
        main.sync_state.update({"last_trigger": None, "last_completed_at": None})

        empty = SnapshotStore(snapshot_dir=tmp_path / "empty")
        assert main.restore_sync_state_from_disk(empty) is False
        assert main.sync_state["last_completed_at"] is None

        seeded = SnapshotStore(snapshot_dir=tmp_path / "seeded")
        as_of = utc_now() - timedelta(hours=3)
        seeded.write(PortfolioSnapshot(as_of=as_of, total_value_usd=1000.0, holdings=[]))
        assert main.restore_sync_state_from_disk(seeded) is True
        assert main.sync_state["last_trigger"] == "restored"
        restored_at = main.sync_state["last_completed_at"]
        assert restored_at is not None
        assert abs((restored_at - as_of).total_seconds()) < 2
    finally:
        main.sync_state.clear()
        main.sync_state.update(saved)
