"""Set-up shared by the Phase 14.1 scraping guards (plan 14.1.1 to 14.1.4, BRD Rule 2).

The guards run the REAL ``SearchPipeline`` and the REAL ``StoreSearchEngine`` (fetch client, rate
limiter, cooldowns, robots checker, cache, extractor); only the boundaries are faked, exactly as
in ``tests/pipeline``: the stores' HTTP by ``respx`` (``StoreWorld``), OpenAI by the shared fakes,
and time by ``FakeClock``. ``GuardWorld`` adds to the shared ``StoreWorld`` only what a guard needs
and the pipeline tests did not:

- a robots.txt that is not "allow everything" (``robots=``), and a search answer of any shape: a
  403, a challenge page, a redirect (``reply=``);
- the fake-clock time of every request to a host, robots.txt included, to check the rate;
- a **catch-all route that records every request nobody expected** (``stray``). ``respx`` does not
  record an unmocked request in ``router.calls``: it raises inside the client, and the engine turns
  that into an "error" result, so a request to a forbidden address would otherwise leave no trace.
  Every guard that says "no request went to X" therefore asserts ``world.stray == []``.

A route registered again with the same pattern replaces the earlier one in ``respx``, which is how
``GuardWorld.add`` swaps in its own robots.txt and search answers after ``StoreWorld.add`` has
registered the defaults.
"""

import json
from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import Any

import httpx
import respx

from tests.factories import make_understand_result
from tests.fakes import FakeClock, FakeUnderstander
from tests.fetch.conftest import (
    ALLOW_ALL_ROBOTS,
    json_response,
    shopify_product,
    suggest_body,
    text_response,
)
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import CDN_HOST, CDN_PREFIX, Site, StoreWorld, generated_body
from vga.interfaces import Understander
from vga.models import (
    InputType,
    ItemIntent,
    SearchRequest,
    SearchResponse,
    StoreConfig,
    UnderstandResult,
)
from vga.pipeline import SearchPipeline
from vga.settings import Settings
from vga.stores import StoreSearchEngine

Reply = Callable[[httpx.Request], httpx.Response]
"""A store's answer to a request."""

MIN_GAP_S = 1.0 - 1e-9
"""BRD Rule 2: at most one request per second to one store."""


class GuardWorld(StoreWorld):
    """``StoreWorld`` plus what the scraping guards observe and vary."""

    def __init__(self, router: respx.MockRouter, clock: FakeClock) -> None:
        super().__init__(router, clock)
        self.robots_times: dict[str, list[float]] = {}
        """Fake-clock time of each robots.txt request, by host."""
        self.cdn_times: list[float] = []
        """Fake-clock time of each request to the image CDN (robots.txt and thumbnails)."""
        self.stray: list[str] = []
        """Every request that no route expected, in order. Must stay empty in a guard."""
        self._sealed = False
        self._serve_cdn(ALLOW_ALL_ROBOTS)

    # --- building the world -------------------------------------------------------------

    def add(
        self,
        store: StoreConfig,
        *,
        robots: str | Reply = ALLOW_ALL_ROBOTS,
        reply: Reply | None = None,
        **options: Any,
    ) -> Site:
        """Serve ``store`` as ``StoreWorld.add`` does, with a chosen robots.txt and, if ``reply``
        is given, that answer to every search request instead of the generated products."""
        site = super().add(store, **options)
        host = site.host
        self.router.get(f"https://{host}/robots.txt").mock(
            side_effect=self._robots(host, robots),
        )
        if reply is not None:
            self.router.get(url__startswith=f"https://{host}/search/suggest.json").mock(
                side_effect=self._search(site, reply),
            )
        return site

    def serve_cdn_robots(self, robots: str) -> None:
        """Replace the image CDN's robots.txt."""
        self._serve_cdn(robots)

    def seal(self) -> None:
        """Route every request nobody expected into ``stray``. Call once the world is built: a
        route added later would never be reached, because the catch-all would match first."""
        if self._sealed:
            return
        self._sealed = True
        self.router.route().mock(side_effect=self._unexpected)

    # --- handlers ---------------------------------------------------------------------------

    def _robots(self, host: str, robots: str | Reply) -> Reply:
        def answer(request: httpx.Request) -> httpx.Response:
            self.robots_times.setdefault(host, []).append(self.clock.monotonic())
            return robots(request) if callable(robots) else text_response(robots)

        return answer

    def _search(self, site: Site, reply: Reply) -> Reply:
        def answer(request: httpx.Request) -> httpx.Response:
            site.queries.append(request.url.params["q"])
            site.times.append(self.clock.monotonic())
            return reply(request)

        return answer

    def _serve_cdn(self, robots: str) -> None:
        def robots_answer(_request: httpx.Request) -> httpx.Response:
            self.cdn_times.append(self.clock.monotonic())
            return text_response(robots)

        async def thumbnail_answer(request: httpx.Request) -> httpx.Response:
            self.cdn_times.append(self.clock.monotonic())
            return await self._thumbnail(request)

        self.router.get(f"{CDN_PREFIX}robots.txt").mock(side_effect=robots_answer)
        self.router.get(url__startswith=f"{CDN_PREFIX}s/files").mock(side_effect=thumbnail_answer)

    def _unexpected(self, request: httpx.Request) -> httpx.Response:
        self.stray.append(str(request.url))
        return httpx.Response(404, text="nobody expected this request")

    # --- what the guards look at -------------------------------------------------------------

    def calls_to(self, host: str) -> list[httpx.Request]:
        """Every request that reached ``host`` (a mocked one), in order."""
        return [call.request for call in self.router.calls if call.request.url.host == host]

    def search_paths(self, host: str) -> list[httpx.URL]:
        """The search-page requests to ``host`` (not robots.txt)."""
        return [r.url for r in self.calls_to(host) if r.url.path != "/robots.txt"]

    def request_times(self, store_id: str) -> list[float]:
        """When each request to the store (robots.txt and search pages) arrived, oldest first."""
        site = self.sites[store_id]
        return sorted([*site.times, *self.robots_times.get(site.host, [])])

    def thumbnails_of(self, store_id: str) -> list[str]:
        """The thumbnail URLs requested for products of ``store_id`` (its tag is in the path)."""
        return [url for url in self.thumbnails if f"-{store_id}-" in url]

    def every_request(self) -> list[httpx.Request]:
        return [call.request for call in self.router.calls]


class GuardPipelines:
    """Builds real pipelines for the guards: ``PipelineMaker`` after sealing the ``GuardWorld``."""

    def __init__(self, world: GuardWorld, maker: PipelineMaker) -> None:
        self._world = world
        self._maker = maker

    def __call__(
        self,
        *,
        understander: Understander | None = None,
        stores: Sequence[StoreConfig] | None = None,
        thumbnails: bool = False,
        engine_settings: Settings | None = None,
    ) -> SearchPipeline:
        self._world.seal()
        return self._maker(
            understander=understander,
            stores=stores,
            thumbnails=thumbnails,
            engine_settings=engine_settings,
        )

    @property
    def engine(self) -> StoreSearchEngine:
        """The real store engine of the pipeline built last."""
        return self._maker.engines[-1]

    async def aclose(self) -> None:
        await self._maker.aclose()


def understanding(*items: ItemIntent, input_type: InputType = InputType.TEXT) -> FakeUnderstander:
    """The model's reading of a request, fixed: these garments with their keyword variants."""
    return FakeUnderstander(make_understand_result(input_type=input_type, items=list(items)))


def understanding_by_words(garments: dict[str, ItemIntent]) -> FakeUnderstander:
    """A model that reads each request as the garment whose word the shopper's text contains."""

    def read(req: SearchRequest) -> UnderstandResult:
        text = (req.text or "").lower()
        item = next(garment for word, garment in garments.items() if word in text)
        return make_understand_result(items=[item])

    return FakeUnderstander(read)


def gaps(times: Sequence[float]) -> list[float]:
    """Seconds between each request and the one before it."""
    return [later - earlier for earlier, later in pairwise(times)]


# --------------------------------------------------------------------------------------------
# Store answers
# --------------------------------------------------------------------------------------------

CHALLENGE_HTML = (
    "<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
    '<body><div class="cf-browser-verification">Checking your browser before accessing the site.'
    "</div></body></html>"
)
CAPTCHA_HTML = (
    "<html><head><title>Access to this page has been denied</title></head>"
    '<body><div id="px-captcha">Press and hold to confirm you are human</div></body></html>'
)


def html_response(body: str, *, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


def reply_status(status: int, **headers: str) -> Reply:
    return lambda _request: httpx.Response(status, text="no", headers=dict(headers))


def reply_html(body: str, *, status: int = 200) -> Reply:
    return lambda _request: html_response(body, status=status)


def reply_redirect(location: str, *, status: int = 302) -> Reply:
    return lambda _request: httpx.Response(status, headers={"location": location})


def reply_json(body: str) -> Reply:
    return lambda _request: json_response(body)


def blazer_products(
    tag: str, prices: Sequence[float] = (120, 180, 230, 290)
) -> list[dict[str, Any]]:
    """Generated Shopify blazer records for store ``tag`` (the same ones ``StoreWorld`` serves)."""
    body = json.loads(generated_body("blazer", tag, prices))
    products: list[dict[str, Any]] = body["resources"]["results"]["products"]
    return products


def trap_product(
    number: int, *, url: str | None = None, image: str | None = None
) -> dict[str, Any]:
    """A blazer record that would be a good result but for one hostile link.

    A part not given is a valid one on the allowed hosts of the ``alpha`` test store, so each trap
    differs from a good product in exactly the link it carries.
    """
    return shopify_product(
        number,
        title=f"Black Oversized Blazer Trap {number}",
        price=f"{150 + number}.00",
        price_min=f"{150 + number}.00",
        price_max=f"{150 + number}.00",
        handle=f"trap-{number}",
        id=9000 + number,
        image=image or f"{CDN_PREFIX}s/files/1/0001/trap-{number}.jpg?v=1",
        url=url or f"/products/trap-{number}",
        type="Coats & Jackets",
    )


def body_of(*products: dict[str, Any]) -> str:
    return suggest_body(*products)


def links_shown(response: SearchResponse) -> list[str]:
    """Every product page and image link the response hands to the shopper."""
    return [
        str(link)
        for scored in response.products
        for link in (scored.product.product_url, scored.product.image_url)
    ]


__all__ = [
    "CAPTCHA_HTML",
    "CDN_HOST",
    "CHALLENGE_HTML",
    "MIN_GAP_S",
    "GuardPipelines",
    "GuardWorld",
    "Reply",
    "blazer_products",
    "body_of",
    "gaps",
    "html_response",
    "links_shown",
    "reply_html",
    "reply_json",
    "reply_redirect",
    "reply_status",
    "trap_product",
    "understanding",
    "understanding_by_words",
]
