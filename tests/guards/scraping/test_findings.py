"""Gaps the Phase 14.1 guards found in the product code, kept as the tests that caught them.

Each test states a rule the code is meant to keep. They began as ``xfail(strict=True)`` tests with
the reason each failed; when the product was fixed the test started to pass, pytest reported that
as an error, and the marker was removed in the fixing change. A test that still carries the marker
is a gap that is still open. They sit together so they can be routed as a list.

1. ``robots.txt`` is read for a redirect target (BRD Rule 2: respect robots.txt). Fixed: the
   client asks the store's robots check about every redirect target before it follows it.
2. A store's second host (``www.`` after an apex redirect) is held to the one-request-a-second
   spacing of the first (BRD Rule 2: about one a second per *store*; the limiter was per host).
3. A product link is not accepted on the shared image CDN, which is on ``allowed_hosts`` but is
   not the store's product page (BRD Rule 1: every result links to the original store's product
   page).
4. Thumbnails on the store's own host are not fetched while the store is in cooldown after a block
   (BRD Rule 2: a store that blocks is not contacted again during its cooldown).
"""

from urllib.parse import urlsplit

import httpx
import pytest

from tests.factories import make_search_request
from tests.guards.scraping.support import (
    MIN_GAP_S,
    GuardPipelines,
    GuardWorld,
    blazer_products,
    body_of,
    gaps,
    reply_json,
    reply_redirect,
    reply_status,
    trap_product,
    understanding,
)
from tests.pipeline.builders import BLAZER, photo_search
from tests.pipeline.world import CDN_HOST, store_for
from vga.settings import Settings

WWW_HOSTS = ["alpha.example", "www.alpha.example", CDN_HOST]
TO_WWW = "https://www.alpha.example/search/suggest.json?q=black"


async def test_a_redirect_to_another_host_of_the_store_does_not_get_round_its_robots_txt(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha", allowed_hosts=WWW_HOSTS), reply=reply_redirect(TO_WWW))
    reached_www = world.serve_other_host(
        "alpha",
        "www.alpha.example",
        robots="User-agent: *\nDisallow: /search\n",  # the www host forbids the search
        search=reply_json(body_of(*blazer_products("alpha"))),
    )
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert reached_www == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING 2: RateLimiter keeps one bucket per host (plan 6.1.3) but BRD Rule 2 says per "
        "store; a search that redirects from alpha.example to www.alpha.example reaches both "
        "hosts in the same second"
    ),
)
async def test_a_store_that_redirects_to_its_other_host_is_still_asked_once_a_second_in_all(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha", allowed_hosts=WWW_HOSTS), reply=reply_redirect(TO_WWW))
    world.serve_other_host(
        "alpha", "www.alpha.example", search=reply_json(body_of(*blazer_products("alpha")))
    )
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    times = world.request_times("alpha")
    assert len(times) >= 3  # robots.txt, the redirecting search, the search it redirects to
    assert all(gap >= MIN_GAP_S for gap in gaps(times))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING 3: Product.product_url is checked against all of the store's allowed_hosts "
        "(vga.stores.normalise._checked_url), and the image CDN is one of them, so a store "
        "response can name a file on cdn.shopify.com as the product page the shopper is sent to"
    ),
)
async def test_a_product_link_on_the_image_host_is_not_shown_as_a_product_page(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    on_the_cdn = f"https://{CDN_HOST}/s/files/1/0001/trap-1.html"
    trap = trap_product(1, url=on_the_cdn)
    world.add(store_for("alpha"), bodies={"blazer": body_of(*blazer_products("alpha"), trap)})
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    pages = [str(scored.product.product_url) for scored in response.products]
    assert [page for page in pages if urlsplit(page).hostname == CDN_HOST] == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING 4: a block puts the store id in cooldown but a thumbnail on the store's own "
        "host is fetched under cooldown_key='host:<name>' (PoliteClient.image_policy), so images "
        "are still requested from a host that has just refused the search. Not reachable with "
        "today's six stores: all serve images from cdn.shopify.com"
    ),
)
async def test_a_store_host_that_just_refused_a_search_is_not_asked_for_thumbnails(
    world: GuardWorld, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    products = blazer_products("alpha")
    for number, product in enumerate(products, start=1):
        product["image"] = f"https://alpha.example/cdn/blazer-alpha-{number}.jpg?v=1"
    answer = reply_json(body_of(*products))
    refuse = reply_status(403)
    asked: list[httpx.Request] = []

    def first_variant_answered_then_refused(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return answer(request) if len(asked) == 1 else refuse(request)

    world.add(store_for("alpha"), reply=first_variant_answered_then_refused)
    images = world.serve_images_on("alpha.example", "/cdn/")
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    assert len(asked) == 2  # the first variant was answered, the second was refused
    assert images == []
