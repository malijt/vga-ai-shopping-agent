"""robots.txt checker (plan 6.2.1): protego matching, RFC 9309 status handling, caching.

The robots bodies are the saved Namshi and 6thStreet/AIVI files and files rebuilt from the rules the
Noon, Level Shoes, Oh Polly and Luxury For You reports quote (see the header of each fixture). The
verdicts asserted are the ones those reports give.
"""

import asyncio
from urllib.robotparser import RobotFileParser

import httpx
import pytest
import respx

from tests.factories import make_store_config
from tests.fakes import FakeClock
from tests.fetch.conftest import ALLOW_ALL_ROBOTS, HOST, ROBOTS_URL, fixture_text, text_response
from vga.errors import StoreBlockedError
from vga.fetch.client import PoliteClient
from vga.fetch.errors import BlockedError, CooldownError, RobotsDeniedError
from vga.fetch.robots import ROBOTS_TTL_S, RobotsChecker
from vga.models import StoreConfig
from vga.settings import Settings


def store_for(host: str, *extra_hosts: str) -> StoreConfig:
    return make_store_config(
        id=host.split(".")[-2],
        name=host,
        search_url_template=f"https://{host}/search?q={{query}}",
        allowed_hosts=[host, *extra_hosts],
    )


async def verdict(
    robots: RobotsChecker, router: respx.MockRouter, fixture: str, host: str, url: str
) -> bool:
    router.get(f"https://{host}/robots.txt").mock(
        return_value=text_response(fixture_text(fixture), content_type="text/plain; charset=utf-8")
    )
    return await robots.can_fetch(url, store_for(host))


# --------------------------------------------------------------------------------------------
# Verdicts the qualification reports give
# --------------------------------------------------------------------------------------------

NOON = "https://www.noon.com"
LEVEL = "https://www.levelshoes.com"
NAMSHI = "https://www.namshi.com"
OHPOLLY = "https://ohpolly.ae"
LFY = "https://luxuryforyou.com"
AIVI = "https://en-ae.aivi.com"

VERDICTS = [
    # Noon (noon.md): the three wildcard rules block every form of the search URL.
    ("robots.noon.txt", f"{NOON}/uae-en/search/?q=black%20blazer", False),
    ("robots.noon.txt", f"{NOON}/uae-en/search?q=black%20blazer", False),
    ("robots.noon.txt", f"{NOON}/uae-en/search", False),
    ("robots.noon.txt", f"{NOON}/uae-en/fashion/men-31225/", True),
    ("robots.noon.txt", f"{NOON}/_svc/anything", False),
    ("robots.noon.txt", f"{NOON}/uae-en/searching-for-shoes/", True),  # `$` anchors, not a prefix
    # Level Shoes (level-shoes.md): `*/catalogsearch/` blocks the Magento search page.
    ("robots.levelshoes.txt", f"{LEVEL}/catalogsearch/result/?q=sneakers", False),
    ("robots.levelshoes.txt", f"{LEVEL}/women/shoes/sneakers.html", True),
    (
        "robots.levelshoes.txt",
        f"{LEVEL}/new-balance-574-sneakers-green-suede-women-low-tops-m0yrt8.html",
        True,
    ),
    ("robots.levelshoes.txt", f"{LEVEL}/women/shoes/sneakers.html?sortBy=price", False),
    ("robots.levelshoes.txt", f"{LEVEL}/api/anything", False),
    # Namshi (namshi.md): `Disallow: ?q=` has no leading slash; read as `*?q=` it blocks search.
    ("robots.namshi.txt", f"{NAMSHI}/uae-en/search?q=black%20blazer", False),
    ("robots.namshi.txt", f"{NAMSHI}/uae-en/women/search/?q=blazer", False),
    ("robots.namshi.txt", f"{NAMSHI}/uae-en/women-clothing/", True),
    ("robots.namshi.txt", f"{NAMSHI}/uae-en/women-clothing/?discount_percent=30", False),
    # Oh Polly and Club L London: the Shopify suggest endpoint is open, other paths are not.
    (
        "robots.ohpolly.txt",
        f"{OHPOLLY}/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product"
        "&resources%5Blimit%5D=10",
        True,
    ),
    ("robots.ohpolly.txt", f"{OHPOLLY}/search?q=black+blazer", True),
    ("robots.ohpolly.txt", f"{OHPOLLY}/collections/jackets", True),
    ("robots.ohpolly.txt", f"{OHPOLLY}/products.json", True),
    ("robots.ohpolly.txt", f"{OHPOLLY}/collections/jackets?sort_by=price-ascending", False),
    ("robots.ohpolly.txt", f"{OHPOLLY}/collections/jackets+coats", False),
    ("robots.ohpolly.txt", f"{OHPOLLY}/cart/add", False),
    ("robots.ohpolly.txt", f"{OHPOLLY}/account/login", False),
    # Luxury For You: everything but the account area.
    ("robots.lfy.txt", f"{LFY}/ae_en/results?query=black%20blazer", True),
    ("robots.lfy.txt", f"{LFY}/ae_en/products/blazer-delilah-21on", True),
    ("robots.lfy.txt", f"{LFY}/account/orders", False),
    # 6thStreet / AIVI saved file: the search path and an exact-match `$` rule.
    ("robots.aivi.txt", f"{AIVI}/catalogsearch/result/?q=blazer", False),
    ("robots.aivi.txt", f"{AIVI}/cart", False),
    ("robots.aivi.txt", f"{AIVI}/cart-pillows", True),
]


@pytest.mark.parametrize(("fixture", "url", "allowed"), VERDICTS)
async def test_the_verdict_matches_the_qualification_report(
    robots: RobotsChecker, router: respx.MockRouter, fixture: str, url: str, allowed: bool
) -> None:
    host = httpx.URL(url).host

    assert await verdict(robots, router, fixture, host, url) is allowed


async def test_a_denied_url_raises_robots_denied_with_the_reason_in_detail(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    router.get("https://www.noon.com/robots.txt").mock(
        return_value=text_response(fixture_text("robots.noon.txt"))
    )

    with pytest.raises(RobotsDeniedError) as excinfo:
        await robots.ensure_allowed(f"{NOON}/uae-en/search?q=x", store_for("www.noon.com"))

    assert "disallows" in (excinfo.value.detail or "")
    assert excinfo.value.store_status.value == "robots_denied"


def test_the_standard_library_parser_would_have_allowed_noons_search_on_this_python() -> None:
    """Why protego: on Python 3.12 ``urllib.robotparser`` ignores ``*`` and ``$`` (noon.md)."""
    stdlib = RobotFileParser()
    stdlib.parse(fixture_text("robots.noon.txt").splitlines())

    assert stdlib.can_fetch("anybot", f"{NOON}/uae-en/search/?q=black%20blazer") is True


@pytest.mark.parametrize(
    ("rule", "url", "allowed"),
    [
        ("Disallow: ?q=", "https://x.example/search?q=a", False),
        ("Disallow: ?q=", "https://x.example/search?p=1", True),
        ("Disallow: search", "https://x.example/uae/search/a", False),
        ("Disallow: /*/search?", "https://x.example/uae/search?q=a", False),
        ("Disallow: /*/search$", "https://x.example/uae/search", False),
        ("Disallow: /*/search$", "https://x.example/uae/search/more", True),
        ("Disallow: */catalogsearch/", "https://x.example/ae/catalogsearch/result", False),
        ("Allow: ?q=\nDisallow: /", "https://x.example/search?q=a", True),
        ("Disallow:", "https://x.example/anything", True),
        ("", "https://x.example/anything", True),
    ],
)
async def test_wildcards_and_rules_without_a_leading_slash(
    robots: RobotsChecker, router: respx.MockRouter, rule: str, url: str, allowed: bool
) -> None:
    router.get("https://x.example/robots.txt").mock(
        return_value=text_response(f"User-agent: *\n{rule}\n")
    )

    assert await robots.can_fetch(url, store_for("x.example")) is allowed


async def test_only_the_group_for_our_user_agent_applies(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    body = "User-agent: GPTBot\nAllow: /\n\nUser-agent: *\nDisallow: /search\n"
    router.get("https://x.example/robots.txt").mock(return_value=text_response(body))

    assert await robots.can_fetch("https://x.example/search?q=a", store_for("x.example")) is False


async def test_a_group_naming_our_own_user_agent_is_honoured(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    body = "User-agent: vga-shopping-agent-demo\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    router.get("https://x.example/robots.txt").mock(return_value=text_response(body))

    assert await robots.can_fetch("https://x.example/search?q=a", store_for("x.example")) is False


# --------------------------------------------------------------------------------------------
# RFC 9309: what each kind of robots.txt answer means
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 410, 451])
async def test_a_4xx_answer_means_no_robots_file_so_everything_is_allowed(
    robots: RobotsChecker, router: respx.MockRouter, status: int
) -> None:
    router.get(ROBOTS_URL).mock(return_value=httpx.Response(status))

    assert await robots.can_fetch(f"https://{HOST}/search?q=a", make_store_config()) is True


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_a_5xx_answer_means_unreachable_so_everything_is_disallowed(
    robots: RobotsChecker, router: respx.MockRouter, status: int
) -> None:
    router.get(ROBOTS_URL).mock(return_value=httpx.Response(status))

    assert await robots.can_fetch(f"https://{HOST}/search?q=a", make_store_config()) is False


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("bad")],
)
async def test_an_unreachable_robots_file_means_everything_is_disallowed(
    robots: RobotsChecker, router: respx.MockRouter, failure: Exception
) -> None:
    router.get(ROBOTS_URL).mock(side_effect=failure)

    assert await robots.can_fetch(f"https://{HOST}/search?q=a", make_store_config()) is False


async def test_a_robots_request_that_hangs_means_disallowed_after_the_timeout(
    robots: RobotsChecker, router: respx.MockRouter, clock: FakeClock, settings: Settings
) -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await clock.sleep(1000)
        return httpx.Response(200)

    router.get(ROBOTS_URL).mock(side_effect=hang)
    started = clock.monotonic()

    allowed = await robots.can_fetch(f"https://{HOST}/search?q=a", make_store_config())

    assert allowed is False
    assert clock.monotonic() - started == pytest.approx(settings.timeout_s)


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        ("<!doctype html><html><body>Welcome</body></html>", "text/html; charset=utf-8"),
        ("<!DOCTYPE html><html></html>", "text/plain"),  # wrong type, still HTML
        ("  \n<html><head></head></html>", ""),
    ],
)
async def test_an_html_page_in_place_of_robots_txt_counts_as_unreachable(
    robots: RobotsChecker, router: respx.MockRouter, body: str, content_type: str
) -> None:
    router.get(ROBOTS_URL).mock(
        return_value=httpx.Response(
            200, content=body.encode(), headers={"content-type": content_type}
        )
    )

    assert await robots.can_fetch(f"https://{HOST}/search?q=a", make_store_config()) is False


async def test_the_namshi_alias_redirect_chain_ending_in_a_home_page_is_unreachable(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    """namshi.md: en-ae.namshi.com/robots.txt -> 301 -> 308 -> the HTML home page."""
    store = make_store_config(
        id="namshi",
        name="Namshi",
        search_url_template="https://en-ae.namshi.com/search?q={query}",
        allowed_hosts=["en-ae.namshi.com", "www.namshi.com"],
    )
    router.get("https://en-ae.namshi.com/robots.txt").mock(
        return_value=httpx.Response(
            301, headers={"location": "https://www.namshi.com/uae-en/robots.txt"}
        )
    )
    router.get("https://www.namshi.com/uae-en/robots.txt").mock(
        return_value=httpx.Response(308, headers={"location": "/uae-en/robots.txt/"})
    )
    router.get("https://www.namshi.com/uae-en/robots.txt/").mock(
        return_value=text_response("<html><body>home</body></html>", content_type="text/html")
    )

    assert await robots.can_fetch("https://en-ae.namshi.com/search?q=x", store) is False


async def test_a_redirect_to_the_canonical_host_is_followed_for_robots_txt(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    """oh-polly.md: www.ohpolly.ae/robots.txt answers 301 to the apex host."""
    store = make_store_config(
        id="ohpolly",
        name="Oh Polly",
        search_url_template="https://www.ohpolly.ae/search?q={query}",
        allowed_hosts=["www.ohpolly.ae", "ohpolly.ae"],
    )
    router.get("https://www.ohpolly.ae/robots.txt").mock(
        return_value=httpx.Response(301, headers={"location": "https://ohpolly.ae/robots.txt"})
    )
    router.get("https://ohpolly.ae/robots.txt").mock(
        return_value=text_response(fixture_text("robots.ohpolly.txt"))
    )

    assert await robots.can_fetch("https://www.ohpolly.ae/search?q=blazer", store) is True
    assert await robots.can_fetch("https://www.ohpolly.ae/cart/add", store) is False


async def test_an_empty_robots_file_allows_everything(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    router.get(ROBOTS_URL).mock(return_value=text_response(""))

    assert await robots.can_fetch(f"https://{HOST}/anything", make_store_config()) is True


# --------------------------------------------------------------------------------------------
# A block while fetching robots.txt is a block
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [403, 429])
async def test_a_blocked_robots_request_blocks_the_store_with_one_request(
    robots: RobotsChecker, client: PoliteClient, router: respx.MockRouter, status: int
) -> None:
    route = router.get(ROBOTS_URL).mock(return_value=httpx.Response(status))
    store = make_store_config()

    with pytest.raises(BlockedError):
        await robots.ensure_allowed(f"https://{HOST}/search?q=a", store)
    with pytest.raises(CooldownError):
        await robots.ensure_allowed(f"https://{HOST}/search?q=b", store)

    assert route.call_count == 1


async def test_a_challenge_page_served_for_robots_txt_blocks_the_store(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    router.get(ROBOTS_URL).mock(
        return_value=text_response(
            "<html><title>Just a moment...</title></html>", content_type="text/html"
        )
    )

    with pytest.raises(BlockedError):
        await robots.ensure_allowed(f"https://{HOST}/search?q=a", make_store_config())


async def test_robots_txt_is_only_fetched_from_an_allowed_https_host(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    from vga.fetch.errors import UrlNotAllowedError

    with pytest.raises(UrlNotAllowedError):
        await robots.ensure_allowed("https://evil.example/search?q=a", make_store_config())
    with pytest.raises(UrlNotAllowedError):
        await robots.ensure_allowed(f"http://{HOST}/search?q=a", make_store_config())

    assert router.calls.call_count == 0


# --------------------------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------------------------


async def test_robots_txt_is_fetched_once_per_host(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    route = router.get(ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    store = make_store_config()

    for query in ("a", "b", "c"):
        await robots.ensure_allowed(f"https://{HOST}/search?q={query}", store)

    assert route.call_count == 1


async def test_each_host_has_its_own_robots_file(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    store = make_store_config(allowed_hosts=[HOST, "cdn.demo-store.example"])
    main = router.get(ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    cdn = router.get("https://cdn.demo-store.example/robots.txt").mock(
        return_value=text_response("User-agent: *\nDisallow: /private\n")
    )

    assert await robots.can_fetch(f"https://{HOST}/private", store) is True
    assert await robots.can_fetch("https://cdn.demo-store.example/private", store) is False
    assert (main.call_count, cdn.call_count) == (1, 1)


async def test_a_parsed_robots_file_is_trusted_for_a_day_then_fetched_again(
    robots: RobotsChecker, router: respx.MockRouter, clock: FakeClock
) -> None:
    route = router.get(ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    store = make_store_config()
    await robots.ensure_allowed(f"https://{HOST}/search?q=a", store)

    clock.advance(ROBOTS_TTL_S - 10)
    await robots.ensure_allowed(f"https://{HOST}/search?q=a", store)
    assert route.call_count == 1

    clock.advance(20)
    await robots.ensure_allowed(f"https://{HOST}/search?q=a", store)
    assert route.call_count == 2


async def test_an_unreachable_verdict_is_remembered_for_the_cooldown_without_new_requests(
    robots: RobotsChecker,
    router: respx.MockRouter,
    clock: FakeClock,
    settings: Settings,
) -> None:
    route = router.get(ROBOTS_URL).mock(return_value=httpx.Response(503))
    store = make_store_config()
    assert await robots.can_fetch(f"https://{HOST}/search?q=a", store) is False

    assert await robots.can_fetch(f"https://{HOST}/search?q=b", store) is False
    assert route.call_count == 1  # no retry, no new request, within the cooldown

    clock.advance(settings.store_cooldown_s + 1)
    route.mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    assert await robots.can_fetch(f"https://{HOST}/search?q=c", store) is True
    assert route.call_count == 2


async def test_concurrent_first_searches_share_one_robots_request(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    route = router.get(ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    store = make_store_config()

    await asyncio.gather(
        *(robots.ensure_allowed(f"https://{HOST}/search?q={i}", store) for i in range(5))
    )

    assert route.call_count == 1


async def test_concurrent_searches_all_see_a_block_from_the_one_robots_request(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    route = router.get(ROBOTS_URL).mock(return_value=httpx.Response(403))
    store = make_store_config()

    outcomes = await asyncio.gather(
        *(robots.ensure_allowed(f"https://{HOST}/search?q={i}", store) for i in range(3)),
        return_exceptions=True,
    )

    assert route.call_count == 1
    assert isinstance(outcomes[0], BlockedError)
    # whoever asked after the block sees the cooldown, never a second request
    assert all(isinstance(outcome, StoreBlockedError) for outcome in outcomes)


async def test_cancelling_the_task_that_fetches_robots_txt_does_not_cancel_the_others(
    robots: RobotsChecker, router: respx.MockRouter
) -> None:
    calls = 0

    async def first_hangs(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.Event().wait()
        return text_response(ALLOW_ALL_ROBOTS)

    router.get(ROBOTS_URL).mock(side_effect=first_hangs)
    store = make_store_config()
    leader = asyncio.create_task(robots.ensure_allowed(f"https://{HOST}/search?q=a", store))
    await asyncio.sleep(0)
    follower = asyncio.create_task(robots.ensure_allowed(f"https://{HOST}/search?q=b", store))
    for _ in range(5):
        await asyncio.sleep(0)

    leader.cancel()

    assert await follower is None
    assert leader.cancelled()
    assert calls == 2


async def test_a_crawl_delay_slows_the_host_down(
    robots: RobotsChecker, client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(ROBOTS_URL).mock(return_value=text_response("User-agent: *\nCrawl-delay: 3\n"))
    router.get(f"https://{HOST}/page").mock(return_value=text_response("ok"))
    store = make_store_config()
    await robots.ensure_allowed(f"https://{HOST}/page", store)
    started = clock.monotonic()

    await client.fetch(f"https://{HOST}/page", store, client.page_policy(store))
    await client.fetch(f"https://{HOST}/page", store, client.page_policy(store))

    assert clock.monotonic() - started >= 3.0 - 1e-9


def two_host_store() -> StoreConfig:
    return make_store_config(
        search_url_template="https://www.shop.example/search?q={query}",
        allowed_hosts=["www.shop.example", "shop.example"],
    )


async def test_a_crawl_delay_on_one_host_of_a_store_slows_the_store_on_its_other_host_too(
    robots: RobotsChecker, client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get("https://www.shop.example/robots.txt").mock(
        return_value=text_response("User-agent: *\nCrawl-delay: 3\n")
    )
    router.get("https://shop.example/robots.txt").mock(return_value=text_response(""))
    router.get(url__startswith="https://shop.example/page").mock(return_value=text_response("ok"))
    store = two_host_store()
    await robots.ensure_allowed("https://www.shop.example/search?q=a", store)
    await robots.ensure_allowed("https://shop.example/page", store)
    first = clock.monotonic()

    await client.fetch("https://shop.example/page", store, client.page_policy(store))
    await client.fetch("https://shop.example/page", store, client.page_policy(store))

    assert clock.monotonic() - first >= 3.0 - 1e-9


async def test_a_shorter_crawl_delay_on_the_other_host_does_not_undo_a_longer_one(
    robots: RobotsChecker, client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get("https://www.shop.example/robots.txt").mock(
        return_value=text_response("User-agent: *\nCrawl-delay: 5\n")
    )
    router.get("https://shop.example/robots.txt").mock(
        return_value=text_response("User-agent: *\nCrawl-delay: 1\n")
    )
    router.get(url__startswith="https://www.shop.example/page").mock(
        return_value=text_response("ok")
    )
    store = two_host_store()
    await robots.ensure_allowed("https://www.shop.example/search?q=a", store)
    await robots.ensure_allowed("https://shop.example/page", store)
    await client.fetch("https://www.shop.example/page", store, client.page_policy(store))
    first = clock.monotonic()

    await client.fetch("https://www.shop.example/page", store, client.page_policy(store))

    assert clock.monotonic() - first >= 5.0 - 1e-9
