"""BRD Rule 2 on a shared platform: "too many requests" (HTTP 429) from one store stops them all.

On 2026-10-08 thirteen Shopify shops answered 429 within 11 milliseconds of each other. That is the
platform counting per client, so a 429 from any store of a platform is the platform's answer: every
store on it goes into cooldown at once, the requests still queued for it are dropped unsent, and
nothing more goes to any of them until the cooldown ends. The cooldown is at least as long as the
``Retry-After`` the answer names. A 403, a challenge page or a login wall stays that one store's
matter (``test_block_policy.py``).

Each test runs the real pipeline and the real store engine against fake stores that are all Shopify
storefronts, so all on one platform, on the ``FakeClock``.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from tests.factories import make_search_request
from tests.fakes import FakeClock
from tests.guards.scraping.support import (
    GuardPipelines,
    GuardWorld,
    Reply,
    reply_status,
    understanding,
    understanding_by_words,
)
from tests.pipeline.builders import BLAZER, OUTFIT, SHIRT, outfit_understander
from tests.pipeline.world import store_for
from vga.models import StoreStatus
from vga.pipeline import messages
from vga.settings import Settings

JARGON = ("http", "429", "too many", "retry", "platform", "queue", "robots")
"""Words that mean something to an engineer and nothing to a shopper."""

SHOPS = tuple(f"shop{number:02d}" for number in range(13))
"""As many stores as the app ships, all on one platform."""


def too_many(**headers: str) -> Reply:
    return reply_status(429, **headers)


def asked_nothing(world: GuardWorld, hosts: tuple[str, ...], *, since: dict[str, int]) -> bool:
    return all(world.requests_to(host) == since[host] for host in hosts)


def sent_so_far(world: GuardWorld, hosts: tuple[str, ...]) -> dict[str, int]:
    return {host: world.requests_to(host) for host in hosts}


# --------------------------------------------------------------------------------------------
# The store that is refused
# --------------------------------------------------------------------------------------------


async def test_a_store_that_answers_429_gets_exactly_one_search_request_and_no_retry(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), reply=too_many(**{"Retry-After": "1"}))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))  # two keyword variants to tempt a retry

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 1  # not the second variant, not a second try
    assert world.requests_to("alpha.example") == 2  # robots.txt, then the one refused search
    assert world.stray == []


async def test_the_store_is_reported_blocked_in_plain_words(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), reply=too_many())
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    skipped = {report.store_id: report for report in response.stores_skipped}
    assert skipped["alpha"].status is StoreStatus.BLOCKED
    assert skipped["alpha"].reason == messages.store_reason(StoreStatus.BLOCKED)
    assert messages.store_warning("Alpha", StoreStatus.BLOCKED) in response.warnings
    shopper_text = " ".join([*(r.reason or "" for r in skipped.values()), *response.warnings])
    assert [word for word in JARGON if word in shopper_text.lower()] == []


# --------------------------------------------------------------------------------------------
# The other stores of the platform
# --------------------------------------------------------------------------------------------


async def test_a_429_from_one_store_sends_nothing_further_to_a_store_beside_it(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), reply=too_many())
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    # Beta's robots.txt had gone out before Alpha was refused; its search was queued behind
    # Alpha's, and was dropped unsent.
    assert world.queries("beta") == []
    assert world.requests_to("beta.example") == 1
    skipped = {report.store_id: report.status for report in response.stores_skipped}
    assert skipped == {"alpha": StoreStatus.BLOCKED, "beta": StoreStatus.COOLDOWN}
    assert messages.store_warning("Beta", StoreStatus.COOLDOWN) in response.warnings
    assert response.result_count == 0
    assert world.stray == []


async def test_one_429_among_thirteen_stores_sends_not_one_more_search_to_any_of_them(
    world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    world.add(store_for(SHOPS[0]), reply=too_many())
    for key in SHOPS[1:]:
        world.add(store_for(key))
    pipeline = build(understander=understanding(BLAZER))
    started = clock.monotonic()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    # Thirteen robots.txt files were asked for first, half a second apart; then the first search in
    # line, at 6.5 s, was refused. The twelve searches queued behind it were dropped there and then:
    # the search ended at once instead of waiting out their turns.
    assert world.search_requests() == 1
    assert clock.monotonic() - started == pytest.approx(6.5)
    assert [report.store_id for report in response.stores_skipped] == list(SHOPS)
    assert {report.status for report in response.stores_skipped} == {
        StoreStatus.BLOCKED,
        StoreStatus.COOLDOWN,
    }
    assert world.stray == []


async def test_the_whole_platform_is_left_alone_for_the_cooldown_and_then_asked_again(
    world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    world.add(store_for(SHOPS[0]), reply=too_many())
    for key in SHOPS[1:]:
        world.add(store_for(key))
    pipeline = build(understander=understanding_by_words({"blazer": BLAZER, "shirt": SHIRT}))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    hosts = tuple(f"{key}.example" for key in SHOPS)
    before = sent_so_far(world, hosts)
    clock.advance(settings.store_cooldown_s / 2)  # well inside the cooldown

    same = await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    other = await pipeline.run(make_search_request(text="white cotton shirt"), settings)

    # Not a search, not a robots.txt, to any store, whatever the second search was for.
    assert asked_nothing(world, hosts, since=before)
    for response in (same, other):
        assert len(response.stores_skipped) == len(SHOPS)
        assert response.stores_used == []
        assert {r.status for r in response.stores_skipped} <= {
            StoreStatus.COOLDOWN,
            StoreStatus.BLOCKED,
        }
    assert world.stray == []

    clock.advance(settings.store_cooldown_s)  # now the cooldown has ended
    await pipeline.run(make_search_request(text="white cotton shirt"), settings)

    # One honest request goes out again, the first store's, which is refused again: so the other
    # twelve, still queued behind it, are dropped once more.
    assert world.search_requests() == 2
    assert world.requests_to(f"{SHOPS[0]}.example") == before[f"{SHOPS[0]}.example"] + 1


async def test_the_first_search_after_the_cooldown_is_one_honest_request_not_a_burst_retry(
    world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    world.add(store_for("alpha"), reply=too_many())
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    searches_before = len(world.queries("alpha"))
    clock.advance(settings.store_cooldown_s + 1)

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == searches_before + 1


async def test_an_outfit_photo_stops_for_every_store_at_the_first_refusal(
    world: GuardWorld, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    world.add(store_for("alpha"), reply=too_many())
    world.add(store_for("beta"))
    pipeline = build(understander=outfit_understander())

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    # Four garments were searched at once in both stores. The first refusal ended all eight.
    assert len(OUTFIT) == 4
    assert len(world.queries("alpha")) == 1
    assert world.queries("beta") == []
    assert world.requests_to("alpha.example") == 2
    assert {report.store_id for report in response.stores_skipped} == {"alpha", "beta"}
    assert response.result_count == 0


async def test_a_429_on_robots_txt_stops_the_platform_before_any_search_is_sent(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots=too_many())
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.requests_to("alpha.example") == 1  # the robots.txt that was refused
    assert world.requests_to("beta.example") == 0  # its robots.txt was still queued: dropped
    assert world.search_requests() == 0
    assert {r.store_id: r.status for r in response.stores_skipped} == {
        "alpha": StoreStatus.BLOCKED,
        "beta": StoreStatus.COOLDOWN,
    }
    assert world.stray == []


# --------------------------------------------------------------------------------------------
# Other refusals stay with the store
# --------------------------------------------------------------------------------------------


async def test_a_403_from_one_store_does_not_stop_the_others(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), reply=reply_status(403))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert [r.store_id for r in response.stores_used] == ["beta"]
    assert {r.store_id: r.status for r in response.stores_skipped} == {"alpha": StoreStatus.BLOCKED}
    assert len(world.queries("beta")) == 1


# --------------------------------------------------------------------------------------------
# Retry-After
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seconds", [3600, 7200])
async def test_the_cooldown_lasts_at_least_as_long_as_retry_after_in_seconds(
    seconds: int,
    world: GuardWorld,
    build: GuardPipelines,
    settings: Settings,
    clock: FakeClock,
) -> None:
    world.add(store_for("alpha"), reply=too_many(**{"Retry-After": str(seconds)}))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    before = world.all_requests()

    clock.advance(settings.store_cooldown_s + 60)  # past the usual cooldown, not past the ask
    still_waiting = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert seconds > settings.store_cooldown_s + 60
    assert world.all_requests() == before
    assert len(still_waiting.stores_skipped) == 2

    clock.advance(seconds)  # now it is over
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.all_requests() > before


async def test_the_cooldown_lasts_at_least_as_long_as_a_retry_after_date(
    world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    in_two_hours = format_datetime(datetime.now(UTC) + timedelta(hours=2), usegmt=True)
    world.add(store_for("alpha"), reply=too_many(**{"Retry-After": in_two_hours}))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    before = world.all_requests()

    clock.advance(3600)  # an hour: past the usual cooldown, well short of the two hours asked

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.all_requests() == before


async def test_a_retry_after_shorter_than_the_usual_cooldown_does_not_shorten_it(
    world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    world.add(store_for("alpha"), reply=too_many(**{"Retry-After": "1"}))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    before = world.all_requests()
    clock.advance(60)  # far longer than the one second asked for, far shorter than the cooldown

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.all_requests() == before


async def test_the_retry_after_is_written_to_the_log(
    world: GuardWorld,
    build: GuardPipelines,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="vga")
    world.add(store_for("alpha"), reply=too_many(**{"Retry-After": "120"}))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    [record] = [r for r in caplog.records if "too many requests" in r.getMessage()]
    assert record.__dict__["retry_after"] == "120"
    assert record.__dict__["retry_after_s"] == 120.0
    assert record.__dict__["platform"] == "platform:shopify"
    assert record.__dict__["store"] == "alpha"
    assert record.__dict__["dropped_requests"] >= 1
