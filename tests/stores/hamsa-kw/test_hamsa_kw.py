"""Hamsa store adapter, offline (plan 12.12).

The fixtures in ``fixtures/`` are real answers from 2026-10-08, recorded through the real
``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
Shopify ``/search/suggest.json`` response each for ``abaya`` and ``kaftan``. Shopify caps the answer
at 10 products and every product is kept; only each ``body`` (the HTML description) was cut to 300
characters to keep the files small. ``robots.txt`` is the store's file, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"95.000"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006). Its one real trap is the
price: on 5 of the 10 abaya records Shopify's ``price`` is the cheapest variant (a head scarf), not
the abaya. The store file sets ``max_price_spread: 1`` so those records are dropped rather than
shown at a price that is not the abaya's; the tests below pin both halves of that.
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

from vga.models import (
    Category,
    ExtractionConfig,
    Gender,
    Product,
    StoreConfig,
    StoreStatus,
    StrategyConfig,
    Tier,
)
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["abaya", "kaftan"]
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""

SEARCH_URL = (
    "https://hamsakw.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0107/8453/8705/"
"""Every image of the store is under this folder of the shared Shopify CDN."""

# The five abaya records whose variants cost different amounts. For each: the price Shopify gives
# as ``price`` (the lowest variant), the highest variant price, and the price of the variant the
# search matched, which is the abaya ("... / Abaya" in the variant title).
AMBIGUOUS_ABAYAS = {
    "Fire Works Abaya": ("20.000", "80.000", "80.000"),
    "Stardust Abaya": ("35.000", "95.000", "95.000"),
    "Collage Abaya": ("35.000", "130.000", "130.000"),
    "Shooting Star Abaya": ("95.000", "365.000", "365.000"),
    "Tonal Abaya/Scarf": ("20.000", "95.000", "75.000"),
}
KEPT_ABAYAS = {
    "Duma Abaya": 135.0,
    "Long Palm Tree Velvet Abaya": 148.0,
    "Star Dust Coat": 75.0,
    "Heyah Abaya": 185.0,
    "Duma Abaya Set": 212.0,
}


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(name: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def raw_by_title(name: str) -> dict[str, dict[str, Any]]:
    return {item["title"]: item for item in raw_products(name)}


def replay(store: StoreConfig, name: str) -> ChainOutcome:
    """The saved response ``name`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(name), store, build_search_url(store, "abaya")
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for name in FULL_FIXTURES for product in replay(store, name).products]


def without_price_option(store: StoreConfig) -> StoreConfig:
    """The same store with a plain ``shopify`` strategy: what the file would do without its
    ``max_price_spread`` line."""
    plain = ExtractionConfig(strategies=[StrategyConfig(name="shopify")])
    return store.model_copy(update={"extraction": plain})


# --------------------------------------------------------------------------------------------
# The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "hamsa-kw"
    assert store.display_name == "Hamsa"
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.PREMIUM
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://hamsakw.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black abaya") == SEARCH_URL.format(query="black%20abaya")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["hamsakw.com", "cdn.shopify.com"]


def test_the_store_file_keeps_the_price_guard_that_makes_the_prices_trustworthy(
    store: StoreConfig,
) -> None:
    """Remove this option and Hamsa shows scarf prices for abayas: the store must then be
    disabled, not left on (docs/store-notes/hamsa-kw.md)."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {"max_price_spread": 1}


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_abaya_and_kaftan_store(store: StoreConfig) -> None:
    # Every garment seen here is an abaya, a kaftan or a dress (docs/store-notes/hamsa-kw.md), so
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
    assert not robots.can_fetch("https://hamsakw.com/cart/", agent)  # parsed, not allow-all


# --------------------------------------------------------------------------------------------
# The fixtures through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_each_recording_holds_ten_products(store: StoreConfig, name: str) -> None:
    assert len(raw_products(name)) == PRODUCTS_IN_EACH_FIXTURE
    assert replay(store, name).examined == PRODUCTS_IN_EACH_FIXTURE


def test_the_kaftan_answer_survives_whole_and_the_abaya_answer_keeps_the_five_with_one_price(
    store: StoreConfig,
) -> None:
    kaftan = replay(store, "suggest-kaftan.json")
    abaya = replay(store, "suggest-abaya.json")

    assert len(kaftan.products) == 10
    assert kaftan.dropped == {}
    assert {p.title for p in abaya.products} == set(KEPT_ABAYAS)
    assert abaya.dropped == {"missing_price": 5}  # the price guard's drops, counted
    assert abaya.strategy == kaftan.strategy == "shopify"


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
        assert product.store == "Hamsa"


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_prices_keep_their_three_decimals_and_sit_in_the_garment_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products
    raw = raw_by_title(name)

    assert all(len(raw[product.title]["price"].split(".")[1]) == 3 for product in products)
    # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000 out,
    # and a scarf price slipping in would be under KWD 50.
    assert all(50 <= product.price <= 400 for product in products)


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    prices = {p.title: p.price for p in replay(store, "suggest-kaftan.json").products}

    assert raw_by_title("suggest-kaftan.json")["Riwaq Kaftan"]["price"] == "95.000"
    assert prices["Riwaq Kaftan"] == 95.0
    assert prices["Rania Kaftan"] == 320.0
    assert prices["Amber Kaftan"] == 55.0


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "hamsakw.com"
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


def test_the_two_recordings_give_fifteen_distinct_valid_products(store: StoreConfig) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 15  # 20 records, 5 dropped by the price guard
    assert len(distinct) == 15
    assert repeats == {}


# --------------------------------------------------------------------------------------------
# The price: what the guard prevents, and what it keeps
# --------------------------------------------------------------------------------------------


def test_five_abaya_records_have_variants_at_different_prices_and_price_is_the_lowest() -> None:
    """The trap, in the real data: ``price`` is ``price_min`` on every record, and on these five
    ``price_max`` is two to nearly five times higher."""
    ranged = {
        item["title"]: (item["price"], item["price_max"])
        for item in raw_products("suggest-abaya.json")
        if item["price_min"] != item["price_max"]
    }
    for item in raw_products("suggest-abaya.json"):
        assert item["price"] == item["price_min"]

    assert ranged == {title: (low, high) for title, (low, high, _) in AMBIGUOUS_ABAYAS.items()}


def test_the_matched_variant_is_the_abaya_but_the_highest_price_is_not_always_its_price() -> None:
    """Why the guard drops instead of correcting. The variant the search matched is an abaya on all
    five (variant 1, title ending "Abaya"), and its price equals the maximum on four. On "Tonal
    Abaya/Scarf" the abaya variant is KWD 75 and the maximum KWD 95, so taking the highest price
    would show a price that abaya does not have."""
    by_title = raw_by_title("suggest-abaya.json")

    for title, (_low, high, abaya_price) in AMBIGUOUS_ABAYAS.items():
        [variant] = by_title[title]["variants"]
        assert "Abaya" in variant["title"]
        assert variant["price"] == abaya_price
        if title == "Tonal Abaya/Scarf":
            assert (abaya_price, high) == ("75.000", "95.000")
        else:
            assert abaya_price == high


def test_without_the_guard_an_abaya_would_be_shown_at_its_scarfs_price(
    store: StoreConfig,
) -> None:
    unguarded = {
        p.title: p.price for p in replay(without_price_option(store), "suggest-abaya.json").products
    }

    assert len(unguarded) == 10
    for title, (low, _high, abaya_price) in AMBIGUOUS_ABAYAS.items():
        assert unguarded[title] == float(low)
        assert float(low) < float(abaya_price)  # the wrong, lower price: the failure mode


def test_with_the_guard_none_of_those_five_is_shown_at_all(store: StoreConfig) -> None:
    shown = {p.title for p in all_products(store)}

    assert shown.isdisjoint(AMBIGUOUS_ABAYAS)


def test_every_kept_record_has_a_single_price_that_is_the_garments(store: StoreConfig) -> None:
    for name in FULL_FIXTURES:
        raw = raw_by_title(name)
        for product in replay(store, name).products:
            item = raw[product.title]
            assert item["price_min"] == item["price_max"] == item["price"]
            assert product.price == float(item["price"])


def test_kept_abayas_show_the_store_price_not_the_struck_through_one(store: StoreConfig) -> None:
    prices = {p.title: p.price for p in replay(store, "suggest-abaya.json").products}
    raw = raw_by_title("suggest-abaya.json")

    assert prices == KEPT_ABAYAS
    assert raw["Star Dust Coat"]["compare_at_price_max"] == "365.000"
    assert prices["Star Dust Coat"] == 75.0  # an abaya coat at 75, not at its pre-sale 365


def test_a_pre_sale_price_equal_to_the_price_is_not_a_discount_and_is_not_used(
    store: StoreConfig,
) -> None:
    raw = raw_by_title("suggest-kaftan.json")
    prices = {p.title: p.price for p in replay(store, "suggest-kaftan.json").products}

    assert raw["Amber Kaftan"]["compare_at_price_max"] == raw["Amber Kaftan"]["price"] == "55.000"
    assert prices["Amber Kaftan"] == 55.0
    assert raw["Pistachio Lotfia Kaftan"]["compare_at_price_max"] == "295.000"
    assert prices["Pistachio Lotfia Kaftan"] == 160.0


# --------------------------------------------------------------------------------------------
# Other quirks of this store's data (docs/store-notes/hamsa-kw.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_handles_do_not_match_titles_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: "Amber Kaftan" lives at ``short-seline-kaftan-copy-1`` and "Short Seline Kaftan" at
    ``long-seline-kaftan-copy``. Rebuilding a link from the title would send the shopper to the
    wrong product."""
    link = {p.title: p.product_url for p in replay(store, "suggest-kaftan.json").products}

    assert link["Amber Kaftan"] == "https://hamsakw.com/products/short-seline-kaftan-copy-1"
    assert link["Short Seline Kaftan"] == "https://hamsakw.com/products/long-seline-kaftan-copy"
    assert link["Ameera Kaftan"] == (
        "https://hamsakw.com/products/gazar-kaftan-with-silver-embroidery"
    )


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-kaftan.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_the_vendor_has_two_spellings_and_the_shoppers_store_name_is_one(
    store: StoreConfig,
) -> None:
    """Quirk: one brand, two ``vendor`` values. The adapter does not read ``vendor``; every product
    carries the store file's display name."""
    vendors = {item["vendor"] for name in FULL_FIXTURES for item in raw_products(name)}

    assert vendors == {"Hamsakw", "Hamsa by Sharifa AlGhanim"}
    assert {product.store for product in all_products(store)} == {"Hamsa"}


def test_the_type_is_inconsistent_so_it_cannot_name_a_category(store: StoreConfig) -> None:
    types = {item["type"] for name in FULL_FIXTURES for item in raw_products(name)}

    assert types == {"ABAYA", "KAFTAN", "DRESS", "casual dresses"}


def test_old_collections_are_still_listed_as_in_stock(store: StoreConfig) -> None:
    """Quirk: product codes S-20-xxx (2020) and W-22-xxx (2022) are searchable and ``available``
    next to W-26-xxx. The adapter reports the store's own stock flag and nothing more."""
    in_stock = {p.title: p.in_stock for p in replay(store, "suggest-abaya.json").products}
    bodies = {item["title"]: item["body"] for item in raw_products("suggest-abaya.json")}

    assert "S-20-002" in bodies["Star Dust Coat"]
    assert "W-22-029" in bodies["Duma Abaya"]
    assert in_stock["Star Dust Coat"] is True
    assert in_stock["Duma Abaya"] is True


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field: every product's gender is
    unknown, and ``genders: [women]`` in the store file does the work."""
    assert {product.gender for product in all_products(store)} == {None}


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
    # Both saved answers are read: a store is sent its second keyword variant only when the first
    # gave fewer than second_variant_below products, and each saved answer has ten.
    settings = make_settings(extra_store_countries=["KW"], second_variant_below=50)
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
    assert len(result.products) == 15
    assert result.dropped == {"missing_price": 5}  # the five scarf-priced abayas, never shown
    assert {product.currency for product in result.products} == {"KWD"}
    assert [str(request.url) for request in seen] == [
        "https://hamsakw.com/robots.txt",
        SEARCH_URL.format(query="abaya"),
        SEARCH_URL.format(query="kaftan"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
