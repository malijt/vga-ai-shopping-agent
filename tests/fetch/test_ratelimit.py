"""Rate limiter (per store or image host), cooldowns and the deadline (plan 6.1.3, 6.1.4)."""

import asyncio
from itertools import pairwise

import pytest

from tests.fakes import FakeClock
from vga.fetch.deadline import run_with_deadline
from vga.fetch.ratelimit import Cooldowns, RateLimiter, SharedLimit


async def test_the_first_request_to_a_host_goes_at_once(clock: FakeClock) -> None:
    limiter = RateLimiter(clock)
    start = clock.monotonic()

    waited = await limiter.acquire("a.example", rps=1)

    assert waited == 0
    assert clock.monotonic() == start


@pytest.mark.parametrize(("count", "rps"), [(2, 1.0), (5, 1.0), (4, 2.0), (6, 5.0)])
async def test_n_requests_take_at_least_n_minus_one_over_rps_seconds(
    clock: FakeClock, count: int, rps: float
) -> None:
    limiter = RateLimiter(clock)
    start = clock.monotonic()

    await asyncio.gather(*(limiter.acquire("a.example", rps) for _ in range(count)))

    assert clock.monotonic() - start >= (count - 1) / rps - 1e-9


async def test_requests_are_spaced_one_interval_apart_even_when_asked_together(
    clock: FakeClock,
) -> None:
    limiter = RateLimiter(clock)
    start = clock.monotonic()
    times: list[float] = []

    async def hit() -> None:
        await limiter.acquire("a.example", rps=2)
        times.append(clock.monotonic() - start)

    await asyncio.gather(hit(), hit(), hit())

    assert times == pytest.approx([0.0, 0.5, 1.0])


async def test_each_host_has_its_own_bucket(clock: FakeClock) -> None:
    limiter = RateLimiter(clock)
    start = clock.monotonic()

    await asyncio.gather(*(limiter.acquire(f"host{i}.example", rps=1) for i in range(5)))

    assert clock.monotonic() == start


async def test_a_busy_host_does_not_delay_another(clock: FakeClock) -> None:
    limiter = RateLimiter(clock)
    start = clock.monotonic()
    finished_at: dict[str, float] = {}

    async def burst(host: str, count: int) -> None:
        for _ in range(count):
            await limiter.acquire(host, rps=1)
        finished_at[host] = clock.monotonic() - start

    await asyncio.gather(burst("slow.example", 4), burst("quick.example", 1))

    assert finished_at["quick.example"] == 0
    assert finished_at["slow.example"] == pytest.approx(3.0)


async def test_a_pause_resets_the_bucket(clock: FakeClock) -> None:
    limiter = RateLimiter(clock)
    await limiter.acquire("a.example", rps=1)
    clock.advance(10)

    waited = await limiter.acquire("a.example", rps=1)

    assert waited == 0


async def test_a_crawl_delay_slows_a_host_but_never_speeds_it_up(clock: FakeClock) -> None:
    limiter = RateLimiter(clock)
    limiter.set_min_interval("slow.example", 4.0)
    start = clock.monotonic()

    await limiter.acquire("slow.example", rps=1)
    await limiter.acquire("slow.example", rps=5)  # asks for 0.2 s, robots.txt says 4 s

    assert clock.monotonic() - start == pytest.approx(4.0)


async def test_a_longer_crawl_delay_is_not_undone_by_a_shorter_one_from_another_host(
    clock: FakeClock,
) -> None:
    """Two hosts of one store share a bucket (``key``); each robots.txt asks for its own delay."""
    limiter = RateLimiter(clock)
    limiter.set_min_interval("store", 4.0, source="www.shop.example")
    limiter.set_min_interval("store", 1.0, source="shop.example")
    start = clock.monotonic()

    await limiter.acquire("store", rps=1)
    await limiter.acquire("store", rps=1)

    assert clock.monotonic() - start == pytest.approx(4.0)


async def test_a_host_can_lower_its_own_crawl_delay(clock: FakeClock) -> None:
    """A robots.txt read again after its day is up may ask for less than it did."""
    limiter = RateLimiter(clock)
    limiter.set_min_interval("store", 4.0, source="www.shop.example")
    limiter.set_min_interval("store", 2.0, source="www.shop.example")
    start = clock.monotonic()

    await limiter.acquire("store", rps=1)
    await limiter.acquire("store", rps=1)

    assert clock.monotonic() - start == pytest.approx(2.0)


# --------------------------------------------------------------------------------------------
# A limit shared by several keys (the stores of one platform)
# --------------------------------------------------------------------------------------------

PLATFORM = SharedLimit("platform:test", rps=2.0)


def platform_limiter(clock: FakeClock, *members: str, limit: SharedLimit = PLATFORM) -> RateLimiter:
    """A limiter in which the keys ``members`` share ``limit`` and every other key is on its own."""
    return RateLimiter(clock, group_of=lambda key: limit if key in members else None)


async def send_times(
    clock: FakeClock, limiter: RateLimiter, keys: list[str], rps: float = 1.0
) -> list[float]:
    """When, relative to now, each of ``keys`` got its slot, all asking at the same moment."""
    start = clock.monotonic()
    times: list[float] = []

    async def hit(key: str) -> None:
        await limiter.acquire(key, rps)
        times.append(clock.monotonic() - start)

    await asyncio.gather(*(hit(key) for key in keys))
    return sorted(times)


async def test_keys_that_share_a_limit_are_spaced_by_it_whichever_key_asks(
    clock: FakeClock,
) -> None:
    keys = [f"store-{i}" for i in range(5)]
    limiter = platform_limiter(clock, *keys)

    times = await send_times(clock, limiter, keys)

    assert times == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])


async def test_without_a_shared_limit_separate_keys_do_not_slow_each_other(
    clock: FakeClock,
) -> None:
    keys = [f"store-{i}" for i in range(5)]

    times = await send_times(clock, RateLimiter(clock), keys)

    assert times == [0.0] * 5


async def test_a_key_outside_the_shared_limit_is_not_held_up_by_it(clock: FakeClock) -> None:
    members = [f"store-{i}" for i in range(4)]
    limiter = platform_limiter(clock, *members)

    times = await send_times(clock, limiter, [*members, "host:cdn.example"])

    assert times == pytest.approx([0.0, 0.0, 0.5, 1.0, 1.5])  # the CDN went at once


async def test_two_shared_limits_do_not_slow_each_other(clock: FakeClock) -> None:
    other = SharedLimit("platform:other", rps=2.0)
    limiter = RateLimiter(clock, group_of=lambda key: PLATFORM if key.startswith("a-") else other)

    times = await send_times(clock, limiter, ["a-1", "a-2", "b-1", "b-2"])

    assert times == pytest.approx([0.0, 0.0, 0.5, 0.5])


async def test_each_key_keeps_its_own_rate_inside_a_faster_shared_limit(clock: FakeClock) -> None:
    limiter = platform_limiter(clock, "slow", "quick", limit=SharedLimit("fast", rps=10.0))
    start = clock.monotonic()
    slow: list[float] = []

    async def hit_slow() -> None:
        await limiter.acquire("slow", rps=1)
        slow.append(clock.monotonic() - start)

    await asyncio.gather(*(hit_slow() for _ in range(3)), limiter.acquire("quick", rps=1))

    assert slow == pytest.approx([0.0, 1.0, 2.0])  # one a second, though the platform allows ten


async def test_both_limits_hold_at_once_for_any_mix_of_requests(clock: FakeClock) -> None:
    """The guard behind the rest: on a busy queue no two requests of one key are closer than the
    key's interval and no two of the whole platform are closer than the platform's."""
    keys = ["a", "b", "c"]
    limiter = platform_limiter(clock, *keys, limit=SharedLimit("p", rps=2.0))
    start = clock.monotonic()
    sent: list[tuple[float, str]] = []

    async def worker(key: str, count: int) -> None:
        for _ in range(count):
            await limiter.acquire(key, rps=1)
            sent.append((clock.monotonic() - start, key))
            await clock.sleep(0.1)  # the request itself takes a moment

    await asyncio.gather(worker("a", 4), worker("b", 3), worker("c", 2))

    everyone = sorted(time for time, _ in sent)
    assert len(everyone) == 9
    assert all(later - earlier >= 0.5 - 1e-9 for earlier, later in pairwise(everyone))
    for key in keys:
        mine = sorted(time for time, owner in sent if owner == key)
        assert all(later - earlier >= 1.0 - 1e-9 for earlier, later in pairwise(mine))


async def test_every_key_gets_its_first_slot_before_any_key_gets_its_second(
    clock: FakeClock,
) -> None:
    keys = [f"store-{i}" for i in range(4)]
    limiter = platform_limiter(clock, *keys)
    start = clock.monotonic()
    order: list[tuple[str, int]] = []

    async def two_requests(key: str) -> None:
        for number in (1, 2):
            await limiter.acquire(key, rps=1)
            order.append((key, number))

    await asyncio.gather(*(two_requests(key) for key in keys))

    assert [number for _key, number in order] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert clock.monotonic() - start == pytest.approx(3.5)  # eight requests, 0.5 s apart


async def test_a_key_that_is_not_ready_does_not_hold_the_shared_queue_up(clock: FakeClock) -> None:
    """A store with a long Crawl-delay waits for its own sake; the stores behind it still go."""
    limiter = platform_limiter(clock, "careful", "other")
    limiter.set_min_interval("careful", 5.0)
    start = clock.monotonic()
    other: list[float] = []

    async def careful() -> None:
        await limiter.acquire("careful", rps=1)
        await limiter.acquire("careful", rps=1)  # five seconds after the first

    async def hurried() -> None:
        for _ in range(3):
            await limiter.acquire("other", rps=1)
            other.append(clock.monotonic() - start)

    await asyncio.gather(careful(), hurried())

    assert other == pytest.approx([0.5, 1.5, 2.5])


async def test_a_request_cancelled_while_it_waits_gives_its_slot_back(clock: FakeClock) -> None:
    limiter = platform_limiter(clock, "a", "b", "c")
    await limiter.acquire("a", rps=1)
    waiting = asyncio.ensure_future(limiter.acquire("b", rps=1))
    await asyncio.sleep(0)
    assert not waiting.done()  # b holds the slot at 0.5 s

    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    start = clock.monotonic()
    waited = await limiter.acquire("c", rps=1)

    assert waited == pytest.approx(0.5)  # the next free slot, not one behind the cancelled request
    assert clock.monotonic() - start == pytest.approx(0.5)


# --------------------------------------------------------------------------------------------
# Cooldowns
# --------------------------------------------------------------------------------------------


def test_a_key_is_free_until_a_cooldown_starts(clock: FakeClock) -> None:
    cooldowns = Cooldowns(clock, 900)

    assert cooldowns.remaining("store-a") == 0


def test_a_cooldown_counts_down_and_ends(clock: FakeClock) -> None:
    cooldowns = Cooldowns(clock, 900)
    cooldowns.start("store-a")

    clock.advance(100)
    assert cooldowns.remaining("store-a") == pytest.approx(800)

    clock.advance(800)
    assert cooldowns.remaining("store-a") == 0


def test_cooldowns_are_per_key(clock: FakeClock) -> None:
    cooldowns = Cooldowns(clock, 900)
    cooldowns.start("store-a")

    assert cooldowns.remaining("store-a") > 0
    assert cooldowns.remaining("store-b") == 0


def test_a_zero_duration_disables_cooldowns(clock: FakeClock) -> None:
    cooldowns = Cooldowns(clock, 0)
    cooldowns.start("store-a")

    assert cooldowns.remaining("store-a") == 0


# --------------------------------------------------------------------------------------------
# Deadline
# --------------------------------------------------------------------------------------------


async def test_work_that_finishes_in_time_returns_its_value(clock: FakeClock) -> None:
    async def work() -> str:
        await clock.sleep(2)
        return "done"

    assert await run_with_deadline(clock, 6, work()) == "done"


async def test_work_that_takes_too_long_is_cancelled_after_the_deadline(clock: FakeClock) -> None:
    started = clock.monotonic()
    cancelled = False

    async def work() -> None:
        nonlocal cancelled
        try:
            await clock.sleep(100)
        except asyncio.CancelledError:
            cancelled = True
            raise

    with pytest.raises(TimeoutError):
        await run_with_deadline(clock, 6, work())

    assert clock.monotonic() - started == pytest.approx(6)
    assert cancelled


async def test_an_error_in_the_work_comes_through_unchanged(clock: FakeClock) -> None:
    async def work() -> None:
        msg = "boom"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="boom"):
        await run_with_deadline(clock, 6, work())


async def test_cancelling_the_caller_cancels_the_work(clock: FakeClock) -> None:
    cancelled = False

    async def work() -> None:
        nonlocal cancelled
        try:
            await clock.sleep(100)
        except asyncio.CancelledError:
            cancelled = True
            raise

    task = asyncio.ensure_future(run_with_deadline(clock, 50, work()))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled
