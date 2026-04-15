"""Runtime telemetry aggregation for latency, context freshness, and cache quality."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import ceil, floor
from threading import Lock
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(float(sorted_values[0]), 2)

    clamped = max(0.0, min(100.0, float(percentile)))
    rank = (clamped / 100.0) * (len(sorted_values) - 1)
    low_idx = floor(rank)
    high_idx = ceil(rank)
    if low_idx == high_idx:
        return round(float(sorted_values[low_idx]), 2)
    low_val = float(sorted_values[low_idx])
    high_val = float(sorted_values[high_idx])
    interp = low_val + (high_val - low_val) * (rank - low_idx)
    return round(interp, 2)


def _round(value: float) -> float:
    return round(float(value), 2)


@dataclass
class _RouteLatencyStats:
    method: str
    path: str
    sample_size: int
    request_count: int = 0
    server_error_count: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    last_status_code: int | None = None
    last_requested_at: datetime | None = None
    latencies_ms: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        self.latencies_ms = deque(maxlen=self.sample_size)

    def record(self, *, latency_ms: float, status_code: int, requested_at: datetime) -> None:
        latency_value = max(0.0, float(latency_ms))
        status = int(status_code)
        self.request_count += 1
        if status >= 500:
            self.server_error_count += 1
        self.total_latency_ms += latency_value
        self.max_latency_ms = max(self.max_latency_ms, latency_value)
        self.last_latency_ms = latency_value
        self.last_status_code = status
        self.last_requested_at = requested_at
        self.latencies_ms.append(latency_value)

    def to_payload(self) -> dict[str, Any]:
        latencies = list(self.latencies_ms)
        avg_latency_ms = (self.total_latency_ms / self.request_count) if self.request_count > 0 else 0.0
        error_rate_pct = (
            (self.server_error_count / self.request_count) * 100.0
            if self.request_count > 0
            else 0.0
        )
        return {
            "method": self.method,
            "path": self.path,
            "request_count": int(self.request_count),
            "server_error_count": int(self.server_error_count),
            "server_error_rate_pct": round(error_rate_pct, 1),
            "avg_latency_ms": _round(avg_latency_ms),
            "p50_latency_ms": _percentile(latencies, 50.0),
            "p95_latency_ms": _percentile(latencies, 95.0),
            "p99_latency_ms": _percentile(latencies, 99.0),
            "max_latency_ms": _round(self.max_latency_ms),
            "last_latency_ms": _round(self.last_latency_ms),
            "last_status_code": self.last_status_code,
            "last_requested_at": self.last_requested_at,
        }


class RuntimeTelemetryTracker:
    """In-memory runtime telemetry tracker for operational dashboard use."""

    def __init__(
        self,
        *,
        route_sample_size: int = 200,
        overall_sample_size: int = 2048,
        max_routes: int = 256,
    ) -> None:
        self._route_sample_size = max(10, int(route_sample_size))
        self._overall_sample_size = max(50, int(overall_sample_size))
        self._max_routes = max(16, int(max_routes))
        self._lock = Lock()
        self._route_stats: dict[str, _RouteLatencyStats] = {}
        self._overall_latencies_ms: deque[float] = deque(maxlen=self._overall_sample_size)
        self._request_count = 0
        self._server_error_count = 0
        self._last_request_at: datetime | None = None
        self._context_snapshot: dict[str, Any] = {
            "as_of": None,
            "last_context_generated_at": None,
            "snapshot_as_of": None,
            "snapshot_age_seconds": None,
            "snapshot_stale": None,
            "snapshot_stale_threshold_seconds": None,
            "coverage_score_pct": None,
            "missing_sections": [],
            "warning_count": 0,
        }

    def reset(self) -> None:
        with self._lock:
            self._route_stats.clear()
            self._overall_latencies_ms.clear()
            self._request_count = 0
            self._server_error_count = 0
            self._last_request_at = None
            self._context_snapshot = {
                "as_of": None,
                "last_context_generated_at": None,
                "snapshot_as_of": None,
                "snapshot_age_seconds": None,
                "snapshot_stale": None,
                "snapshot_stale_threshold_seconds": None,
                "coverage_score_pct": None,
                "missing_sections": [],
                "warning_count": 0,
            }

    def record_api_latency(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
    ) -> None:
        method_value = str(method or "GET").upper()
        path_value = str(path or "/")
        status_value = int(status_code)
        now = utc_now()
        key = f"{method_value} {path_value}"

        with self._lock:
            route = self._route_stats.get(key)
            if route is None:
                if len(self._route_stats) >= self._max_routes:
                    self._evict_oldest_route_locked()
                route = _RouteLatencyStats(
                    method=method_value,
                    path=path_value,
                    sample_size=self._route_sample_size,
                )
                self._route_stats[key] = route

            route.record(
                latency_ms=latency_ms,
                status_code=status_value,
                requested_at=now,
            )
            latency_value = max(0.0, float(latency_ms))
            self._overall_latencies_ms.append(latency_value)
            self._request_count += 1
            if status_value >= 500:
                self._server_error_count += 1
            self._last_request_at = now

    def record_context_payload(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        freshness = quality.get("freshness") if isinstance(quality.get("freshness"), dict) else {}
        coverage = quality.get("coverage") if isinstance(quality.get("coverage"), dict) else {}
        warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
        missing_sections = coverage.get("missing_sections") if isinstance(coverage.get("missing_sections"), list) else []

        snapshot = {
            "as_of": utc_now(),
            "last_context_generated_at": _to_datetime(payload.get("generated_at")),
            "snapshot_as_of": _to_datetime(freshness.get("snapshot_as_of")),
            "snapshot_age_seconds": _coerce_float_or_none(freshness.get("snapshot_age_seconds")),
            "snapshot_stale": _coerce_bool_or_none(freshness.get("snapshot_stale")),
            "snapshot_stale_threshold_seconds": _coerce_float_or_none(
                freshness.get("snapshot_stale_threshold_seconds")
            ),
            "coverage_score_pct": _coerce_float_or_none(coverage.get("score_pct")),
            "missing_sections": [str(item) for item in missing_sections if str(item).strip()],
            "warning_count": len(warnings),
        }

        with self._lock:
            self._context_snapshot = snapshot

    def latency_snapshot(self, *, top_routes: int = 8) -> dict[str, Any]:
        with self._lock:
            latencies = list(self._overall_latencies_ms)
            avg_latency_ms = (sum(latencies) / len(latencies)) if latencies else 0.0
            error_rate_pct = (
                (self._server_error_count / self._request_count) * 100.0
                if self._request_count > 0
                else 0.0
            )
            route_payloads = [item.to_payload() for item in self._route_stats.values()]

            route_payloads.sort(
                key=lambda item: (
                    float(item.get("p95_latency_ms") or 0.0),
                    float(item.get("avg_latency_ms") or 0.0),
                    int(item.get("request_count") or 0),
                ),
                reverse=True,
            )
            route_payloads = route_payloads[: max(1, int(top_routes))]

            return {
                "as_of": utc_now(),
                "request_count": int(self._request_count),
                "server_error_count": int(self._server_error_count),
                "server_error_rate_pct": round(error_rate_pct, 1),
                "window_sample_count": len(latencies),
                "avg_latency_ms": _round(avg_latency_ms),
                "p50_latency_ms": _percentile(latencies, 50.0),
                "p95_latency_ms": _percentile(latencies, 95.0),
                "p99_latency_ms": _percentile(latencies, 99.0),
                "max_latency_ms": _round(max(latencies)) if latencies else 0.0,
                "last_request_at": self._last_request_at,
                "routes": route_payloads,
            }

    def context_snapshot(self) -> dict[str, Any]:
        with self._lock:
            payload = dict(self._context_snapshot)
            missing = payload.get("missing_sections")
            payload["missing_sections"] = list(missing) if isinstance(missing, list) else []
            return payload

    def _evict_oldest_route_locked(self) -> None:
        oldest_key: str | None = None
        oldest_seen: datetime | None = None
        for key, entry in self._route_stats.items():
            seen = entry.last_requested_at
            if oldest_seen is None or (seen is not None and seen < oldest_seen):
                oldest_seen = seen
                oldest_key = key
        if oldest_key is None and self._route_stats:
            oldest_key = next(iter(self._route_stats.keys()))
        if oldest_key is not None:
            self._route_stats.pop(oldest_key, None)


def _coerce_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def summarize_cache_quality(*, enabled: bool, stores: list[dict[str, Any]]) -> dict[str, Any]:
    total_lookup_count = 0
    total_hit_count = 0
    normalized_stores: list[dict[str, Any]] = []

    for store in stores:
        name = str(store.get("name") or "unknown")
        entries = int(store.get("entries") or 0)
        max_entries = max(1, int(store.get("max_entries") or 1))
        lookup_count = int(store.get("lookup_count") or 0)
        hit_count = int(store.get("hit_count") or 0)
        miss_count = int(store.get("miss_count") or 0)
        write_count = int(store.get("write_count") or 0)
        eviction_count = int(store.get("eviction_count") or 0)
        expired_pruned = int(store.get("expired_pruned") or 0)
        hit_rate_pct = float(store.get("hit_rate_pct") or 0.0)

        total_lookup_count += lookup_count
        total_hit_count += hit_count

        utilization_pct = round((entries / max_entries) * 100.0, 1)
        quality_status = "warming"
        if lookup_count <= 0:
            quality_status = "warming"
        elif hit_rate_pct >= 70.0:
            quality_status = "healthy"
        elif hit_rate_pct >= 40.0:
            quality_status = "mixed"
        else:
            quality_status = "cold"

        normalized_stores.append(
            {
                "name": name,
                "max_entries": max_entries,
                "entries": entries,
                "utilization_pct": utilization_pct,
                "lookup_count": lookup_count,
                "hit_count": hit_count,
                "miss_count": miss_count,
                "write_count": write_count,
                "eviction_count": eviction_count,
                "expired_pruned": expired_pruned,
                "hit_rate_pct": round(hit_rate_pct, 1),
                "quality_status": quality_status,
            }
        )

    combined_hit_rate_pct = (
        round((total_hit_count / total_lookup_count) * 100.0, 1)
        if total_lookup_count > 0
        else 0.0
    )

    return {
        "as_of": utc_now(),
        "enabled": bool(enabled),
        "total_lookup_count": int(total_lookup_count),
        "total_hit_count": int(total_hit_count),
        "combined_hit_rate_pct": combined_hit_rate_pct,
        "stores": normalized_stores,
    }
