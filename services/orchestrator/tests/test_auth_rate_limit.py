from __future__ import annotations

from buildwealth_orchestrator.services.auth_rate_limit import SlidingWindowRateLimiter


def test_sliding_window_allows_then_blocks_then_recovers() -> None:
    limiter = SlidingWindowRateLimiter()
    for i in range(3):
        allowed, retry_after = limiter.allow("k", limit=3, window_seconds=60, now=float(i))
        assert allowed is True
        assert retry_after == 0

    blocked, retry_after = limiter.allow("k", limit=3, window_seconds=60, now=10.0)
    assert blocked is False
    assert retry_after >= 1

    # The window slides: once the oldest attempt ages out, room opens.
    allowed, _ = limiter.allow("k", limit=3, window_seconds=60, now=61.0)
    assert allowed is True


def test_blocked_attempts_do_not_extend_the_penalty() -> None:
    limiter = SlidingWindowRateLimiter()
    for i in range(3):
        limiter.allow("k", limit=3, window_seconds=60, now=float(i))
    # Hammering while blocked doesn't push the recovery time out.
    for now in (5.0, 20.0, 40.0):
        allowed, _ = limiter.allow("k", limit=3, window_seconds=60, now=now)
        assert allowed is False
    allowed, _ = limiter.allow("k", limit=3, window_seconds=60, now=60.5)
    assert allowed is True


def test_clear_resets_a_single_key() -> None:
    limiter = SlidingWindowRateLimiter()
    for i in range(3):
        limiter.allow("a", limit=3, window_seconds=60, now=float(i))
        limiter.allow("b", limit=3, window_seconds=60, now=float(i))
    limiter.clear("a")
    assert limiter.allow("a", limit=3, window_seconds=60, now=4.0)[0] is True
    assert limiter.allow("b", limit=3, window_seconds=60, now=4.0)[0] is False
