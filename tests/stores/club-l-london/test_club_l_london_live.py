"""Club L London UAE live smoke test (plan 12.5.3). Talks to the real store: run it by hand.

    uv run pytest -m live tests/stores/club-l-london -q -rP

Deselected by default (``-m 'not live'`` in ``pyproject.toml``) and never run in CI. It builds the
real ``StoreSearchEngine`` from the real settings and the real store file, so the honest
User-Agent, the robots.txt check (protego), the 1 request/s limit, the allow-list and the block
handling all run for real. It makes 4 requests: robots.txt once (the engine caches it), then one
search for each query. There are no retries: on a block or a robots refusal the store reports it
and the test fails, which is the correct outcome (BRD Rule 2: dropped, never bypassed).

Pass rule (plan 12.x.3): each query returns status ``ok`` with at least 3 valid products, inside
the store's time budget. The store's results are dress-heavy and dresses are outside the app's
four categories, but extraction keeps them (ranking filters them out later); the test prints how
many products of each query are not dresses, which decides how useful this store is.
"""

import pytest
from tests.factories import make_item_intent

from vga.models import Category, StoreStatus
from vga.settings import DEFAULT_STORES_DIR, load_settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.registry import StoreRegistry

pytestmark = pytest.mark.live

STORE_ID = "club-l-london"
MIN_PRODUCTS = 3
QUERIES = (
    ("blazer", Category.OUTERWEAR),
    ("jacket", Category.OUTERWEAR),
    ("heels", Category.SHOES),
)


async def test_three_queries_each_return_valid_products_in_time() -> None:
    settings = load_settings()
    stored = StoreRegistry.from_directory(DEFAULT_STORES_DIR).get(STORE_ID)
    assert stored is not None
    # Enabled in memory so the test can run before the file says `enabled: true` (and after).
    store = stored.model_copy(update={"enabled": True})
    # One robots.txt fetch plus one search: the engine's own time budget for a single keyword.
    budget_s = 2 * (store.timeout_s or settings.timeout_s)

    engine = StoreSearchEngine(settings, StoreRegistry([store]))
    failures: list[str] = []
    try:
        for keyword, category in QUERIES:
            item = make_item_intent(category=category, search_keywords=[keyword])
            [result] = await engine.search(item, [store])
            seconds = result.duration_ms / 1000
            not_dresses = [p for p in result.products if "dress" not in p.title.lower()]
            # Shown with -rP; the numbers go into the store notes.
            print(
                f"[club-l-london] {keyword!r}: status={result.status.value} "
                f"products={len(result.products)} not_dresses={len(not_dresses)} "
                f"seconds={seconds:.2f} dropped={result.dropped} detail={result.detail}"
            )
            if result.status is not StoreStatus.OK:
                failures.append(f"{keyword}: status {result.status.value} ({result.detail})")
                break  # a block or a refusal: stop, never retry (BRD Rule 2)
            if len(result.products) < MIN_PRODUCTS:
                failures.append(f"{keyword}: only {len(result.products)} valid products")
            if seconds > budget_s:
                failures.append(f"{keyword}: took {seconds:.1f} s, budget {budget_s:g} s")
    finally:
        await engine.aclose()

    assert not failures, "; ".join(failures)
