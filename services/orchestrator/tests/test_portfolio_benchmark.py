import asyncio
from datetime import datetime, timezone
from pathlib import Path

from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_benchmark import BuildWealthBenchmarkService
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


def test_benchmark_service_computes_native_comparison(tmp_path: Path) -> None:
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

    service = BuildWealthBenchmarkService(
        snapshot_store=snapshot_store,
        research_service=research,
        base_currency="USD",
    )

    result = asyncio.run(service.compare(benchmark_symbols=["SPY"], limit=30))

    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.summary.portfolio_return_pct == 20.0
    assert result.summary.benchmark_return_pct_by_symbol["SPY"] == 10.0
    assert len(result.series) == 3


def test_benchmark_service_uses_flat_index_when_benchmark_history_is_missing(tmp_path: Path) -> None:
    snapshot_store = SnapshotStore(tmp_path / "snapshots")
    _write_snapshots(snapshot_store)
    research = _FakeResearch({})

    service = BuildWealthBenchmarkService(
        snapshot_store=snapshot_store,
        research_service=research,
        base_currency="USD",
    )

    result = asyncio.run(service.compare(benchmark_symbols=["SPY"], limit=30))

    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.summary.benchmark_return_pct_by_symbol["SPY"] == 0.0
    assert result.summary.alpha_pct_by_symbol["SPY"] == 20.0
