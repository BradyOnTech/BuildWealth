from buildwealth_orchestrator.services.today_review_checkpoints import TodayReviewCheckpointStore


def test_today_review_checkpoint_store_round_trips_latest(tmp_path) -> None:
    store = TodayReviewCheckpointStore(tmp_path / "today" / "review_checkpoint.json")

    assert store.latest() is None

    saved = store.save(
        {
            "recorded_at": "2026-04-30T12:00:00+00:00",
            "total_value_usd": 300000,
            "top_holding_symbol": "AAPL",
            "ignored_none": None,
        }
    )

    assert saved == {
        "recorded_at": "2026-04-30T12:00:00+00:00",
        "total_value_usd": 300000,
        "top_holding_symbol": "AAPL",
    }
    assert store.latest() == saved
