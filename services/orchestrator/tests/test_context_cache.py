import time

from buildwealth_orchestrator.services.context_cache import ExpiringCache


def test_expiring_cache_lookup_hit_and_expire() -> None:
    cache = ExpiringCache(max_entries=4)
    cache.set("k1", {"value": 1}, ttl_seconds=0.02)

    hit, value = cache.lookup("k1")
    assert hit is True
    assert value == {"value": 1}

    time.sleep(0.03)
    hit_after, value_after = cache.lookup("k1")
    assert hit_after is False
    assert value_after is None


def test_expiring_cache_evicts_oldest_entry() -> None:
    cache = ExpiringCache(max_entries=2)
    cache.set("a", 1, ttl_seconds=30)
    cache.set("b", 2, ttl_seconds=30)
    cache.set("c", 3, ttl_seconds=30)

    hit_a, _ = cache.lookup("a")
    hit_b, value_b = cache.lookup("b")
    hit_c, value_c = cache.lookup("c")

    assert hit_a is False
    assert hit_b is True
    assert value_b == 2
    assert hit_c is True
    assert value_c == 3
