"""Thumbnail fetching for the image ranker (plan 6.5.5): ``fetch_image(product)`` -> bytes/None."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
import pytest
import respx

from tests.factories import make_image_bytes, make_product
from tests.fakes import FakeClock
from tests.fetch.conftest import fixture_text, shopify_store, text_response
from vga.models import Product
from vga.settings import Settings
from vga.stores import IMAGE_TIMEOUT_S, StoreSearchEngine
from vga.stores.registry import StoreRegistry

CDN = "https://cdn.shopify.com/s/files/1/0757/9670/9661/files"
CDN_ROBOTS_URL = "https://cdn.shopify.com/robots.txt"
PNG = make_image_bytes("PNG")


def oh_polly_product(index: int = 1, **overrides: object) -> Product:
    fields: dict[str, object] = {
        "store": "Oh Polly",
        "image_url": f"{CDN}/blazer-{index}.jpg?v=1",
        "product_url": f"https://ohpolly.ae/products/blazer-{index}",
    }
    return make_product(index, **{**fields, **overrides})


def image_response(body: bytes = PNG, content_type: str = "image/png") -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": content_type})


@pytest.fixture(autouse=True)
def cdn_robots(router: respx.MockRouter) -> respx.Route:
    """cdn.shopify.com's robots.txt, as reported on 2026-10-07: it leaves product images open."""
    return router.get(CDN_ROBOTS_URL).mock(
        return_value=text_response(fixture_text("robots.cdn-shopify.txt"))
    )


@pytest.fixture
def engine(settings: Settings, clock: FakeClock, router: respx.MockRouter) -> StoreSearchEngine:
    return StoreSearchEngine(settings, StoreRegistry([shopify_store()]), clock=clock)


def test_fetch_image_has_the_shape_the_image_ranker_phase_receives(
    engine: StoreSearchEngine,
) -> None:
    fetch: Callable[[Product], Awaitable[bytes | None]] = engine.fetch_image

    assert callable(fetch)


async def test_a_thumbnail_comes_back_as_bytes(
    engine: StoreSearchEngine, router: respx.MockRouter, settings: Settings
) -> None:
    route = router.get(url__startswith=CDN).mock(return_value=image_response())

    data = await engine.fetch_image(oh_polly_product())

    assert data == PNG
    assert route.call_count == 1
    sent = route.calls.last.request
    assert sent.headers["user-agent"] == settings.user_agent
    assert sent.headers["accept"] == "image/*"
    assert "cookie" not in sent.headers


async def test_the_image_host_rate_is_used_and_not_the_store_rate(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(url__startswith=CDN).mock(return_value=image_response())
    started = clock.monotonic()

    await asyncio.gather(*(engine.fetch_image(oh_polly_product(n)) for n in range(1, 11)))

    # robots.txt and 10 thumbnails on one host at 5 requests per second: the 11th request goes
    # out 10 / 5 = 2.0 s in
    assert clock.monotonic() - started == pytest.approx(2.0)


async def test_a_thumbnail_on_the_stores_own_host_keeps_the_store_rate(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    store = shopify_store(allowed_hosts=["ohpolly.ae", "cdn.shopify.com"])
    engine = StoreSearchEngine(settings, StoreRegistry([store]), clock=clock)
    router.get("https://ohpolly.ae/robots.txt").mock(return_value=text_response(""))
    router.get(url__startswith="https://ohpolly.ae/cdn/").mock(return_value=image_response())
    started = clock.monotonic()

    await asyncio.gather(
        *(
            engine.fetch_image(oh_polly_product(n, image_url=f"https://ohpolly.ae/cdn/{n}.jpg"))
            for n in range(1, 4)
        )
    )

    # robots.txt and 3 thumbnails on the store's own host, one request per second
    assert clock.monotonic() - started == pytest.approx(3.0)


async def test_a_slow_thumbnail_is_given_up_after_four_seconds(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    request_times: list[float] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        request_times.append(clock.monotonic())
        await clock.sleep(1000)
        return image_response()

    router.get(url__startswith=CDN).mock(side_effect=hang)

    data = await engine.fetch_image(oh_polly_product())

    assert data is None
    assert IMAGE_TIMEOUT_S == 4.0
    assert len(request_times) == 1  # no retry
    assert clock.monotonic() - request_times[0] == pytest.approx(IMAGE_TIMEOUT_S)


async def test_the_store_default_timeout_does_not_apply_to_thumbnails(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    slow_store = shopify_store(timeout_s=15)
    engine = StoreSearchEngine(settings, StoreRegistry([slow_store]), clock=clock)

    request_times: list[float] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        request_times.append(clock.monotonic())
        await clock.sleep(1000)
        return image_response()

    router.get(url__startswith=CDN).mock(side_effect=hang)

    assert await engine.fetch_image(oh_polly_product()) is None
    assert clock.monotonic() - request_times[0] == pytest.approx(4.0)


async def test_an_oversized_thumbnail_is_refused(
    engine: StoreSearchEngine, router: respx.MockRouter, settings: Settings
) -> None:
    router.get(url__startswith=CDN).mock(
        return_value=image_response(b"x" * (settings.max_response_bytes + 1))
    )

    assert await engine.fetch_image(oh_polly_product()) is None


async def test_the_stores_own_size_cap_applies_to_thumbnails(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    engine = StoreSearchEngine(
        settings, StoreRegistry([shopify_store(max_response_bytes=100)]), clock=clock
    )
    router.get(url__startswith=CDN).mock(return_value=image_response(b"x" * 101))

    assert await engine.fetch_image(oh_polly_product()) is None


@pytest.mark.parametrize(
    "image_url",
    [
        "https://evil.example/img.jpg",
        "https://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1/img.jpg",
        "https://[::1]/img.jpg",
        "https://cdn.shopify.com.evil.example/img.jpg",
        "https://cdn.shopify.com:8443/img.jpg",
    ],
)
async def test_an_image_url_off_the_stores_allow_list_is_never_requested(
    engine: StoreSearchEngine, router: respx.MockRouter, image_url: str
) -> None:
    assert await engine.fetch_image(oh_polly_product(image_url=image_url)) is None
    assert router.calls.call_count == 0


async def test_a_product_from_a_store_the_engine_does_not_know_is_not_fetched(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    stranger = oh_polly_product(store="Unknown Store")

    assert await engine.fetch_image(stranger) is None
    assert router.calls.call_count == 0


async def test_stores_seen_by_search_are_known_to_fetch_image(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    engine = StoreSearchEngine(settings, clock=clock)  # an empty registry
    router.get(url__startswith=CDN).mock(return_value=image_response())
    assert await engine.fetch_image(oh_polly_product()) is None

    engine.registry.add(shopify_store())

    assert await engine.fetch_image(oh_polly_product()) == PNG


async def test_a_redirect_off_the_allow_list_is_not_followed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(url__startswith=CDN).mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example/img.jpg"})
    )
    evil = router.get("https://evil.example/img.jpg").mock(return_value=image_response())

    assert await engine.fetch_image(oh_polly_product()) is None
    assert not evil.called


async def test_a_redirect_within_the_same_cdn_is_followed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(f"{CDN}/blazer-1.jpg?v=1").mock(
        return_value=httpx.Response(301, headers={"location": f"{CDN}/final.jpg"})
    )
    router.get(f"{CDN}/final.jpg").mock(return_value=image_response())

    assert await engine.fetch_image(oh_polly_product()) == PNG


@pytest.mark.parametrize("status", [404, 410, 500, 503])
async def test_an_error_status_gives_none_and_is_not_retried(
    engine: StoreSearchEngine, router: respx.MockRouter, status: int
) -> None:
    route = router.get(url__startswith=CDN).mock(return_value=httpx.Response(status))

    assert await engine.fetch_image(oh_polly_product()) is None
    assert route.call_count == 1


@pytest.mark.parametrize("status", [403, 429])
async def test_a_blocked_image_host_is_left_alone_for_the_cooldown(
    engine: StoreSearchEngine, router: respx.MockRouter, status: int
) -> None:
    route = router.get(url__startswith=CDN).mock(return_value=httpx.Response(status))

    results = [await engine.fetch_image(oh_polly_product(n)) for n in range(1, 5)]

    assert results == [None] * 4
    assert route.call_count == 1  # the other three made no request at all


async def test_a_blocked_image_host_does_not_block_the_stores_search(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(url__startswith=CDN).mock(return_value=httpx.Response(403))

    await engine.fetch_image(oh_polly_product())

    assert engine.client.cooldowns.remaining("oh-polly") == 0
    assert engine.client.cooldowns.remaining("host:cdn.shopify.com") > 0


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"<html><body>hello</body></html>", "text/html"),
        (b'{"error": "not found"}', "application/json"),
        (b"plain text", "text/plain"),
        (b"\x89PNG", ""),
    ],
)
async def test_something_that_is_not_an_image_gives_none(
    engine: StoreSearchEngine, router: respx.MockRouter, body: bytes, content_type: str
) -> None:
    router.get(url__startswith=CDN).mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": content_type})
    )

    assert await engine.fetch_image(oh_polly_product()) is None


async def test_a_challenge_page_in_place_of_an_image_is_a_block(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(url__startswith=CDN).mock(
        return_value=httpx.Response(
            200,
            content=b"<html><title>Just a moment...</title></html>",
            headers={"content-type": "text/html"},
        )
    )

    assert await engine.fetch_image(oh_polly_product()) is None
    assert engine.client.cooldowns.remaining("host:cdn.shopify.com") > 0


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), RuntimeError("bug")],
)
async def test_any_failure_gives_none_and_never_raises(
    engine: StoreSearchEngine, router: respx.MockRouter, failure: Exception
) -> None:
    router.get(url__startswith=CDN).mock(side_effect=failure)

    assert await engine.fetch_image(oh_polly_product()) is None


async def test_cancelling_a_thumbnail_fetch_is_not_swallowed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        return image_response()

    router.get(url__startswith=CDN).mock(side_effect=hang)
    task = asyncio.create_task(engine.fetch_image(oh_polly_product()))
    for _ in range(5):
        await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_failures_are_logged_not_silent(
    engine: StoreSearchEngine, router: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    router.get(url__startswith=CDN).mock(return_value=httpx.Response(404))

    await engine.fetch_image(oh_polly_product())
    await engine.fetch_image(oh_polly_product(store="Nobody"))

    messages = [r.getMessage() for r in caplog.records]
    assert "image not fetched: bad status" in messages
    assert "image not fetched: unknown store" in messages


# --------------------------------------------------------------------------------------------
# robots.txt applies to thumbnails too (BRD Rule 2)
# --------------------------------------------------------------------------------------------


async def test_the_image_hosts_robots_txt_is_fetched_before_the_image(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(url__startswith=CDN).mock(return_value=image_response())

    await engine.fetch_image(oh_polly_product())

    assert [call.request.url.path.rsplit("/", 1)[-1] for call in router.calls] == [
        "robots.txt",
        "blazer-1.jpg",
    ]


async def test_an_image_host_whose_robots_txt_disallows_the_image_path_gives_none_and_no_request(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    cdn_robots.mock(return_value=text_response("User-agent: *\nDisallow: /s/files/\n"))
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    assert await engine.fetch_image(oh_polly_product()) is None

    assert image_route.call_count == 0
    assert cdn_robots.call_count == 1


async def test_a_wildcard_rule_with_a_query_string_is_honoured_for_images(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    cdn_robots.mock(return_value=text_response("User-agent: *\nDisallow: /*?*width=\n"))
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    denied = await engine.fetch_image(oh_polly_product(image_url=f"{CDN}/a.jpg?v=1&width=400"))
    allowed = await engine.fetch_image(oh_polly_product(image_url=f"{CDN}/a.jpg?v=1"))

    assert (denied, allowed) == (None, PNG)
    assert image_route.call_count == 1


async def test_the_reported_cdn_shopify_rules_allow_product_images_under_s_files(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    data = await engine.fetch_image(oh_polly_product(image_url=f"{CDN}/blazer-1.jpg?v=1&width=400"))

    assert data == PNG
    assert image_route.call_count == 1


async def test_the_reported_cdn_shopify_rules_still_disallow_the_two_script_paths(
    engine: StoreSearchEngine,
) -> None:
    store = shopify_store()
    robots = engine.robots

    assert await robots.can_fetch(f"{CDN}/blazer-1.jpg", store) is True
    assert await robots.can_fetch("https://cdn.shopify.com/wpm/app.js", store) is False
    assert (
        await robots.can_fetch("https://cdn.shopify.com/x/blog-article-remove-faq-utms-9.js", store)
        is False
    )


async def test_the_robots_fetch_for_an_image_host_happens_once_and_is_cached(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route, clock: FakeClock
) -> None:
    router.get(url__startswith=CDN).mock(return_value=image_response())

    first_wave = await asyncio.gather(*(engine.fetch_image(oh_polly_product(n)) for n in range(5)))
    second_wave = [await engine.fetch_image(oh_polly_product(n)) for n in range(5, 8)]
    clock.advance(3600)  # an hour later: still trusted (parsed files are kept for a day)
    later = await engine.fetch_image(oh_polly_product(9))

    assert all(data == PNG for data in [*first_wave, *second_wave, later])
    assert cdn_robots.call_count == 1


async def test_an_unreachable_robots_txt_on_the_image_host_gives_none_and_no_image_request(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    cdn_robots.mock(return_value=httpx.Response(503))
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    results = [await engine.fetch_image(oh_polly_product(n)) for n in range(1, 4)]

    assert results == [None, None, None]
    assert image_route.call_count == 0
    assert cdn_robots.call_count == 1  # remembered: no new robots request for each image


async def test_a_missing_robots_txt_on_the_image_host_allows_the_image(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    cdn_robots.mock(return_value=httpx.Response(404))
    router.get(url__startswith=CDN).mock(return_value=image_response())

    assert await engine.fetch_image(oh_polly_product()) == PNG


async def test_an_html_page_in_place_of_the_image_hosts_robots_txt_counts_as_unreachable(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    cdn_robots.mock(return_value=text_response("<html>home</html>", content_type="text/html"))
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    assert await engine.fetch_image(oh_polly_product()) is None
    assert image_route.call_count == 0


async def test_a_slow_robots_txt_on_the_image_host_is_given_up_after_four_seconds(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route, clock: FakeClock
) -> None:
    request_times: list[float] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        request_times.append(clock.monotonic())
        await clock.sleep(1000)
        return text_response("")

    cdn_robots.mock(side_effect=hang)
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    assert await engine.fetch_image(oh_polly_product()) is None

    assert clock.monotonic() - request_times[0] == pytest.approx(IMAGE_TIMEOUT_S)
    assert image_route.call_count == 0


async def test_a_blocked_robots_request_on_the_image_host_cools_down_that_host_not_the_store(
    engine: StoreSearchEngine, router: respx.MockRouter, cdn_robots: respx.Route
) -> None:
    cdn_robots.mock(return_value=httpx.Response(403))
    image_route = router.get(url__startswith=CDN).mock(return_value=image_response())

    results = [await engine.fetch_image(oh_polly_product(n)) for n in range(1, 4)]

    assert results == [None, None, None]
    assert (cdn_robots.call_count, image_route.call_count) == (1, 0)
    assert engine.client.cooldowns.remaining("host:cdn.shopify.com") > 0
    assert engine.client.cooldowns.remaining("oh-polly") == 0


async def test_the_image_hosts_robots_txt_uses_the_image_host_rate(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(url__startswith=CDN).mock(return_value=image_response())
    started = clock.monotonic()

    await engine.fetch_image(oh_polly_product())

    # robots.txt at once, the image 1 / 5 s later (a store page would wait a whole second)
    assert clock.monotonic() - started == pytest.approx(0.2)


async def test_a_thumbnail_on_the_stores_own_host_shares_the_robots_verdict_with_the_search(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    store = shopify_store(allowed_hosts=["ohpolly.ae", "cdn.shopify.com"])
    engine = StoreSearchEngine(settings, StoreRegistry([store]), clock=clock)
    robots = router.get("https://ohpolly.ae/robots.txt").mock(return_value=text_response(""))
    router.get(url__startswith="https://ohpolly.ae/cdn/").mock(return_value=image_response())
    await engine.robots.ensure_allowed("https://ohpolly.ae/search?q=blazer", store)

    data = await engine.fetch_image(oh_polly_product(image_url="https://ohpolly.ae/cdn/1.jpg"))

    assert data == PNG
    assert robots.call_count == 1


async def test_a_block_on_the_stores_own_host_while_fetching_its_robots_blocks_the_store(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    store = shopify_store(allowed_hosts=["ohpolly.ae", "cdn.shopify.com"])
    engine = StoreSearchEngine(settings, StoreRegistry([store]), clock=clock)
    router.get("https://ohpolly.ae/robots.txt").mock(return_value=httpx.Response(403))

    data = await engine.fetch_image(oh_polly_product(image_url="https://ohpolly.ae/cdn/1.jpg"))

    assert data is None
    assert engine.client.cooldowns.remaining("oh-polly") > 0


async def test_a_thumbnail_redirected_to_another_host_needs_that_hosts_robots_txt_to_allow_it(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get("https://ohpolly.ae/robots.txt").mock(return_value=text_response(""))
    router.get("https://ohpolly.ae/cdn/1.jpg").mock(
        return_value=httpx.Response(301, headers={"location": "https://www.ohpolly.ae/cdn/1.jpg"})
    )
    www_robots = router.get("https://www.ohpolly.ae/robots.txt").mock(
        return_value=text_response("User-agent: *\nDisallow: /cdn/\n")
    )
    landing = router.get("https://www.ohpolly.ae/cdn/1.jpg").mock(return_value=image_response())

    data = await engine.fetch_image(oh_polly_product(image_url="https://ohpolly.ae/cdn/1.jpg"))

    assert data is None
    assert www_robots.call_count == 1
    assert landing.call_count == 0


async def test_a_thumbnail_redirected_to_a_host_whose_robots_txt_allows_it_is_fetched(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get("https://ohpolly.ae/robots.txt").mock(return_value=text_response(""))
    router.get("https://ohpolly.ae/cdn/1.jpg").mock(
        return_value=httpx.Response(301, headers={"location": "https://www.ohpolly.ae/cdn/1.jpg"})
    )
    router.get("https://www.ohpolly.ae/robots.txt").mock(return_value=text_response(""))
    router.get("https://www.ohpolly.ae/cdn/1.jpg").mock(return_value=image_response())

    data = await engine.fetch_image(oh_polly_product(image_url="https://ohpolly.ae/cdn/1.jpg"))

    assert data == PNG


OWN_HOST_IMAGE = "https://ohpolly.ae/cdn/1.jpg"


def engine_with_images_on_the_stores_own_host(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> tuple[StoreSearchEngine, respx.Route]:
    """Oh Polly serving its thumbnails itself; its robots.txt allows everything."""
    store = shopify_store(allowed_hosts=["ohpolly.ae", "cdn.shopify.com"])
    engine = StoreSearchEngine(settings, StoreRegistry([store]), clock=clock)
    router.get("https://ohpolly.ae/robots.txt").mock(return_value=text_response(""))
    images = router.get(url__startswith="https://ohpolly.ae/cdn/").mock(
        return_value=image_response()
    )
    return engine, images


async def test_a_thumbnail_on_the_stores_own_host_is_not_requested_while_the_store_is_cooling(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    engine, images = engine_with_images_on_the_stores_own_host(settings, clock, router)
    store = engine.registry.by_display_name("Oh Polly")
    assert store is not None
    await engine.robots.ensure_allowed("https://ohpolly.ae/search?q=blazer", store)  # the search
    engine.client.cooldowns.start("oh-polly")  # ... and the store refused it

    data = await engine.fetch_image(oh_polly_product(image_url=OWN_HOST_IMAGE))

    assert data is None
    assert images.call_count == 0


async def test_nothing_at_all_is_requested_from_a_cooling_store_for_a_thumbnail(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    engine, _images = engine_with_images_on_the_stores_own_host(settings, clock, router)
    engine.client.cooldowns.start("oh-polly")

    data = await engine.fetch_image(oh_polly_product(image_url=OWN_HOST_IMAGE))

    assert data is None
    assert router.calls.call_count == 0  # not the thumbnail, and not its robots.txt either


async def test_a_thumbnail_on_the_image_cdn_is_still_fetched_while_the_store_is_cooling(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    route = router.get(url__startswith=CDN).mock(return_value=image_response())
    engine.client.cooldowns.start("oh-polly")

    data = await engine.fetch_image(oh_polly_product())

    assert data == PNG  # cdn.shopify.com did not refuse us
    assert route.call_count == 1


async def test_a_block_on_a_thumbnail_from_the_stores_own_host_cools_the_store_down(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    engine, images = engine_with_images_on_the_stores_own_host(settings, clock, router)
    images.mock(return_value=httpx.Response(403))

    results = [
        await engine.fetch_image(oh_polly_product(n, image_url=f"https://ohpolly.ae/cdn/{n}.jpg"))
        for n in range(1, 4)
    ]

    assert results == [None, None, None]
    assert images.call_count == 1  # the other two were never asked for
    assert engine.client.cooldowns.remaining("oh-polly") > 0
    assert engine.client.cooldowns.remaining("host:ohpolly.ae") == 0


async def test_a_robots_refusal_for_an_image_is_logged_with_its_reason(
    engine: StoreSearchEngine,
    router: respx.MockRouter,
    cdn_robots: respx.Route,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    cdn_robots.mock(return_value=text_response("User-agent: *\nDisallow: /s/files/\n"))

    await engine.fetch_image(oh_polly_product())

    refusals = [r for r in caplog.records if r.getMessage() == "image not fetched"]
    assert [r.reason for r in refusals] == ["robots_denied"]  # type: ignore[attr-defined]
    assert "disallows" in refusals[0].detail  # type: ignore[attr-defined]
    assert any(r.getMessage() == "robots.txt disallows the URL; skipped" for r in caplog.records)
