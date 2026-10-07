"""Bazza Alzouman store adapter, offline (plan 12.11).

The fixtures in ``fixtures/`` are real answers from 2026-10-08, recorded through the real
``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
Shopify ``/search/suggest.json`` response each for ``gown`` and ``dress``. Shopify caps the answer
at 10 products and every product is kept; only each ``body`` (the HTML description) was cut to 300
characters to keep the files small. ``robots.txt`` is the store's file, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"245.000"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006).
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

from vga.models import Category, Gender, Product, StoreConfig, StoreStatus, Tier
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["gown", "dress"]
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
DISTINCT_PRODUCTS_IN_BOTH_FIXTURES = 17
"""20 records; three gowns answered both queries."""

SEARCH_URL = (
    "https://bazzaalzouman.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0244/0753/9793/"
"""Every image of the store is under this folder of the shared Shopify CDN."""


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(name: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def replay(store: StoreConfig, name: str) -> ChainOutcome:
    """The saved response ``name`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(name), store, build_search_url(store, "gown")
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for name in FULL_FIXTURES for product in replay(store, name).products]


# --------------------------------------------------------------------------------------------
# The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "bazza-alzouman"
    assert store.display_name == "Bazza Alzouman"
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.LUXURY
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://bazzaalzouman.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "evening gown") == SEARCH_URL.format(query="evening%20gown")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["bazzaalzouman.com", "cdn.shopify.com"]


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_evening_gown_store(store: StoreConfig) -> None:
    # Every garment seen here is a gown or a dress (docs/store-notes/bazza-alzouman.md), so a
    # search for shoes, jeans, tops or jackets would only waste a request to it.
    assert store.categories == frozenset({Category.DRESSES})
    assert store.sells_category(Category.DRESSES)
    for other in (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://bazzaalzouman.com/cart/", agent)  # parsed, not allow-all


# --------------------------------------------------------------------------------------------
# The fixtures through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_each_recording_holds_ten_products_and_all_ten_survive_validation(
    store: StoreConfig, name: str
) -> None:
    outcome = replay(store, name)

    assert len(raw_products(name)) == PRODUCTS_IN_EACH_FIXTURE
    assert outcome.examined == PRODUCTS_IN_EACH_FIXTURE
    assert len(outcome.products) == PRODUCTS_IN_EACH_FIXTURE
    assert outcome.dropped == {}
    assert outcome.strategy == "shopify"


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_every_product_has_all_six_required_fields_and_a_dinar_price(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "KWD"
        assert product.image_url
        assert product.product_url
        assert product.store == "Bazza Alzouman"


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_prices_keep_their_three_decimals_and_sit_in_the_gown_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products
    raw = {item["title"]: item["price"] for item in raw_products(name)}

    assert all(len(raw[product.title].split(".")[1]) == 3 for product in products)
    # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000 out.
    assert all(200 <= product.price <= 400 for product in products)


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    title = "Strapless Gown With Side Organza Ruched Drape"
    prices = {p.title: p.price for p in replay(store, "suggest-gown.json").products}
    [raw] = [item for item in raw_products("suggest-gown.json") if item["title"] == title]

    assert raw["price"] == "245.000"
    assert prices[title] == 245.0
    assert prices["Slim Cut Crepe Gown With Gathered Tulle Illusion Neckline And Sleeve"] == 260.0


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "bazzaalzouman.com"
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert urlsplit(product.image_url).path.startswith(IMAGE_FOLDER)


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_image_urls_carry_width_400_and_keep_the_version_parameter(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params


def test_the_two_recordings_give_seventeen_distinct_valid_products(store: StoreConfig) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 2 * PRODUCTS_IN_EACH_FIXTURE
    assert len(distinct) == DISTINCT_PRODUCTS_IN_BOTH_FIXTURES
    assert repeats == {"duplicate_url": 3}


# --------------------------------------------------------------------------------------------
# Quirks of this store's data (docs/store-notes/bazza-alzouman.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_every_record_has_a_single_price_so_the_default_price_is_the_garments(
    store: StoreConfig,
) -> None:
    """Unlike Hamsa, no record here has variants at different prices: the lowest and the highest
    price are the same on all 20, so reading ``price`` cannot pick up an add-on."""
    for name in FULL_FIXTURES:
        for item in raw_products(name):
            assert item["price_min"] == item["price_max"] == item["price"]


def test_the_price_is_what_the_shopper_pays_not_the_struck_through_price(
    store: StoreConfig,
) -> None:
    title = "Long Sleeve Collared Wrap A Line Gown"
    [wrap_gown] = [p for p in replay(store, "suggest-gown.json").products if p.title == title]
    [raw] = [p for p in raw_products("suggest-gown.json") if p["title"] == title]

    assert raw["compare_at_price_max"] == "295.000"
    assert wrap_gown.price == 206.0


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-gown.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_the_type_is_dresses_dress_or_gown_so_it_never_separates_categories(
    store: StoreConfig,
) -> None:
    """Quirk: the same kind of garment is filed under three spellings, and every one of the 20
    records is a gown or a dress. ``categories: [dresses]`` in the store file rests on this."""
    types = {item["type"] for name in FULL_FIXTURES for item in raw_products(name)}

    assert types == {"Dresses", "Dress", "Gown"}


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's evening wear, but it never says so in a field: every product's gender
    is unknown, and ``genders: [women]`` in the store file does the work."""
    assert {product.gender for product in all_products(store)} == {None}


def test_the_same_gown_can_answer_two_queries_and_repeats_collapse(store: StoreConfig) -> None:
    gown = replay(store, "suggest-gown.json").products
    dress = replay(store, "suggest-dress.json").products

    distinct, repeats = dedupe_products([*gown, *dress])

    assert len(distinct) == DISTINCT_PRODUCTS_IN_BOTH_FIXTURES
    assert repeats == {"duplicate_url": 3}


def test_a_handle_that_is_not_the_title_is_still_linked_by_its_handle(store: StoreConfig) -> None:
    """The link is the store's own ``url`` (its handle), never rebuilt from the title: this store's
    handles differ from the slugged title (``...-at-neck-1``, ``sleeveless-baloon-...``)."""
    by_title = {p.title: p.product_url for p in replay(store, "suggest-gown.json").products}

    assert by_title["One Shoulder Crepe Gown With Gathered Tulle At Neck"] == (
        "https://bazzaalzouman.com/products/one-shoulder-crepe-gown-with-gathered-tulle-at-neck-1"
    )
    assert by_title["Sleeveless Balloon Collar Gown With Square Train"] == (
        "https://bazzaalzouman.com/products/sleeveless-baloon-collar-gown-with-square-train"
    )


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
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
        query = parse_qs(request.url.query.decode())["q"][0]
        return httpx.Response(
            200,
            content=fixture_text(f"suggest-{query}.json").encode(),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    # A Kuwaiti store is searched only when Kuwait is among the extra countries (settings.yaml).
    settings = make_settings(extra_store_countries=["KW"])
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=["gown", "dress"]),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == DISTINCT_PRODUCTS_IN_BOTH_FIXTURES
    assert result.dropped == {}
    assert {product.currency for product in result.products} == {"KWD"}
    assert [str(request.url) for request in seen] == [
        "https://bazzaalzouman.com/robots.txt",
        SEARCH_URL.format(query="gown"),
        SEARCH_URL.format(query="dress"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
