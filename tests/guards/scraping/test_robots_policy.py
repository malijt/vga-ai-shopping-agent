"""Plan 14.1.1, robots.txt (BRD Rule 2): a URL robots.txt disallows is never requested.

The real pipeline and the real robots checker (``protego``, never ``urllib.robotparser``, which
ignores ``*`` and ``$`` on Python 3.12) against fake stores. A store's robots.txt that cannot be
read counts as "everything disallowed" (RFC 9309); a missing one (404) as "everything allowed".
"""

import httpx
import pytest

from tests.factories import make_search_request
from tests.guards.scraping.support import (
    GuardPipelines,
    GuardWorld,
    Reply,
    html_response,
    reply_status,
    understanding,
)
from tests.pipeline.builders import BLAZER, photo_search
from tests.pipeline.world import store_for
from vga.models import StoreStatus
from vga.pipeline import messages
from vga.settings import Settings

DENIALS: dict[str, str] = {
    "the search path": "User-agent: *\nDisallow: /search\n",
    "the exact endpoint": "User-agent: *\nDisallow: /search/suggest.json\n",
    "a wildcard in the path": "User-agent: *\nDisallow: /*suggest.json\n",
    "a wildcard before the query string": "User-agent: *\nDisallow: /*?q=\n",
    "a rule ending in a dollar sign": "User-agent: *\nDisallow: /search*$\n",
    "a rule with no leading slash": "User-agent: *\nDisallow: ?q=\n",
    "everything": "User-agent: *\nDisallow: /\n",
    "our own user agent by name": (
        "User-agent: vga-shopping-agent-demo\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
    ),
}
"""robots.txt files that forbid the search page, in the shapes real stores write them."""

OPEN: dict[str, str] = {
    "other pages only": "User-agent: *\nDisallow: /cart\nDisallow: /checkout\nDisallow: /account\n",
    "nothing disallowed": "User-agent: *\nDisallow:\n",
    "another robot only": "User-agent: BadBot\nDisallow: /\n",
    "a longer allow beating a shorter disallow": (
        "User-agent: *\nDisallow: /search\nAllow: /search/suggest.json\n"
    ),
}
"""robots.txt files that leave the search open: the guard must not be a blanket refusal."""


def broken(kind: str) -> Reply:
    """A robots.txt request that cannot be answered with a usable file."""

    def fail(request: httpx.Request) -> httpx.Response:
        if kind == "connection_error":
            raise httpx.ConnectError("connection refused", request=request)
        if kind == "timeout":
            raise httpx.ReadTimeout("no answer", request=request)
        raise AssertionError(kind)

    return fail


UNREADABLE: dict[str, Reply] = {
    "server_error_500": reply_status(500),
    "unavailable_503": reply_status(503),
    "a_web_page_instead": lambda _request: html_response("<html><body>Welcome</body></html>"),
    "connection_error": broken("connection_error"),
    "timeout": broken("timeout"),
}
"""Answers that are not a robots.txt. RFC 9309: unreachable means disallowed."""


def one_store_denying(world: GuardWorld, robots: str | Reply) -> None:
    """Alpha publishes ``robots``; Beta is an ordinary working store."""
    world.add(store_for("alpha"), robots=robots)
    world.add(store_for("beta"))


# --------------------------------------------------------------------------------------------
# A disallowed URL is never requested
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("robots", DENIALS.values(), ids=list(DENIALS))
async def test_a_search_url_that_robots_txt_disallows_is_never_requested(
    robots: str, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    one_store_denying(world, robots)
    pipeline = build(understander=understanding(BLAZER))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.queries("alpha") == []
    assert [request.url.path for request in world.calls_to("alpha.example")] == ["/robots.txt"]
    assert world.stray == []


@pytest.mark.parametrize("robots", DENIALS.values(), ids=list(DENIALS))
async def test_a_store_whose_robots_txt_forbids_the_search_is_skipped_in_plain_words(
    robots: str, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    one_store_denying(world, robots)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("alpha", StoreStatus.ROBOTS_DENIED)
    assert skipped.reason == messages.store_reason(StoreStatus.ROBOTS_DENIED)
    assert messages.store_warning("Alpha", StoreStatus.ROBOTS_DENIED) in response.warnings
    assert {scored.product.store for scored in response.products} == {"Beta"}


async def test_a_store_that_forbade_the_search_is_not_asked_again_on_the_next_search(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    one_store_denying(world, DENIALS["the search path"])
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.requests_to("alpha.example") == 1  # the one robots.txt, read once and remembered


# --------------------------------------------------------------------------------------------
# Not a blanket refusal
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("robots", OPEN.values(), ids=list(OPEN))
async def test_a_robots_txt_that_leaves_the_search_open_lets_it_through(
    robots: str, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    one_store_denying(world, robots)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 2  # both keyword variants
    assert {report.store_id for report in response.stores_used} == {"alpha", "beta"}


async def test_a_store_with_no_robots_txt_at_all_may_be_searched(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    one_store_denying(world, reply_status(404))  # RFC 9309: no file means no restriction
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 2
    assert {report.store_id for report in response.stores_used} == {"alpha", "beta"}


# --------------------------------------------------------------------------------------------
# An unreadable robots.txt is a refusal
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("robots", UNREADABLE.values(), ids=list(UNREADABLE))
async def test_a_robots_txt_that_cannot_be_read_means_no_search_is_sent(
    robots: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    one_store_denying(world, robots)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.queries("alpha") == []
    assert [report.store_id for report in response.stores_skipped] == ["alpha"]
    assert world.stray == []


# --------------------------------------------------------------------------------------------
# Thumbnails are held to the image host's robots.txt too
# --------------------------------------------------------------------------------------------


async def test_a_thumbnail_the_image_host_disallows_is_never_requested(
    world: GuardWorld, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    one_store_denying(world, "User-agent: *\nDisallow:\n")
    world.serve_cdn_robots("User-agent: *\nDisallow: /s/files\n")
    pipeline = build(understander=photo_search(), thumbnails=True)

    response = await pipeline.run(
        make_search_request(image=photo, text="black oversized blazer"), settings
    )

    assert world.thumbnails == []
    assert response.result_count > 0  # the search still answers, ranked without the photo


async def test_thumbnails_are_requested_when_the_image_host_allows_them(
    world: GuardWorld, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    one_store_denying(world, "User-agent: *\nDisallow:\n")
    pipeline = build(understander=photo_search(), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text="black oversized blazer"), settings)

    assert world.thumbnails  # the refusal above is the robots.txt's doing, not the set-up's
