"""Club L London UAE store adapter (plan 12.5.1 and 12.5.2), offline.

Loads the real ``config/stores/club-l-london.yaml`` through the real registry and replays three
real ``/search/suggest.json`` responses through the real extraction chain and validation. The
responses were recorded on 2026-10-08 from a live run through ``StoreSearchEngine`` (queries
``blazer``, ``jacket``, ``heels``); only each product's ``body`` text was cut to 300 characters.
Nothing here touches the network.

What the fixtures hold, and how many products survive validation:

- ``suggest-blazer.json``: 10 products (all blazers), 10 survive.
- ``suggest-jacket.json``: 10 products (all blazers or jackets), 10 survive.
- ``suggest-heels.json``: 10 products (5 shoes and 5 dresses), 10 survive: extraction keeps
  dresses, because filtering by category happens later, in ranking.

Shopify's endpoint returns at most 10 products per call, so the plan's "at least 20 products" is
met only across the three files (30 products); each file alone holds 10.
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

from vga.models import Gender, Product, StoreConfig, StoreStatus, Tier
from vga.settings import DEFAULT_STORES_DIR
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.registry import StoreRegistry
from vga.stores.urls import build_search_url

STORE_FILE = DEFAULT_STORES_DIR / "club-l-london.yaml"
FIXTURES = Path(__file__).parent / "fixtures"

# fixture file -> (products in the saved response, products that survive validation)
FIXTURE_COUNTS = {
    "suggest-blazer.json": (10, 10),
    "suggest-jacket.json": (10, 10),
    "suggest-heels.json": (10, 10),
}
STORE_HOST = "www.clubllondon.ae"
SEARCH_URL_FOR_BLAZER = (
    "https://www.clubllondon.ae/search/suggest.json"
    "?q=blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def saved_products(name: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> StoreConfig:
    """The shipped store file, loaded by the real registry (from a copy, so a broken file for
    another store cannot fail this test)."""
    folder = tmp_path_factory.mktemp("stores")
    shutil.copy(STORE_FILE, folder / STORE_FILE.name)
    loaded = StoreRegistry.from_directory(folder).get("club-l-london")
    assert loaded is not None
    return loaded


def extract(store: StoreConfig, name: str) -> list[Product]:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text(name), store, build_search_url(store, "blazer")
    )
    assert outcome.strategy == "shopify"
    return outcome.products


# --------------------------------------------------------------------------------------------
# 12.5.1: the config entry
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_with_the_documented_fields(store: StoreConfig) -> None:
    assert store.id == "club-l-london" == STORE_FILE.stem
    assert store.display_name == "Club L London UAE"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.tier_hint is Tier.PREMIUM
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]
    assert store.allowed_hosts == [STORE_HOST, "cdn.shopify.com"]


def test_the_search_url_is_shopifys_suggest_endpoint_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://www.clubllondon.ae/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "blazer") == SEARCH_URL_FOR_BLAZER


def test_a_multi_word_query_is_percent_encoded_in_the_search_url(store: StoreConfig) -> None:
    url = build_search_url(store, "black blazer")

    assert urlsplit(url).netloc == STORE_HOST
    assert parse_qs(urlsplit(url).query)["q"] == ["black blazer"]
    assert "q=black%20blazer&" in url


def test_the_store_sells_for_women_only(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)  # no gender asked for
    assert store.sells_for_gender(Gender.UNISEX)  # unisex does not narrow the audience
    assert not store.sells_for_gender(Gender.MEN)


# --------------------------------------------------------------------------------------------
# 12.5.2: the saved responses through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_every_saved_product_survives_validation(store: StoreConfig, name: str) -> None:
    expected_saved, expected_kept = FIXTURE_COUNTS[name]
    outcome = ExtractionChain(default_registry()).run(
        fixture_text(name), store, build_search_url(store, "blazer")
    )

    assert len(saved_products(name)) == expected_saved
    assert len(outcome.products) == expected_kept
    assert outcome.examined == expected_saved
    assert outcome.dropped == {}
    assert outcome.strategy == "shopify"


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_every_product_has_all_six_required_fields(store: StoreConfig, name: str) -> None:
    for product in extract(store, name):
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "AED"
        assert product.image_url
        assert product.product_url
        assert product.store == "Club L London UAE"


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_prices_are_positive_aed_and_match_the_saved_strings(store: StoreConfig, name: str) -> None:
    saved = {item["title"]: float(item["price"]) for item in saved_products(name)}

    for product in extract(store, name):
        assert product.currency == "AED"
        assert product.price > 0
        assert product.price == saved[product.title]


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in extract(store, name):
        product_url = urlsplit(product.product_url)
        image_url = urlsplit(product.image_url)
        assert product_url.scheme == image_url.scheme == "https"
        assert product_url.hostname in store.allowed_hosts
        assert image_url.hostname in store.allowed_hosts
        assert product_url.hostname == STORE_HOST
        assert product_url.path.startswith("/products/")
        assert image_url.hostname == "cdn.shopify.com"


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_product_links_drop_the_tracking_parameters(store: StoreConfig, name: str) -> None:
    for product in extract(store, name):
        parts = urlsplit(product.product_url)
        assert parts.query == ""
        assert "_pos" not in product.product_url
        assert "_psq" not in product.product_url


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_image_urls_carry_width_400_and_keep_the_version(store: StoreConfig, name: str) -> None:
    for product in extract(store, name):
        query = parse_qs(urlsplit(product.image_url).query)
        assert query["width"] == ["400"]
        assert "v" in query  # the CDN version parameter is left as the store wrote it


@pytest.mark.parametrize("name", FIXTURE_COUNTS)
def test_in_stock_comes_from_the_product_level_available_flag(
    store: StoreConfig, name: str
) -> None:
    assert all(product.in_stock is True for product in extract(store, name))


def test_extraction_keeps_the_dresses_of_a_heels_search(store: StoreConfig) -> None:
    """Dresses dominate this store; they are outside the four categories but extraction keeps
    them: filtering happens later, in ranking."""
    products = extract(store, "suggest-heels.json")

    dresses = [product for product in products if "dress" in product.title.lower()]
    others = [product for product in products if "dress" not in product.title.lower()]
    assert (len(dresses), len(others)) == (5, 5)
    assert all("heel" in product.title.lower() for product in others)


# --------------------------------------------------------------------------------------------
# The engine around the same response (robots.txt first, then one search)
# --------------------------------------------------------------------------------------------


async def test_the_real_engine_reads_the_saved_response_after_checking_robots(
    store: StoreConfig,
) -> None:
    """Fakes only the store's HTTP. The engine's own robots check, rate limit, allow-list and
    extraction run for real, so this also pins the exact URL a search sends."""
    enabled = store.model_copy(update={"enabled": True})
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as router:
        router.get(f"https://{STORE_HOST}/robots.txt").mock(
            return_value=httpx.Response(
                200,
                content=b"User-agent: *\nAllow: /\nDisallow: /cart/\n",
                headers={"content-type": "text/plain"},
            )
        )
        search = router.get(url__startswith=f"https://{STORE_HOST}/search/suggest.json").mock(
            return_value=httpx.Response(
                200,
                content=fixture_text("suggest-blazer.json").encode("utf-8"),
                headers={"content-type": "application/json; charset=utf-8"},
            )
        )
        engine = StoreSearchEngine(make_settings(), clock=FakeClock())
        try:
            [result] = await engine.search(make_item_intent(search_keywords=["blazer"]), [enabled])
        finally:
            await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 10
    assert result.dropped == {}
    assert {product.store for product in result.products} == {"Club L London UAE"}
    assert str(search.calls.last.request.url) == SEARCH_URL_FOR_BLAZER
    assert search.call_count == 1
