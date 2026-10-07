"""Oh Polly UAE store adapter, offline (plan 12.4.1 and 12.4.2).

The fixtures in ``fixtures/`` are real answers recorded on 2026-10-08 through the real
``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second):

- ``suggest-blazer.json``, ``suggest-jacket.json``, ``suggest-heels.json``: one full Shopify
  ``/search/suggest.json`` response each. Shopify caps the answer at 10 products and every product
  is kept; only each ``body`` (the HTML description) was cut to 300 characters to keep the files
  small. Nothing else was changed.
- ``robots.txt``: the store's robots.txt, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and
the fixtures through the real extraction chain, validation and search engine.
"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from protego import Protego
from tests.factories import make_item_intent, make_settings
from tests.fakes import FakeClock

from vga.models import Gender, Product, StoreConfig, StoreStatus, Tier
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["blazer", "jacket", "heels"]

PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each saved response is a full answer."""
SURVIVING_VALIDATION_IN_EACH_FIXTURE = 10
"""All of them: the store's data is clean, so validation drops nothing."""
PRODUCTS_IN_ALL_FIXTURES = 30
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 27
"""Three ski jackets come back for both "blazer" and "jacket"."""

SEARCH_URL = (
    "https://ohpolly.ae/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(query: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(f"suggest-{query}.json"))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def replay(store: StoreConfig, query: str) -> ChainOutcome:
    """The saved response for ``query`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(f"suggest-{query}.json"), store, build_search_url(store, query)
    )


# --------------------------------------------------------------------------------------------
# 12.4.1 The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "oh-polly"
    assert store.display_name == "Oh Polly UAE"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.tier_hint is Tier.MID_RANGE
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://ohpolly.ae/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black blazer") == SEARCH_URL.format(query="black%20blazer")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["ohpolly.ae", "cdn.shopify.com"]


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://ohpolly.ae/cart/", agent)  # parsed, not allow-all


# --------------------------------------------------------------------------------------------
# 12.4.2 The fixtures through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_fixture_holds_ten_products_and_all_ten_survive_validation(
    store: StoreConfig, query: str
) -> None:
    outcome = replay(store, query)

    assert len(raw_products(query)) == PRODUCTS_IN_EACH_FIXTURE
    assert outcome.examined == PRODUCTS_IN_EACH_FIXTURE
    assert len(outcome.products) == SURVIVING_VALIDATION_IN_EACH_FIXTURE
    assert outcome.dropped == {}
    assert outcome.strategy == "shopify"


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_all_six_required_fields(store: StoreConfig, query: str) -> None:
    for product in replay(store, query).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "AED"
        assert product.image_url
        assert product.product_url
        assert product.store == "Oh Polly UAE"


@pytest.mark.parametrize("query", QUERIES)
def test_prices_are_positive_aed_amounts_in_a_plausible_range(
    store: StoreConfig, query: str
) -> None:
    prices = [product.price for product in replay(store, query).products]

    assert all(price > 0 for price in prices)
    assert all(product.currency == "AED" for product in replay(store, query).products)
    assert all(100 <= price <= 1500 for price in prices)  # a misread unit would be far outside


@pytest.mark.parametrize("query", QUERIES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "ohpolly.ae"
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"


@pytest.mark.parametrize("query", QUERIES)
def test_image_urls_carry_width_400_and_keep_the_version_parameter(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params


def test_the_three_fixtures_give_at_least_twenty_distinct_valid_products(
    store: StoreConfig,
) -> None:
    every_product: list[Product] = [
        product for query in QUERIES for product in replay(store, query).products
    ]
    distinct, _repeats = dedupe_products(every_product)

    assert len(every_product) == PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) == DISTINCT_PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) >= 20  # plan 12.x.2


# --------------------------------------------------------------------------------------------
# Quirks of this store's data (docs/store-notes/oh-polly.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_the_price_is_what_the_shopper_pays_not_the_struck_through_price(
    store: StoreConfig,
) -> None:
    [white_blazer] = [
        p for p in replay(store, "blazer").products if p.title.endswith("Blazer in White")
    ]
    [raw] = [p for p in raw_products("blazer") if p["title"].endswith("Blazer in White")]

    assert raw["compare_at_price_max"] == "400.00"
    assert white_blazer.price == 230.0


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    assert all("_pos=" in p["url"] for p in raw_products("blazer"))  # the store adds them

    for product in replay(store, "blazer").products:
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_a_double_space_in_a_heel_title_is_collapsed(store: StoreConfig) -> None:
    raw_titles = [p["title"] for p in raw_products("heels")]
    assert "Heeled Thong Sandals  in Arctic Blue" in raw_titles  # the store writes two spaces

    titles = [p.title for p in replay(store, "heels").products]
    assert "Heeled Thong Sandals in Arctic Blue" in titles
    assert all("  " not in title for title in titles)


def test_a_blazer_mini_dress_is_filed_under_coats_and_jackets_so_only_the_title_tells() -> None:
    dresses = [p for p in raw_products("blazer") if "Mini Dress" in p["title"]]

    assert len(dresses) == 2
    assert {p["type"] for p in dresses} == {"Coats & Jackets"}


def test_a_blazer_search_is_also_answered_with_another_brands_ski_jackets(
    store: StoreConfig,
) -> None:
    vendors = {p["vendor"] for p in raw_products("blazer")}

    assert vendors == {"Oh Polly", "Bo+Tee"}  # all sold in this one store
    assert {p.store for p in replay(store, "blazer").products} == {"Oh Polly UAE"}


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


async def test_the_engine_reads_the_saved_answer_after_checking_robots_txt(
    store: StoreConfig,
) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                content=fixture_text("robots.txt").encode(),
                headers={"content-type": "text/plain"},
            )
        return httpx.Response(
            200,
            content=fixture_text("suggest-blazer.json").encode(),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    settings = make_settings()
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=["blazer"]),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == SURVIVING_VALIDATION_IN_EACH_FIXTURE
    assert result.dropped == {}
    assert [str(request.url) for request in seen] == [
        "https://ohpolly.ae/robots.txt",
        SEARCH_URL.format(query="blazer"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
