"""Plan 14.1.2, request budget and rate (BRD Rule 2: about one request a second per store).

The real pipeline and the real store engine, counting what reaches the fake stores:

- *Budget*: a store is sent robots.txt once plus one request per keyword variant, never more, for a
  single garment and for an outfit of four.
- *Rate*: the fake-clock time of every request to a store, robots.txt included, is at least one
  second after the one before, however many garments and searches are running at once.
- *Cache*: the same search again inside the cache window sends nothing; robots.txt is read once.

The rate tests fail when the rate limiter is bypassed, the cache tests fail when the result cache
or the robots.txt cache is bypassed, and the budget tests fail when the per-garment or per-store
variant caps are removed (each was checked by breaking that part of ``src/`` for one local run).

The last test reads the shipped ``config/stores/`` files: a store file may not ask for a faster rate
than the BRD allows, because ``StoreConfig.rps`` accepts up to five requests a second.
"""

import asyncio
import gzip

import httpx
import yaml

from tests.factories import make_item_intent, make_search_request
from tests.fakes import FakeClock
from tests.guards.scraping.support import (
    MIN_GAP_S,
    GuardPipelines,
    GuardWorld,
    blazer_products,
    body_of,
    gaps,
    reply_json,
    understanding,
    understanding_by_words,
)
from tests.pipeline.builders import BLAZER, OUTFIT, SHIRT, outfit_understander, photo_search
from tests.pipeline.world import store_for
from vga.models import StoreConfig, StoreStatus
from vga.pipeline.planning import MAX_OUTFIT_KEYWORDS
from vga.settings import DEFAULT_STORES_DIR, PROJECT_ROOT, Settings
from vga.stores import StoreRegistry

STORES = ("alpha", "beta")
PLATFORM_STORES = tuple(f"shop{number:02d}" for number in range(13))
"""As many stores as the app ships, all Shopify storefronts, so all on one platform."""
THREE_VARIANTS = make_item_intent(
    search_keywords=["black blazer", "oversized blazer", "tailored jacket"]
)


def robots_requests(world: GuardWorld, host: str) -> int:
    return sum(1 for request in world.calls_to(host) if request.url.path == "/robots.txt")


# --------------------------------------------------------------------------------------------
# Budget: robots.txt plus the keyword variants
# --------------------------------------------------------------------------------------------


async def test_one_garment_costs_each_store_robots_txt_plus_one_request_per_keyword_variant(
    world: GuardWorld, two_stores: list[StoreConfig], build: GuardPipelines, settings: Settings
) -> None:
    pipeline = build(understander=understanding(THREE_VARIANTS))

    await pipeline.run(make_search_request(text="black blazer"), settings)

    budget = 1 + len(THREE_VARIANTS.search_keywords)
    for store_id in STORES:
        assert world.requests_to(f"{store_id}.example") <= budget
        assert len(world.queries(store_id)) <= len(THREE_VARIANTS.search_keywords)
    assert world.stray == []


async def test_robots_txt_is_fetched_once_per_store_however_many_variants_follow(
    world: GuardWorld, two_stores: list[StoreConfig], build: GuardPipelines, settings: Settings
) -> None:
    pipeline = build(understander=understanding(THREE_VARIANTS))

    await pipeline.run(make_search_request(text="black blazer"), settings)

    for store_id in STORES:
        assert robots_requests(world, f"{store_id}.example") == 1


async def test_a_store_limited_to_one_variant_is_sent_only_that_one(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha", max_variants=1))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(THREE_VARIANTS))

    await pipeline.run(make_search_request(text="black blazer"), settings)

    assert len(world.queries("alpha")) == 1
    assert world.requests_to("alpha.example") <= 2
    assert world.requests_to("beta.example") <= 4


async def test_an_outfit_costs_each_store_robots_txt_plus_two_variants_per_garment_at_most(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = build(understander=outfit_understander())

    await pipeline.run(make_search_request(image=photo, text=None), settings)

    budget = 1 + len(OUTFIT) * MAX_OUTFIT_KEYWORDS
    assert all(len(item.search_keywords) > MAX_OUTFIT_KEYWORDS for item in OUTFIT)
    for store_id in STORES:
        assert world.requests_to(f"{store_id}.example") <= budget
        assert robots_requests(world, f"{store_id}.example") == 1
    assert world.stray == []


async def test_at_most_ten_thumbnails_are_fetched_for_any_one_store(
    world: GuardWorld, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    many = {"blazer": tuple(range(100, 1500, 100))}  # fourteen blazers in each store
    world.add(store_for("alpha"), prices=many)
    world.add(store_for("beta"), prices=many)
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    for store_id in STORES:
        fetched = world.thumbnails_of(store_id)
        assert 0 < len(fetched) <= 10
    assert world.stray == []


# --------------------------------------------------------------------------------------------
# Rate: never faster than one request a second to one store
# --------------------------------------------------------------------------------------------


async def test_no_store_is_sent_requests_faster_than_one_a_second(
    world: GuardWorld, two_stores: list[StoreConfig], build: GuardPipelines, settings: Settings
) -> None:
    pipeline = build(understander=understanding(THREE_VARIANTS))

    await pipeline.run(make_search_request(text="black blazer"), settings)

    for store_id in STORES:
        times = world.request_times(store_id)
        assert len(times) == 4  # robots.txt and three variants: a real sequence to space
        assert all(gap >= MIN_GAP_S for gap in gaps(times))


async def test_an_outfit_of_four_garments_still_keeps_one_second_between_requests_to_a_store(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = build(understander=outfit_understander())

    await pipeline.run(make_search_request(image=photo, text=None), settings)

    for store_id in STORES:
        times = world.request_times(store_id)
        assert len(times) == 1 + len(OUTFIT) * MAX_OUTFIT_KEYWORDS
        assert all(gap >= MIN_GAP_S for gap in gaps(times))


async def test_two_searches_running_at_the_same_time_share_one_second_spacing(
    world: GuardWorld, two_stores: list[StoreConfig], build: GuardPipelines, settings: Settings
) -> None:
    pipeline = build(understander=understanding_by_words({"blazer": BLAZER, "shirt": SHIRT}))

    await asyncio.gather(
        pipeline.run(make_search_request(text="black oversized blazer"), settings),
        pipeline.run(make_search_request(text="white cotton shirt"), settings),
    )

    for store_id in STORES:
        times = world.request_times(store_id)
        assert len(times) == 1 + 2 * 2
        assert all(gap >= MIN_GAP_S for gap in gaps(times))


async def test_requests_to_all_the_stores_of_one_platform_are_never_closer_than_the_platform_rate(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    for store_id in PLATFORM_STORES:
        world.add(store_for(store_id))
    pipeline = build(understander=understanding(THREE_VARIANTS))

    await pipeline.run(make_search_request(text="black blazer"), settings)

    everything = sorted(t for store_id in PLATFORM_STORES for t in world.request_times(store_id))
    assert len(everything) >= 2 * len(PLATFORM_STORES)  # robots.txt and a search for every store
    assert all(gap >= 1 / settings.rps_per_platform - 1e-9 for gap in gaps(everything))
    assert world.stray == []


async def test_a_crawl_delay_in_robots_txt_slows_that_store_down_and_only_that_store(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots="User-agent: *\nCrawl-delay: 5\nDisallow:\n")
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(THREE_VARIANTS))

    await pipeline.run(make_search_request(text="black blazer"), settings)

    alpha_searches = world.sites["alpha"].times
    beta_searches = world.sites["beta"].times
    assert len(alpha_searches) == 3
    assert all(gap >= 5.0 - 1e-9 for gap in gaps(alpha_searches))
    assert all(gap < 5.0 for gap in gaps(beta_searches))


async def test_thumbnails_are_fetched_from_an_image_host_no_faster_than_five_a_second(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    assert len(world.cdn_times) > 10  # robots.txt and the thumbnails of both stores
    assert all(gap >= 1 / settings.rps_images_per_host - 1e-9 for gap in gaps(world.cdn_times))


# --------------------------------------------------------------------------------------------
# Cache: asking again does not ask the store again
# --------------------------------------------------------------------------------------------


async def test_the_same_search_again_inside_the_cache_window_sends_no_request_at_all(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    clock: FakeClock,
) -> None:
    pipeline = build(understander=understanding(BLAZER))
    first = await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    sent_before = world.all_requests()
    clock.advance(settings.store_cache_ttl_s / 2)

    second = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.all_requests() == sent_before
    assert all(report.from_cache for report in second.stores_used)
    assert second.result_count == first.result_count


async def test_a_different_search_does_not_fetch_a_stores_robots_txt_again(
    world: GuardWorld, two_stores: list[StoreConfig], build: GuardPipelines, settings: Settings
) -> None:
    pipeline = build(understander=understanding_by_words({"blazer": BLAZER, "shirt": SHIRT}))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    await pipeline.run(make_search_request(text="white cotton shirt"), settings)

    for store_id in STORES:
        assert robots_requests(world, f"{store_id}.example") == 1
        assert len(world.queries(store_id)) == 4  # two variants for each of the two garments


async def test_after_the_cache_expires_a_store_is_asked_again_but_robots_txt_is_not(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    clock: FakeClock,
) -> None:
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    clock.advance(settings.store_cache_ttl_s + 1)

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    for store_id in STORES:
        assert len(world.queries(store_id)) == 4  # fresh answers, not stale ones for ever
        assert robots_requests(world, f"{store_id}.example") == 1  # its own 24 hour cache


# --------------------------------------------------------------------------------------------
# Who is asking
# --------------------------------------------------------------------------------------------


async def test_every_request_carries_the_honest_user_agent_and_no_cookie_or_identity(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    sent = world.every_request()
    assert len(sent) > 10
    for request in sent:
        assert request.headers["user-agent"] == settings.user_agent
        names = {name.lower() for name in request.headers}
        assert not names & {"cookie", "authorization", "referer", "proxy-authorization"}
        assert all("@" not in value for value in request.headers.values())  # no e-mail address
    assert not any(token in settings.user_agent for token in ("Mozilla", "Chrome", "Safari"))


async def test_a_cookie_a_store_sets_is_never_sent_back_to_it(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    def with_cookie(response: httpx.Response) -> httpx.Response:
        response.headers["set-cookie"] = "session=abc123; Path=/; HttpOnly"
        return response

    search = reply_json(body_of(*blazer_products("alpha")))
    world.add(
        store_for("alpha"),
        robots=lambda _request: with_cookie(httpx.Response(200, text="User-agent: *\nDisallow:\n")),
        reply=lambda request: with_cookie(search(request)),
    )
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    sent = world.calls_to("alpha.example")
    assert len(sent) == 3  # robots.txt and the two variants: the later ones could carry a cookie
    assert all("cookie" not in request.headers for request in sent)


# --------------------------------------------------------------------------------------------
# Size: a store cannot make us read without end
# --------------------------------------------------------------------------------------------


async def test_a_response_that_declares_more_than_the_size_cap_is_refused_after_one_request(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    declared = str(settings.max_response_bytes + 1)

    def too_big(_request: httpx.Request) -> httpx.Response:
        headers = {"content-length": declared, "content-type": "application/json"}
        return httpx.Response(200, content=b"{}", headers=headers)

    world.add(store_for("alpha"), reply=too_big)
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 1
    assert [(r.store_id, r.status) for r in response.stores_skipped] == [
        ("alpha", StoreStatus.ERROR)
    ]
    assert {scored.product.store for scored in response.products} == {"Beta"}


async def test_a_compressed_response_that_grows_past_the_size_cap_is_cut_off_after_one_request(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    # A few kilobytes on the wire, twenty times the cap once decompressed.
    padding = b" " * (settings.max_response_bytes * 20)
    bomb = gzip.compress(b'{"resources": {"results": {"products": [' + padding + b"]}}}")
    assert len(bomb) < settings.max_response_bytes // 10

    def explode(_request: httpx.Request) -> httpx.Response:
        headers = {"content-encoding": "gzip", "content-type": "application/json"}
        return httpx.Response(200, content=bomb, headers=headers)

    world.add(store_for("alpha"), reply=explode)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 1
    assert [(r.store_id, r.status) for r in response.stores_skipped] == [
        ("alpha", StoreStatus.ERROR)
    ]


# --------------------------------------------------------------------------------------------
# The shipped store files
# --------------------------------------------------------------------------------------------


def test_no_shipped_store_file_asks_for_more_than_one_request_a_second() -> None:
    stores = StoreRegistry.from_directory(DEFAULT_STORES_DIR).stores
    shipped = yaml.safe_load((PROJECT_ROOT / "config" / "settings.yaml").read_text("utf-8"))

    assert stores  # the shipped stores were found, so the loop below checks something
    assert shipped["rps_per_store"] <= 1
    assert [store.id for store in stores if store.rps is not None and store.rps > 1] == []
