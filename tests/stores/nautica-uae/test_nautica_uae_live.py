"""Nautica UAE live smoke test (plan 12.2.3). Real requests to https://nautica-ae.com/.

Run it by hand, never in CI and never in a loop::

    uv run pytest -m live tests/stores/nautica-uae -q

It builds the real ``StoreSearchEngine`` with the shipped store file and searches three queries
that suit the store's assortment (menswear; the qualification report saw no shoes). The engine does
the honest User-Agent, the robots.txt check (protego), the 1 request/s limit, the allow-list and
the block handling (a block is reported, never retried, never bypassed). One engine serves all
three queries, so the test sends 4 requests: robots.txt once, then one search per query.

Pass rule, per query: status ``ok`` with at least 3 valid products, within the store's timeout.
The store file is switched on in memory here, so the test can run before ``enabled: true`` is set.
"""

import pytest
from tests.factories import make_item_intent

from vga.models import StoreConfig, StoreStatus
from vga.settings import load_settings
from vga.stores.engine import StoreSearchEngine

pytestmark = pytest.mark.live

QUERIES = ["men shirt", "jacket", "trousers"]
MIN_PRODUCTS = 3


async def test_each_query_returns_at_least_three_valid_products_within_the_timeout(
    store: StoreConfig,
) -> None:
    settings = load_settings()
    timeout_s = store.timeout_s or settings.timeout_s
    engine = StoreSearchEngine(settings)
    failures: list[str] = []
    try:
        for query in QUERIES:
            item = make_item_intent(search_keywords=[query])
            [result] = await engine.search(item, [store.model_copy(update={"enabled": True})])
            seconds = result.duration_ms / 1000
            print(  # the run's evidence: shown with -s, and by pytest when the test fails
                f"{query!r}: status={result.status.value} products={len(result.products)} "
                f"seconds={seconds:.2f} strategy={result.strategy} dropped={result.dropped} "
                f"detail={result.detail}"
            )
            if result.status is not StoreStatus.OK:
                failures.append(f"{query!r}: status {result.status.value} ({result.detail})")
                break  # a block, a robots denial or any other failure: ask for nothing more
            if len(result.products) < MIN_PRODUCTS:
                failures.append(f"{query!r}: only {len(result.products)} valid products")
            if seconds > timeout_s:
                failures.append(f"{query!r}: took {seconds:.2f} s, more than {timeout_s:g} s")
            assert all(product.store == store.display_name for product in result.products)
    finally:
        await engine.aclose()

    assert not failures, "; ".join(failures)
