"""The polite client: honest identity, https only, redirects, size cap, timeouts, blocks, no
retries (plan 6.1.1 to 6.1.4). Every request is answered by respx; time is the FakeClock."""

import asyncio

import httpx
import pytest
import respx

from tests.factories import make_settings, make_store_config
from tests.fakes import FakeClock
from tests.fetch.conftest import CDN, HOST, SEARCH_URL, text_response
from vga.fetch.client import IMAGE_TIMEOUT_S, PoliteClient
from vga.fetch.errors import (
    BlockedError,
    CooldownError,
    CrossDomainRedirectError,
    FetchFailedError,
    FetchTimeoutError,
    ResponseTooLargeError,
    RobotsDeniedError,
    TooManyRedirectsError,
    UrlNotAllowedError,
)
from vga.models import StoreConfig
from vga.settings import Settings


async def fetch(client: PoliteClient, store: StoreConfig, url: str = SEARCH_URL):
    return await client.fetch(url, store, client.page_policy(store))


# --------------------------------------------------------------------------------------------
# 6.1.1 Client wrapper
# --------------------------------------------------------------------------------------------


async def test_the_request_carries_the_configured_user_agent_and_no_cookie_or_extra_identity(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, settings: Settings
) -> None:
    route = router.get(SEARCH_URL).mock(return_value=text_response("hello"))

    response = await fetch(client, store)

    sent = route.calls.last.request
    assert sent.headers["user-agent"] == settings.user_agent
    assert "cookie" not in sent.headers
    assert "authorization" not in sent.headers
    assert "referer" not in sent.headers
    assert response.status == 200
    assert response.text == "hello"
    assert response.ok


async def test_an_http_url_is_refused_and_never_requested(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    with pytest.raises(UrlNotAllowedError):
        await fetch(client, store, f"http://{HOST}/search?q=x")

    assert router.calls.call_count == 0


async def test_an_oversized_response_is_aborted(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, settings: Settings
) -> None:
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, content=b"x" * (settings.max_response_bytes + 1))
    )

    with pytest.raises(ResponseTooLargeError):
        await fetch(client, store)


async def test_a_response_exactly_at_the_cap_is_accepted(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, settings: Settings
) -> None:
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, content=b"x" * settings.max_response_bytes)
    )

    response = await fetch(client, store)

    assert len(response.body) == settings.max_response_bytes


async def test_a_declared_length_over_the_cap_is_rejected(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, settings: Settings
) -> None:
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"content-length": str(settings.max_response_bytes + 1)},
            content=b"x",
        )
    )

    with pytest.raises(ResponseTooLargeError):
        await fetch(client, store)


async def test_a_store_can_raise_the_size_cap_above_the_global_one(
    client: PoliteClient, router: respx.MockRouter, settings: Settings
) -> None:
    big_store = make_store_config(max_response_bytes=3_000_000)
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, content=b"x" * (settings.max_response_bytes + 1000))
    )

    response = await fetch(client, big_store)

    assert len(response.body) > settings.max_response_bytes


async def test_a_store_can_lower_the_size_cap_below_the_global_one(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    small_store = make_store_config(max_response_bytes=100)
    router.get(SEARCH_URL).mock(return_value=httpx.Response(200, content=b"x" * 101))

    with pytest.raises(ResponseTooLargeError):
        await fetch(client, small_store)


async def test_the_size_cap_counts_decompressed_bytes(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, settings: Settings
) -> None:
    import gzip

    bomb = gzip.compress(b"a" * (settings.max_response_bytes + 1))
    assert len(bomb) < 10_000  # tiny on the wire, huge once unpacked
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, headers={"content-encoding": "gzip"}, content=bomb)
    )

    with pytest.raises(ResponseTooLargeError):
        await fetch(client, store)


async def test_a_slow_response_times_out_after_the_global_timeout(
    client: PoliteClient,
    store: StoreConfig,
    router: respx.MockRouter,
    clock: FakeClock,
    settings: Settings,
) -> None:
    attempts: list[str] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        await clock.sleep(1000)
        return httpx.Response(200)

    router.get(SEARCH_URL).mock(side_effect=hang)
    started = clock.monotonic()

    with pytest.raises(FetchTimeoutError):
        await fetch(client, store)

    assert clock.monotonic() - started == pytest.approx(settings.timeout_s)
    assert attempts == [SEARCH_URL]  # one request, no retry


async def test_a_store_can_set_its_own_timeout(
    client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    slow_store = make_store_config(timeout_s=15)

    async def slow(request: httpx.Request) -> httpx.Response:
        await clock.sleep(10)  # past the global 6 s, inside this store's 15 s
        return text_response("late but fine")

    router.get(SEARCH_URL).mock(side_effect=slow)

    response = await fetch(client, slow_store)

    assert response.text == "late but fine"


async def test_a_transport_failure_is_reported_not_raised_as_an_httpx_error(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(FetchFailedError):
        await fetch(client, store)
    assert router.calls.call_count == 1


async def test_an_httpx_timeout_is_reported_as_a_timeout(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(FetchTimeoutError):
        await fetch(client, store)


@pytest.mark.parametrize("status", [404, 410, 500, 502, 503])
async def test_an_error_status_is_returned_to_the_caller_and_never_retried(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, status: int
) -> None:
    route = router.get(SEARCH_URL).mock(return_value=httpx.Response(status))

    response = await fetch(client, store)

    assert response.status == status
    assert not response.ok
    assert route.call_count == 1


async def test_cookies_set_by_a_store_are_never_sent_back(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    route = router.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, headers={"set-cookie": "session=abc123; Path=/"})
    )

    await fetch(client, store)
    await fetch(client, store)

    assert "cookie" not in route.calls[1].request.headers


async def test_proxy_settings_in_the_environment_are_ignored(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY"):
        monkeypatch.setenv(name, "http://proxy.example:3128")
    polite = PoliteClient(settings, clock=FakeClock())

    http_client = polite._http_client()

    assert http_client._mounts == {}
    await polite.aclose()


def test_the_client_survives_a_new_event_loop(settings: Settings, router: respx.MockRouter) -> None:
    """A UI that runs ``asyncio.run`` for every request must not reuse a client from a dead loop."""
    first = make_store_config(id="first")
    second = make_store_config(
        id="second",
        search_url_template="https://www.second.example/search?q={query}",
        allowed_hosts=["www.second.example"],
    )
    router.get(SEARCH_URL).mock(return_value=text_response("one"))
    router.get("https://www.second.example/search?q=x").mock(return_value=text_response("two"))
    polite = PoliteClient(settings)

    one = asyncio.run(fetch(polite, first))
    two = asyncio.run(fetch(polite, second, "https://www.second.example/search?q=x"))

    assert (one.text, two.text) == ("one", "two")


# --------------------------------------------------------------------------------------------
# 6.1.2 Host allow-list (as the client enforces it)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/search?q=x",
        "https://127.0.0.1/search?q=x",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/search",
        "https://10.0.0.8/search",
        "https://localhost/search",
        f"https://{HOST}:8443/search",
        f"https://user:pw@{HOST}/search",
    ],
)
async def test_a_url_off_the_allow_list_is_never_requested(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, url: str
) -> None:
    with pytest.raises(UrlNotAllowedError):
        await fetch(client, store, url)

    assert router.calls.call_count == 0


async def test_a_listed_but_private_looking_host_is_still_never_requested(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    sneaky = make_store_config(
        search_url_template="https://metadata.google.internal/search?q={query}",
        allowed_hosts=["metadata.google.internal"],
    )

    with pytest.raises(UrlNotAllowedError):
        await fetch(client, sneaky, "https://metadata.google.internal/search?q=x")

    assert router.calls.call_count == 0


async def test_a_redirect_to_an_off_list_host_is_not_followed(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(302, headers={"location": f"https://www.{HOST}/x"})
    )
    evil = router.get(url__startswith="https://www.www.demo-store.example/")

    with pytest.raises((CrossDomainRedirectError, UrlNotAllowedError)):
        await fetch(client, store)

    assert not evil.called
    assert router.calls.call_count == 1


@pytest.mark.parametrize(
    "target",
    [
        "https://127.0.0.1/admin",
        "https://169.254.169.254/latest/meta-data/",
        "http://www.demo-store.example/search?q=x",
        "https://[::1]/",
        "https://evil.example/landing",
    ],
)
async def test_a_redirect_to_a_forbidden_target_is_not_requested(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, target: str
) -> None:
    router.get(SEARCH_URL).mock(return_value=httpx.Response(301, headers={"location": target}))

    with pytest.raises((CrossDomainRedirectError, UrlNotAllowedError)):
        await fetch(client, store)

    assert [str(call.request.url) for call in router.calls] == [SEARCH_URL]


async def test_a_redirect_to_another_registered_domain_stops_the_request_even_if_listed(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    moved = make_store_config(
        allowed_hosts=[HOST, CDN, "www.new-home.example"],
    )
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(301, headers={"location": "https://www.new-home.example/s"})
    )
    target = router.get("https://www.new-home.example/s").mock(return_value=text_response("hi"))

    with pytest.raises(CrossDomainRedirectError):
        await fetch(client, moved)

    assert not target.called


async def test_a_redirect_between_two_allowed_hosts_of_the_same_domain_is_followed(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    two_hosts = make_store_config(
        search_url_template="https://www.shop.example/search?q={query}",
        allowed_hosts=["www.shop.example", "shop.example"],
    )
    router.get("https://www.shop.example/search?q=x").mock(
        return_value=httpx.Response(301, headers={"location": "https://shop.example/search?q=x"})
    )
    router.get("https://shop.example/search?q=x").mock(return_value=text_response("landed"))

    response = await fetch(client, two_hosts, "https://www.shop.example/search?q=x")

    assert response.text == "landed"
    assert response.url == "https://shop.example/search?q=x"


TWO_HOSTS = {
    "search_url_template": "https://www.shop.example/search?q={query}",
    "allowed_hosts": ["www.shop.example", "shop.example"],
}


class Vetting:
    """A ``vet_redirect`` that records what it was asked and refuses the hosts it is told to."""

    def __init__(self, *, refuse: str | None = None) -> None:
        self.asked: list[tuple[str, str]] = []
        self._refuse = refuse

    async def __call__(self, url: str, store: StoreConfig) -> None:
        self.asked.append((url, store.id))
        if self._refuse and self._refuse in url:
            raise RobotsDeniedError(detail=f"robots.txt disallows {url}")


async def test_every_redirect_target_is_vetted_before_it_is_requested(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    two_hosts = make_store_config(**TWO_HOSTS)
    router.get("https://www.shop.example/a").mock(
        return_value=httpx.Response(302, headers={"location": "https://shop.example/b"})
    )
    router.get("https://shop.example/b").mock(
        return_value=httpx.Response(302, headers={"location": "/c"})
    )
    router.get("https://shop.example/c").mock(return_value=text_response("landed"))
    vetting = Vetting()

    response = await client.fetch(
        "https://www.shop.example/a",
        two_hosts,
        client.page_policy(two_hosts),
        vet_redirect=vetting,
    )

    assert response.text == "landed"
    assert vetting.asked == [
        ("https://shop.example/b", two_hosts.id),
        ("https://shop.example/c", two_hosts.id),
    ]  # the URL the caller asked for is the caller's to check, not the client's


async def test_a_redirect_the_vetting_refuses_is_not_requested_and_the_refusal_reaches_the_caller(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    two_hosts = make_store_config(**TWO_HOSTS)
    router.get("https://www.shop.example/a").mock(
        return_value=httpx.Response(302, headers={"location": "https://shop.example/b"})
    )
    target = router.get("https://shop.example/b").mock(return_value=text_response("landed"))

    with pytest.raises(RobotsDeniedError):
        await client.fetch(
            "https://www.shop.example/a",
            two_hosts,
            client.page_policy(two_hosts),
            vet_redirect=Vetting(refuse="shop.example/b"),
        )

    assert not target.called
    assert client.cooldowns.remaining(two_hosts.id) == 0  # a refusal is not a block


async def test_a_redirect_to_a_host_off_the_allow_list_is_refused_before_it_is_vetted(
    client: PoliteClient, router: respx.MockRouter
) -> None:
    two_hosts = make_store_config(**TWO_HOSTS)
    router.get("https://www.shop.example/a").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.shop.example/b"})
    )
    other = router.get("https://other.shop.example/b").mock(return_value=text_response("x"))
    vetting = Vetting()

    with pytest.raises(UrlNotAllowedError):
        await client.fetch(
            "https://www.shop.example/a",
            two_hosts,
            client.page_policy(two_hosts),
            vet_redirect=vetting,
        )

    assert vetting.asked == []  # robots.txt of a host we may not contact is never asked for
    assert not other.called


async def test_a_fetch_without_a_redirect_asks_the_vetting_nothing(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(return_value=text_response("hello"))
    vetting = Vetting()

    await client.fetch(SEARCH_URL, store, client.page_policy(store), vet_redirect=vetting)

    assert vetting.asked == []


async def test_a_relative_redirect_is_resolved_and_followed(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(302, headers={"location": "/search/new?q=black%20blazer"})
    )
    router.get(f"https://{HOST}/search/new?q=black%20blazer").mock(
        return_value=text_response("moved")
    )

    assert (await fetch(client, store)).text == "moved"


async def test_at_most_three_redirects_are_followed(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    for i in range(6):
        router.get(f"https://{HOST}/r{i}").mock(
            return_value=httpx.Response(302, headers={"location": f"/r{i + 1}"})
        )

    with pytest.raises(TooManyRedirectsError):
        await fetch(client, store, f"https://{HOST}/r0")

    assert router.calls.call_count == 4  # the first request and 3 followed redirects


async def test_three_redirects_are_allowed(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    for i in range(3):
        router.get(f"https://{HOST}/r{i}").mock(
            return_value=httpx.Response(302, headers={"location": f"/r{i + 1}"})
        )
    router.get(f"https://{HOST}/r3").mock(return_value=text_response("end"))

    assert (await fetch(client, store, f"https://{HOST}/r0")).text == "end"


async def test_a_redirect_without_a_location_is_returned_as_it_is(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(return_value=httpx.Response(302))

    response = await fetch(client, store)

    assert response.status == 302
    assert not response.ok


# --------------------------------------------------------------------------------------------
# 6.1.3 Rate limiting through the client
# --------------------------------------------------------------------------------------------


async def test_requests_to_one_store_are_spaced_by_its_rate(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(url__startswith=f"https://{HOST}/").mock(return_value=text_response("ok"))
    started = clock.monotonic()

    await asyncio.gather(*(fetch(client, store, f"https://{HOST}/p{i}") for i in range(4)))

    assert clock.monotonic() - started >= 3.0 - 1e-9


async def test_a_store_can_set_its_own_rate(
    client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    quick = make_store_config(rps=4)
    router.get(url__startswith=f"https://{HOST}/").mock(return_value=text_response("ok"))
    started = clock.monotonic()

    await asyncio.gather(*(fetch(client, quick, f"https://{HOST}/p{i}") for i in range(5)))

    assert clock.monotonic() - started == pytest.approx(1.0)


async def test_every_redirect_hop_takes_a_rate_limit_slot(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(f"https://{HOST}/a").mock(
        return_value=httpx.Response(302, headers={"location": "/b"})
    )
    router.get(f"https://{HOST}/b").mock(return_value=text_response("ok"))
    started = clock.monotonic()

    await fetch(client, store, f"https://{HOST}/a")

    assert clock.monotonic() - started == pytest.approx(1.0)


async def test_the_hosts_of_one_store_share_one_rate(
    client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    two_hosts = make_store_config(**TWO_HOSTS)
    router.get(url__startswith="https://www.shop.example/").mock(return_value=text_response("ok"))
    router.get(url__startswith="https://shop.example/").mock(return_value=text_response("ok"))
    started = clock.monotonic()

    await asyncio.gather(
        fetch(client, two_hosts, "https://www.shop.example/a"),
        fetch(client, two_hosts, "https://shop.example/b"),
        fetch(client, two_hosts, "https://www.shop.example/c"),
    )

    assert clock.monotonic() - started == pytest.approx(2.0)  # three requests, one a second


async def test_a_redirect_to_the_stores_other_host_takes_the_stores_next_slot(
    client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    two_hosts = make_store_config(**TWO_HOSTS)
    router.get("https://www.shop.example/a").mock(
        return_value=httpx.Response(302, headers={"location": "https://shop.example/b"})
    )
    router.get("https://shop.example/b").mock(return_value=text_response("ok"))
    started = clock.monotonic()

    await fetch(client, two_hosts, "https://www.shop.example/a")

    assert clock.monotonic() - started == pytest.approx(1.0)


async def test_an_image_cdn_keeps_its_own_rate_apart_from_the_store(
    client: PoliteClient, router: respx.MockRouter, clock: FakeClock
) -> None:
    shop = make_store_config(
        search_url_template="https://www.shop.example/search?q={query}",
        allowed_hosts=["www.shop.example", "cdn.shopify.com"],
    )
    router.get("https://www.shop.example/a").mock(return_value=text_response("ok"))
    router.get("https://cdn.shopify.com/i.jpg").mock(return_value=text_response("ok"))
    started = clock.monotonic()

    await asyncio.gather(
        fetch(client, shop, "https://www.shop.example/a"),
        client.fetch(
            "https://cdn.shopify.com/i.jpg",
            shop,
            client.image_policy(shop, "cdn.shopify.com", timeout_s=4),
        ),
    )

    assert clock.monotonic() == started  # neither waited for the other


# --------------------------------------------------------------------------------------------
# 6.1.4 Block detection and cooldown
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403, 429])
async def test_a_blocking_status_makes_exactly_one_request_and_no_retry(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, status: int
) -> None:
    route = router.get(SEARCH_URL).mock(return_value=httpx.Response(status))

    with pytest.raises(BlockedError):
        await fetch(client, store)

    assert route.call_count == 1


@pytest.mark.parametrize("status", [403, 429])
async def test_after_a_block_the_store_gets_no_request_until_the_cooldown_ends(
    client: PoliteClient,
    store: StoreConfig,
    router: respx.MockRouter,
    clock: FakeClock,
    settings: Settings,
    status: int,
) -> None:
    route = router.get(url__startswith=f"https://{HOST}/").mock(return_value=httpx.Response(status))
    with pytest.raises(BlockedError):
        await fetch(client, store)

    with pytest.raises(CooldownError):
        await fetch(client, store, f"https://{HOST}/search?q=another")
    assert route.call_count == 1  # the second search made zero requests

    clock.advance(settings.store_cooldown_s - 1)
    with pytest.raises(CooldownError):
        await fetch(client, store)
    assert route.call_count == 1

    clock.advance(2)
    route.mock(return_value=text_response("back again"))
    assert (await fetch(client, store)).text == "back again"
    assert route.call_count == 2


async def test_a_cooldown_covers_the_store_not_one_host(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(return_value=httpx.Response(403))
    other = router.get(f"https://{CDN}/robots.txt").mock(return_value=text_response("x"))
    with pytest.raises(BlockedError):
        await fetch(client, store)

    with pytest.raises(CooldownError):
        await fetch(client, store, f"https://{CDN}/robots.txt")

    assert not other.called


async def test_another_store_is_not_affected_by_a_blocked_one(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(return_value=httpx.Response(403))
    friend = make_store_config(
        id="friend",
        name="Friend",
        search_url_template="https://www.friend.example/s?q={query}",
        allowed_hosts=["www.friend.example"],
    )
    router.get("https://www.friend.example/s?q=x").mock(return_value=text_response("fine"))
    with pytest.raises(BlockedError):
        await fetch(client, store)

    assert (await fetch(client, friend, "https://www.friend.example/s?q=x")).text == "fine"


@pytest.mark.parametrize(
    "body",
    [
        "<html><head><title>Just a moment...</title></head><body>Checking...</body></html>",
        '<html><div class="cf-browser-verification">wait</div></html>',
        "<html><title>Attention Required! | Cloudflare</title></html>",
        '<html><div id="px-captcha"></div></html>',
        "<html><body>Pardon Our Interruption</body></html>",
        "<html><body>Please verify you are human to continue</body></html>",
        "<html><body>Access Denied - you don't have permission</body></html>",
        "<html><body><script src='/_Incapsula_Resource?x=1'></script></body></html>",
    ],
)
async def test_a_challenge_page_with_status_200_counts_as_blocked(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter, body: str
) -> None:
    route = router.get(SEARCH_URL).mock(return_value=text_response(body, content_type="text/html"))

    with pytest.raises(BlockedError) as excinfo:
        await fetch(client, store)

    assert route.call_count == 1
    assert "challenge" in (excinfo.value.detail or "")
    with pytest.raises(CooldownError):
        await fetch(client, store)
    assert route.call_count == 1


async def test_json_that_mentions_a_challenge_phrase_is_not_a_block(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    body = '{"products": [{"title": "Access Denied Tee", "body": "Just a moment... wow"}]}'
    router.get(SEARCH_URL).mock(return_value=text_response(body, content_type="application/json"))

    response = await fetch(client, store)

    assert response.ok


async def test_a_challenge_marker_beyond_the_first_20_kb_is_ignored(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    page = "<html><body>" + "x" * 25_000 + "access denied</body></html>"
    router.get(SEARCH_URL).mock(return_value=text_response(page, content_type="text/html"))

    assert (await fetch(client, store)).ok


async def test_a_redirect_to_a_login_page_counts_as_blocked(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    router.get(SEARCH_URL).mock(
        return_value=httpx.Response(302, headers={"location": "/account/login?return_to=/search"})
    )
    login = router.get(url__startswith=f"https://{HOST}/account/login")

    with pytest.raises(BlockedError):
        await fetch(client, store)

    assert not login.called


async def test_concurrent_searches_make_one_blocked_request_not_several(
    client: PoliteClient, store: StoreConfig, router: respx.MockRouter
) -> None:
    route = router.get(url__startswith=f"https://{HOST}/").mock(return_value=httpx.Response(403))

    outcomes = await asyncio.gather(
        *(fetch(client, store, f"https://{HOST}/search?q={i}") for i in range(4)),
        return_exceptions=True,
    )

    assert route.call_count == 1
    assert isinstance(outcomes[0], BlockedError)
    assert all(isinstance(outcome, CooldownError) for outcome in outcomes[1:])


# --------------------------------------------------------------------------------------------
# Per-request limits come from the store, else the settings
# --------------------------------------------------------------------------------------------


def test_the_page_policy_prefers_the_store_values(settings: Settings, clock: FakeClock) -> None:
    polite = PoliteClient(settings, clock=clock)
    plain = make_store_config()
    tuned = make_store_config(rps=2, timeout_s=15, max_response_bytes=3_000_000)

    assert polite.page_policy(plain).rps == settings.rps_per_store
    assert polite.page_policy(plain).timeout_s == settings.timeout_s
    assert polite.page_policy(plain).max_bytes == settings.max_response_bytes
    assert (
        polite.page_policy(tuned).rps,
        polite.page_policy(tuned).timeout_s,
        polite.page_policy(tuned).max_bytes,
    ) == (2, 15, 3_000_000)


def test_an_image_cdn_gets_the_image_rate_but_the_stores_own_domain_keeps_the_store_rate(
    clock: FakeClock,
) -> None:
    settings = make_settings(rps_per_store=1, rps_images_per_host=5)
    polite = PoliteClient(settings, clock=clock)
    store = make_store_config()

    assert polite.image_policy(store, "cdn.shopify.com", timeout_s=4).rps == 5
    assert polite.image_policy(store, HOST, timeout_s=4).rps == 1
    assert polite.image_policy(store, CDN, timeout_s=4).rps == 1  # same registered domain


def test_a_thumbnail_on_the_stores_own_domain_is_in_the_stores_cooldown_not_a_hosts() -> None:
    polite = PoliteClient(make_settings(), clock=FakeClock())
    store = make_store_config()

    assert polite.image_policy(store, HOST, timeout_s=4).cooldown_key == store.id
    assert polite.image_policy(store, CDN, timeout_s=4).cooldown_key == store.id  # same domain


def test_a_thumbnail_on_a_separate_image_cdn_is_in_that_hosts_cooldown_not_the_stores() -> None:
    polite = PoliteClient(make_settings(), clock=FakeClock())
    store = make_store_config()

    policy = polite.image_policy(store, "cdn.shopify.com", timeout_s=4)

    assert policy.cooldown_key == "host:cdn.shopify.com"


def test_robots_txt_of_the_stores_own_domain_uses_the_page_policy(clock: FakeClock) -> None:
    polite = PoliteClient(make_settings(), clock=clock)
    store = make_store_config(rps=2, timeout_s=15)

    assert polite.robots_policy(store, HOST) == polite.page_policy(store)
    assert polite.robots_policy(store, CDN) == polite.page_policy(store)  # same registered domain


def test_robots_txt_of_an_image_cdn_uses_the_image_rate_timeout_and_its_own_cooldown_key(
    clock: FakeClock,
) -> None:
    polite = PoliteClient(make_settings(rps_per_store=1, rps_images_per_host=5), clock=clock)
    store = make_store_config(timeout_s=15)

    policy = polite.robots_policy(store, "cdn.shopify.com")

    assert (policy.rps, policy.timeout_s) == (5, IMAGE_TIMEOUT_S)
    assert policy.cooldown_key == "host:cdn.shopify.com"
    assert policy.accept != "image/*"  # it asks for a text file, not an image
