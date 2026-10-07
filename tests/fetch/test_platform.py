"""The stores of one hosted platform share one request queue (``Settings.rps_per_platform``).

On 2026-10-08 thirteen different Shopify shops answered HTTP 429 within 11 milliseconds of each
other: the platform counts requests per client, not per shop. Each shop is still held to about one
request a second (BRD Rule 2); on top of that every request to a store's own site takes a slot in
the queue its whole platform shares.
"""

import asyncio
from typing import Any

import httpx
import pytest
import respx

from tests.factories import make_settings, make_store_config
from tests.fakes import FakeClock
from tests.fetch.conftest import ALLOW_ALL_ROBOTS, text_response
from vga.fetch import PoliteClient, RobotsChecker, platform_of
from vga.models import ExtractionConfig, StoreConfig, StrategyConfig


def store_on(strategy: str, key: str, **overrides: Any) -> StoreConfig:
    """A store ``key`` at ``https://<key>.example`` that reads its answers with ``strategy``."""
    fields: dict[str, Any] = {
        "id": key,
        "name": key.title(),
        "search_url_template": f"https://{key}.example/search?q={{query}}",
        "allowed_hosts": [f"{key}.example", "cdn.shopify.com"],
        "extraction": ExtractionConfig(strategies=[StrategyConfig(name=strategy)]),
    }
    return make_store_config(**{**fields, **overrides})


def shopify(key: str, **overrides: Any) -> StoreConfig:
    return store_on("shopify", key, **overrides)


class FakeShops:
    """Every ``*.example`` shop and the image CDN answer anything with 200, and note when each
    request arrived (seconds after the shops were set up, on the fake clock)."""

    def __init__(self, router: respx.MockRouter, clock: FakeClock) -> None:
        self._clock = clock
        self._start = clock.monotonic()
        self.arrivals: list[tuple[str, float]] = []
        router.get(url__regex=r"https://([a-z0-9-]+\.example|cdn\.shopify\.com)/.*").mock(
            side_effect=self._answer
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.arrivals.append((str(request.url), self._clock.monotonic() - self._start))
        return text_response(ALLOW_ALL_ROBOTS)

    def times(self, only: str = "") -> list[float]:
        return sorted(time for url, time in self.arrivals if only in url)


@pytest.fixture
def shops(router: respx.MockRouter, clock: FakeClock) -> FakeShops:
    return FakeShops(router, clock)


async def get(client: PoliteClient, store: StoreConfig, path: str = "/p") -> None:
    await client.fetch(f"https://{store.id}.example{path}", store, client.page_policy(store))


# --------------------------------------------------------------------------------------------
# Which platform a store is on
# --------------------------------------------------------------------------------------------


def test_every_shopify_storefront_is_on_the_shopify_platform() -> None:
    assert platform_of(shopify("one")) == platform_of(shopify("two")) == "platform:shopify"


def test_a_store_on_no_known_platform_is_its_own_platform() -> None:
    plain = store_on("store_json", "plain")
    other = store_on("json_ld", "other")

    assert platform_of(plain) == "own:plain"
    assert platform_of(other) == "own:other"
    assert platform_of(plain) != platform_of(other)


def test_the_platform_comes_from_any_strategy_of_the_chain() -> None:
    chain = ExtractionConfig(
        strategies=[StrategyConfig(name="json_ld"), StrategyConfig(name="shopify")]
    )

    assert platform_of(shopify("mixed", extraction=chain)) == "platform:shopify"


def test_a_platform_name_cannot_be_mistaken_for_a_store_id_or_an_image_host() -> None:
    for store in (shopify("shopify"), store_on("css", "platform")):
        key = platform_of(store)
        assert ":" in key
        assert key != store.id
        assert not key.startswith("host:")


# --------------------------------------------------------------------------------------------
# One queue for the whole platform
# --------------------------------------------------------------------------------------------


async def test_requests_to_different_shops_of_one_platform_go_half_a_second_apart(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = PoliteClient(make_settings(), clock=clock)

    await asyncio.gather(*(get(client, shopify(f"shop{i}")) for i in range(5)))

    assert shops.times() == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])


async def test_the_platform_rate_is_a_setting(clock: FakeClock, shops: FakeShops) -> None:
    client = PoliteClient(make_settings(rps_per_platform=1), clock=clock)

    await asyncio.gather(*(get(client, shopify(f"shop{i}")) for i in range(3)))

    assert shops.times() == pytest.approx([0.0, 1.0, 2.0])


async def test_shops_of_different_platforms_do_not_share_a_queue(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = PoliteClient(make_settings(), clock=clock)
    others = [shopify("one"), store_on("store_json", "two"), store_on("css", "three")]

    await asyncio.gather(*(get(client, shop) for shop in others))

    assert shops.times() == [0.0, 0.0, 0.0]


async def test_a_store_alone_on_its_platform_is_still_held_to_the_platform_rate(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = PoliteClient(make_settings(rps_per_platform=2), clock=clock)
    quick = store_on("store_json", "quick", rps=4)  # it asks for faster than its platform allows

    await asyncio.gather(*(get(client, quick, f"/p{i}") for i in range(5)))

    assert shops.times() == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])


async def test_each_shop_keeps_its_own_second_inside_the_platform_queue(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = PoliteClient(make_settings(rps_per_platform=5), clock=clock)
    shop = shopify("shop")

    await asyncio.gather(*(get(client, shop, f"/p{i}") for i in range(3)))

    assert shops.times() == pytest.approx([0.0, 1.0, 2.0])


async def test_robots_txt_and_redirect_hops_take_platform_slots_too(
    clock: FakeClock, router: respx.MockRouter
) -> None:
    arrivals: list[float] = []
    start = clock.monotonic()

    def stamp(response: httpx.Response):
        def answer(_request: httpx.Request) -> httpx.Response:
            arrivals.append(clock.monotonic() - start)
            return response

        return answer

    router.get("https://one.example/robots.txt").mock(
        side_effect=stamp(text_response(ALLOW_ALL_ROBOTS))
    )
    router.get("https://two.example/old").mock(
        side_effect=stamp(httpx.Response(302, headers={"location": "/new"}))
    )
    router.get("https://two.example/new").mock(side_effect=stamp(text_response("ok")))
    client = PoliteClient(make_settings(), clock=clock)
    one, two = shopify("one"), shopify("two")

    await asyncio.gather(
        RobotsChecker(client).ensure_allowed("https://one.example/search?q=x", one),
        get(client, two, "/old"),
    )

    # robots.txt of one, the first hop of two, then the second hop (a second after the first)
    assert sorted(arrivals) == pytest.approx([0.0, 0.5, 1.5])


async def test_an_image_host_is_not_part_of_the_platform_queue(
    clock: FakeClock, shops: FakeShops
) -> None:
    client = PoliteClient(make_settings(), clock=clock)
    shop = shopify("shop")

    async def thumbnail(number: int) -> None:
        await client.fetch(
            f"https://cdn.shopify.com/i{number}.jpg",
            shop,
            client.image_policy(shop, "cdn.shopify.com", timeout_s=4),
        )

    await asyncio.gather(get(client, shop), *(thumbnail(i) for i in range(6)))

    # the page goes at once and so does the first thumbnail; the rest are 5 a second apart
    assert shops.times("shop.example") == [0.0]
    assert shops.times("cdn.shopify.com") == pytest.approx([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
