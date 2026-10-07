"""Plan 14.1.1, block policy (BRD Rule 2): a store that turns an honest client away is dropped,
never bypassed, and left alone for its cooldown.

Each test runs the real pipeline and the real store engine against a fake store that answers with a
403, a 429, a bot-challenge page, a CAPTCHA page, a login redirect or a blocked robots.txt.
"Exactly one request" counts the store's search-page requests: robots.txt is fetched first, once,
by design, so a blocked search page is two requests to the host in all and a blocked robots.txt is
one.
"""

import pytest

from tests.factories import make_search_request
from tests.fakes import FakeClock
from tests.guards.scraping.support import (
    CAPTCHA_HTML,
    CHALLENGE_HTML,
    GuardPipelines,
    GuardWorld,
    Reply,
    reply_html,
    reply_redirect,
    reply_status,
    understanding,
    understanding_by_words,
)
from tests.pipeline.builders import BLAZER, OUTFIT, SHIRT, outfit_understander
from tests.pipeline.world import store_for
from vga.models import StoreStatus
from vga.pipeline import messages
from vga.settings import Settings

BLOCKS: dict[str, Reply] = {
    "http_403": reply_status(403),
    "http_429_with_retry_after": reply_status(429, **{"Retry-After": "1"}),
    "http_401": reply_status(401),
    "cloudflare_challenge_page": reply_html(CHALLENGE_HTML),
    "captcha_page_with_a_503": reply_html(CAPTCHA_HTML, status=503),
    "redirect_to_a_login_page": reply_redirect("/account/login?return_url=%2Fsearch"),
}
"""Every way a store says "not you" that the client must not argue with."""

JARGON = ("http", "403", "429", "401", "captcha", "challenge", "cloudflare", "login", "robots")
"""Words that mean something to an engineer and nothing to a shopper."""

pytestmark = pytest.mark.parametrize("block", BLOCKS.values(), ids=list(BLOCKS))


def blocked_store(world: GuardWorld, block: Reply) -> None:
    """Alpha refuses every search with ``block``; Beta is an ordinary working store."""
    world.add(store_for("alpha"), reply=block)
    world.add(store_for("beta"))


# --------------------------------------------------------------------------------------------
# One request, no retry
# --------------------------------------------------------------------------------------------


async def test_a_store_that_blocks_the_search_gets_exactly_one_search_request(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=understanding(BLAZER))  # two keyword variants to tempt a retry

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert len(world.queries("alpha")) == 1  # not the second variant, not a second try
    assert world.requests_to("alpha.example") == 2  # robots.txt, then the one refused search
    assert world.stray == []  # and nothing else: no login page, no other address


# --------------------------------------------------------------------------------------------
# Skipped with a plain warning; the others carry on
# --------------------------------------------------------------------------------------------


async def test_a_blocked_store_is_skipped_and_the_other_stores_still_answer(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("alpha", StoreStatus.BLOCKED)
    assert [report.store_id for report in response.stores_used] == ["beta"]
    assert {scored.product.store for scored in response.products} == {"Beta"}
    assert response.result_count > 0


async def test_a_blocked_store_is_explained_to_the_shopper_in_plain_words(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    [skipped] = response.stores_skipped
    assert skipped.reason == messages.store_reason(StoreStatus.BLOCKED)
    assert messages.store_warning("Alpha", StoreStatus.BLOCKED) in response.warnings
    shopper_text = " ".join([skipped.reason or "", *response.warnings]).lower()
    assert [word for word in JARGON if word in shopper_text] == []


# --------------------------------------------------------------------------------------------
# The cooldown
# --------------------------------------------------------------------------------------------


async def test_a_second_search_inside_the_cooldown_sends_the_blocked_store_nothing(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=understanding(SHIRT))
    await pipeline.run(make_search_request(text="white shirt"), settings)
    sent_before = world.requests_to("alpha.example")
    clock.advance(settings.store_cooldown_s / 2)  # well inside the cooldown

    second = await pipeline.run(make_search_request(text="white shirt"), settings)

    assert world.requests_to("alpha.example") == sent_before  # not even robots.txt
    [skipped] = second.stores_skipped
    assert (skipped.store_id, skipped.status) == ("alpha", StoreStatus.COOLDOWN)
    assert messages.store_warning("Alpha", StoreStatus.COOLDOWN) in second.warnings
    assert world.stray == []


async def test_a_different_search_inside_the_cooldown_also_sends_the_blocked_store_nothing(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=understanding_by_words({"blazer": BLAZER, "shirt": SHIRT}))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    sent_before = world.requests_to("alpha.example")

    # Another garment, so no cached answer could stand in for a request.
    other = await pipeline.run(make_search_request(text="white cotton shirt"), settings)

    assert world.requests_to("alpha.example") == sent_before
    assert [report.store_id for report in other.stores_skipped] == ["alpha"]


async def test_the_blocked_store_is_asked_again_only_once_the_cooldown_has_ended(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings, clock: FakeClock
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    searches_before = len(world.queries("alpha"))
    clock.advance(settings.store_cooldown_s + 1)

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    # One honest new request; the block is not remembered forever, and not bypassed either.
    assert len(world.queries("alpha")) == searches_before + 1


# --------------------------------------------------------------------------------------------
# An outfit: four garments are four searches, but one refusal ends them all
# --------------------------------------------------------------------------------------------


async def test_an_outfit_photo_sends_a_store_that_blocks_it_one_search_request_in_all(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    blocked_store(world, block)
    pipeline = build(understander=outfit_understander())

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    # Four garments were searched at once; the first refusal started the cooldown, so the other
    # three searches waiting for their turn were never sent.
    assert len(world.queries("alpha")) == 1
    assert world.requests_to("alpha.example") == 2
    assert len(OUTFIT) == 4
    assert [report.store_id for report in response.stores_skipped] == ["alpha"]
    assert all(group.result_count > 0 for group in response.groups)  # Beta covers every garment


# --------------------------------------------------------------------------------------------
# A block on robots.txt itself
# --------------------------------------------------------------------------------------------


async def test_a_store_that_blocks_its_robots_txt_gets_that_one_request_and_nothing_else(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots=block)
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.queries("alpha") == []  # no search was sent without permission
    assert world.requests_to("alpha.example") == 1  # the robots.txt request that was refused
    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("alpha", StoreStatus.BLOCKED)
    assert world.stray == []


async def test_a_store_that_blocked_its_robots_txt_is_left_alone_on_the_next_search(
    block: Reply, world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"), robots=block)
    world.add(store_for("beta"))
    pipeline = build(understander=understanding(BLAZER))
    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.requests_to("alpha.example") == 1
