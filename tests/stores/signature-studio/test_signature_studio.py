"""Signature Studio store adapter, offline (plan 12.x.1 and 12.x.2).

The fixtures in ``fixtures/`` are real answers from 2026-10-08:

- ``suggest-dress.json`` and ``suggest-kaftan.json`` were recorded through the real
  ``StoreSearchEngine`` (honest User-Agent, robots.txt checked, one request per second): one full
  Shopify ``/search/suggest.json`` response each. Shopify caps the answer at 10 products and every
  product is kept; only each ``body`` (the HTML description) was cut to 300 characters to keep the
  files small. Nothing else was changed.
- ``qualification-suggest-kurta.json`` and ``qualification-suggest-abaya.json`` are byte copies of
  the first 4 of 10 products of the qualification pass's ``kurta`` and ``abaya`` answers
  (``docs/store-qualification/samples/signature-studio/``), same cut ``body``. The kurta sample is
  the store's men's kurta sets (tag ``Menswear``); the abaya sample shows that the store has no
  abayas and answers with designer pieces whose names resemble the word.
- ``robots.txt``: the store's robots.txt, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and
the fixtures through the real extraction chain, validation and search engine.
"""

import json
from collections import Counter
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
QUERIES = ["dress", "kaftan"]
"""The two full recordings."""
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
SHORT_FIXTURES = ["qualification-suggest-kurta.json", "qualification-suggest-abaya.json"]
ALL_FIXTURES = [*FULL_FIXTURES, *SHORT_FIXTURES]
MENS_FIXTURE = "qualification-suggest-kurta.json"

PRODUCTS_IN_EACH_FULL_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
PRODUCTS_IN_EACH_SHORT_FIXTURE = 4
PRODUCTS_IN_ALL_FIXTURES = 28
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 28

SEARCH_URL = (
    "https://www.signaturestudio.ae/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0549/4394/"
"""Every image of the store is under this folder of the shared Shopify CDN."""
NO_BREAK_SPACE = chr(0xA0)


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


def all_raw_products() -> list[dict[str, Any]]:
    return [raw for name in ALL_FIXTURES for raw in raw_products(name)]


# --------------------------------------------------------------------------------------------
# 12.x.1 The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "signature-studio"
    assert store.display_name == "Signature Studio"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.tier_hint is Tier.MID_RANGE
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://www.signaturestudio.ae/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "kaftan set") == SEARCH_URL.format(query="kaftan%20set")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == ["www.signaturestudio.ae", "cdn.shopify.com"]


def test_the_store_is_searched_for_either_gender_because_it_sells_both(
    store: StoreConfig,
) -> None:
    assert store.genders is None
    assert store.sells_for_gender(Gender.MEN)
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)


def test_only_a_dresses_search_is_sent_to_this_dress_store(store: StoreConfig) -> None:
    # Every product seen here is a kaftan, dress, formal or co-ord set, or a men's kurta-trouser
    # set (docs/store-notes/signature-studio.md), so a search for shoes, jeans, tops or jackets
    # would only waste a request to it.
    assert store.categories == frozenset({Category.DRESSES})
    assert store.sells_category(Category.DRESSES)
    for other in (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch("https://www.signaturestudio.ae/cart/", agent)  # not allow-all


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
        assert product.store == "Signature Studio"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_prices_are_positive_aed_amounts_in_a_plausible_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products

    assert all(product.currency == "AED" for product in products)
    assert all(150 <= product.price <= 3000 for product in products)  # a unit slip would be far out


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "www.signaturestudio.ae"
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
# Quirks of this store's data (docs/store-notes/signature-studio.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_type_and_the_main_tag_are_the_same_on_every_record_so_neither_says_what_it_is() -> None:
    """Quirk: ``type`` is "Clothing" and the tag "Buy Dresses" is present on every record, so a
    kaftan, a wedding set and a men's kurta set look alike in the structured fields."""
    records = all_raw_products()

    assert {raw["type"] for raw in records} == {"Clothing"}
    assert all("Buy Dresses" in raw["tags"] for raw in records)


def test_the_mens_kurta_sets_are_read_as_mens_from_the_menswear_tag(store: StoreConfig) -> None:
    """Quirk: ``type`` names no gender, and the only sign that a kurta set is for men is the tag
    ``Menswear``. The extractor reads that word (it did not before 2026-10-08), so a woman's search
    does not show these sets as unknown. Without it all four would be ``None``."""
    raw = raw_products(MENS_FIXTURE)
    products = replay(store, MENS_FIXTURE).products

    assert all("Menswear" in p["tags"] for p in raw)
    assert [product.gender for product in products] == [Gender.MEN] * 4


def test_womens_items_carry_no_gender_tag_so_they_stay_unknown(store: StoreConfig) -> None:
    """The other 24 records in the fixtures are women's wear, and none of them says so: the ranker
    reads their titles. Nothing is labelled men's except the four Menswear sets."""
    labelled = Counter(product.gender for product in all_products(store))

    assert labelled == {Gender.MEN: 4, None: 24}


def test_a_title_that_ends_with_a_no_break_space_is_trimmed_and_double_spaces_collapse(
    store: StoreConfig,
) -> None:
    raw_titles = [raw["title"] for raw in raw_products("suggest-dress.json")]
    assert f"MANTO - Deedar Dress Kaftaan Beige{NO_BREAK_SPACE}" in raw_titles  # as written
    assert "ALEENA FAREENA - Midnight  mirage" in raw_titles
    assert "MANTO  - Mehru Dress Saree Beige" in raw_titles

    titles = [p.title for p in replay(store, "suggest-dress.json").products]

    assert "MANTO - Deedar Dress Kaftaan Beige" in titles
    assert "ALEENA FAREENA - Midnight mirage" in titles
    assert "MANTO - Mehru Dress Saree Beige" in titles
    assert all(title == title.strip() and "  " not in title for title in titles)


def test_every_title_starts_with_the_designer_label_and_the_adapter_keeps_it(
    store: StoreConfig,
) -> None:
    """Quirk: the store is multi-brand and repeats the label in the title ("HAFSA MALIK - Noor
    Jahan"), with varying capitals. The adapter passes the whole title on; showing the label
    separately is a display choice for later."""
    by_url = {p.product_url.rsplit("/", 1)[-1]: p for p in all_products(store)}

    for raw in all_raw_products():
        assert raw["title"].casefold().startswith(raw["vendor"].casefold())
        assert raw["vendor"].casefold() in by_url[raw["handle"]].title.casefold()


def test_prices_may_have_fractions_and_are_read_exactly(store: StoreConfig) -> None:
    [saree] = [
        p for p in replay(store, "suggest-dress.json").products if "Mehru Dress Saree" in p.title
    ]

    assert saree.price == 554.4


def test_the_price_is_what_the_shopper_pays_when_a_pre_sale_price_exists(
    store: StoreConfig,
) -> None:
    """Only 2 of the 20 recorded records carry a pre-sale price: Noor Jahan (AED 2,625 before) and
    Pink Printed (AED 474 before). The adapter uses ``price``."""
    raw = {p["title"]: p for p in raw_products("suggest-dress.json")}
    products = {p.title: p for p in replay(store, "suggest-dress.json").products}

    assert raw["HAFSA MALIK - Noor Jahan"]["compare_at_price_max"] == "2625.00"
    assert products["HAFSA MALIK - Noor Jahan"].price == 1838.0
    assert raw["MARIA RAO - Pink Printed"]["compare_at_price_max"] == "474.00"
    assert products["MARIA RAO - Pink Printed"].price == 403.0
    discounted = [
        p
        for name in FULL_FIXTURES
        for p in raw_products(name)
        if p["compare_at_price_max"] != "0.00"
    ]
    assert len(discounted) == 2


def test_the_abaya_word_finds_no_abayas_only_designer_pieces_with_similar_names(
    store: StoreConfig,
) -> None:
    """Quirk: a fuzzy search. "abaya" returns pret and formal pieces named Aysal, Maya, Amaya,
    Fusan; none is an abaya, and the title says so by not containing the word."""
    titles = [p.title for p in replay(store, "qualification-suggest-abaya.json").products]

    assert len(titles) == 4
    assert not any("abaya" in title.casefold() for title in titles)


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = raw_products("suggest-dress.json")
    assert all("_pos=" in p["url"] for p in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_images_may_be_jpg_or_webp_and_both_are_accepted(store: StoreConfig) -> None:
    extensions = {
        urlsplit(product.image_url).path.rsplit(".", 1)[-1] for product in all_products(store)
    }

    assert {"jpg", "webp"} <= extensions


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
            make_item_intent(search_keywords=["dress", "kaftan"]),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 20
    assert result.dropped == {}
    assert [str(request.url) for request in seen] == [
        "https://www.signaturestudio.ae/robots.txt",
        SEARCH_URL.format(query="dress"),
        SEARCH_URL.format(query="kaftan"),
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
