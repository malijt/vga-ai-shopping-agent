"""Thumbnail fetching for the image ranker (plan 6.5.5): ``fetch_image(product)`` -> bytes/None."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
import pytest
import respx

from tests.factories import make_image_bytes, make_product
from tests.fakes import FakeClock
from tests.fetch.conftest import shopify_store
from vga.models import Product
from vga.settings import Settings
from vga.stores.engine import IMAGE_TIMEOUT_S, StoreSearchEngine
from vga.stores.registry import StoreRegistry

CDN = "https://cdn.shopify.com/s/files/1/0757/9670/9661/files"
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


async def test_robots_txt_is_not_consulted_for_a_thumbnail(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(url__startswith=CDN).mock(return_value=image_response())

    await engine.fetch_image(oh_polly_product())

    assert [call.request.url.host for call in router.calls] == ["cdn.shopify.com"]


async def test_the_image_host_rate_is_used_and_not_the_store_rate(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(url__startswith=CDN).mock(return_value=image_response())
    started = clock.monotonic()

    await asyncio.gather(*(engine.fetch_image(oh_polly_product(n)) for n in range(1, 11)))

    # 10 thumbnails at 5 requests per second: the last one goes out 9 / 5 = 1.8 s in
    assert clock.monotonic() - started == pytest.approx(1.8)


async def test_a_thumbnail_on_the_stores_own_host_keeps_the_store_rate(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    store = shopify_store(allowed_hosts=["ohpolly.ae", "cdn.shopify.com"])
    engine = StoreSearchEngine(settings, StoreRegistry([store]), clock=clock)
    router.get(url__startswith="https://ohpolly.ae/cdn/").mock(return_value=image_response())
    started = clock.monotonic()

    await asyncio.gather(
        *(
            engine.fetch_image(oh_polly_product(n, image_url=f"https://ohpolly.ae/cdn/{n}.jpg"))
            for n in range(1, 4)
        )
    )

    assert clock.monotonic() - started == pytest.approx(2.0)  # 1 request per second


async def test_a_slow_thumbnail_is_given_up_after_four_seconds(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    attempts = 0

    async def hang(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        await clock.sleep(1000)
        return image_response()

    router.get(url__startswith=CDN).mock(side_effect=hang)
    started = clock.monotonic()

    data = await engine.fetch_image(oh_polly_product())

    assert data is None
    assert IMAGE_TIMEOUT_S == 4.0
    assert clock.monotonic() - started == pytest.approx(IMAGE_TIMEOUT_S)
    assert attempts == 1  # no retry


async def test_the_store_default_timeout_does_not_apply_to_thumbnails(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    slow_store = shopify_store(timeout_s=15)
    engine = StoreSearchEngine(settings, StoreRegistry([slow_store]), clock=clock)

    async def hang(request: httpx.Request) -> httpx.Response:
        await clock.sleep(1000)
        return image_response()

    router.get(url__startswith=CDN).mock(side_effect=hang)
    started = clock.monotonic()

    assert await engine.fetch_image(oh_polly_product()) is None
    assert clock.monotonic() - started == pytest.approx(4.0)


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
