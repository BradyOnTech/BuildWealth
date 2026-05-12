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
                name="portfolio_benchmark",
                base_url="http://localhost:8411",
                enabled=True,
                health_paths=("/health", "/api/v1/health"),
                version_paths=("/version",),
                expected_contract_version=1,
            )
        ],
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(tracker.probe_all())
    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.name == "portfolio_benchmark"
    assert item.enabled is True
    assert item.reachable is True
    assert item.contract_version == 1
    assert item.expected_contract_version == 1
    assert item.contract_compatible is True
    assert item.last_error is None
    assert item.last_checked_at is not None
    assert calls == ["/health", "/api/v1/health", "/version"]


def test_engine_status_probe_marks_unreachable_when_all_paths_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": f"down: {request.url.path}"})

    tracker = EngineStatusTracker(
        configs=[
            EngineProbeConfig(
                name="plan_simulation",
                base_url="http://localhost:8412",
                enabled=True,
                health_paths=("/health", "/api/health"),
                version_paths=("/version",),
                expected_contract_version=1,
            )
        ],
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(tracker.probe_all())
    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.name == "plan_simulation"
    assert item.reachable is False
    assert item.contract_version is None
    assert item.expected_contract_version == 1
    assert item.contract_compatible is None
    assert item.last_error is not None
    assert "/api/health" in item.last_error


def test_engine_status_tracker_increments_degraded_count() -> None:
    tracker = EngineStatusTracker(
        configs=[
            EngineProbeConfig(
                name="plan_simulation",
                base_url="http://localhost:8412",
                enabled=False,
                health_paths=("/health",),
                version_paths=("/version",),
            )
        ],
        timeout_seconds=1,
    )

    asyncio.run(tracker.increment_degraded("plan_simulation", reason="fallback active"))
    asyncio.run(tracker.increment_degraded("plan_simulation"))

    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.degraded_count == 2
    assert item.last_error == "fallback active"


def test_engine_status_probe_marks_contract_mismatch_and_guard_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/health":
            return httpx.Response(status_code=200, json={"status": "OK"})
        if request.url.path == "/version":
            return httpx.Response(status_code=200, json={"contract_version": 2})
        return httpx.Response(status_code=404, json={"detail": "unknown"})

    tracker = EngineStatusTracker(
        configs=[
            EngineProbeConfig(
                name="portfolio_benchmark",
                base_url="http://localhost:8411",
                enabled=True,
                health_paths=("/api/v1/health",),
                version_paths=("/version",),
                expected_contract_version=1,
            )
        ],
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(tracker.probe_all())
    snapshot = asyncio.run(tracker.snapshot())
    item = snapshot.engines[0]

    assert item.reachable is True
    assert item.contract_version == 2
    assert item.expected_contract_version == 1
    assert item.contract_compatible is False
    assert item.last_error == "Contract version mismatch (expected v1, got v2)"

    guard_reason = asyncio.run(tracker.sidecar_guard_reason("portfolio_benchmark"))
    assert guard_reason == "Sidecar contract version mismatch (expected v1, got v2)"
