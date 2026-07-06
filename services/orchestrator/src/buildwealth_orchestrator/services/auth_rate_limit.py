"""Sliding-window rate limiting for the auth endpoints.

In-memory and per-process on purpose: the production shape is one orchestrator
process behind Caddy, and the goal is blunting credential stuffing and
registration spam, not distributed quota accounting. If the deployment ever
grows multiple processes, this seam is where a shared store would go.

Windows are sliding (timestamps pruned per check), not fixed buckets, so an
attacker can't burst at a bucket boundary.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: float, now: float | None = None) -> tuple[bool, int]:
        """Record an attempt and answer (allowed, retry_after_seconds).

        The attempt is only recorded when allowed — a blocked caller doesn't
        extend their own penalty by retrying.
        """
        moment = time.monotonic() if now is None else now
        cutoff = moment - window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - moment) + 1)
                return False, retry_after
            events.append(moment)
            return True, 0

    def clear(self, key: str) -> None:
        """Forget a key — e.g. failed-login counters reset on success."""
        with self._lock:
            self._events.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._events.clear()
