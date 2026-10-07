"""Live smoke test for Giordano UAE (plan 12.1.3). Talks to the real store; never runs by default.

Run it once, by hand::

    uv run pytest -m live tests/stores/giordano-uae -q -s

It builds the real ``StoreSearchEngine`` with the real ``config/stores/giordano-uae.yaml`` and
searches three queries that suit this store's assortment. Everything the store rules require
(robots.txt check with protego, 1 request/s, the honest User-Agent from settings, the host
allow-list, stop on a block) is done by the engine, not by this test. The test makes at most 4
requests: robots.txt once, then one search per query.

The pass rule, per query: status ``ok``, at least 3 valid products after validation, and an answer
within the store's timeout. If the store blocks us or robots.txt denies the path, the status says so
and the test fails: leave the store ``enabled: false`` then (BRD Rule 2: dropped, never bypassed).

The store file keeps ``enabled: false`` until this test has passed. The test enables the store in
memory only, so it runs the same whatever the file says.

Set ``VGA_STORE_RECORD_DIR`` to a folder to also save every raw response (robots.txt and the three
search answers) there. That is how the offline fixture in ``fixtures/`` was taken from a live run,
with no extra request; it is also how to refresh it if the store changes.
"""

import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from vga.models import Category, ItemIntent, StoreConfig, StoreStatus
from vga.settings import DEFAULT_STORES_DIR, load_settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.registry import load_store_configs

pytestmark = pytest.mark.live

STORE_ID = "giordano-uae"
QUERIES = (
    ("men shirt", Category.TOPS),
    ("jacket", Category.OUTERWEAR),
    ("shoes", Category.SHOES),
)
MIN_PRODUCTS = 3
RECORD_DIR_ENV = "VGA_STORE_RECORD_DIR"


class _RecordingTransport(httpx.AsyncBaseTransport):
    """The real network transport that also keeps a copy of each response body in memory.

    It sends exactly what the engine's client asks it to send (no header or URL change) and hands
    the response back untouched; it only reads the body first so it can keep a copy.
    """

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self.bodies: list[tuple[str, str]] = []
        """``(url, decoded body)`` of every response, in request order."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        await response.aread()
        self.bodies.append((str(request.url), response.text))
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


def _load_store(tmp_path: Path) -> StoreConfig:
    """The store file loaded by the real registry. Only this store's file is copied into a
    temporary folder, so another store's file can never break this test."""
    shutil.copy(DEFAULT_STORES_DIR / f"{STORE_ID}.yaml", tmp_path / f"{STORE_ID}.yaml")
    [store] = load_store_configs(tmp_path)
    return store.model_copy(update={"enabled": True})


def _save_recordings(recorder: _RecordingTransport, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for number, (url, body) in enumerate(recorder.bodies, start=1):
        parts = urlsplit(url)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{parts.path}-{parts.query}").strip("-")[:80]
        (folder / f"{number:02d}-{slug}.txt").write_text(body, encoding="utf-8")


async def test_three_queries_return_valid_products_within_the_timeout(tmp_path: Path) -> None:
    settings = load_settings()
    store = _load_store(tmp_path)
    timeout_s = store.timeout_s or settings.timeout_s
    recorder = _RecordingTransport()
    engine = StoreSearchEngine(settings, transport=recorder)

    problems: list[str] = []
    summary: list[str] = []
    try:
        for query, category in QUERIES:
            item = ItemIntent(category=category, search_keywords=[query])
            [result] = await engine.search(item, [store])
            seconds = result.duration_ms / 1000
            summary.append(
                f"{query!r}: status={result.status.value} products={len(result.products)} "
                f"dropped={result.dropped} seconds={seconds:.2f} detail={result.detail}"
            )
            if result.status is not StoreStatus.OK:
                problems.append(f"{query!r}: status is {result.status.value}: {result.detail}")
            if len(result.products) < MIN_PRODUCTS:
                problems.append(
                    f"{query!r}: {len(result.products)} valid products, need {MIN_PRODUCTS}"
                )
            if seconds > timeout_s:
                problems.append(f"{query!r}: took {seconds:.1f} s, the timeout is {timeout_s:g} s")
            for product in result.products:
                if urlsplit(product.product_url).hostname not in store.allowed_hosts:
                    problems.append(f"{query!r}: product link off the allow-list: {product.key}")
                if urlsplit(product.image_url).hostname not in store.allowed_hosts:
                    problems.append(f"{query!r}: image off the allow-list: {product.image_url}")
                if product.store != store.display_name or product.currency != store.currency:
                    problems.append(f"{query!r}: wrong store or currency on {product.key}")
    finally:
        await engine.aclose()

    requests_made = len(recorder.bodies)
    summary.append(f"requests made to the store: {requests_made}")
    print("\n" + "\n".join(summary))
    if os.environ.get(RECORD_DIR_ENV):
        _save_recordings(recorder, Path(os.environ[RECORD_DIR_ENV]))
    if requests_made > len(QUERIES) + 1:
        problems.append(f"{requests_made} requests made, expected at most {len(QUERIES) + 1}")

    assert not problems, "\n".join([*problems, *summary])
