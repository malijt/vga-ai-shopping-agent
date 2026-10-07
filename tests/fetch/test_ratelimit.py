"""Per-host rate limiter, cooldowns and the clock-based deadline (plan 6.1.3, 6.1.4)."""

import asyncio

import pytest

from tests.fakes import FakeClock
from vga.fetch.deadline import run_with_deadline
from vga.fetch.ratelimit import Cooldowns, RateLimiter


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
