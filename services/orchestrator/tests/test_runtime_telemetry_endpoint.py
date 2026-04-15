import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PortfolioSnapshot


def _request_scope(path: str, method: str = "GET") -> dict[str, object]:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }


def test_telemetry_latency_middleware_records_only_api_paths() -> None:
    main.runtime_telemetry_tracker.reset()

    async def _call_next(_: Request) -> Response:
        return Response(status_code=204)

    asyncio.run(main.telemetry_latency_middleware(Request(_request_scope("/api/test")), _call_next))
    asyncio.run(main.telemetry_latency_middleware(Request(_request_scope("/health")), _call_next))

    telemetry = main.get_runtime_telemetry()
    assert telemetry.api_latency.request_count >= 1
    assert all(route.path.startswith("/api/") for route in telemetry.api_latency.routes)


def test_get_runtime_telemetry_uses_snapshot_fallback_for_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main.runtime_telemetry_tracker.reset()
    main.copilot_context_research_cache.clear()
    main.copilot_context_projection_cache.clear()

    stale_as_of = datetime.now(timezone.utc) - timedelta(hours=3)
    snapshot = PortfolioSnapshot(
        as_of=stale_as_of,
        base_currency="USD",
        total_value_usd=200000.0,
        total_investment_usd=150000.0,
        net_performance_usd=50000.0,
        net_performance_percent=33.3,
        holdings=[],
        accounts=[],
        raw={},
    )
    monkeypatch.setattr(
        main,
        "snapshot_store",
        SimpleNamespace(latest=lambda: snapshot),
    )
    monkeypatch.setattr(main.settings, "copilot_context_snapshot_stale_after_seconds", 3600.0)
    monkeypatch.setattr(main.settings, "copilot_context_cache_enabled", True)

    main.copilot_context_research_cache.set("r1", {"ok": True}, ttl_seconds=30)
    main.copilot_context_projection_cache.set("p1", {"ok": True}, ttl_seconds=30)
    main.copilot_context_research_cache.lookup("r1")
    main.copilot_context_research_cache.lookup("missing")

    main.runtime_telemetry_tracker.record_api_latency(
        method="GET",
        path="/api/copilot/context/cache",
        status_code=200,
        latency_ms=32.0,
    )

    telemetry = main.get_runtime_telemetry()

    assert telemetry.api_latency.request_count == 1
    assert telemetry.context_freshness.snapshot_stale is True
    assert telemetry.context_freshness.snapshot_age_seconds is not None
    assert telemetry.context_freshness.snapshot_stale_threshold_seconds == 3600.0

    stores = {item.name: item for item in telemetry.cache_quality.stores}
    assert stores["research"].lookup_count == 2
    assert stores["baseline_projection"].entries == 1


def test_get_runtime_telemetry_prefers_recorded_context_payload() -> None:
    main.runtime_telemetry_tracker.reset()
    generated_at = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)

    main.runtime_telemetry_tracker.record_context_payload(
        {
            "generated_at": generated_at.isoformat(),
            "warnings": ["one", "two"],
            "quality": {
                "freshness": {
                    "snapshot_as_of": (generated_at - timedelta(minutes=20)).isoformat(),
                    "snapshot_age_seconds": 1200,
                    "snapshot_stale": False,
                    "snapshot_stale_threshold_seconds": 3600,
                },
                "coverage": {
                    "score_pct": 96.0,
                    "missing_sections": [],
                },
            },
        }
    )

    telemetry = main.get_runtime_telemetry()

    assert telemetry.context_freshness.last_context_generated_at == generated_at
    assert telemetry.context_freshness.snapshot_stale is False
    assert telemetry.context_freshness.coverage_score_pct == 96.0
    assert telemetry.context_freshness.warning_count == 2
