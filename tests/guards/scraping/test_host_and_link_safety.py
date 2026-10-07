"""Plan 14.1.3, host and link safety (BRD Rule 1, "Outbound requests" in CLAUDE.md, risk R18).

End to end, with the real pipeline and the real store engine: a store response that carries a
product link on another domain, an ``http://`` image, a link to a private address or any other
hostile link must cause **no request** to it and must leave **no such link in the response**; a
redirect to another host is never followed.

"No request" is asserted two ways: ``world.stray`` (the catch-all that records any request nobody
expected, which ``respx`` would otherwise swallow) and the list of hosts the run really contacted.
"""

from urllib.parse import urlsplit

import pytest

from tests.factories import make_product, make_search_request
from tests.guards.scraping.support import (
    GuardPipelines,
    GuardWorld,
    Reply,
    blazer_products,
    body_of,
    links_shown,
    reply_redirect,
    trap_product,
    understanding,
)
from tests.pipeline.builders import BLAZER, outfit_understander, photo_search
from tests.pipeline.world import CDN_HOST, store_for
from vga.models import StoreConfig
from vga.settings import Settings

STORE_HOST = "alpha.example"
CONTACTABLE = {STORE_HOST, CDN_HOST}
"""The only hosts a run against the ``alpha`` store may contact."""

LINK_TRAPS: dict[str, tuple[str, str]] = {
    "another_domain": ("https://evil.example/products/x", "evil.example"),
    "lookalike_domain": ("https://alpha.example.evil.example/p", "evil.example"),
    "credentials_naming_our_host_but_going_elsewhere": (
        "https://alpha.example@evil.example/p",
        "evil.example",
    ),
    "credentials_on_the_real_host": ("https://user:pass@alpha.example/p", "user:pass"),
    "protocol_relative_other_host": ("//evil.example/p", "evil.example"),
    "plain_http_on_the_real_host": ("http://alpha.example/products/x", "http://alpha.example"),
    "private_address": ("https://10.0.0.5/products/x", "10.0.0.5"),
    "metadata_address_over_http": ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
    "metadata_address_over_https": ("https://169.254.169.254/latest/meta-data/", "169.254.169.254"),
    "loopback_address": ("https://127.0.0.1/admin", "127.0.0.1"),
    "ipv6_loopback": ("https://[::1]/admin", "[::1]"),
    "local_host_name": ("https://localhost/admin", "localhost"),
    "a_number_standing_for_an_address": ("https://2130706433/", "2130706433"),
    "a_script": ("javascript:alert(1)", "javascript:"),
    "a_sibling_host_not_on_the_list": ("https://admin.alpha.example/p", "admin.alpha.example"),
    "another_port": ("https://alpha.example:8443/p", "8443"),
}
"""A hostile product link, and a fragment of it that must appear nowhere in the response."""

IMAGE_TRAPS: dict[str, tuple[str, str]] = {
    "plain_http_image": (f"http://{CDN_HOST}/s/files/1/0001/trap-1.jpg", f"http://{CDN_HOST}"),
    "plain_http_image_on_the_store": (f"http://{STORE_HOST}/img/trap-1.jpg", "http://alpha"),
    "image_on_another_domain": ("https://evil.example/trap-1.jpg", "evil.example"),
    "image_at_a_private_address": ("https://10.0.0.5/trap-1.jpg", "10.0.0.5"),
    "image_at_the_metadata_address": (
        "http://169.254.169.254/latest/meta-data/iam/trap-1.jpg",
        "169.254.169.254",
    ),
    "image_at_a_loopback_address": ("https://127.0.0.1/trap-1.jpg", "127.0.0.1"),
    "protocol_relative_image": ("//evil.example/trap-1.jpg", "evil.example"),
    "an_inline_data_image": ("data:image/png;base64,AAAA", "data:image"),
    "image_on_a_sibling_host_not_on_the_list": (
        "https://cdn.alpha.example/trap-1.jpg",
        "cdn.alpha.example",
    ),
}
"""A hostile image link, and a fragment of it that must appear nowhere in the response."""

REDIRECTS: dict[str, str] = {
    "another_domain": "https://evil.example/search/suggest.json?q=black",
    "a_private_address": "https://10.0.0.5/search/suggest.json?q=black",
    "the_metadata_address_over_http": "http://169.254.169.254/latest/meta-data/",
    "a_sibling_host_not_on_the_list": "https://admin.alpha.example/search/suggest.json?q=black",
    "a_downgrade_to_http": "http://alpha.example/search/suggest.json?q=black",
    "protocol_relative_other_host": "//evil.example/search/suggest.json?q=black",
    "another_port": "https://alpha.example:8443/search/suggest.json?q=black",
}
"""Where a store may try to send us on."""

GOOD_PRODUCTS = len(blazer_products("alpha"))
"""How many ordinary blazers each trapped store also sells."""

MAX_REDIRECTS_FOLLOWED = 3
"""The client's promise (``vga.fetch.client``): at most three redirects, then it stops."""


def trapped_store(world: GuardWorld, trap: dict) -> StoreConfig:
    """Alpha answers every search with its good blazers and one ``trap`` among them."""
    store = store_for("alpha")
    world.add(store, bodies={"blazer": body_of(*blazer_products("alpha"), trap)})
    return store


# --------------------------------------------------------------------------------------------
# A hostile link in a store's response
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("link", "needle"), LINK_TRAPS.values(), ids=list(LINK_TRAPS))
async def test_a_hostile_product_link_in_a_store_response_is_never_requested(
    link: str,
    needle: str,
    world: GuardWorld,
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    trapped_store(world, trap_product(1, url=link))
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    assert world.stray == []
    assert {request.url.host for request in world.every_request()} <= CONTACTABLE
    assert {request.url.scheme for request in world.every_request()} == {"https"}
    assert not [url for url in world.thumbnails if "trap-" in url]  # its record was dropped whole


@pytest.mark.parametrize(("link", "needle"), LINK_TRAPS.values(), ids=list(LINK_TRAPS))
async def test_a_hostile_product_link_in_a_store_response_does_not_reach_the_response(
    link: str, needle: str, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    trapped_store(world, trap_product(1, url=link))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert needle not in response.model_dump_json()
    assert not [shown for shown in links_shown(response) if "trap-" in shown]
    assert not [title for title in (s.product.title for s in response.products) if "Trap" in title]
    assert response.result_count == GOOD_PRODUCTS  # the trapped one is gone
    [used] = response.stores_used
    assert sum(used.dropped.values()) >= 1  # the drop is counted (once per variant), not silent


@pytest.mark.parametrize(("link", "needle"), IMAGE_TRAPS.values(), ids=list(IMAGE_TRAPS))
async def test_a_hostile_image_link_in_a_store_response_is_never_requested(
    link: str,
    needle: str,
    world: GuardWorld,
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    trapped_store(world, trap_product(1, image=link))
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    assert world.stray == []
    assert {request.url.host for request in world.every_request()} <= CONTACTABLE
    assert {request.url.scheme for request in world.every_request()} == {"https"}
    assert world.thumbnails  # the good products' thumbnails were fetched, so thumbnails are on


@pytest.mark.parametrize(("link", "needle"), IMAGE_TRAPS.values(), ids=list(IMAGE_TRAPS))
async def test_a_hostile_image_link_in_a_store_response_does_not_reach_the_response(
    link: str, needle: str, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    trapped_store(world, trap_product(1, image=link))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert needle not in response.model_dump_json()
    assert not [title for title in (s.product.title for s in response.products) if "Trap" in title]
    assert response.result_count == GOOD_PRODUCTS
    [used] = response.stores_used
    assert sum(used.dropped.values()) >= 1


# --------------------------------------------------------------------------------------------
# The links that are shown are the store's own
# --------------------------------------------------------------------------------------------


async def test_every_link_in_the_response_is_https_and_on_its_own_stores_allowed_hosts(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = build(understander=outfit_understander())
    by_name = {store.display_name: store for store in two_stores}

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    assert len(response.products) > 20
    for scored in response.products:
        store = by_name[scored.product.store]
        for link in (scored.product.product_url, scored.product.image_url):
            parts = urlsplit(link)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
            assert parts.username is None
            assert parts.port is None
        # the product page is on the store itself, not only on its image host (BRD Rule 1)
        assert urlsplit(scored.product.product_url).hostname == f"{store.id}.example"


# --------------------------------------------------------------------------------------------
# Redirects to another host are not followed
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("target", REDIRECTS.values(), ids=list(REDIRECTS))
async def test_a_search_page_that_redirects_to_another_host_is_not_followed(
    target: str, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), reply=reply_redirect(target))
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.stray == []
    assert {request.url.host for request in world.every_request()} <= {
        STORE_HOST,
        "beta.example",
        CDN_HOST,
    }
    assert len(world.queries("alpha")) == 1  # the redirecting request itself, nothing after it
    assert [report.store_id for report in response.stores_skipped] == ["alpha"]
    assert {scored.product.store for scored in response.products} == {"Beta"}


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_a_redirect_to_another_domain_is_not_followed_whatever_its_status(
    status: int, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), reply=reply_redirect(REDIRECTS["another_domain"], status=status))
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.stray == []
    assert world.requests_to("evil.example") == 0


async def test_a_robots_txt_that_redirects_to_another_domain_is_not_followed_and_no_search_is_sent(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots=reply_redirect("https://evil.example/robots.txt"))
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.stray == []
    assert world.queries("alpha") == []


async def test_a_thumbnail_that_redirects_to_another_domain_is_not_followed(
    world: GuardWorld,
    two_stores: list[StoreConfig],
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
) -> None:
    world.serve_thumbnails(reply_redirect("https://evil.example/pixel.png"))
    pipeline = build(understander=photo_search(), thumbnails=True)

    response = await pipeline.run(
        make_search_request(image=photo, text="black oversized blazer"), settings
    )

    assert world.thumbnails  # they were asked for, and each was refused its redirect
    assert world.stray == []
    assert response.result_count > 0  # the search still answers, ranked without the photo


async def test_a_redirect_loop_on_the_store_is_given_up_after_a_few_hops(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    looping: Reply = reply_redirect(f"https://{STORE_HOST}/search/suggest.json?q=again")
    world.add(store_for("alpha"), reply=looping)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 1 + MAX_REDIRECTS_FOLLOWED
    assert [report.store_id for report in response.stores_skipped] == ["alpha"]


# --------------------------------------------------------------------------------------------
# The thumbnail fetcher is a second line of defence
# --------------------------------------------------------------------------------------------

IMAGE_FETCH_TRAPS: dict[str, str] = {
    "another_domain": "https://evil.example/x.jpg",
    "a_private_address": "https://10.0.0.5/x.jpg",
    "the_metadata_address": "https://169.254.169.254/latest/meta-data/x.jpg",
    "a_loopback_address": "https://127.0.0.1/x.jpg",
    "a_local_host_name": "https://localhost/x.jpg",
    "a_sibling_host_not_on_the_list": "https://admin.alpha.example/x.jpg",
    "a_lookalike_host": "https://alpha.example.evil.example/x.jpg",
}


@pytest.mark.parametrize("image_url", IMAGE_FETCH_TRAPS.values(), ids=list(IMAGE_FETCH_TRAPS))
async def test_the_thumbnail_fetcher_makes_no_request_for_an_image_off_the_stores_hosts(
    image_url: str, world: GuardWorld, build: GuardPipelines
) -> None:
    store = store_for("alpha")
    world.add(store)
    build(understander=understanding(BLAZER))
    product = make_product(store="Alpha", image_url=image_url)

    fetched = await build.engine.fetch_image(product)

    assert fetched is None
    assert world.every_request() == []  # not even a robots.txt request
    assert world.stray == []
