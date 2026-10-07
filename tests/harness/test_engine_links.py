"""The link check's page fetch goes through the project's own fetch engine (plan 16.1.1).

Nothing here touches the network: HTTP is answered by ``respx`` and time by ``FakeClock``. The
fetch is the real ``StoreSearchEngine`` and ``PoliteClient``, so these tests also prove that a link
is requested under the same rules as a search page: honest User-Agent, robots.txt, rate limit,
allowed hosts, redirect checks, cooldown.
"""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx

from eval.harness.engine_links import ACCEPT_HTML, EngineLinkFetch, MeteredLimiter, page_title
from eval.harness.links import LinkChecker, allowed_hosts_from_stores
from tests.factories import make_product, make_settings, make_store_config
from tests.fakes import FakeClock
from vga.fetch.client import FetchResponse
from vga.models import StoreConfig
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine

HOST = "www.demo-store.example"
PRODUCT = f"https://{HOST}/products/black-oversized-blazer"
ALLOW_ALL = "User-agent: *\nDisallow:\n"


def product_page(title: str = "Black Oversized Blazer | Demo Store") -> str:
    return f"<html><head><title>{title}</title></head><body><h1>Blazer</h1></body></html>"


def html(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, content=body.encode("utf-8"), headers={"content-type": "text/html; charset=utf-8"}
    )


def text(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, content=body.encode("utf-8"), headers={"content-type": "text/plain"}
    )


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def store() -> StoreConfig:
    return make_store_config()


@pytest.fixture
async def engine(
    settings: Settings, store: StoreConfig, clock: FakeClock, router: respx.MockRouter
) -> AsyncIterator[StoreSearchEngine]:
    router.get(f"https://{HOST}/robots.txt").mock(return_value=text(ALLOW_ALL))
    live = StoreSearchEngine(settings, StoreRegistry([store]), clock=clock)
    yield live
    await live.aclose()


@pytest.fixture
def fetch(engine: StoreSearchEngine, store: StoreConfig) -> EngineLinkFetch:
    return EngineLinkFetch(engine, [store])


class TestAnOrdinaryProductPage:
    async def test_it_opens_and_reports_status_title_and_no_redirect(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        router.get(PRODUCT).mock(return_value=html(product_page()))

        result = await fetch(PRODUCT)

        assert result.error is None
        assert result.status == 200
        assert result.title == "Black Oversized Blazer | Demo Store"
        assert result.final_url is None
        assert result.redirects == 0
        assert result.elapsed_s is not None

    async def test_it_sends_the_honest_user_agent_and_nothing_else_identifying(
        self, fetch: EngineLinkFetch, router: respx.MockRouter, settings: Settings
    ) -> None:
        route = router.get(PRODUCT).mock(return_value=html(product_page()))

        await fetch(PRODUCT)

        headers = route.calls.last.request.headers
        assert headers["user-agent"] == settings.user_agent
        assert "cookie" not in headers
        assert headers["accept"] == ACCEPT_HTML

    async def test_a_page_that_is_not_found_reports_its_status(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        router.get(PRODUCT).mock(return_value=html(product_page("404 Not Found"), 404))

        result = await fetch(PRODUCT)

        assert result.status == 404
        assert result.title == "404 Not Found"

    async def test_a_heavy_product_page_is_not_failed_for_its_size(
        self, fetch: EngineLinkFetch, router: respx.MockRouter, settings: Settings
    ) -> None:
        # Bigger than the 2 MB meant for a search answer, smaller than a link page may be.
        padding = "x" * (settings.max_response_bytes + 1_000_000)
        router.get(PRODUCT).mock(return_value=html(product_page() + f"<!-- {padding} -->"))

        result = await fetch(PRODUCT)

        assert result.error is None
        assert result.status == 200

    async def test_the_checker_passes_a_working_link_end_to_end(
        self, fetch: EngineLinkFetch, router: respx.MockRouter, store: StoreConfig
    ) -> None:
        router.get(PRODUCT).mock(return_value=html(product_page()))
        product = make_product(
            1, title="Black Oversized Blazer", product_url=PRODUCT, store=store.display_name
        )

        check = await LinkChecker(fetch, allowed_hosts_from_stores([store])).check(product)

        assert check.ok, check.problems


class TestRedirects:
    async def test_a_redirect_on_the_same_site_is_followed_and_reported(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        moved = f"https://{HOST}/products/black-blazer-v2"
        router.get(PRODUCT).mock(return_value=httpx.Response(301, headers={"location": moved}))
        router.get(moved).mock(return_value=html(product_page()))

        result = await fetch(PRODUCT)

        assert result.status == 200
        assert result.final_url == moved
        assert result.redirects == 1

    async def test_a_redirect_to_another_site_is_not_followed(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        other = router.get("https://elsewhere.example/").mock(return_value=html("<title>x</title>"))
        router.get(PRODUCT).mock(
            return_value=httpx.Response(302, headers={"location": "https://elsewhere.example/"})
        )

        result = await fetch(PRODUCT)

        assert result.status is None
        assert result.error is not None
        assert result.error.startswith("cross_domain_redirect")
        assert other.call_count == 0

    async def test_more_than_three_redirects_is_refused(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        for number in range(6):
            here = PRODUCT if number == 0 else f"{PRODUCT}-{number}"
            router.get(here).mock(
                return_value=httpx.Response(301, headers={"location": f"{PRODUCT}-{number + 1}"})
            )

        result = await fetch(PRODUCT)

        assert result.error is not None
        assert result.error.startswith("too_many_redirects")


class TestTheRulesOfTheFetchEngineApply:
    async def test_a_page_robots_txt_disallows_is_not_requested(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        router.get(f"https://{HOST}/robots.txt").mock(
            return_value=text("User-agent: *\nDisallow: /products/\n")
        )
        page = router.get(PRODUCT).mock(return_value=html(product_page()))

        result = await fetch(PRODUCT)

        assert result.error is not None
        assert result.error.startswith("robots_denied")
        assert page.call_count == 0

    async def test_a_store_that_blocks_us_is_left_alone_for_its_other_links(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        first = router.get(PRODUCT).mock(return_value=html("Forbidden", 403))
        second = router.get(f"{PRODUCT}-2").mock(return_value=html(product_page()))

        blocked = await fetch(PRODUCT)
        waiting = await fetch(f"{PRODUCT}-2")

        assert blocked.error is not None
        assert blocked.error.startswith("store_blocked")
        assert waiting.error is not None
        assert waiting.error.startswith("store_cooldown")
        assert (first.call_count, second.call_count) == (1, 0)  # no request, no retry

    async def test_a_link_a_store_turned_away_is_marked_throttled_not_broken(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        router.get(PRODUCT).mock(return_value=html("Too many requests", 429))

        blocked = await fetch(PRODUCT)
        in_cooldown = await fetch(f"{PRODUCT}-2")

        assert blocked.throttled is True  # turned away just now
        assert in_cooldown.throttled is True  # not asked, because the store is cooling down

    async def test_other_failures_are_not_marked_throttled(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        router.get(f"https://{HOST}/robots.txt").mock(
            return_value=text("User-agent: *\nDisallow: /products/denied\n")
        )
        router.get(PRODUCT).mock(return_value=html("<title>x</title>", 404))

        missing = await fetch(PRODUCT)
        denied = await fetch(f"https://{HOST}/products/denied")
        unknown = await fetch("https://www.unknown-store.example/products/a")

        assert (missing.throttled, denied.throttled, unknown.throttled) == (False, False, False)

    async def test_a_host_that_belongs_to_no_store_is_not_requested(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        router.get("https://www.unknown-store.example/products/a").mock(
            return_value=html(product_page())
        )

        result = await fetch("https://www.unknown-store.example/products/a")

        assert result.error is not None
        assert "allowed_hosts" in result.error
        assert not any(
            call.request.url.host == "www.unknown-store.example" for call in router.calls
        )

    async def test_an_address_that_is_not_https_is_not_requested(
        self, fetch: EngineLinkFetch, router: respx.MockRouter
    ) -> None:
        page = router.get(f"http://{HOST}/products/a").mock(return_value=html(product_page()))

        result = await fetch(f"http://{HOST}/products/a")

        assert result.error is not None
        assert result.error.startswith("url_not_allowed")
        assert page.call_count == 0

    async def test_two_links_to_one_store_are_spaced_by_the_rate_limit(
        self, fetch: EngineLinkFetch, router: respx.MockRouter, clock: FakeClock
    ) -> None:
        router.get(PRODUCT).mock(return_value=html(product_page()))
        router.get(f"{PRODUCT}-2").mock(return_value=html(product_page()))

        await fetch(PRODUCT)
        await fetch(f"{PRODUCT}-2")

        assert any(seconds == pytest.approx(1.0) for seconds in clock.sleeps)  # 1 request/s

    async def test_the_wait_for_the_rate_limiter_is_not_counted_as_the_stores_time(
        self, fetch: EngineLinkFetch, router: respx.MockRouter, clock: FakeClock
    ) -> None:
        # The second link waits a second for its slot, then the store answers at once. The 6 s
        # rule in rubric.md is about how fast the store answered, so that wait must not count.
        router.get(PRODUCT).mock(return_value=html(product_page()))
        router.get(f"{PRODUCT}-2").mock(return_value=html(product_page()))
        await fetch(PRODUCT)
        before = clock.monotonic()

        second = await fetch(f"{PRODUCT}-2")

        assert clock.monotonic() - before >= 1.0  # it really did wait
        assert second.elapsed_s == pytest.approx(0.0, abs=0.01)

    async def test_a_slow_store_is_timed_by_the_time_it_took(
        self, fetch: EngineLinkFetch, router: respx.MockRouter, clock: FakeClock
    ) -> None:
        async def slow(request: httpx.Request) -> httpx.Response:
            await clock.sleep(4.0)
            return html(product_page())

        router.get(PRODUCT).mock(side_effect=slow)

        result = await fetch(PRODUCT)

        assert result.elapsed_s == pytest.approx(4.0, abs=0.01)

    async def test_the_limiter_is_still_the_engines_own(
        self, engine: StoreSearchEngine, fetch: EngineLinkFetch
    ) -> None:
        assert isinstance(engine.client.limiter, MeteredLimiter)


class TestTheTitle:
    def response(self, body: str, content_type: str = "text/html") -> FetchResponse:
        return FetchResponse(PRODUCT, 200, content_type, body.encode("utf-8"))

    def test_the_title_is_read_and_tidied(self) -> None:
        page = self.response("<html><head><title>\n  Black   Blazer \n</title></head></html>")

        assert page_title(page) == "Black Blazer"

    def test_without_a_title_the_open_graph_title_is_used(self) -> None:
        page = self.response(
            '<html><head><meta property="og:title" content="Wool Blazer"></head></html>'
        )

        assert page_title(page) == "Wool Blazer"

    def test_a_page_with_no_title_has_none(self) -> None:
        assert page_title(self.response("<html><body>hello</body></html>")) is None

    def test_a_response_that_is_not_html_has_none(self) -> None:
        assert page_title(self.response('{"title": "x"}', "application/json")) is None

    def test_a_very_long_title_is_cut(self) -> None:
        page = self.response(f"<title>{'word ' * 200}</title>")

        title = page_title(page)

        assert title is not None
        assert len(title) <= 300

    def test_markup_in_a_title_is_text_not_markup(self) -> None:
        page = self.response("<title>Blazer &lt;script&gt;alert(1)&lt;/script&gt;</title>")

        assert page_title(page) == "Blazer <script>alert(1)</script>"


class TestSeveralStores:
    @pytest.fixture
    def stores(self) -> list[StoreConfig]:
        return [
            make_store_config(
                id="alpha",
                name="Alpha",
                search_url_template="https://www.alpha.example/search?q={query}",
                allowed_hosts=["www.alpha.example", "cdn.shared.example"],
            ),
            make_store_config(
                id="beta",
                name="Beta",
                search_url_template="https://www.beta.example/search?q={query}",
                allowed_hosts=["www.beta.example", "cdn.shared.example"],
            ),
        ]

    async def test_a_block_by_one_store_does_not_stop_the_links_of_another(
        self,
        stores: list[StoreConfig],
        settings: Settings,
        clock: FakeClock,
        router: respx.MockRouter,
    ) -> None:
        for host in ("www.alpha.example", "www.beta.example"):
            router.get(f"https://{host}/robots.txt").mock(return_value=text(ALLOW_ALL))
        router.get("https://www.alpha.example/products/a").mock(return_value=html("no", 403))
        router.get("https://www.beta.example/products/b").mock(return_value=html(product_page()))
        engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
        fetch = EngineLinkFetch(engine, stores)

        blocked = await fetch("https://www.alpha.example/products/a")
        fine = await fetch("https://www.beta.example/products/b")
        await engine.aclose()

        assert blocked.error is not None
        assert blocked.error.startswith("store_blocked")
        assert fine.status == 200

    async def test_a_link_is_fetched_under_the_store_whose_own_domain_it_is_on(
        self,
        stores: list[StoreConfig],
        settings: Settings,
        clock: FakeClock,
        router: respx.MockRouter,
    ) -> None:
        # Both stores list the shared CDN host, but a product page on beta's own host is beta's.
        router.get("https://www.beta.example/robots.txt").mock(return_value=text(ALLOW_ALL))
        router.get("https://www.beta.example/products/b").mock(return_value=html("no", 403))
        engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
        fetch = EngineLinkFetch(engine, stores)

        await fetch("https://www.beta.example/products/b")
        in_cooldown = {
            store.id: engine.client.cooldowns.remaining(store.id) > 0 for store in stores
        }
        await engine.aclose()

        assert in_cooldown == {"alpha": False, "beta": True}
