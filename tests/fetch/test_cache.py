"""Result cache (plan 6.5.3)."""

import pytest

from tests.factories import make_store_result
from tests.fakes import FakeClock
from vga.models import StoreStatus
from vga.stores.cache import ResultCache, variant_key


def test_a_miss_returns_nothing(clock: FakeClock) -> None:
    assert ResultCache(clock, 600).get("store-a", "black blazer") is None


def test_a_hit_returns_the_result_marked_from_cache(clock: FakeClock) -> None:
    cache = ResultCache(clock, 600)
    stored = make_store_result(store_id="store-a")
    cache.put("store-a", "black blazer", stored)

    hit = cache.get("store-a", "black blazer")

    assert hit is not None
    assert hit.from_cache is True
    assert hit.products == stored.products
    assert stored.from_cache is False  # the original is untouched


def test_an_entry_expires_after_the_ttl_on_the_injected_clock(clock: FakeClock) -> None:
    cache = ResultCache(clock, 600)
    cache.put("store-a", "black blazer", make_store_result(store_id="store-a"))

    clock.advance(599)
    assert cache.get("store-a", "black blazer") is not None

    clock.advance(2)
    assert cache.get("store-a", "black blazer") is None
    assert len(cache) == 0


def test_the_key_is_store_and_variant(clock: FakeClock) -> None:
    cache = ResultCache(clock, 600)
    cache.put("store-a", "black blazer", make_store_result(store_id="store-a"))

    assert cache.get("store-b", "black blazer") is None
    assert cache.get("store-a", "oversized blazer") is None


def test_case_and_spacing_do_not_make_a_different_variant(clock: FakeClock) -> None:
    cache = ResultCache(clock, 600)
    cache.put("store-a", "Black  Blazer", make_store_result(store_id="store-a"))

    assert cache.get("store-a", " black blazer ") is not None
    assert variant_key("Black  Blazer") == "black blazer"


@pytest.mark.parametrize(
    "status",
    [
        StoreStatus.TIMEOUT,
        StoreStatus.BLOCKED,
        StoreStatus.ROBOTS_DENIED,
        StoreStatus.COOLDOWN,
        StoreStatus.ERROR,
    ],
)
def test_a_failure_is_never_cached(clock: FakeClock, status: StoreStatus) -> None:
    cache = ResultCache(clock, 600)

    cache.put("store-a", "black blazer", make_store_result(status, store_id="store-a"))

    assert cache.get("store-a", "black blazer") is None


def test_an_empty_result_is_cached(clock: FakeClock) -> None:
    cache = ResultCache(clock, 600)
    cache.put("store-a", "xyzzy", make_store_result(StoreStatus.EMPTY, store_id="store-a"))

    hit = cache.get("store-a", "xyzzy")

    assert hit is not None
    assert hit.status is StoreStatus.EMPTY


def test_a_zero_ttl_turns_the_cache_off(clock: FakeClock) -> None:
    cache = ResultCache(clock, 0)

    cache.put("store-a", "black blazer", make_store_result(store_id="store-a"))

    assert cache.get("store-a", "black blazer") is None


def test_the_cache_is_bounded_and_drops_the_oldest_first(clock: FakeClock) -> None:
    cache = ResultCache(clock, 600, max_entries=3)
    for index in range(5):
        cache.put("store-a", f"query {index}", make_store_result(store_id="store-a"))

    assert len(cache) == 3
    assert cache.get("store-a", "query 0") is None
    assert cache.get("store-a", "query 1") is None
    assert cache.get("store-a", "query 4") is not None
