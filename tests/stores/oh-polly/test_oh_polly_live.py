"""Live smoke test for Oh Polly UAE (plan 12.4.3). Talks to the real store; never runs in CI.

Run it with::

    uv run pytest -m live tests/stores/oh-polly -q

It builds the real ``StoreSearchEngine`` (honest User-Agent from the settings, robots.txt checked
with protego, 1 request per second, a stop on any block) and searches three queries that suit this
store's assortment: ``blazer``, ``jacket`` and ``heels``. One engine serves all three, so
robots.txt is fetched once: 4 requests to the store in total.

Pass rule, per query: status ``ok``, at least 3 valid products after validation, finished within the
store's timeout. When it passes, ``enabled: true`` goes in ``config/stores/oh-polly.yaml``. If the
store blocks, robots.txt denies the path, or a query misses the rule, the store stays disabled and
the reason is written down in ``docs/store-notes/oh-polly.md``. Nothing here retries or works around
a refusal.

The test sets ``enabled`` itself so it can run before the file says ``enabled: true`` (that flag
is the result of this test, not an input to it).
"""

import httpx
import pytest
from tests.factories import make_item_intent

from vga.models import Category, StoreConfig, StoreStatus
from vga.settings import load_settings
from vga.stores.engine import StoreSearchEngine

pytestmark = pytest.mark.live

QUERIES = [
    ("blazer", Category.OUTERWEAR),
    ("jacket", Category.OUTERWEAR),
    ("heels", Category.SHOES),
]
MIN_VALID_PRODUCTS = 3
MAX_REQUESTS = 4  # robots.txt once + one search per query


class CountingTransport(httpx.AsyncBaseTransport):
    """The normal network transport, plus a list of the URLs asked for (to prove the budget)."""

    def __init__(self) -> None:
        self._real = httpx.AsyncHTTPTransport()
        self.urls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        return await self._real.handle_async_request(request)

    async def aclose(self) -> None:
        await self._real.aclose()


async def test_three_queries_each_return_valid_products_within_the_timeout(
    store: StoreConfig,
) -> None:
    settings = load_settings()
    limit_s = store.timeout_s or settings.timeout_s
    transport = CountingTransport()
    engine = StoreSearchEngine(settings, transport=transport)
    live_store = store.model_copy(update={"enabled": True})

    failures: list[str] = []
    try:
        for query, category in QUERIES:
            item = make_item_intent(
                category=category, colour=None, style=None, search_keywords=[query]
            )
            [result] = await engine.search(item, [live_store])
            seconds = result.duration_ms / 1000
            print(
                f"{query!r}: status={result.status.value} products={len(result.products)} "
                f"dropped={result.dropped} seconds={seconds:.2f} detail={result.detail}"
            )
            if result.status is not StoreStatus.OK:
                failures.append(f"{query!r}: status {result.status.value} ({result.detail})")
                break  # a block or a robots refusal: stop at once, ask for nothing more
            if len(result.products) < MIN_VALID_PRODUCTS:
                failures.append(f"{query!r}: only {len(result.products)} valid products")
            if seconds > limit_s:
                failures.append(
                    f"{query!r}: took {seconds:.2f} s, the store's timeout is {limit_s:g} s"
                )
    finally:
        await engine.aclose()
        print(f"requests to the store: {len(transport.urls)}")

    assert not failures, "; ".join(failures)
    assert len(transport.urls) <= MAX_REQUESTS
    assert all(url.startswith("https://ohpolly.ae/") for url in transport.urls)
