"""Veil Essentials store adapter, offline (plan 12.17).

The fixtures in ``fixtures/`` are real answers from 2026-10-08: ``suggest-jilbab.json``,
``suggest-abaya.json`` and ``suggest-khimar.json`` are one full Shopify ``/search/suggest.json``
response each (10 products each, the most Shopify gives; only each product's ``body``, the HTML
description, was cut to 300 characters to keep the files small), and ``robots.txt`` is the store's
file, byte for byte. They were saved by the qualification run
(``scripts/qualify_store.py``, honest User-Agent, robots.txt first, one request per second).

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"12.500"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006). Unlike Hamsa, every record has
one price, so the store file sets no price option. The ranker's word lists do not name a khimar (a
head covering), so those titles get no category; the tests below pin that as today's behaviour.
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
    Gender,
    GenderSource,
    Product,
    StoreConfig,
    StoreStatus,
    Tier,
)
from vga.money import to_base
from vga.rank.category import classify_title
from vga.rank.filters import apply_hard_filters
from vga.settings import load_settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "veilessentialskw.com"
DISPLAY_NAME = "Veil Essentials"
QUERIES = ["jilbab", "abaya", "khimar"]
"""One saved answer per query: ``fixtures/suggest-<query>.json``."""
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 30
"""30 records and no product repeated: the three queries share nothing."""

SEARCH_URL = (
    f"https://{HOST}/search/suggest.json?q={{query}}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0800/1889/9238/files/"
"""Every image of the store is under this folder of the shared Shopify CDN."""

SALE_ABAYAS = {
    "Abaya jawhara": ("12.900", "16.900"),
    "Abaya hala": ("11.900", "15.900"),
    "Ombre": ("15.000", "21.000"),
    "Abaya Sitr": ("11.900", "15.900"),
    "Abaya zahra": ("11.900", "15.900"),
}
"""The five records whose struck-through price is above the price: title, (price, pre-sale)."""
KHIMAR_SETS = {
    "Hafsa khimar set": 16.0,
    "KHIMAR COMBO SET - 4 PC": 33.5,
    "Customize Your Khimar Set": 16.0,
    "Butterfly khimar set": 14.6,
}
"""The four khimar records that are sets with an abaya, by title, with their KWD price."""


def fixture_name(query: str) -> str:
    """The saved answer for ``query``: a space in the query is a hyphen in the file name."""
    return f"suggest-{query.replace(' ', '-')}.json"


FULL_FIXTURES = [fixture_name(query) for query in QUERIES]


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(name: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def every_raw_record() -> list[dict[str, Any]]:
    return [item for name in FULL_FIXTURES for item in raw_products(name)]


def raw_by_title() -> dict[str, dict[str, Any]]:
    return {item["title"]: item for item in every_raw_record()}


def replay(store: StoreConfig, name: str) -> ChainOutcome:
    """The saved response ``name`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(name), store, build_search_url(store, "abaya")
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
    assert store.id == "veil-essentials-kw"
    assert store.display_name == DISPLAY_NAME
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.BUDGET
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        f"https://{HOST}/search/suggest.json?q={{query}}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black abaya") == SEARCH_URL.format(query="black%20abaya")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_the_store_file_sets_no_extractor_option_because_every_record_has_one_price(
    store: StoreConfig,
) -> None:
    """No ``max_price_spread`` (Hamsa's price guard) and no other option: the defaults suit this
    store. The test after the next section shows why the guard is not needed."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {}


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_jilbab_abaya_and_khimar_store(
    store: StoreConfig,
) -> None:
    # Every garment seen here is a jilbab, an abaya, a khimar or a khimar-and-abaya set
    # (docs/store-notes/veil-essentials-kw.md), so a search for shoes, jeans, tops or jackets would
    # only waste a request to it.
    assert store.categories == frozenset({Category.DRESSES})
    assert store.sells_category(Category.DRESSES)
    for other in (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart() -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(SEARCH_URL.format(query=query), agent)
    assert not robots.can_fetch(f"https://{HOST}/cart/", agent)  # parsed, not allow-all


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
        assert product.store == DISPLAY_NAME


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_prices_keep_their_three_decimals_and_sit_in_the_garment_range(
    store: StoreConfig, name: str
) -> None:
    products = replay(store, name).products
    raw = {item["title"]: item for item in raw_products(name)}

    assert all(len(raw[product.title]["price"].split(".")[1]) == 3 for product in products)
    # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000 out:
    # KWD 12,500 or KWD 0.0125. Everything seen costs between KWD 7.55 and KWD 33.5.
    assert all(7 <= product.price <= 35 for product in products)


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    prices = {title: product.price for title, product in by_title(store).items()}
    raw = raw_by_title()

    assert raw["Ayesha Jilbab"]["price"] == "12.500"
    assert prices["Ayesha Jilbab"] == 12.5
    assert raw["2 layer khimar Azra"]["price"] == "7.550"
    assert prices["2 layer khimar Azra"] == 7.55
    assert raw["Ahli Jilbab"]["price"] == "13.750"
    assert prices["Ahli Jilbab"] == 13.75
    assert prices["KHIMAR COMBO SET - 4 PC"] == 33.5


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    for product in replay(store, name).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == HOST
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


def test_the_three_recordings_give_thirty_distinct_valid_products(store: StoreConfig) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 30
    assert len(distinct) == DISTINCT_PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) >= 20  # plan 12.x.2
    assert repeats == {}


# --------------------------------------------------------------------------------------------
# The price: why the store file needs no guard, and what the shopper pays
# --------------------------------------------------------------------------------------------


def test_every_record_has_a_single_price_so_the_default_price_is_the_garments() -> None:
    """Unlike Hamsa, no record here has variants at different prices (``price``, ``price_min`` and
    ``price_max`` are equal and the ``variants`` list is empty on all 30), so reading ``price``
    cannot pick up a cheaper add-on. If the store ever changes this, the file needs
    ``max_price_spread`` (ADR 0012)."""
    records = every_raw_record()

    assert len(records) == 30
    for item in records:
        assert item["price_min"] == item["price_max"] == item["price"]
        assert item["variants"] == []


def test_five_abayas_carry_a_struck_through_price_and_the_adapter_shows_the_price(
    store: StoreConfig,
) -> None:
    raw = raw_by_title()
    prices = {title: product.price for title, product in by_title(store).items()}

    on_sale = {
        title: (item["price"], item["compare_at_price_max"])
        for title, item in raw.items()
        if item["compare_at_price_max"] != "0.000"
    }
    assert on_sale == SALE_ABAYAS
    assert prices["Abaya hala"] == 11.9  # not the pre-sale 15.9
    assert prices["Ombre"] == 15.0  # not the pre-sale 21


def test_every_record_is_listed_as_in_stock(store: StoreConfig) -> None:
    """Stock is product-level only: ``available`` is true on all 30 and the adapter reports it."""
    assert all(item["available"] is True for item in every_raw_record())
    assert {product.in_stock for product in all_products(store)} == {True}


def test_at_the_shipped_rate_every_jilbab_and_abaya_costs_under_600_dirhams() -> None:
    """Why the tier hint is ``budget``: the first abayas seen that sit under about AED 600. The
    figure the shopper compares is the dirham one, worked out from the fixed rate in
    ``config/settings.yaml`` (ADR 0006)."""
    settings = load_settings(env={})
    rate = settings.fx_rates["KWD"]
    garments = [
        item
        for name in ("suggest-jilbab.json", "suggest-abaya.json")
        for item in raw_products(name)
    ]
    dirhams = [to_base(float(item["price"]), "KWD", settings) for item in garments]
    abayas = [
        to_base(float(item["price"]), "KWD", settings)
        for item in raw_products("suggest-abaya.json")
    ]

    assert len(garments) == 20
    assert all(value is not None and 100 < value < 600 for value in dirhams)
    assert min(v for v in abayas if v is not None) == pytest.approx(11.9 * rate, abs=0.01)
    assert max(v for v in abayas if v is not None) == pytest.approx(26.0 * rate, abs=0.01)


def test_a_khimar_set_costs_more_than_a_single_khimar(store: StoreConfig) -> None:
    """Quirk: the ``khimar`` answer mixes single khimars (head coverings, KWD 7.55 to 11.6) with
    sets that include an abaya (KWD 14.6 to 33.5, by the store's own description). The adapter keeps
    both; a shopper reads the title."""
    prices = {title: product.price for title, product in by_title(store).items()}
    khimar_titles = {item["title"] for item in raw_products("suggest-khimar.json")}
    singles = {title: prices[title] for title in khimar_titles - set(KHIMAR_SETS)}

    assert {title: prices[title] for title in KHIMAR_SETS} == KHIMAR_SETS
    assert len(singles) == 6
    assert (min(singles.values()), max(singles.values())) == (7.55, 11.6)
    assert min(KHIMAR_SETS.values()) > max(singles.values())


# --------------------------------------------------------------------------------------------
# Other quirks of this store's data (docs/store-notes/veil-essentials-kw.md), pinned by the real
# responses
# --------------------------------------------------------------------------------------------


def test_each_search_word_finds_what_it_names_and_the_store_does_not_pad_the_answer() -> None:
    """Unlike a store that pads a search with unrelated items, all 10 ``jilbab`` titles and all 10
    ``khimar`` titles hold the word asked for, and so do 9 of the 10 ``abaya`` titles (the tenth,
    "Ombre", is an abaya whose title names no garment)."""
    for query, expected in (("jilbab", 10), ("abaya", 9), ("khimar", 10)):
        titles = [item["title"].lower() for item in raw_products(fixture_name(query))]
        assert sum(query in title for title in titles) == expected


def test_handles_do_not_always_match_titles_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: "Fathema Jilbab" lives at ``/products/jilbab``, "jilbab Luma" at ``batwing-jilbab``
    and "KHIMAR COMBO SET - 4 PC" at ``untitled-9may_13-10``. Rebuilding a link from the title would
    send the shopper to the wrong page."""
    link = {title: product.product_url for title, product in by_title(store).items()}

    assert link["Fathema Jilbab"] == f"https://{HOST}/products/jilbab"
    assert link["jilbab Luma"] == f"https://{HOST}/products/batwing-jilbab"
    assert link["KHIMAR COMBO SET - 4 PC"] == f"https://{HOST}/products/untitled-9may_13-10"
    assert link["Hafsa khimar set"] == (
        f"https://{HOST}/products/2-layer-butterfly-khimar-abaya-set"
    )


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    assert all("_pos=" in item["url"] for item in every_raw_record())  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_the_vendor_has_two_spellings_and_the_shoppers_store_name_is_one(
    store: StoreConfig,
) -> None:
    """Quirk: one shop, two ``vendor`` values: "Veilessentialskw" on 23 of 30 records and
    "Veilessentials" on 7 (the same 7 that carry ``type`` "jilbab"). The adapter does not read
    ``vendor``; every product carries the store file's display name."""
    vendors = [item["vendor"] for item in every_raw_record()]

    assert (vendors.count("Veilessentialskw"), vendors.count("Veilessentials")) == (23, 7)
    assert {product.store for product in all_products(store)} == {DISPLAY_NAME}


def test_the_type_is_empty_on_most_records_so_it_cannot_name_a_category() -> None:
    """Quirk: ``type`` is "jilbab" on 7 of the 10 jilbab records and empty on the other 23 (all
    abayas and khimars). The ranker has to read the title."""
    types = [item["type"] for item in every_raw_record()]

    assert {item["type"] for item in raw_products("suggest-abaya.json")} == {""}
    assert {item["type"] for item in raw_products("suggest-khimar.json")} == {""}
    assert (types.count("jilbab"), types.count("")) == (7, 23)


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field: ``tags`` is empty on 29 of 30
    records (the other holds "J1", a code), so every product's gender is unknown and
    ``genders: [women]`` in the store file does the work."""
    tags = [tag for item in every_raw_record() for tag in item["tags"]]

    assert tags == ["J1"]
    assert {product.gender for product in all_products(store)} == {None}


# --------------------------------------------------------------------------------------------
# What the ranker makes of these titles (src/vga/rank/lexicon.py, not changed by this adapter)
# --------------------------------------------------------------------------------------------


def test_the_ranker_reads_every_jilbab_and_abaya_title_as_a_dress(store: StoreConfig) -> None:
    """The ``categories: [dresses]`` line rests on this: jilbab and abaya are dress-category words.
    One abaya, "Ombre", has a title with no garment word and gets no category."""
    kinds = {title: classify_title(title) for title in by_title(store)}
    jilbab_and_abaya_titles = [
        item["title"]
        for name in ("suggest-jilbab.json", "suggest-abaya.json")
        for item in raw_products(name)
    ]

    assert len(jilbab_and_abaya_titles) == 20
    unnamed = [title for title in jilbab_and_abaya_titles if kinds[title] is None]
    assert unnamed == ["Ombre"]
    assert all(kinds[t] is Category.DRESSES for t in jilbab_and_abaya_titles if t != "Ombre")


def test_a_khimar_title_gets_no_category_so_it_is_kept_for_a_dress_search(
    store: StoreConfig,
) -> None:
    """Today's behaviour, 2026-10-08: ``khimar`` is in none of the ranker's word lists (the
    project owner has yet to decide whether a khimar is a garment or a head covering; see the
    comment at ``CATEGORY_WORDS`` in ``src/vga/rank/lexicon.py``). Every khimar title, single or
    set, therefore has no inferred category: the hard filters keep it and give it no category
    bonus. If khimars are added to a list later, this test is the one to change."""
    item = make_item_intent(
        category=Category.DRESSES,
        colour=None,
        style=None,
        search_keywords=["abaya"],
        gender=Gender.WOMEN,
        gender_source=GenderSource.EXPLICIT,
    )
    khimar_products = replay(store, "suggest-khimar.json").products

    assert len(khimar_products) == 10
    for product in khimar_products:
        assert classify_title(product.title) is None
        result = apply_hard_filters(item, product)
        assert result.keep
        assert result.category is None


def test_a_dress_search_for_a_woman_keeps_all_thirty_products(store: StoreConfig) -> None:
    """Nothing is dropped as a child's or a man's item, an out-of-scope garment or another category.
    19 products come out as dresses (10 jilbabs and 9 abayas); 11 have no category (the 10 khimars
    and the abaya titled "Ombre")."""
    item = make_item_intent(
        category=Category.DRESSES,
        colour=None,
        style=None,
        search_keywords=["abaya"],
        gender=Gender.WOMEN,
        gender_source=GenderSource.EXPLICIT,
    )

    results = [apply_hard_filters(item, product) for product in all_products(store)]

    assert all(result.keep for result in results)
    assert sum(result.category is Category.DRESSES for result in results) == 19
    assert sum(result.category is None for result in results) == 11


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
    store: StoreConfig,
) -> None:
    sent = ["abaya", "jilbab"]  # a store is sent at most two keyword variants, never a third
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
            content=fixture_text(fixture_name(query)).encode(),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    # A Kuwaiti store is searched only when Kuwait is among the extra countries (settings.yaml).
    # Both saved answers are read: a store is sent its second keyword variant only when the first
    # gave fewer than second_variant_below products, and each saved answer has ten.
    settings = make_settings(extra_store_countries=["KW"], second_variant_below=50)
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(category=Category.DRESSES, search_keywords=sent),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 20  # the two answers share no product
    assert result.dropped == {}
    assert {product.currency for product in result.products} == {"KWD"}
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[SEARCH_URL.format(query=query) for query in sent],
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
