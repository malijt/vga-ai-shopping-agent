"""BRD Rule 2, spend the waiting where nobody waits: at start-up the pipeline reads the robots.txt
of every store it will search, through the same queue as any request, so the first search does not
pay for thirteen extra requests (6.5 s at the platform's two a second).

The real pipeline and the real store engine against fake stores on the ``FakeClock``. Reading
robots.txt early changes nothing about what is allowed: the verdicts are cached exactly as a search
would have cached them, a file that cannot be read still means "everything disallowed", and a block
is a block (it starts its cooldown). ``warm_up()`` never raises because of a store.
"""

import pytest

from tests.factories import make_search_request
from tests.fakes import FakeClock
from tests.guards.scraping.support import (
    GuardPipelines,
    GuardWorld,
    gaps,
    reply_status,
    understanding,
)
from tests.pipeline.builders import BLAZER
from tests.pipeline.world import store_for
from vga.models import StoreStatus
from vga.pipeline import messages
from vga.settings import Settings

SHOPS = tuple(f"shop{number:02d}" for number in range(13))


def robots_total(world: GuardWorld) -> int:
    return sum(len(times) for times in world.robots_times.values())


@pytest.fixture
def thirteen(world: GuardWorld) -> None:
    for key in SHOPS:
        world.add(store_for(key))


async def test_warm_up_reads_every_stores_robots_txt_once_and_nothing_else(
    world: GuardWorld, thirteen: None, build: GuardPipelines
) -> None:
    pipeline = build(understander=understanding(BLAZER))

    ready = await pipeline.warm_up()

    assert ready is True  # the image ranker's answer is unchanged
    assert [world.robots_times.get(f"{key}.example", []) != [] for key in SHOPS] == [True] * 13
    assert robots_total(world) == 13
    assert world.search_requests() == 0
    assert world.thumbnails == []
    assert world.stray == []


async def test_warm_up_goes_through_the_platform_queue_half_a_second_apart(
    world: GuardWorld, thirteen: None, build: GuardPipelines, clock: FakeClock
) -> None:
    pipeline = build(understander=understanding(BLAZER))
    started = clock.monotonic()

    await pipeline.warm_up()

    everything = sorted(t for times in world.robots_times.values() for t in times)
    assert everything == pytest.approx([started + 0.5 * n for n in range(13)])
    assert all(gap >= 0.5 - 1e-9 for gap in gaps(everything))
    # Every store's first request goes before any store's second (here, no second exists).
    assert clock.monotonic() - started == pytest.approx(6.0)


async def test_the_first_search_after_warm_up_asks_for_no_robots_txt(
    world: GuardWorld,
    thirteen: None,
    build: GuardPipelines,
    settings: Settings,
    clock: FakeClock,
) -> None:
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.warm_up()
    robots_before = robots_total(world)
    clock.advance(60)  # the shopper opens the page a minute later
    started = clock.monotonic()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert robots_total(world) == robots_before == 13  # read once, at start-up
    assert world.search_requests() == 13  # one search a store: nothing else was sent
    assert len(response.stores_used) == 13
    # Thirteen searches at two a second, none of them waiting behind a robots.txt: 6 s, not 12.5.
    assert clock.monotonic() - started == pytest.approx(6.0)
    assert world.stray == []


async def test_without_warm_up_the_first_search_pays_for_the_robots_txt_files(
    world: GuardWorld,
    thirteen: None,
    build: GuardPipelines,
    settings: Settings,
    clock: FakeClock,
) -> None:
    pipeline = build(understander=understanding(BLAZER))
    started = clock.monotonic()

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert robots_total(world) == 13
    assert clock.monotonic() - started == pytest.approx(12.5)  # 26 requests, 0.5 s apart


async def test_warming_up_twice_asks_nothing_the_second_time(
    world: GuardWorld, thirteen: None, build: GuardPipelines
) -> None:
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.warm_up()

    await pipeline.warm_up()

    assert robots_total(world) == 13


async def test_a_robots_txt_that_cannot_be_read_does_not_stop_warm_up_and_stays_disallowed(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots=reply_status(500))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    ready = await pipeline.warm_up()  # does not raise

    assert ready is True
    assert robots_total(world) == 2
    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    # As in any search, an unreadable robots.txt means "everything disallowed" (RFC 9309), and it
    # is not asked for again: Alpha got its one robots.txt request, at start-up, and nothing since.
    assert world.requests_to("alpha.example") == 1
    assert world.queries("alpha") == []
    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("alpha", StoreStatus.ROBOTS_DENIED)
    assert [report.store_id for report in response.stores_used] == ["beta"]


async def test_a_robots_txt_that_forbids_the_search_is_honoured_after_warm_up(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots="User-agent: *\nDisallow: /search\n")
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.warm_up()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.queries("alpha") == []
    assert world.requests_to("alpha.example") == 1
    assert [(r.store_id, r.status) for r in response.stores_skipped] == [
        ("alpha", StoreStatus.ROBOTS_DENIED)
    ]


async def test_a_429_during_warm_up_stops_the_platform_and_warm_up_still_returns(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots=reply_status(429, **{"Retry-After": "600"}))
    world.add(store_for("beta"))
    world.add(store_for("gamma"))
    pipeline = build(understander=understanding(BLAZER))

    ready = await pipeline.warm_up()  # does not raise

    assert ready is True
    assert world.requests_to("alpha.example") == 1
    assert world.requests_to("beta.example") == 0  # still queued behind Alpha's: dropped unsent
    assert world.requests_to("gamma.example") == 0
    sent = world.all_requests()
    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    assert world.all_requests() == sent  # the platform is left alone for its cooldown
    assert {r.store_id: r.status for r in response.stores_skipped} == {
        "alpha": StoreStatus.COOLDOWN,
        "beta": StoreStatus.COOLDOWN,
        "gamma": StoreStatus.COOLDOWN,
    }
    assert messages.store_warning("Beta", StoreStatus.COOLDOWN) in response.warnings


async def test_a_disabled_store_is_not_asked_for_its_robots_txt(
    world: GuardWorld, build: GuardPipelines
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("off", enabled=False))
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.warm_up()

    assert world.requests_to("alpha.example") == 1
    assert world.requests_to("off.example") == 0
