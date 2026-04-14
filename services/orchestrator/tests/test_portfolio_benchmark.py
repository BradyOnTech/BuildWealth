import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.engine_adapter import SidecarAdapter
from buildwealth_orchestrator.services.portfolio_benchmark import GhostfolioBenchmarkService
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore


class _FakeResearch:
    def __init__(self, history_by_symbol: dict[str, list[dict]]):
        self.history_by_symbol = history_by_symbol

    def get_price_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict]:
        _ = (period, interval)
        return self.history_by_symbol.get(symbol, [])


def _write_snapshots(snapshot_store: SnapshotStore) -> None:
    snapshot_store.write(
        PortfolioSnapshot(
            as_of=datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc),
            total_value_usd=1000.0,
            net_performance_usd=0.0,
            net_performance_percent=0.0,
        )
    )
    snapshot_store.write(
        PortfolioSnapshot(
            as_of=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            total_value_usd=1100.0,
            net_performance_usd=100.0,
            net_performance_percent=10.0,
        )
    )
    snapshot_store.write(
        PortfolioSnapshot(
            as_of=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
            total_value_usd=1200.0,
            net_performance_usd=200.0,
            net_performance_percent=20.0,
        )
    )


def test_benchmark_service_uses_local_fallback_when_sidecar_disabled(tmp_path: Path) -> None:
    snapshot_store = SnapshotStore(tmp_path / "snapshots")
    _write_snapshots(snapshot_store)
    research = _FakeResearch(
        {
            "SPY": [
                {"date": "2026-04-08", "close": 400},
                {"date": "2026-04-09", "close": 420},
                {"date": "2026-04-10", "close": 440},
            ]
        }
    )

    service = GhostfolioBenchmarkService(
        snapshot_store=snapshot_store,
        research_service=research,
        sidecar_adapter=None,
        sidecar_enabled=False,
        sidecar_path="/v1/benchmark/compare",
        base_currency="USD",
    )

    result = asyncio.run(service.compare(benchmark_symbols=["SPY"], limit=30))

    assert result.engine_status == "degraded"
    assert result.fallback_method == "sidecar_disabled"
    assert result.summary.portfolio_return_pct == 20.0
    assert result.summary.benchmark_return_pct_by_symbol["SPY"] == 10.0
    assert len(result.series) == 3


def test_benchmark_service_uses_sidecar_response_when_enabled(tmp_path: Path) -> None:
    snapshot_store = SnapshotStore(tmp_path / "snapshots")
    _write_snapshots(snapshot_store)
    research = _FakeResearch({})

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ghostfolio",
                "engine_status": "ok",
                "fallback_method": None,
                "summary": {
                    "portfolio_return_pct": 20.0,
                    "benchmark_return_pct_by_symbol": {"SPY": 10.0},
                    "alpha_pct_by_symbol": {"SPY": 10.0},
                    "tracking_error_pct": 0.0,
                    "max_drawdown_pct": -1.0,
                },
                "series": [
                    {
                        "date": "2026-04-08",
                        "portfolio_index": 100.0,
                        "benchmark_index_by_symbol": {"SPY": 100.0},
                        "alpha_index_by_symbol": {"SPY": 0.0},
                    },
                    {
                        "date": "2026-04-10",
                        "portfolio_index": 120.0,
                        "benchmark_index_by_symbol": {"SPY": 110.0},
                        "alpha_index_by_symbol": {"SPY": 10.0},
                    },
                ],
                "warnings": [],
                "generated_at": "2026-04-10T12:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = GhostfolioBenchmarkService(
        snapshot_store=snapshot_store,
        research_service=research,
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/benchmark/compare",
        base_currency="USD",
    )

    result = asyncio.run(service.compare(benchmark_symbols=["SPY"], limit=30))

    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.summary.alpha_pct_by_symbol["SPY"] == 10.0


def test_benchmark_service_falls_back_when_sidecar_call_fails(tmp_path: Path) -> None:
    snapshot_store = SnapshotStore(tmp_path / "snapshots")
    _write_snapshots(snapshot_store)
    research = _FakeResearch({"SPY": [{"date": "2026-04-08", "close": 400}]})

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": "service unavailable"})

    adapter = SidecarAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = GhostfolioBenchmarkService(
        snapshot_store=snapshot_store,
        research_service=research,
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/benchmark/compare",
        base_currency="USD",
    )

    result = asyncio.run(service.compare(benchmark_symbols=["SPY"], limit=30))

    assert result.engine_status == "degraded"
    assert result.fallback_method == "local_benchmark_fallback"
    assert any("sidecar unavailable" in warning.lower() for warning in result.warnings)


def test_benchmark_service_skips_sidecar_when_contract_guarded(tmp_path: Path) -> None:
    snapshot_store = SnapshotStore(tmp_path / "snapshots")
    _write_snapshots(snapshot_store)
    research = _FakeResearch(
        {
            "SPY": [
                {"date": "2026-04-08", "close": 400},
                {"date": "2026-04-09", "close": 420},
                {"date": "2026-04-10", "close": 440},
            ]
        }
    )
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(status_code=200, json={})

    adapter = SidecarAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = GhostfolioBenchmarkService(
        snapshot_store=snapshot_store,
        research_service=research,
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/benchmark/compare",
        base_currency="USD",
    )

    result = asyncio.run(
        service.compare(
            benchmark_symbols=["SPY"],
            limit=30,
            sidecar_guard_reason="Sidecar contract version mismatch (expected v1, got v2)",
        )
    )

    assert calls["count"] == 0
    assert result.engine_status == "degraded"
    assert result.fallback_method == "contract_version_guard"
    assert any("sidecar skipped" in warning.lower() for warning in result.warnings)
