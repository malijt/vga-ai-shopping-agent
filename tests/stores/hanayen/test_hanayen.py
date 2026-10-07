"""Hanayen store adapter, offline (plan 12.x.1 and 12.x.2).

The fixtures in ``fixtures/`` are real answers from 2026-10-08:

- ``suggest-abaya.json`` and ``suggest-kaftan.json`` were recorded through the real
  ``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
  Shopify ``/search/suggest.json`` response each. Shopify caps the answer at 10 products and every
  product is kept; only each ``body`` (the HTML description) was cut to 300 characters to keep the
  files small. Nothing else was changed.
- ``qualification-suggest-dress.json`` and ``qualification-suggest-kurta.json`` are byte copies of
  the first 4 of 10 products of the qualification pass's ``dress`` and ``kurta`` answers
  (``docs/store-qualification/samples/hanayen/``), same cut ``body``. They add products the two
  full recordings do not hold, such as the under-abaya "Inner" dresses.
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

from vga.models import Category, Gender, Product, StoreConfig, StoreStatus, Tier
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["abaya", "kaftan"]
"""The two full recordings."""
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
SHORT_FIXTURES = ["qualification-suggest-dress.json", "qualification-suggest-kurta.json"]
ALL_FIXTURES = [*FULL_FIXTURES, *SHORT_FIXTURES]

PRODUCTS_IN_EACH_FULL_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
PRODUCTS_IN_EACH_SHORT_FIXTURE = 4
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 24
"""20 + 4 + 4 records; "abaya" and "kaftan" share 3 products and "kurta" repeats the first abaya."""

SEARCH_URL = (
    "https://hanayen.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0528/4682/"
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
        fixture_text(name), store, build_search_url(store, "abaya")
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for name in ALL_FIXTURES for product in replay(store, name).products]


# --------------------------------------------------------------------------------------------
# 12.x.1 The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "hanayen"
    assert store.display_name == "Hanayen"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.tier_hint is Tier.PREMIUM
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://hanayen.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black abaya") == SEARCH_URL.format(query="black%20abaya")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["hanayen.com", "cdn.shopify.com"]


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_dress_store(store: StoreConfig) -> None:
    # Every garment seen here is an abaya or an under-abaya dress (docs/store-notes/hanayen.md), so
    # a search for shoes, jeans, tops or jackets would only waste a request to it.
    assert store.categories == frozenset({Category.DRESSES})
    assert store.sells_category(Category.DRESSES)
    for other in (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://hanayen.com/cart/", agent)  # parsed, not allow-all


# --------------------------------------------------------------------------------------------
# 12.x.2 The fixtures through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_each_full_recording_holds_ten_products_and_all_ten_survive_validation(
    store: StoreConfig, name: str
) -> None:
    outcome = replay(store, name)

    assert len(raw_products(name)) == PRODUCTS_IN_EACH_FULL_FIXTURE
    assert outcome.examined == PRODUCTS_IN_EACH_FULL_FIXTURE
    assert len(outcome.products) == PRODUCTS_IN_EACH_FULL_FIXTURE
    assert outcome.dropped == {}
    assert outcome.strategy == "shopify"


@pytest.mark.parametrize("name", SHORT_FIXTURES)
def test_each_qualification_sample_holds_four_products_and_all_four_survive(
    store: StoreConfig, name: str
) -> None:
    outcome = replay(store, name)

    assert outcome.examined == PRODUCTS_IN_EACH_SHORT_FIXTURE
    assert len(outcome.products) == PRODUCTS_IN_EACH_SHORT_FIXTURE
    assert outcome.dropped == {}


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_every_product_has_all_six_required_fields(store: StoreConfig, name: str) -> None:
    for product in replay(store, name).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "AED"
        assert product.image_url
        assert product.product_url
        assert product.store == "Hanayen"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_prices_are_positive_aed_amounts_in_a_plausible_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products

    assert all(product.currency == "AED" for product in products)
    assert all(100 <= product.price <= 6000 for product in products)  # a unit slip would be far out


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "hanayen.com"
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert urlsplit(product.image_url).path.startswith(IMAGE_FOLDER)


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_image_urls_carry_width_400_and_keep_the_version_parameter(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params


def test_the_four_fixtures_give_at_least_twenty_distinct_valid_products(
    store: StoreConfig,
) -> None:
    every_product = all_products(store)
    distinct, _repeats = dedupe_products(every_product)

    assert len(every_product) == 28
    assert len(distinct) == DISTINCT_PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) >= 20  # plan 12.x.2


# --------------------------------------------------------------------------------------------
# Quirks of this store's data (docs/store-notes/hanayen.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_the_price_is_what_the_shopper_pays_not_the_struck_through_price(
    store: StoreConfig,
) -> None:
    title = "Modern A-Line Lapel Abaya"
    [lapel_abaya] = [p for p in replay(store, "suggest-abaya.json").products if p.title == title]
    [raw] = [p for p in raw_products("suggest-abaya.json") if p["title"] == title]

    assert raw["compare_at_price_max"] == "900.00"
    assert lapel_abaya.price == 675.0


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-abaya.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_a_kaftan_search_is_padded_with_sheilas_and_the_adapter_keeps_them(
    store: StoreConfig,
) -> None:
    """Quirk: the store has no kaftan garment, so "kaftan" returns four sheilas (head scarves, type
    SHEILA, an accessory), one under-abaya dress and five abayas. The adapter makes no
    store-specific exclusion: dropping accessories is the ranker's job, for every store."""
    raw = raw_products("suggest-kaftan.json")
    sheilas = [p for p in raw if p["type"] == "SHEILA"]
    assert len(sheilas) == 4

    titles = {p.title for p in replay(store, "suggest-kaftan.json").products}

    assert {p["title"] for p in sheilas} <= titles
    assert len(titles) == 10


def test_inner_dresses_have_the_same_type_as_abayas_so_only_the_tag_and_the_title_tell(
    store: StoreConfig,
) -> None:
    """Quirk: an under-abaya "inner" is a plain slip dress (AED 250 to 275) that the store files
    under type "Abaya" like everything else; the tag ``Inner`` is the only structured sign."""
    raw = raw_products("qualification-suggest-kurta.json")
    inners = [p for p in raw if "Inner" in p["tags"]]
    [outer] = [p for p in raw if "Inner" not in p["tags"]]

    assert len(inners) == 3
    assert {p["type"] for p in inners} == {outer["type"]} == {"Abaya"}
    inner_titles = {p["title"] for p in inners}
    prices = {p.title: p.price for p in replay(store, "qualification-suggest-kurta.json").products}
    assert {prices[title] for title in inner_titles} == {250.0, 275.0}


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field: every product's gender is
    unknown, and ``genders: [women]`` in the store file does the work."""
    assert {product.gender for product in all_products(store)} == {None}


def test_the_same_product_can_answer_two_queries_and_repeats_collapse(store: StoreConfig) -> None:
    abaya = replay(store, "suggest-abaya.json").products
    kaftan = replay(store, "suggest-kaftan.json").products

    distinct, repeats = dedupe_products([*abaya, *kaftan])

    assert len(distinct) == 17
    assert repeats == {"duplicate_url": 3}


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

    settings = make_settings()
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=["abaya", "kaftan"]),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 17  # 20 records, 3 of them answered both queries
    assert result.dropped == {}
    assert [str(request.url) for request in seen] == [
        "https://hanayen.com/robots.txt",
        SEARCH_URL.format(query="abaya"),
        SEARCH_URL.format(query="kaftan"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
