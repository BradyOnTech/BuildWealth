from datetime import datetime, timezone

from buildwealth_orchestrator.services.runtime_telemetry import (
    RuntimeTelemetryTracker,
    summarize_cache_quality,
)


def test_runtime_telemetry_tracker_records_latency_distributions() -> None:
    tracker = RuntimeTelemetryTracker(route_sample_size=16, overall_sample_size=64)

    tracker.record_api_latency(method="GET", path="/api/a", status_code=200, latency_ms=25.0)
    tracker.record_api_latency(method="GET", path="/api/a", status_code=500, latency_ms=75.0)
    tracker.record_api_latency(method="POST", path="/api/b", status_code=201, latency_ms=40.0)

    payload = tracker.latency_snapshot(top_routes=8)

    assert payload["request_count"] == 3
    assert payload["server_error_count"] == 1
    assert payload["server_error_rate_pct"] == 33.3
    assert payload["window_sample_count"] == 3
    assert payload["p95_latency_ms"] is not None

    routes = {(item["method"], item["path"]): item for item in payload["routes"]}
    route_a = routes[("GET", "/api/a")]
    assert route_a["request_count"] == 2
    assert route_a["server_error_count"] == 1
    assert route_a["p95_latency_ms"] is not None


def test_runtime_telemetry_tracker_records_context_payload() -> None:
    tracker = RuntimeTelemetryTracker()
    generated_at = datetime(2026, 4, 15, 12, 30, tzinfo=timezone.utc)
    snapshot_as_of = datetime(2026, 4, 15, 11, 0, tzinfo=timezone.utc)

    tracker.record_context_payload(
        {
            "generated_at": generated_at.isoformat(),
            "warnings": ["snapshot stale"],
            "quality": {
                "freshness": {
                    "snapshot_as_of": snapshot_as_of.isoformat(),
                    "snapshot_age_seconds": 5400,
                    "snapshot_stale": True,
                    "snapshot_stale_threshold_seconds": 3600,
                },
                "coverage": {
                    "score_pct": 82.5,
                    "missing_sections": ["research", "planning"],
                },
            },
        }
    )

    payload = tracker.context_snapshot()
    assert payload["last_context_generated_at"] == generated_at
    assert payload["snapshot_as_of"] == snapshot_as_of
    assert payload["snapshot_age_seconds"] == 5400.0
    assert payload["snapshot_stale"] is True
    assert payload["coverage_score_pct"] == 82.5
    assert payload["missing_sections"] == ["research", "planning"]
    assert payload["warning_count"] == 1


def test_summarize_cache_quality_combines_store_metrics() -> None:
    payload = summarize_cache_quality(
        enabled=True,
        stores=[
            {
                "name": "research",
                "max_entries": 100,
                "entries": 45,
                "lookup_count": 20,
                "hit_count": 15,
                "miss_count": 5,
                "write_count": 8,
                "eviction_count": 0,
                "expired_pruned": 1,
                "hit_rate_pct": 75.0,
            },
            {
                "name": "baseline_projection",
                "max_entries": 100,
                "entries": 80,
                "lookup_count": 10,
                "hit_count": 2,
                "miss_count": 8,
                "write_count": 9,
                "eviction_count": 3,
                "expired_pruned": 2,
                "hit_rate_pct": 20.0,
            },
        ],
    )

    assert payload["enabled"] is True
    assert payload["total_lookup_count"] == 30
    assert payload["total_hit_count"] == 17
    assert payload["combined_hit_rate_pct"] == 56.7

    stores = {item["name"]: item for item in payload["stores"]}
    assert stores["research"]["quality_status"] == "healthy"
    assert stores["baseline_projection"]["quality_status"] == "cold"
