"""Small in-memory TTL cache for copilot context sub-payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CacheEntry:
    value: Any
    created_at: datetime
    expires_at: datetime


class ExpiringCache:
    def __init__(self, max_entries: int = 128):
        self.max_entries = max(1, int(max_entries))
        self._entries: dict[str, CacheEntry] = {}
        self._reset_counters()

    def _reset_counters(self) -> None:
        self._lookup_count = 0
        self._hit_count = 0
        self._miss_count = 0
        self._write_count = 0
        self._eviction_count = 0
        self._expired_pruned = 0

    def clear(self, *, reset_metrics: bool = True) -> None:
        self._entries.clear()
        if reset_metrics:
            self._reset_counters()

    def lookup(self, key: str) -> tuple[bool, Any]:
        self._lookup_count += 1
        entry = self._entries.get(key)
        if entry is None:
            self._miss_count += 1
            return False, None
        if entry.expires_at <= utc_now():
            self._entries.pop(key, None)
            self._expired_pruned += 1
            self._miss_count += 1
            return False, None
        self._hit_count += 1
        return True, entry.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._write_count += 1
        ttl_value = max(0.0, float(ttl_seconds))
        now = utc_now()
        expires_at = now + timedelta(seconds=ttl_value)

        if key not in self._entries and len(self._entries) >= self.max_entries:
            self._evict_oldest()

        self._entries[key] = CacheEntry(
            value=value,
            created_at=now,
            expires_at=expires_at,
        )

    def prune_expired(self) -> int:
        now = utc_now()
        expired_keys = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)
        expired_count = len(expired_keys)
        self._expired_pruned += expired_count
        return expired_count

    def stats(self) -> dict[str, int | float]:
        self.prune_expired()
        hit_rate_pct = (
            round((self._hit_count / self._lookup_count) * 100.0, 1)
            if self._lookup_count > 0
            else 0.0
        )
        return {
            "max_entries": int(self.max_entries),
            "entries": len(self._entries),
            "lookup_count": int(self._lookup_count),
            "hit_count": int(self._hit_count),
            "miss_count": int(self._miss_count),
            "write_count": int(self._write_count),
            "eviction_count": int(self._eviction_count),
            "expired_pruned": int(self._expired_pruned),
            "hit_rate_pct": hit_rate_pct,
        }

    def _evict_oldest(self) -> None:
        oldest_key: str | None = None
        oldest_created_at: datetime | None = None
        for key, entry in self._entries.items():
            if oldest_created_at is None or entry.created_at < oldest_created_at:
                oldest_created_at = entry.created_at
                oldest_key = key

        if oldest_key is not None:
            self._entries.pop(oldest_key, None)
            self._eviction_count += 1
