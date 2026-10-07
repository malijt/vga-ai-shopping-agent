"""A small fake world for the pipeline tests: store HTTP answered by ``respx``, on a ``FakeClock``.

The pipeline tests run the REAL store engine, extractor, ranker and price-range shaper. Only three
things are faked (plan section 7, Phase 13 test rule): the stores' HTTP (here), OpenAI
(``FakeUnderstander``) and the image model (``FakeImageRanker`` or a fake embedder).

``StoreWorld`` serves, for each store it is given,

- ``/robots.txt`` (allow everything), and
- the Shopify ``/search/suggest.json`` endpoint, answering from a body per kind of garment (the
  kind is read from the query: "blazer", "shoes", "shirt" or "jeans"), and
- the thumbnail CDN, answering with a tiny PNG.

It counts requests so a test can say "no request was made", and a store can be made slow or
broken. The saved responses in ``tests/fetch/fixtures/`` can be served instead of generated ones.
"""

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import respx

from tests.factories import make_image_bytes
from tests.fakes import FakeClock
from tests.fetch.conftest import (
    ALLOW_ALL_ROBOTS,
    SUGGEST_PATH,
    json_response,
    shopify_product,
    shopify_store,
    suggest_body,
    text_response,
)
from vga.models import Gender, StoreConfig

CDN_HOST = "cdn.shopify.com"
CDN_PREFIX = f"https://{CDN_HOST}/"

KINDS: dict[str, re.Pattern[str]] = {
    "blazer": re.compile(r"blazer|jacket|coat"),
    "shoes": re.compile(r"shoe|sneaker|boot|heel|mule"),
    "shirt": re.compile(r"shirt|blouse|\btop\b"),
    "jeans": re.compile(r"jeans|trouser|pants"),
}

TITLES: dict[str, str] = {
    "blazer": "{colour} Oversized Blazer {tag}{n}",
    "shoes": "{colour} Leather Sneakers {tag}{n}",
    "shirt": "{colour} Cotton Shirt {tag}{n}",
    "jeans": "{colour} Wide-Leg Jeans {tag}{n}",
}
PRODUCT_TYPES = {
    "blazer": "Coats & Jackets",
    "shoes": "Footwear",
    "shirt": "Tops",
    "jeans": "Bottoms",
}

DEFAULT_PRICES: dict[str, Sequence[float]] = {
    "blazer": (120, 180, 230, 290, 340, 450, 650, 900),
    "shoes": (150, 210, 260, 320, 430, 540, 700, 990),
    "shirt": (60, 85, 110, 140, 190, 260, 340, 480),
    "jeans": (90, 130, 170, 220, 300, 380, 520, 760),
}


def kind_of_query(query: str) -> str | None:
    lowered = query.lower()
    for kind, pattern in KINDS.items():
        if pattern.search(lowered):
            return kind
    return None


def generated_body(kind: str, tag: str, prices: Sequence[float], *, colour: str = "Black") -> str:
    """A Shopify suggest response with one product per price, titled for ``kind``."""
    products = []
    for number, price in enumerate(prices, start=1):
        slug = f"{kind}-{tag}-{number}"
        products.append(
            shopify_product(
                number,
                title=TITLES[kind].format(colour=colour, tag=tag.upper(), n=number),
                price=f"{price:.2f}",
                price_min=f"{price:.2f}",
                price_max=f"{price:.2f}",
                handle=slug,
                id=2000 + number,
                image=f"{CDN_PREFIX}s/files/1/0001/{slug}.jpg?v=1",
                url=f"/products/{slug}?_pos={number}",
                type=PRODUCT_TYPES[kind],
            )
        )
    return suggest_body(*products)


def store_for(
    key: str,
    *,
    genders: Sequence[Gender] | None = None,
    host: str | None = None,
    **overrides: Any,
) -> StoreConfig:
    """A Shopify-style test store ``key`` at ``https://<key>.example`` (or ``host``)."""
    where = host or f"{key}.example"
    fields: dict[str, Any] = {
        "id": key,
        "name": key.replace("-", " ").title(),
        "search_url_template": f"https://{where}{SUGGEST_PATH}",
        "allowed_hosts": [where, CDN_HOST],
        "genders": frozenset(genders) if genders is not None else None,
        "tier_hint": None,
    }
    return shopify_store(**{**fields, **overrides})


@dataclass
class Site:
    """One store as the world serves it."""

    store: StoreConfig
    bodies: dict[str, str]
    """Response body by kind of garment. A query of another kind gets an empty answer."""
    delay: Callable[[str], float] = lambda _query: 0.0
    """Seconds (on the fake clock) a search answer takes, by query."""
    status: int = 200
    queries: list[str] = field(default_factory=list)
    """Every search query this store received, in order."""

    @property
    def host(self) -> str:
        return httpx.URL(self.store.search_url_template.replace("{query}", "q")).host


class StoreWorld:
    """All the fake stores of one test, and the counters."""

    def __init__(self, router: respx.MockRouter, clock: FakeClock) -> None:
        self.router = router
        self.clock = clock
        self.sites: dict[str, Site] = {}
        self.thumbnails: list[str] = []
        """URLs of every thumbnail requested, in order."""
        router.get(f"{CDN_PREFIX}robots.txt").mock(return_value=text_response(ALLOW_ALL_ROBOTS))
        router.get(url__startswith=f"{CDN_PREFIX}s/files").mock(side_effect=self._thumbnail)

    # --- building the world -------------------------------------------------------------

    def add(
        self,
        store: StoreConfig,
        *,
        bodies: Mapping[str, str] | None = None,
        prices: Mapping[str, Sequence[float]] | None = None,
        delay: float | Callable[[str], float] = 0.0,
        status: int = 200,
        colour: str = "Black",
    ) -> Site:
        """Serve ``store``. Without ``bodies`` it sells generated products of every kind."""
        chosen = dict(bodies) if bodies is not None else {}
        if bodies is None:
            for kind, default in DEFAULT_PRICES.items():
                list_prices = (prices or {}).get(kind, default)
                chosen[kind] = generated_body(kind, store.id, list_prices, colour=colour)
        site = Site(
            store=store,
            bodies=chosen,
            delay=delay if callable(delay) else (lambda _query, seconds=delay: seconds),
            status=status,
        )
        self.sites[store.id] = site
        host = site.host
        self.router.get(f"https://{host}/robots.txt").mock(
            return_value=text_response(ALLOW_ALL_ROBOTS)
        )
        self.router.get(url__startswith=f"https://{host}/search/suggest.json").mock(
            side_effect=self._answer(site)
        )
        return site

    def _answer(self, site: Site) -> Callable[[httpx.Request], Awaitable[httpx.Response]]:
        async def answer(request: httpx.Request) -> httpx.Response:
            query = request.url.params["q"]
            site.queries.append(query)
            seconds = site.delay(query)
            if seconds > 0:
                await self.clock.sleep(seconds)
            if site.status != 200:
                return httpx.Response(site.status, text="no")
            kind = kind_of_query(query)
            body = site.bodies.get(kind or "", suggest_body())
            return json_response(body)

        return answer

    async def _thumbnail(self, request: httpx.Request) -> httpx.Response:
        self.thumbnails.append(str(request.url))
        shade = 255 if len(request.url.path) % 2 else 150
        data = make_image_bytes("PNG", (8, 8), (shade, 0, 0))
        return httpx.Response(200, content=data, headers={"content-type": "image/png"})

    # --- counters --------------------------------------------------------------------------

    def stores(self) -> list[StoreConfig]:
        return [site.store for site in self.sites.values()]

    def requests_to(self, host: str) -> int:
        return sum(1 for call in self.router.calls if call.request.url.host == host)

    def search_requests(self) -> int:
        """Search-page requests to every store (not robots.txt, not thumbnails)."""
        return sum(
            1 for call in self.router.calls if call.request.url.path == "/search/suggest.json"
        )

    def all_requests(self) -> int:
        return int(self.router.calls.call_count)

    def queries(self, store_id: str) -> list[str]:
        return list(self.sites[store_id].queries)
