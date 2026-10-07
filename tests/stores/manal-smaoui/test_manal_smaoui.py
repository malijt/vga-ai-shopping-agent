"""Manal Smaoui store adapter, offline (plan 12.13).

The fixtures in ``fixtures/`` are real answers from 2026-10-08, recorded through the real
``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
Shopify ``/search/suggest.json`` response each for ``dress`` and ``kaftan``. Shopify caps the answer
at 10 products and every product is kept; only each ``body`` (the HTML description) was cut to 300
characters to keep the files small. ``robots.txt`` is the store's file, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"85.000"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006). It sells dresses, kaftans, a
blazer, trousers, skirts and a top, and its ``type`` is a collection label, so its store file sets
no ``categories`` and the ranker sorts the products by title.
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
from vga.rank.category import OUT_OF_SCOPE, classify_title
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["dress", "kaftan"]
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
DISTINCT_PRODUCTS_IN_BOTH_FIXTURES = 13
"""20 records; seven products answered both queries. The catalogue is small."""

SEARCH_URL = (
    "https://manalsmaoui.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0682/5885/7253/"
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
    return [product for name in FULL_FIXTURES for product in replay(store, name).products]


def by_title(store: StoreConfig) -> dict[str, Product]:
    return {product.title: product for product in all_products(store)}


# --------------------------------------------------------------------------------------------
# The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "manal-smaoui"
    assert store.display_name == "Manal Smaoui"
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.MID_RANGE
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://manalsmaoui.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black blazer") == SEARCH_URL.format(query="black%20blazer")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["manalsmaoui.com", "cdn.shopify.com"]


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_a_search_for_any_of_the_five_categories_is_sent_to_this_mixed_store(
    store: StoreConfig,
) -> None:
    """The store sells dresses and kaftans, a blazer, trousers, skirts and a top, so no category is
    ruled out (docs/store-notes/manal-smaoui.md). ``categories`` is left unset on purpose."""
    assert store.categories is None
    for category in Category:
        assert store.sells_category(category)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://manalsmaoui.com/cart/", agent)  # parsed, not allow-all


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
        assert product.store == "Manal Smaoui"


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_prices_keep_their_three_decimals_and_sit_in_the_garment_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products
    raw = {item["title"]: item["price"] for item in raw_products(name)}

    assert all(len(raw[product.title].split(".")[1]) == 3 for product in products)
    # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000 out.
    assert all(5 <= product.price <= 100 for product in products)


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    products = by_title(store)

    assert raw_products("suggest-kaftan.json")[0]["price"] == "85.000"
    assert products["AICHA KAFTAN - BROWN"].price == 85.0
    assert products["THE BELLE DRESS - BLACK (LIMITED EDITION)"].price == 55.0
    assert products["THE MUSE PANTS - BLACK"].price == 29.0
    assert products["HEADBANDS"].price == 5.0


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "manalsmaoui.com"
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


def test_the_two_recordings_give_thirteen_distinct_valid_products(store: StoreConfig) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 2 * PRODUCTS_IN_EACH_FIXTURE
    assert len(distinct) == DISTINCT_PRODUCTS_IN_BOTH_FIXTURES
    assert repeats == {"duplicate_url": 7}


# --------------------------------------------------------------------------------------------
# Quirks of this store's data (docs/store-notes/manal-smaoui.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_every_record_has_a_single_price_so_the_default_price_is_the_garments() -> None:
    """Unlike Hamsa, no record here has variants at different prices (the ``variants`` list is
    empty on all 20), so reading ``price`` cannot pick up an add-on."""
    for name in FULL_FIXTURES:
        for item in raw_products(name):
            assert item["price_min"] == item["price_max"] == item["price"]
            assert item["variants"] == []


def test_nothing_is_discounted_today_so_there_is_no_struck_through_price() -> None:
    for name in FULL_FIXTURES:
        assert {item["compare_at_price_max"] for item in raw_products(name)} == {"0.000"}


def test_the_type_is_a_collection_label_so_it_says_nothing_about_the_garment() -> None:
    """Quirk: ``type`` names a collection ("BLACK SETS"), and a headband carries "KAFTANS". It
    cannot give a category, which is why the store file lists none."""
    types = {item["type"] for name in FULL_FIXTURES for item in raw_products(name)}
    by_name = {item["title"]: item["type"] for item in raw_products("suggest-dress.json")}

    assert types == {"EID COLLECTION", "BLACK SETS", "BABY PINK SETS", "WHITE SETS", "KAFTANS"}
    assert by_name["THE MUSE PANTS - BLACK"] == by_name["THE MUSE TOP - BLACK"] == "BLACK SETS"
    assert by_name["HEADBANDS"] == "KAFTANS"


def test_the_ranker_reads_each_products_category_from_its_title(store: StoreConfig) -> None:
    """The title is where the garment is named, and the ranker (not the adapter) reads it. This pins
    that it sorts the whole range this store returns: dresses and kaftans, a blazer, trousers,
    skirts and a top, and drops the headband as an accessory."""
    kinds = {title: classify_title(title) for title in by_title(store)}

    assert {k for t, k in kinds.items() if "DRESS" in t.upper() or "KAFTAN" in t.upper()} == {
        Category.DRESSES
    }
    assert kinds["THE MUSE PANTS - BLACK"] is Category.BOTTOMS
    assert kinds["THE MUSE SKIRT - WHITE"] is Category.BOTTOMS
    assert kinds["THE MUSE TOP - BLACK"] is Category.TOPS
    assert kinds["The Ladylike Blazer - White"] is Category.OUTERWEAR
    assert kinds["HEADBANDS"] == OUT_OF_SCOPE


def test_a_headband_is_an_accessory_and_the_adapter_still_hands_it_over(
    store: StoreConfig,
) -> None:
    """Quirk: both answers hold the KWD 5 headband. The adapter makes no store-specific exclusion:
    dropping accessories is the ranker's job, for every store (see the test above)."""
    for name in FULL_FIXTURES:
        assert "HEADBANDS" in {p.title for p in replay(store, name).products}


def test_handles_do_not_always_match_titles_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: "THE MUSE SKIRT - BABY PINK" lives at ``the-muse-skirt-striped-grey`` and "THE MUSE
    PANTS - BABY PINK" at ``the-f-w-pants-only-baby-pink``. Rebuilding a link from the title would
    send the shopper to the wrong product."""
    link = {title: product.product_url for title, product in by_title(store).items()}

    assert link["THE MUSE SKIRT - BABY PINK"] == (
        "https://manalsmaoui.com/products/the-muse-skirt-striped-grey"
    )
    assert link["THE MUSE PANTS - BABY PINK"] == (
        "https://manalsmaoui.com/products/the-f-w-pants-only-baby-pink"
    )
    assert link["AICHA KAFTAN - BABY BLUE"] == (
        "https://manalsmaoui.com/products/aicha-kaftan-royal-blue"
    )


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-kaftan.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_titles_mix_upper_and_mixed_case_and_the_colour_follows_a_dash(
    store: StoreConfig,
) -> None:
    titles = set(by_title(store))

    assert "AICHA KAFTAN - BROWN" in titles  # upper case, colour after the dash
    assert "The Ladylike Blazer - White" in titles  # mixed case


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field: every product's gender is
    unknown, and ``genders: [women]`` in the store file does the work."""
    assert {product.gender for product in all_products(store)} == {None}


def test_the_same_pieces_answer_both_queries_and_repeats_collapse(store: StoreConfig) -> None:
    dress = replay(store, "suggest-dress.json").products
    kaftan = replay(store, "suggest-kaftan.json").products

    distinct, repeats = dedupe_products([*dress, *kaftan])

    assert len(distinct) == DISTINCT_PRODUCTS_IN_BOTH_FIXTURES
    assert repeats == {"duplicate_url": 7}


def test_a_dress_search_is_padded_and_a_kaftan_search_holds_only_three_kaftans(
    store: StoreConfig,
) -> None:
    """Quirk: the store pads its answers (qualification report): 2 of 10 for ``dress`` are dresses
    and 3 of 10 for ``kaftan`` are kaftans; the rest are trousers, skirts, a top, a blazer and the
    headband. The ranker filters by category, not the adapter."""
    for name, word, count in (
        ("suggest-dress.json", "DRESS", 2),
        ("suggest-kaftan.json", "KAFTAN", 3),
    ):
        titles = [p.title for p in replay(store, name).products]
        assert len([t for t in titles if word in t.upper()]) == count


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
            make_item_intent(search_keywords=["dress", "kaftan"]),
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
        "https://manalsmaoui.com/robots.txt",
        SEARCH_URL.format(query="dress"),
        SEARCH_URL.format(query="kaftan"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
