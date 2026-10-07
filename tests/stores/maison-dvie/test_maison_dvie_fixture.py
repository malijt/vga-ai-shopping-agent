"""Maison D'Vie offline fixture test (plan 12.6.2): real responses through the real chain.

The three files in ``fixtures/`` are the raw bodies of the three searches the live smoke test made
on 2026-10-08 (``blazer``, ``shirt``, ``trousers``), pretty-printed. No value was edited or cut:
the longest ``body`` string is 450 characters and each file is about 11 KB. Each response holds 10
products, 30 in all, and all 30 survive validation.

Nothing here touches the network. The store file is the shipped ``config/stores/maison-dvie.yaml``,
loaded by the real registry; the records go through the real ``shopify`` extractor, the real
validation (``normalise_records``) and, in the last test, the real ``StoreSearchEngine`` with only
the HTTP boundary faked.
"""

import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from tests.factories import make_item_intent, make_settings
from tests.fakes import FakeClock

from vga.models import Category, Gender, StoreConfig, StoreStatus
from vga.settings import DEFAULT_STORES_DIR
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.registry import load_store_configs

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ("blazer", "shirt", "trousers")
HELD_PER_FIXTURE = 10
"""Every fixture holds 10 products: the page size the search URL asks for."""
SURVIVING_PER_FIXTURE = 10
"""All 10 pass validation in every fixture: nothing is dropped, nothing is a duplicate."""
SEARCH_URL = (
    "https://maisondvie.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
ALLOW_ALL_ROBOTS = "User-agent: *\nAllow: /\n"


def fixture_text(query: str) -> str:
    return (FIXTURES / f"suggest-{query}.json").read_text(encoding="utf-8")


def raw_products(query: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = json.loads(fixture_text(query))["resources"]["results"][
        "products"
    ]
    return products


@pytest.fixture
def store(tmp_path: Path) -> StoreConfig:
    """The shipped store file, loaded by the real registry (a copy, so no sibling file loads)."""
    shutil.copy(DEFAULT_STORES_DIR / "maison-dvie.yaml", tmp_path / "maison-dvie.yaml")
    [loaded] = load_store_configs(tmp_path)
    return loaded


# --------------------------------------------------------------------------------------------
# The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_with_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.id == "maison-dvie"
    assert store.display_name == "Maison D'Vie"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.search_url_template == (
        "https://maisondvie.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert store.allowed_hosts == ["maisondvie.com", "cdn.shopify.com"]
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]
    assert store.tier_hint == "luxury"


def test_genders_are_left_unset_because_the_responses_show_men_and_women() -> None:
    men_tagged = [p["title"] for q in QUERIES for p in raw_products(q) if "Men" in p["tags"]]
    women_tagged = [p["title"] for q in QUERIES for p in raw_products(q) if "Women" in p["tags"]]

    assert men_tagged, "the fixtures should show men's items (the `shirt` search does)"
    assert women_tagged, "the fixtures should show women's items"


def test_a_store_that_sells_for_both_genders_is_searched_for_either(store: StoreConfig) -> None:
    assert store.genders is None
    assert store.sells_for_gender(Gender.MEN)
    assert store.sells_for_gender(Gender.WOMEN)


# --------------------------------------------------------------------------------------------
# The three real responses through the real chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_fixture_holds_ten_products_and_all_ten_survive_validation(
    store: StoreConfig, query: str
) -> None:
    assert len(raw_products(query)) == HELD_PER_FIXTURE

    outcome = ExtractionChain(default_registry()).run(
        fixture_text(query), store, SEARCH_URL.format(query=query)
    )

    assert outcome.strategy == "shopify"
    assert outcome.examined == HELD_PER_FIXTURE
    assert len(outcome.products) == SURVIVING_PER_FIXTURE
    assert outcome.dropped == {}


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_all_six_required_fields_in_positive_aed(
    store: StoreConfig, query: str
) -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text(query), store, SEARCH_URL.format(query=query)
    )

    for product in outcome.products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "AED"
        assert product.image_url
        assert product.product_url
        assert product.store == "Maison D'Vie"


@pytest.mark.parametrize("query", QUERIES)
def test_links_and_images_are_https_on_allowed_hosts_with_a_400_wide_thumbnail(
    store: StoreConfig, query: str
) -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text(query), store, SEARCH_URL.format(query=query)
    )

    for product in outcome.products:
        page, image = urlsplit(product.product_url), urlsplit(product.image_url)
        assert page.scheme == image.scheme == "https"
        assert page.hostname == "maisondvie.com"
        assert page.path.startswith("/products/")
        assert page.query == ""  # the tracking parameters (_pos, _psq, ...) are removed
        assert image.hostname == "cdn.shopify.com"
        assert {page.hostname, image.hostname} <= set(store.allowed_hosts)
        assert parse_qs(image.query)["width"] == ["400"]


def test_the_thirty_products_have_thirty_different_links(store: StoreConfig) -> None:
    chain = ExtractionChain(default_registry())
    products = [
        product
        for query in QUERIES
        for product in chain.run(
            fixture_text(query), store, SEARCH_URL.format(query=query)
        ).products
    ]

    assert len(products) == 30
    assert len({product.product_url for product in products}) == 30


def test_the_store_marks_every_fixture_product_in_stock(store: StoreConfig) -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text("shirt"), store, SEARCH_URL.format(query="shirt")
    )

    assert {product.in_stock for product in outcome.products} == {True}


# --------------------------------------------------------------------------------------------
# The whole engine, with only the HTTP boundary faked
# --------------------------------------------------------------------------------------------


async def test_the_engine_asks_robots_then_the_documented_url_and_returns_the_ten_products(
    store: StoreConfig,
) -> None:
    enabled = store.model_copy(update={"enabled": True})
    engine = StoreSearchEngine(make_settings(), clock=FakeClock())
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.get("https://maisondvie.com/robots.txt").mock(
            return_value=httpx.Response(200, text=ALLOW_ALL_ROBOTS)
        )
        search = router.get(url__startswith="https://maisondvie.com/search/suggest.json").mock(
            return_value=httpx.Response(
                200, text=fixture_text("blazer"), headers={"content-type": "application/json"}
            )
        )

        item = make_item_intent(category=Category.OUTERWEAR, search_keywords=["blazer"])
        [result] = await engine.search(item, [enabled])
    await engine.aclose()

    assert str(search.calls.last.request.url) == SEARCH_URL.format(query="blazer")
    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == SURVIVING_PER_FIXTURE
    assert result.dropped == {}
