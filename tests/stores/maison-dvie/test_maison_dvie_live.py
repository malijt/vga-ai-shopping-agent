"""Live smoke test for Maison D'Vie (plan 12.6.3): three real searches through the real engine.

Run it by hand, never in CI (it is deselected by default)::

    uv run pytest -m live tests/stores/maison-dvie -q

It builds the real ``StoreSearchEngine`` (honest User-Agent from the settings, robots.txt checked
with protego, 1 request/s, allow-list, block handling) with this store's file and searches three
queries that suit the assortment. Pass rule: each query returns status ``ok`` with at least
``MIN_VALID`` valid products after validation, inside the store's timeout.

Request budget (BRD Rule 2): one robots.txt plus one search per query, so 4 requests. The test
asserts the count, and it stops at the first block or robots refusal instead of asking again.

The file's ``enabled`` flag is forced on here, because the test is what decides whether the file
may say ``enabled: true``.

Set ``VGA_RECORD_DIR`` to a directory to also save each raw response body there (used once, to make
the offline fixtures). Nothing is saved otherwise.
"""

import os
import shutil
from pathlib import Path

import httpx
import pytest
from tests.factories import make_item_intent

from vga.fetch.client import FetchPolicy, FetchResponse
from vga.models import Category, StoreConfig, StoreResult, StoreStatus
from vga.settings import DEFAULT_STORES_DIR, load_settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.registry import load_store_configs

pytestmark = pytest.mark.live

STORE_FILE = DEFAULT_STORES_DIR / "maison-dvie.yaml"
QUERIES = (
    ("blazer", Category.OUTERWEAR),
    ("shirt", Category.TOPS),
    ("trousers", Category.BOTTOMS),
)
MIN_VALID = 3
REQUEST_BUDGET = 4
"""robots.txt plus one search for each of the three queries. The task allows 10 in all."""
RECORD_DIR_ENV = "VGA_RECORD_DIR"


class CountingTransport(httpx.AsyncBaseTransport):
    """The ordinary network transport, plus a list of every URL requested."""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport(trust_env=False)
        self.urls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def save_bodies(directory: str | None, bodies: dict[str, bytes]) -> None:
    """Write each raw search response to ``directory`` (does nothing when it is not set)."""
    if not directory:
        return
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    for query, body in bodies.items():
        (folder / f"suggest-{query}.json").write_bytes(body)


def load_this_store(tmp_path: Path) -> StoreConfig:
    """The store file as the real registry loads it, then switched on for this run."""
    shutil.copy(STORE_FILE, tmp_path / STORE_FILE.name)
    [store] = load_store_configs(tmp_path)
    return store.model_copy(update={"enabled": True})


async def test_three_real_searches_each_return_enough_valid_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = load_this_store(tmp_path)
    settings = load_settings()
    transport = CountingTransport()
    engine = StoreSearchEngine(settings, transport=transport)

    bodies: dict[str, bytes] = {}
    original_fetch = engine.client.fetch

    async def recording_fetch(
        url: str, for_store: StoreConfig, policy: FetchPolicy
    ) -> FetchResponse:
        response = await original_fetch(url, for_store, policy)
        if "suggest.json" in url:
            bodies[url.split("q=")[1].split("&")[0]] = response.body
        return response

    monkeypatch.setattr(engine.client, "fetch", recording_fetch)

    results: dict[str, StoreResult] = {}
    try:
        for keywords, category in QUERIES:
            item = make_item_intent(
                category=category, colour=None, style=None, search_keywords=[keywords]
            )
            [result] = await engine.search(item, [store])
            results[keywords] = result
            if result.status in {StoreStatus.BLOCKED, StoreStatus.ROBOTS_DENIED}:
                break  # never ask a store again after a block or a robots refusal
    finally:
        await engine.aclose()
        save_bodies(os.environ.get(RECORD_DIR_ENV), bodies)

    timeout_s = store.timeout_s or settings.timeout_s
    lines = []
    for keywords, result in results.items():
        returned = len(result.products) + sum(result.dropped.values())
        lines.append(
            f"{keywords!r}: {result.status.value}, returned {returned}, kept "
            f"{len(result.products)}, {result.duration_ms / 1000:.2f} s, "
            f"strategy {result.strategy}, dropped {result.dropped}, detail {result.detail}"
        )
    print("\n".join(["", *lines, f"requests made: {len(transport.urls)}", *transport.urls]))

    assert len(transport.urls) <= REQUEST_BUDGET, transport.urls
    assert set(results) == {keywords for keywords, _ in QUERIES}, "\n".join(lines)
    for keywords, result in results.items():
        assert result.status is StoreStatus.OK, f"{keywords!r}: {result.status} {result.detail}"
        assert len(result.products) >= MIN_VALID, f"{keywords!r}: only {len(result.products)}"
        assert result.duration_ms / 1000 <= timeout_s, f"{keywords!r}: {result.duration_ms} ms"
        assert all(product.currency == "AED" for product in result.products)
