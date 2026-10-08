"""HTTP 429 ("too many requests") from one store is the whole platform's answer.

On 2026-10-08 thirteen Shopify shops answered 429 within 11 milliseconds of each other: the
platform counts requests per client, not per shop. So when any store of a platform answers 429,
every store on that platform goes into cooldown at once, the requests still queued for the
platform are dropped unsent, and the cooldown is at least as long as the ``Retry-After`` the answer
names. A 403, a challenge page or a login wall stays that one store's matter. Nothing here
retries: the client makes the one request that was asked for and reports what came back.

(The same rules, seen through the whole pipeline, are in ``tests/guards/scraping``.)
"""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest
import respx

from tests.factories import make_settings
from tests.fakes import FakeClock
from tests.fetch.conftest import text_response
from tests.fetch.platforms import FakeShops, get, shopify, store_on
from vga.fetch import BlockedError, CooldownError, PoliteClient
from vga.fetch.blocking import MAX_RETRY_AFTER_S, parse_retry_after
from vga.fetch.ratelimit import Cooldowns, RateLimiter, RequestDropped, SharedLimit

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def shops(router: respx.MockRouter, clock: FakeClock) -> FakeShops:
    return FakeShops(router, clock)


def client_at(clock: FakeClock, **settings: Any) -> PoliteClient:
    return PoliteClient(make_settings(**settings), clock=clock, wall_clock=lambda: NOW)


# --------------------------------------------------------------------------------------------
# The whole platform stops
# --------------------------------------------------------------------------------------------


async def test_a_429_puts_every_store_of_the_platform_in_cooldown_at_once(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shops.refuse("one", 429)

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    for key in ("one", "two", "three"):  # two and three were never asked
        assert client.cooldown_remaining(shopify(key)) == pytest.approx(900)


async def test_a_store_cooling_with_its_platform_is_sent_no_request(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shops.refuse("one", 429)
    with pytest.raises(BlockedError):
        await get(client, shopify("one"))
    sent_before = len(shops.arrivals)

    with pytest.raises(CooldownError):
        await get(client, shopify("two"))
    with pytest.raises(CooldownError):
        await get(client, shopify("three"), "/anything-else")

    assert len(shops.arrivals) == sent_before


async def test_the_platform_is_asked_again_when_the_cooldown_ends(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock, store_cooldown_s=900)
    shops.refuse("one", 429)
    with pytest.raises(BlockedError):
        await get(client, shopify("one"))
    clock.advance(901)

    await get(client, shopify("two"))

    assert len(shops.times("two.example")) == 1  # a request really went out


async def test_requests_queued_for_the_platform_are_dropped_unsent_and_at_once(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shops.refuse("one", 429)
    queued = [shopify(f"queued{number}") for number in range(4)]
    started = clock.monotonic()

    results = await asyncio.gather(
        get(client, shopify("one")),
        *(get(client, store) for store in queued),
        return_exceptions=True,
    )

    assert isinstance(results[0], BlockedError)
    assert all(isinstance(result, CooldownError) for result in results[1:])
    assert [url for url, _time in shops.arrivals] == ["https://one.example/p"]  # nobody else's
    assert clock.monotonic() == started  # and nobody sat out a wait for a slot it would not use


async def test_dropped_requests_leave_no_delay_behind_for_when_the_platform_is_asked_again(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock, store_cooldown_s=900)
    shops.refuse("one", 429)
    await asyncio.gather(
        get(client, shopify("one")), get(client, shopify("two")), return_exceptions=True
    )
    clock.advance(901)
    started = clock.monotonic()

    await get(client, shopify("three"))

    assert clock.monotonic() == started  # the slots of the dropped requests were given back


async def test_a_429_in_the_middle_of_a_redirect_chain_stops_the_platform_too(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shop = shopify("one")
    shops.answer(
        "one.example",
        lambda request: (
            httpx.Response(302, headers={"location": "/next"})
            if request.url.path == "/p"
            else httpx.Response(429)
        ),
    )

    with pytest.raises(BlockedError):
        await get(client, shop)

    assert client.cooldown_remaining(shopify("two")) > 0


# --------------------------------------------------------------------------------------------
# What stays one store's matter
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
async def test_a_401_or_403_is_that_stores_matter_alone(
    status: int, clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shops.refuse("one", status)

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    assert client.cooldown_remaining(shopify("one")) > 0
    assert client.cooldown_remaining(shopify("two")) == 0
    await get(client, shopify("two"))  # still welcome


async def test_a_login_wall_and_a_challenge_page_stay_with_their_store(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shops.answer(
        "one.example", lambda _r: httpx.Response(302, headers={"location": "/account/login"})
    )
    shops.answer(
        "two.example",
        lambda _r: text_response("<title>Just a moment...</title>", content_type="text/html"),
    )

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))
    with pytest.raises(BlockedError):
        await get(client, shopify("two"))

    assert client.cooldown_remaining(shopify("three")) == 0


async def test_a_429_from_a_store_on_another_platform_does_not_stop_the_shopify_stores(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shops.refuse("plain", 429)
    plain = store_on("store_json", "plain")

    with pytest.raises(BlockedError):
        await get(client, plain)

    assert client.cooldown_remaining(plain) > 0
    assert client.cooldown_remaining(shopify("shop")) == 0


async def test_a_429_from_the_image_host_is_the_image_hosts_matter_not_the_platforms(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shop = shopify("shop")
    shops.answer("cdn.shopify.com", lambda _r: httpx.Response(429))

    with pytest.raises(BlockedError):
        await client.fetch(
            "https://cdn.shopify.com/i.jpg",
            shop,
            client.image_policy(shop, "cdn.shopify.com", timeout_s=4),
        )

    assert client.cooldowns.remaining("host:cdn.shopify.com") > 0
    assert client.cooldown_remaining(shop) == 0
    assert client.cooldown_remaining(shopify("other")) == 0


async def test_a_429_for_a_thumbnail_on_the_stores_own_host_stops_the_platform(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock)
    shop = shopify("shop")
    shops.refuse("shop", 429)

    with pytest.raises(BlockedError):
        await client.fetch(
            "https://shop.example/thumb.jpg",
            shop,
            client.image_policy(shop, "shop.example", timeout_s=4),
        )

    assert client.cooldown_remaining(shopify("other")) > 0


# --------------------------------------------------------------------------------------------
# Retry-After
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("3600", 3600),
        ("1800", 1800),
        (format_datetime(NOW + timedelta(hours=2), usegmt=True), 7200),
        ("Thu, 08 Oct 2026 14:00:00 GMT", 7200),
    ],
    ids=["seconds", "seconds-over-default", "date", "date-literal"],
)
async def test_the_cooldown_is_the_retry_after_when_that_is_longer_than_the_default(
    header: str, expected: float, clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock, store_cooldown_s=900)
    shops.refuse("one", 429, **{"Retry-After": header})

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    assert client.cooldown_remaining(shopify("one")) == pytest.approx(expected)
    assert client.cooldown_remaining(shopify("two")) == pytest.approx(expected)


@pytest.mark.parametrize(
    "header",
    ["30", "0", "-5", "soon", "", "Thu, 08 Oct 2026 11:00:00 GMT", "12abc"],
    ids=["short", "zero", "negative", "words", "empty", "past-date", "mixed"],
)
async def test_a_retry_after_that_asks_for_less_or_makes_no_sense_leaves_the_default(
    header: str, clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock, store_cooldown_s=900)
    shops.refuse("one", 429, **{"Retry-After": header})

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    assert client.cooldown_remaining(shopify("two")) == pytest.approx(900)


async def test_a_429_without_a_retry_after_uses_the_default_cooldown(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = client_at(clock, store_cooldown_s=600)
    shops.refuse("one", 429)

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    assert client.cooldown_remaining(shopify("two")) == pytest.approx(600)


async def test_an_absurd_retry_after_is_capped_at_a_day(clock: FakeClock, shops: FakeShops) -> None:
    client = client_at(clock)
    shops.refuse("one", 429, **{"Retry-After": "9" * 400})

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    assert client.cooldown_remaining(shopify("two")) == pytest.approx(MAX_RETRY_AFTER_S)
    assert MAX_RETRY_AFTER_S == 24 * 3600


async def test_a_retry_after_on_a_403_is_not_read(clock: FakeClock, shops: FakeShops) -> None:
    client = client_at(clock, store_cooldown_s=900)
    shops.refuse("one", 403, **{"Retry-After": "7200"})

    with pytest.raises(BlockedError):
        await get(client, shopify("one"))

    assert client.cooldown_remaining(shopify("one")) == pytest.approx(900)


async def test_with_cooldowns_switched_off_a_429_obeys_its_retry_after_and_nothing_else(
    clock: FakeClock, shops: FakeShops
) -> None:
    off = client_at(clock, store_cooldown_s=0)
    shops.refuse("one", 429)
    shops.refuse("three", 429, **{"Retry-After": "120"})

    with pytest.raises(BlockedError):
        await get(off, shopify("one"))
    assert off.cooldown_remaining(shopify("two")) == 0

    with pytest.raises(BlockedError):
        await get(off, shopify("three"))
    assert off.cooldown_remaining(shopify("two")) == pytest.approx(120)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("120", 120.0),
        (" 120 ", 120.0),
        ("0", None),
        ("-1", None),
        ("1.5", None),
        ("", None),
        (None, None),
        ("Thu, 08 Oct 2026 12:02:00 GMT", 120.0),
        ("Thu, 08 Oct 2026 12:02:00 +0000", 120.0),
        ("Thu, 08 Oct 2026 11:59:00 GMT", None),
        ("not a date", None),
        ("٣٠", None),  # digits of another script are not seconds
        ("99999999999999", float(MAX_RETRY_AFTER_S)),
    ],
)
def test_parse_retry_after(header: str | None, expected: float | None) -> None:
    assert parse_retry_after(header, NOW) == expected


# --------------------------------------------------------------------------------------------
# The limiter and the cooldowns underneath
# --------------------------------------------------------------------------------------------

PLATFORM = SharedLimit("platform:test", rps=2.0)


async def test_a_dropped_waiter_raises_and_releases_its_slot(clock: FakeClock) -> None:
    limiter = RateLimiter(clock, group_of=lambda _key: PLATFORM)
    await limiter.acquire("a", rps=1)
    waiting = asyncio.ensure_future(limiter.acquire("b", rps=1))
    await asyncio.sleep(0)
    assert not waiting.done()

    assert limiter.drop_waiting(PLATFORM.name) == 1
    with pytest.raises(RequestDropped):
        await waiting

    waited = await limiter.acquire("c", rps=1)
    assert waited == pytest.approx(0.5)  # the next free slot, not one behind the dropped request


async def test_dropping_waiters_of_one_limit_leaves_those_of_another(clock: FakeClock) -> None:
    other = SharedLimit("platform:other", rps=2.0)
    limiter = RateLimiter(clock, group_of=lambda key: PLATFORM if key.startswith("p") else other)
    await asyncio.gather(limiter.acquire("p1", 1), limiter.acquire("o1", 1))
    stopped = asyncio.ensure_future(limiter.acquire("p2", rps=1))
    carried_on = asyncio.ensure_future(limiter.acquire("o2", rps=1))
    await asyncio.sleep(0)

    limiter.drop_waiting(PLATFORM.name)

    with pytest.raises(RequestDropped):
        await stopped
    assert await carried_on == pytest.approx(0.5)


def test_dropping_when_nobody_waits_does_nothing(clock: FakeClock) -> None:
    assert RateLimiter(clock).drop_waiting("platform:nobody") == 0


def test_a_cooldown_lasts_at_least_as_long_as_the_server_asked(clock: FakeClock) -> None:
    cooldowns = Cooldowns(clock, 900)

    assert cooldowns.start("a", at_least_s=3600) == 3600
    assert cooldowns.start("b", at_least_s=60) == 900
    assert cooldowns.start("c") == 900

    assert cooldowns.remaining("a") == pytest.approx(3600)
    assert cooldowns.remaining("b") == pytest.approx(900)


def test_a_running_cooldown_is_never_shortened(clock: FakeClock) -> None:
    cooldowns = Cooldowns(clock, 900)
    cooldowns.start("a", at_least_s=3600)
    clock.advance(100)

    cooldowns.start("a")  # a shorter one asked for later

    assert cooldowns.remaining("a") == pytest.approx(3500)


def test_a_zero_default_switches_cooldowns_off_unless_the_server_asked_for_a_wait(
    clock: FakeClock,
) -> None:
    cooldowns = Cooldowns(clock, 0)

    assert cooldowns.start("a") == 0
    assert cooldowns.remaining("a") == 0
    assert cooldowns.start("b", at_least_s=120) == 120
    assert cooldowns.remaining("b") == pytest.approx(120)
