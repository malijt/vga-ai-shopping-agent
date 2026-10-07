"""Sacoor Brothers UAE live smoke test (plan 12.3.3). Talks to the real store; never runs in CI.

Run it once, by hand::

    uv run pytest -m live tests/stores/sacoor-brothers-uae -q -rP

It builds the real ``StoreSearchEngine`` with the shipped store file and searches three queries
that suit this store's assortment (men's shirts, blazers, shoes). Everything the BRD asks of a
polite client is the engine's doing: the honest User-Agent from the settings, the robots.txt check
with protego, one request per second, no retries, and a stop on a block. A block (403, 429, a
challenge page) or a robots refusal fails the test; nothing is retried or worked around.

Request budget: one robots.txt fetch plus one search per query, so 4 requests. The test fails if
the engine ever sends more than ``REQUEST_BUDGET`` requests.

Pass rule, per query: status ``ok``, at least ``MIN_PRODUCTS`` valid products after validation,
and finished within the store's timeout. The store file is loaded as shipped and then switched to
``enabled`` in memory, because the engine skips a disabled store without a request; whether the
file itself says ``enabled: true`` is the result of this test, not an input to it.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from vga.models import Category, ItemIntent, StoreConfig, StoreResult, StoreStatus
from vga.settings import Settings, load_settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.registry import load_store_configs

pytestmark = pytest.mark.live

STORE_ID = "sacoor-brothers-uae"
STORE_DIR = Path(__file__).resolve().parents[3] / "config" / "stores"

QUERIES = [
    ("men shirt", Category.TOPS),
    ("black blazer", Category.OUTERWEAR),
    ("shoes", Category.SHOES),
]
MIN_PRODUCTS = 3
REQUEST_BUDGET = 10
"""BRD Rule 2 budget for the whole task: never more than this many requests to the store."""


class CountingTransport(httpx.AsyncBaseTransport):
    """The normal network transport, plus a list of what was asked for. It changes nothing."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self.requests: list[tuple[str, int]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        self.requests.append((str(request.url), response.status_code))
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


@dataclass
class Run:
    store: StoreConfig
    settings: Settings
    results: dict[str, StoreResult]
    seconds: dict[str, float]
    requests: list[tuple[str, int]]


def load_store() -> StoreConfig:
    stores = {store.id: store for store in load_store_configs(STORE_DIR)}
    return stores[STORE_ID].model_copy(update={"enabled": True})


async def run_queries(store: StoreConfig, settings: Settings) -> Run:
    transport = CountingTransport()
    engine = StoreSearchEngine(settings, transport=transport)
    results: dict[str, StoreResult] = {}
    seconds: dict[str, float] = {}
    try:
        for query, category in QUERIES:
            item = ItemIntent.model_validate({"category": category, "search_keywords": [query]})
            started = time.monotonic()
            [results[query]] = await engine.search(item, [store])
            seconds[query] = round(time.monotonic() - started, 2)
            if results[query].status is not StoreStatus.OK:
                break  # BRD Rule 2: on a block, a refusal or any failure, stop; never retry
    finally:
        await engine.aclose()
    return Run(store, settings, results, seconds, transport.requests)


@pytest.fixture(scope="module")
def run() -> Run:
    settings = load_settings()
    store = load_store()
    outcome = asyncio.run(run_queries(store, settings))
    print(f"\nlive run for {STORE_ID}: {len(outcome.requests)} request(s) to the store")
    for url, status in outcome.requests:
        print(f"  HTTP {status} {url}")
    for query, result in outcome.results.items():
        print(
            f"  {query!r}: status={result.status.value} products={len(result.products)} "
            f"dropped={result.dropped} seconds={outcome.seconds[query]} detail={result.detail}"
        )
    return outcome


def test_the_request_budget_was_respected_and_only_the_store_host_was_contacted(run: Run) -> None:
    assert 0 < len(run.requests) <= REQUEST_BUDGET
    assert {urlsplit(url).hostname for url, _ in run.requests} == {"ae.sacoorbrothers.com"}


@pytest.mark.parametrize("query", [query for query, _ in QUERIES])
def test_the_query_returns_ok_with_enough_valid_products_within_the_timeout(
    run: Run, query: str
) -> None:
    result = run.results.get(query)
    assert result is not None, f"{query!r} was not searched: an earlier query failed and we stopped"
    timeout_s = run.store.timeout_s or run.settings.timeout_s

    assert result.status is StoreStatus.OK, f"status {result.status.value}: {result.detail}"
    assert len(result.products) >= MIN_PRODUCTS
    assert run.seconds[query] <= timeout_s
    assert result.duration_ms / 1000 <= timeout_s
    assert result.strategy == "shopify"
    for product in result.products:
        assert product.store == run.store.display_name
        assert product.currency == "AED"
        assert product.price > 0
        assert urlsplit(product.product_url).hostname in run.store.allowed_hosts
        assert urlsplit(product.image_url).hostname in run.store.allowed_hosts
