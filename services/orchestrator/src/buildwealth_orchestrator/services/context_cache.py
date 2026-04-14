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

    def clear(self) -> None:
        self._entries.clear()

    def lookup(self, key: str) -> tuple[bool, Any]:
        entry = self._entries.get(key)
        if entry is None:
            return False, None
        if entry.expires_at <= utc_now():
            self._entries.pop(key, None)
            return False, None
        return True, entry.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
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

    def _evict_oldest(self) -> None:
        oldest_key: str | None = None
        oldest_created_at: datetime | None = None
        for key, entry in self._entries.items():
            if oldest_created_at is None or entry.created_at < oldest_created_at:
                oldest_created_at = entry.created_at
                oldest_key = key

        if oldest_key is not None:
            self._entries.pop(oldest_key, None)
