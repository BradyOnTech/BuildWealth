import asyncio

import httpx

from buildwealth_orchestrator.services.engine_status import EngineProbeConfig, EngineStatusTracker


def test_engine_status_probe_uses_fallback_health_path_and_parses_version() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(status_code=404, json={"detail": "missing"})
        if request.url.path == "/api/v1/health":
            return httpx.Response(status_code=200, json={"status": "OK"})
        if request.url.path == "/version":
            return httpx.Response(status_code=200, json={"version": "v1.2.3"})
        return httpx.Response(status_code=404, json={"detail": "unknown"})

    tracker = EngineStatusTracker(
        configs=[
            EngineProbeConfig(
                name="ghostfolio_benchmark",
                base_url="http://localhost:8411",
                enabled=True,
                health_paths=("/health", "/api/v1/health"),
                version_paths=("/version",),
            )
        ],
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(tracker.probe_all())
    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.name == "ghostfolio_benchmark"
    assert item.enabled is True
    assert item.reachable is True
    assert item.contract_version == 1
    assert item.last_error is None
    assert item.last_checked_at is not None
    assert calls == ["/health", "/api/v1/health", "/version"]


def test_engine_status_probe_marks_unreachable_when_all_paths_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": f"down: {request.url.path}"})

    tracker = EngineStatusTracker(
        configs=[
            EngineProbeConfig(
                name="ignidash_scenario",
                base_url="http://localhost:8412",
                enabled=True,
                health_paths=("/health", "/api/health"),
                version_paths=("/version",),
            )
        ],
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(tracker.probe_all())
    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.name == "ignidash_scenario"
    assert item.reachable is False
    assert item.contract_version is None
    assert item.last_error is not None
    assert "/api/health" in item.last_error


def test_engine_status_tracker_increments_degraded_count() -> None:
    tracker = EngineStatusTracker(
        configs=[
            EngineProbeConfig(
                name="ignidash_scenario",
                base_url="http://localhost:8412",
                enabled=False,
                health_paths=("/health",),
                version_paths=("/version",),
            )
        ],
        timeout_seconds=1,
    )

    asyncio.run(tracker.increment_degraded("ignidash_scenario", reason="fallback active"))
    asyncio.run(tracker.increment_degraded("ignidash_scenario"))

    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.degraded_count == 2
    assert item.last_error == "fallback active"
