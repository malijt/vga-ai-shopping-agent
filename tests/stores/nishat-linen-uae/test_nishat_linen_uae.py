"""Nishat Linen UAE store adapter, offline (plan 12.x.1 and 12.x.2).

The fixtures in ``fixtures/`` are real answers from 2026-10-08:

- ``suggest-dress.json`` and ``suggest-kurta.json`` were recorded through the real
  ``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
  Shopify ``/search/suggest.json`` response each. Shopify caps the answer at 10 products and every
  product is kept; only each ``body`` (the HTML description) was cut to 300 characters to keep the
  files small. Nothing else was changed.
- ``qualification-suggest-kaftan.json`` and ``qualification-suggest-abaya.json`` are byte copies of
  the first 4 of 10 products of the qualification pass's ``kaftan`` and ``abaya`` answers
  (``docs/store-qualification/samples/nishat-linen-uae/``), same cut ``body``. They add the kaftans,
  gown and embroidered suits that the two full recordings do not hold. (The ``abaya`` query has no
  abayas here: the store pads the answer.)
- ``robots.txt``: the store's robots.txt, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and
the fixtures through the real extraction chain, validation and search engine.
"""

import json
import re
from collections import Counter
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
QUERIES = ["dress", "kurta"]
"""The two full recordings."""
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
SHORT_FIXTURES = ["qualification-suggest-kaftan.json", "qualification-suggest-abaya.json"]
ALL_FIXTURES = [*FULL_FIXTURES, *SHORT_FIXTURES]

PRODUCTS_IN_EACH_FULL_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
PRODUCTS_IN_EACH_SHORT_FIXTURE = 4
PRODUCTS_IN_ALL_FIXTURES = 28
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 28

SEARCH_URL = (
    "https://www.nishatlinenuae.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0283/9766/"
"""Every image of the store is under this folder of the shared Shopify CDN."""
TITLE_ENDS_WITH_A_CODE = re.compile(r" - [A-Z]{2,3}\d{2}-\d{2,3}$")


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
    assert store.id == "nishat-linen-uae"
    assert store.display_name == "Nishat Linen UAE"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.tier_hint is Tier.BUDGET
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://www.nishatlinenuae.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "long dress") == SEARCH_URL.format(query="long%20dress")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["www.nishatlinenuae.com", "cdn.shopify.com"]


def test_the_store_is_searched_for_either_gender_because_it_sells_both(
    store: StoreConfig,
) -> None:
    assert store.genders is None
    assert store.sells_for_gender(Gender.MEN)
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://www.nishatlinenuae.com/cart/", agent)  # not allow-all


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
        assert product.store == "Nishat Linen UAE"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_prices_are_positive_aed_amounts_in_a_plausible_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products

    assert all(product.currency == "AED" for product in products)
    assert all(30 <= product.price <= 300 for product in products)  # a unit slip would be far out


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "www.nishatlinenuae.com"
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
# Quirks of this store's data (docs/store-notes/nishat-linen-uae.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_the_price_is_the_sale_price_not_the_struck_through_double(store: StoreConfig) -> None:
    """Quirk: the whole range was at 50% off on 2026-10-08. ``compare_at_price_max`` is exactly
    twice the price on every recorded record; the adapter uses ``price``, what the shopper pays."""
    for name in ALL_FIXTURES:
        for raw in raw_products(name):
            assert float(raw["compare_at_price_max"]) == 2 * float(raw["price"])

    [dress] = [p for p in replay(store, "suggest-dress.json").products if "AS26-92" in p.title]
    [raw] = [p for p in raw_products("suggest-dress.json") if "AS26-92" in p["title"]]
    assert raw["compare_at_price_max"] == "159.00"
    assert dress.price == 79.5


def test_titles_are_a_garment_word_and_a_code_so_the_title_has_little_to_rank_on(
    store: StoreConfig,
) -> None:
    titles = [product.title for product in all_products(store)]

    assert all(TITLE_ENDS_WITH_A_CODE.search(title) for title in titles)
    assert "Printed Dress - AS26-92" in titles
    assert "2 Piece - Embroidered Gown - FE26-128" in titles
    assert all("nishat" not in title.casefold() for title in titles)  # no brand in the title


def test_a_kurta_search_returns_only_mens_kurtas_and_the_type_says_so(store: StoreConfig) -> None:
    """Quirk: the word kurta finds only the men's range (type "RTW Men"); the women's embroidered
    sets are filed as Fustan, Aura and so on. Reading ``type`` first labels all ten as men's."""
    raw = raw_products("suggest-kurta.json")
    products = replay(store, "suggest-kurta.json").products

    assert {p["type"] for p in raw} == {"RTW Men"}
    assert [product.gender for product in products] == [Gender.MEN] * 10


def test_the_women_tag_is_on_only_some_womens_items_so_the_rest_stay_unknown(
    store: StoreConfig,
) -> None:
    """Quirk: 7 of the 10 "dress" results carry the tag ``Women``; 3 women's dresses (a printed
    Fustan, an embroidered Aura, a basic Fustan) carry no gender tag at all. They get no gender
    here and the ranker reads their titles. Nothing labels a woman's dress as a man's."""
    raw = raw_products("suggest-dress.json")
    products = replay(store, "suggest-dress.json").products

    assert sum("Women" in p["tags"] for p in raw) == 7
    assert Counter(product.gender for product in products) == {Gender.WOMEN: 7, None: 3}
    assert Gender.MEN not in {product.gender for product in products}


def test_the_genders_over_all_four_fixtures(store: StoreConfig) -> None:
    counted = Counter(product.gender for product in all_products(store))

    assert counted == {Gender.WOMEN: 12, Gender.MEN: 10, None: 6}


def test_the_same_title_can_belong_to_two_different_products(store: StoreConfig) -> None:
    """Quirk: "Basic Kurta - NQ26-010" is listed twice, at AED 39.50 under the handle nq26-028 (a
    bottoms item by its tags) and at AED 64.50 under nq26-010. Validation tells them apart by link
    and price and keeps both."""
    title = "Basic Kurta - NQ26-010"
    same = [p for p in raw_products("suggest-kurta.json") if p["title"] == title]
    kept = [p for p in replay(store, "suggest-kurta.json").products if p.title == title]

    assert sorted(p["handle"] for p in same) == ["nq26-010", "nq26-028"]
    assert sorted(p.price for p in kept) == [39.5, 64.5]
    assert len({p.product_url for p in kept}) == 2


def test_colour_is_not_a_field_the_adapter_maps_it_stays_in_the_description(
    store: StoreConfig,
) -> None:
    raw = raw_products("suggest-kurta.json")

    assert all("Color:" in p["body"] for p in raw)  # written in the description, not a field
    assert {product.colour for product in all_products(store)} == {None}


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-dress.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


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
            make_item_intent(search_keywords=["dress", "kurta"]),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 20
    assert result.dropped == {}
    assert Counter(product.gender for product in result.products) == {
        Gender.WOMEN: 7,
        Gender.MEN: 10,
        None: 3,
    }
    assert [str(request.url) for request in seen] == [
        "https://www.nishatlinenuae.com/robots.txt",
        SEARCH_URL.format(query="dress"),
        SEARCH_URL.format(query="kurta"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
