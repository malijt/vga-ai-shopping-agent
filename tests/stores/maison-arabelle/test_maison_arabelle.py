"""Maison Arabelle store adapter, offline (plan 12.x.1 and 12.x.2).

The fixtures in ``fixtures/`` are real answers from 2026-10-08:

- ``suggest-dress.json`` and ``suggest-abaya.json`` were recorded through the real
  ``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
  Shopify ``/search/suggest.json`` response each. Shopify caps the answer at 10 products and every
  product is kept; only each ``body`` (the HTML description) was cut to 300 characters to keep the
  files small. Nothing else was changed.
- ``qualification-suggest-kaftan.json`` and ``qualification-suggest-kurta.json`` are byte copies of
  the first 4 of 10 products of the qualification pass's ``kaftan`` and ``kurta`` answers
  (``docs/store-qualification/samples/maison-arabelle/``), same cut ``body``. They add the kaftans
  that the two full recordings hold few of.
- ``robots.txt``: the store's robots.txt, byte for byte (a short hand-written file, not Shopify's
  default).

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
QUERIES = ["dress", "abaya"]
"""The two full recordings."""
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
SHORT_FIXTURES = ["qualification-suggest-kaftan.json", "qualification-suggest-kurta.json"]
ALL_FIXTURES = [*FULL_FIXTURES, *SHORT_FIXTURES]

PRODUCTS_IN_EACH_FULL_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
PRODUCTS_IN_EACH_SHORT_FIXTURE = 4
PRODUCTS_IN_ALL_FIXTURES = 28
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 25
"""28 records; "dress" and "abaya" share 2 products and the two qualification samples share 1."""

SEARCH_URL = (
    "https://maisonarabelle.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0747/8444/"
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
        fixture_text(name), store, build_search_url(store, "dress")
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for name in ALL_FIXTURES for product in replay(store, name).products]


# --------------------------------------------------------------------------------------------
# 12.x.1 The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "maison-arabelle"
    assert store.display_name == "Maison Arabelle"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.tier_hint is Tier.LUXURY
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://maisonarabelle.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "floral kaftan") == SEARCH_URL.format(query="floral%20kaftan")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["maisonarabelle.com", "cdn.shopify.com"]


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart_and_checkout() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://maisonarabelle.com/cart", agent)  # parsed, not allow-all
    assert not robots.can_fetch("https://maisonarabelle.com/checkout", agent)
    assert not robots.can_fetch("https://maisonarabelle.com/admin", agent)


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
        assert product.store == "Maison Arabelle"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_prices_are_positive_aed_amounts_in_a_plausible_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products

    assert all(product.currency == "AED" for product in products)
    assert all(500 <= product.price <= 3000 for product in products)  # a unit slip would be far out


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "maisonarabelle.com"
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

    assert len(every_product) == PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) == DISTINCT_PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) >= 20  # plan 12.x.2


# --------------------------------------------------------------------------------------------
# Quirks of this store's data (docs/store-notes/maison-arabelle.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "price", "compare_at"),
    [
        pytest.param("MARWA WHITE", 1040.0, "890.00", id="compare-at below the price"),
        pytest.param("SHAMAA", 980.0, "790.00", id="compare-at below the price, again"),
        pytest.param("SHIMMER", 1600.0, "1600.00", id="compare-at equal to the price"),
    ],
)
def test_a_compare_at_price_at_or_below_the_price_is_never_read_as_a_discount(
    store: StoreConfig, title: str, price: float, compare_at: str
) -> None:
    """Quirk: three pieces in the "dress" answer carry a ``compare_at_price_max`` that is not above
    the price. A real struck-through price would be higher; these are leftovers. The adapter reads
    ``price`` only, so the shopper sees what the store charges."""
    [raw] = [p for p in raw_products("suggest-dress.json") if p["title"] == title]
    [product] = [p for p in replay(store, "suggest-dress.json").products if p.title == title]

    assert raw["compare_at_price_max"] == compare_at
    assert float(raw["compare_at_price_max"]) <= float(raw["price"])
    assert product.price == price


def test_every_other_piece_has_no_compare_at_price() -> None:
    others = [
        p
        for name in FULL_FIXTURES
        for p in raw_products(name)
        if p["title"] not in {"MARWA WHITE", "SHAMAA", "SHIMMER"}
    ]

    assert len(others) == 17
    assert {p["compare_at_price_max"] for p in others} == {"0.00"}


def test_the_vendor_is_spelled_two_ways_but_the_shopper_sees_one_store_name(
    store: StoreConfig,
) -> None:
    vendors = {p["vendor"] for p in raw_products("suggest-dress.json")}

    assert vendors == {"MAISON ARABELLE", "Maison Arabelle"}  # one brand, written two ways
    assert {v.casefold() for v in vendors} == {"maison arabelle"}
    assert {p.store for p in all_products(store)} == {"Maison Arabelle"}


def test_many_titles_are_only_a_name_so_the_garment_is_not_in_the_title(
    store: StoreConfig,
) -> None:
    """Quirk: "MARWA WHITE", "SHIMMER", "SHAMAA", "MAYRA BLACK" say neither kaftan nor abaya, and
    ``type`` is the same string on every record. The adapter passes the titles on as written (upper
    case, typos included); category has to come from the ranker's reading of title and text."""
    titles = {p.title for p in replay(store, "suggest-dress.json").products}
    types = {p["type"] for name in ALL_FIXTURES for p in raw_products(name)}

    assert {"MARWA WHITE", "SHIMMER", "SHAMAA", "MAYRA BLACK", "BADER LINEN NAVY BLUE"} <= titles
    assert types == {"Kaftans and Abayas"}
    assert "LARA GRAY EMBROIREDED ABAYA" in titles  # the store's own typo is kept


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field (``tags`` is empty on most
    records): every product's gender is unknown, and ``genders: [women]`` does the work."""
    assert {product.gender for product in all_products(store)} == {None}


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-dress.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_images_may_be_png_or_jpg_and_both_are_accepted(store: StoreConfig) -> None:
    extensions = {
        urlsplit(product.image_url).path.rsplit(".", 1)[-1] for product in all_products(store)
    }

    assert {"jpg", "png"} <= extensions


def test_the_same_product_can_answer_two_queries_and_repeats_collapse(store: StoreConfig) -> None:
    dress = replay(store, "suggest-dress.json").products
    abaya = replay(store, "suggest-abaya.json").products

    distinct, repeats = dedupe_products([*dress, *abaya])

    assert len(distinct) == 18
    assert repeats == {"duplicate_url": 2}  # the Lara grey and Charlotte off-white abayas


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
            make_item_intent(search_keywords=["dress", "abaya"]),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 18  # 20 records, 2 of them answered both queries
    assert result.dropped == {}
    assert [str(request.url) for request in seen] == [
        "https://maisonarabelle.com/robots.txt",
        SEARCH_URL.format(query="dress"),
        SEARCH_URL.format(query="abaya"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
