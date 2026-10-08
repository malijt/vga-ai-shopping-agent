"""Al Jazeera Clothing store adapter, offline (plan 12.18).

The fixtures in ``fixtures/`` are real answers from 2026-10-08, recorded by the qualification
script (honest User-Agent, robots.txt first, one request per second):

- ``suggest-dishdasha.json``, ``suggest-thobe.json``, ``suggest-winter.json`` and
  ``suggest-men.json`` are one full Shopify predictive-search response each, from the store's
  English address ``/en/search/suggest.json``. Shopify caps an answer at 10 products and every
  product is kept; only each ``body`` (the HTML description) was cut to 300 characters.
- ``suggest-417-unsupported-locale.json`` is the 86-byte answer the store gave, three times, to the
  plain ``/search/suggest.json`` (HTTP 417, "Unsupported buyer locale"). It is why the store file's
  address has ``/en/`` in it.
- ``robots.txt`` is the store's file, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

The store is a Kuwaiti label of traditional menswear whose default language is Arabic. It prices in
Kuwaiti dinars with three decimals (``"9.000"``); the response has no currency, so ``currency: KWD``
comes from the store file (ADR 0006). The search found 30 distinct records: 12 men's (3 dishdashas,
9 underwear, nightwear and multipacks) and 18 children's dishdashas. The store file sets
``max_price_spread: 1``, which drops the 9 records whose variants differ in price, and the tests
below pin both halves of that.
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
from vga.money import to_base
from vga.settings import load_settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
STORE_ID = "al-jazeera-clothing"
DISPLAY_NAME = "Al Jazeera Clothing"
HOST = "aljazeera-clothing.com"
CURRENCY = "KWD"
QUERIES = ["dishdasha", "thobe", "winter", "men"]
"""One saved answer per query: ``fixtures/suggest-<query>.json``."""
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
KEPT_PER_QUERY = {"dishdasha": 7, "thobe": 8, "winter": 5, "men": 9}
"""What survives the price rule, per answer. The rest are dropped as ``missing_price``."""
LOCALE_REFUSAL = "suggest-417-unsupported-locale.json"
UNSUPPORTED_LOCALE_URL = (
    f"https://{HOST}/search/suggest.json?q={{query}}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
"""The plain address, without ``/en/``: what the store answered with HTTP 417."""
SEARCH_URL = (
    f"https://{HOST}/en/search/suggest.json?q={{query}}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
PRODUCT_FOLDER = "/en/products/"
IMAGE_FOLDER = "/s/files/1/0960/9602/6936/"
"""Every image of the store is under this folder of the shared Shopify CDN."""

MENS_TYPE = "Apparel for men"
KIDS_TYPE = "Apparel for kids"
APOSTROPHE = chr(0x2019)
"""The store writes most apostrophes as the curly right single quotation mark (in 20 of the
27 titles that have one)."""

ADULT_DISHDASHA_PRICE = 9.0
ADULT_DISHDASHAS = {
    "summer-dishdasha-al-jazeera-for-men-with-name-embroidery": "Summer Dishdasha",
    "elegant-winter-dishdasha-al-jazeera-for-men": "Elegant Winter Dishdasha",
    "winter-dishdasha-al-jazeera-for-men-with-name-embroidery": "Winter Dishdasha",
}
"""The only adult dishdashas in 30 distinct records: the handle, then the part of the title
between "Men's" and "by Al Jazeera"."""

# The nine records whose variants differ in price, by handle: (lowest, highest) as the store
# writes them. Eight are children's dishdashas, one is a men's multipack. The one record that
# lists a variant shows that the lowest price is the smallest size ("6 Months (18 Inch)").
RANGED_RECORDS = {
    "beige-linen-dishdasha-al-jazeera-for-kids": ("12.000", "14.000"),
    "special-dishdasha-with-line-for-boys-with-name-embroidery": ("12.000", "14.000"),
    "boys-stripes-v-neck-half-sleeve-sleeping-dishdasha-by-al-jazeera-mix-colors": (
        "2.000",
        "2.250",
    ),
    "stripes-moroccan-dishdasha-for-boys-with-name-printing-option": ("5.000", "6.000"),
    "boys-beige-light-winter-dishdasha-by-al-jazeera": ("6.000", "7.000"),
    "boys-dark-beige-light-winter-dishdasha-by-al-jazeera": ("6.000", "7.000"),
    "boys-dark-grey-light-winter-dishdasha-by-al-jazeera": ("6.000", "7.000"),
    "boys-light-grey-light-winter-dishdasha-by-al-jazeera": ("6.000", "7.000"),
    "6-pcs-cotton-half-pants-al-jazeera-for-men": ("6.600", "9.000"),
}
RANGED_MENS_RECORD = "6-pcs-cotton-half-pants-al-jazeera-for-men"

# Children's records that no "boys" or "kids" word in the title marks: only the type and the tags
# say so. Three say "Youth" and one "Newborn".
CHILDREN_WITHOUT_A_KIDS_WORD = {
    "youth-summer-dishdasha-by-al-jazeera-with-elegant-fit",
    "white-al-jazeera-dishdasha-for-newborn-with-name-embroidery",
    "youth-winter-dishdasha-by-al-jazeera",
    "youth-stripes-v-neck-half-sleeve-sleeping-dishdasha-by-al-jazeera-mix-colors",
}


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(query: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(f"suggest-{query}.json"))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def raw_by_handle() -> dict[str, dict[str, Any]]:
    """Every distinct raw record of the four answers, by handle (30 of the 40 records)."""
    return {item["handle"]: item for query in QUERIES for item in raw_products(query)}


def handle_of(product: Product) -> str:
    return urlsplit(product.product_url).path.removeprefix(PRODUCT_FOLDER)


def replay(store: StoreConfig, query: str) -> ChainOutcome:
    """The saved answer for ``query`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(f"suggest-{query}.json"), store, build_search_url(store, query)
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for query in QUERIES for product in replay(store, query).products]


def distinct_products(store: StoreConfig) -> list[Product]:
    distinct, _repeats = dedupe_products(all_products(store))
    return distinct


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
    assert store.id == STORE_ID
    assert store.display_name == DISPLAY_NAME
    assert (store.country, store.currency) == ("KW", CURRENCY)
    assert store.tier_hint is Tier.BUDGET
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_on_the_english_address(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        f"https://{HOST}/en/search/suggest.json?q={{query}}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "white thobe") == SEARCH_URL.format(query="white%20thobe")


def test_the_search_address_keeps_the_english_prefix_the_store_needs(store: StoreConfig) -> None:
    """The store's default language is Arabic and Shopify's predictive search does not serve it:
    without ``/en/`` every search is refused with HTTP 417 (see the store note). Remove the prefix
    from the store file and this test fails first."""
    searched = urlsplit(build_search_url(store, "dishdasha"))

    assert searched.hostname == HOST
    assert searched.path == "/en/search/suggest.json"
    assert build_search_url(store, "dishdasha") != UNSUPPORTED_LOCALE_URL.format(query="dishdasha")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_the_store_file_keeps_the_options_that_make_the_prices_and_genders_trustworthy(
    store: StoreConfig,
) -> None:
    """Remove ``max_price_spread`` and the children's sizes are shown at their smallest size's
    price; remove ``gender_fields`` and the men's labels fall back to the default order (which
    here gives the same answer, so the line is documentation as much as setting)."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {"gender_fields": ["type", "tags"], "max_price_spread": 1}


def test_a_womens_request_is_not_sent_to_this_mens_and_boys_store(store: StoreConfig) -> None:
    # 12 of the 30 records seen are men's and 18 are children's (not a gender in the contract);
    # none was women's (docs/store-notes/al-jazeera-clothing.md).
    assert store.genders == frozenset({Gender.MEN})
    assert store.sells_for_gender(Gender.MEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.WOMEN)


def test_only_a_dresses_search_is_sent_to_this_dishdasha_store(store: StoreConfig) -> None:
    # Thobes and dishdashas are in the dresses category. The other nine men's records are
    # underwear, nightwear and multipacks, which are out of scope, so a search for tops, trousers,
    # jackets or shoes would only waste a request to it.
    assert store.categories == frozenset({Category.DRESSES})
    assert store.sells_category(Category.DRESSES)
    for other in (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_the_budget_tier_hint_matches_a_mens_dishdasha_at_about_one_hundred_dirhams(
    store: StoreConfig,
) -> None:
    settings = load_settings(env={})
    dirhams = to_base(ADULT_DISHDASHA_PRICE, CURRENCY, settings)

    assert store.tier_hint is Tier.BUDGET
    assert dirhams is not None
    assert 100 <= dirhams <= 115  # KWD 9 at the shipped fixed rate (11.92) is about AED 107


def test_robots_txt_allows_the_english_search_and_product_paths_and_still_closes_the_cart(
    store: StoreConfig,
) -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(build_search_url(store, query), agent)
    for handle in ADULT_DISHDASHAS:
        assert robots.can_fetch(f"https://{HOST}{PRODUCT_FOLDER}{handle}", agent)
    assert not robots.can_fetch(f"https://{HOST}/cart/", agent)  # parsed, not allow-all
    assert not robots.can_fetch(f"https://{HOST}/en/cart/", agent)
    assert not robots.can_fetch(f"https://{HOST}/en/checkout", agent)


# --------------------------------------------------------------------------------------------
# The fixtures through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_recording_holds_ten_products_and_the_price_rule_keeps_only_some(
    store: StoreConfig, query: str
) -> None:
    outcome = replay(store, query)

    assert len(raw_products(query)) == PRODUCTS_IN_EACH_FIXTURE
    assert outcome.strategy == "shopify"
    assert outcome.examined == PRODUCTS_IN_EACH_FIXTURE
    assert len(outcome.products) == KEPT_PER_QUERY[query]
    assert outcome.dropped == {"missing_price": PRODUCTS_IN_EACH_FIXTURE - KEPT_PER_QUERY[query]}


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_all_six_required_fields_and_a_dinar_price(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == CURRENCY
        assert product.image_url
        assert product.product_url
        assert product.in_stock is True
        assert product.store == DISPLAY_NAME


@pytest.mark.parametrize("query", QUERIES)
def test_product_and_image_urls_are_https_and_on_allowed_hosts(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == HOST
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert urlsplit(product.image_url).path.startswith(IMAGE_FOLDER)


@pytest.mark.parametrize("query", QUERIES)
def test_product_links_stay_on_the_english_storefront(store: StoreConfig, query: str) -> None:
    """Quirk: the store's links are ``/en/products/<handle>``. They are kept as the store gave
    them, because that is the English page; the Arabic page is ``/products/<handle>``."""
    raw = {item["handle"]: item["url"] for item in raw_products(query)}

    for product in replay(store, query).products:
        path = urlsplit(product.product_url).path
        assert path.startswith(PRODUCT_FOLDER)
        assert raw[handle_of(product)].startswith(path)


@pytest.mark.parametrize("query", QUERIES)
def test_image_urls_carry_width_400_and_keep_the_version_parameter(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params


def test_the_saved_answers_give_twenty_one_distinct_valid_products(store: StoreConfig) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    # 40 records over four answers, 30 distinct. The price rule drops 11 of the 40 (9 distinct
    # records, two of which came up twice), leaving 29 valid, and 8 of those are repeats.
    assert sum(KEPT_PER_QUERY.values()) == len(every_product) == 29
    assert len(distinct) == 21
    assert repeats == {"duplicate_url": 8}
    assert len(distinct) >= 20  # plan 12.18.2: the thin margin is real, see the store note


# --------------------------------------------------------------------------------------------
# Three-decimal dinar prices
# --------------------------------------------------------------------------------------------


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    prices = {handle_of(p): p.price for p in distinct_products(store)}
    raw = raw_by_handle()

    assert raw["summer-dishdasha-al-jazeera-for-men-with-name-embroidery"]["price"] == "9.000"
    assert prices["summer-dishdasha-al-jazeera-for-men-with-name-embroidery"] == 9.0
    # Half dinars are written "7.500", and the cheapest kept record is "2.500".
    assert raw["men-s-blue-t-shirt-and-checkered-pants-pajama-set"]["price"] == "7.500"
    assert prices["men-s-blue-t-shirt-and-checkered-pants-pajama-set"] == 7.5
    youth_sleeping = "youth-stripes-v-neck-half-sleeve-sleeping-dishdasha-by-al-jazeera-mix-colors"
    assert prices[youth_sleeping] == 2.5


def test_prices_keep_their_three_decimals_and_sit_in_the_garment_range(
    store: StoreConfig,
) -> None:
    raw = raw_by_handle()
    products = distinct_products(store)

    assert all(len(raw[handle_of(p)]["price"].split(".")[1]) == 3 for p in products)
    # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000 out.
    assert all(2 <= p.price <= 18 for p in products)


# --------------------------------------------------------------------------------------------
# The price rule: what it drops, what it keeps, what it would have shown
# --------------------------------------------------------------------------------------------


def test_nine_records_have_variants_at_different_prices_and_price_is_the_lowest() -> None:
    """In the real data ``price`` is ``price_min`` on every record, and on these nine
    ``price_max`` is 1.1 to 1.4 times higher."""
    raw = raw_by_handle()
    ranged = {
        handle: (item["price_min"], item["price_max"])
        for handle, item in raw.items()
        if item["price_min"] != item["price_max"]
    }

    assert all(item["price"] == item["price_min"] for item in raw.values())
    assert ranged == RANGED_RECORDS


def test_eight_of_the_nine_ranged_records_are_childrens_and_one_is_a_mens_multipack() -> None:
    raw = raw_by_handle()
    types = Counter(raw[handle]["type"] for handle in RANGED_RECORDS)

    assert types == {KIDS_TYPE: 8, MENS_TYPE: 1}
    assert raw[RANGED_MENS_RECORD]["title"].startswith(f"Men{APOSTROPHE}s 6 Pcs Cotton Half Pants")


def test_the_one_ranged_record_that_lists_a_variant_shows_the_lowest_price_is_a_size() -> None:
    """Why the rule exists: ``price`` is the smallest size. The special boys' dishdasha costs KWD
    12 in the first size listed ("6 Months (18 Inch)") and up to KWD 14 in another."""
    item = raw_by_handle()["special-dishdasha-with-line-for-boys-with-name-embroidery"]
    [variant] = item["variants"]

    assert variant["title"] == "Light Gray / 6 Months (18 Inch)"
    assert variant["price"] == item["price"] == "12.000"
    assert item["price_max"] == "14.000"


def test_with_the_rule_none_of_those_nine_is_shown_at_all(store: StoreConfig) -> None:
    shown = {handle_of(p) for p in all_products(store)}

    assert shown.isdisjoint(RANGED_RECORDS)
    assert set(raw_by_handle()) - shown == set(RANGED_RECORDS)


def test_without_the_rule_a_childrens_dishdasha_would_be_shown_at_its_smallest_sizes_price(
    store: StoreConfig,
) -> None:
    unguarded = {
        handle_of(p): p.price
        for query in QUERIES
        for p in replay(without_price_option(store), query).products
    }

    assert len(unguarded) == 30
    for handle, (low, high) in RANGED_RECORDS.items():
        assert unguarded[handle] == float(low)
        assert float(low) < float(high)  # the lower figure: not one price the shopper can count on


def test_every_kept_record_has_a_single_price(store: StoreConfig) -> None:
    raw = raw_by_handle()

    for product in distinct_products(store):
        item = raw[handle_of(product)]
        assert item["price_min"] == item["price_max"] == item["price"]
        assert product.price == float(item["price"])


def test_the_pre_sale_price_is_zero_everywhere_so_no_record_is_on_sale() -> None:
    """``compare_at_price`` is ``"0.000"`` on all 30 records: nothing is marked down, and the
    adapter reads ``price`` and nothing else."""
    raw = raw_by_handle()

    assert {(i["compare_at_price_min"], i["compare_at_price_max"]) for i in raw.values()} == {
        ("0.000", "0.000")
    }


# --------------------------------------------------------------------------------------------
# Who the products are for, and how thin the adult range is
# --------------------------------------------------------------------------------------------


def test_the_type_names_who_the_product_is_for_and_never_the_garment() -> None:
    raw = raw_by_handle()

    assert Counter(item["type"] for item in raw.values()) == {KIDS_TYPE: 18, MENS_TYPE: 12}
    assert {item["vendor"] for item in raw.values()} == {"JAZEERA"}


def test_every_mens_product_is_labelled_men_and_every_childrens_product_stays_unknown(
    store: StoreConfig,
) -> None:
    """The type "Apparel for men" names men; "Apparel for kids" and the kids' tags ("boys",
    "kids") name no gender word, so the children's products have no gender. Only the title can
    mark them as children's (see the next test)."""
    raw = raw_by_handle()
    seen: dict[str, set[Gender | None]] = {MENS_TYPE: set(), KIDS_TYPE: set()}
    for product in distinct_products(store):
        seen[raw[handle_of(product)]["type"]].add(product.gender)

    assert seen == {MENS_TYPE: {Gender.MEN}, KIDS_TYPE: {None}}
    mens_tags = [raw[handle]["tags"] for handle in raw if raw[handle]["type"] == MENS_TYPE]
    assert len(mens_tags) == 12
    assert all("men" in " ".join(tags).lower().split() for tags in mens_tags)  # tags agree


def test_four_childrens_titles_have_no_boys_or_kids_word_so_only_the_type_marks_them() -> None:
    kids_word = re.compile(r"\b(?:boys?|kids?)\b")
    raw = raw_by_handle()
    unmarked = {
        handle
        for handle, item in raw.items()
        if item["type"] == KIDS_TYPE and not kids_word.search(item["title"].lower())
    }

    assert unmarked == CHILDREN_WITHOUT_A_KIDS_WORD
    for handle in unmarked:
        assert {"kids"} <= set(raw[handle]["tags"])  # the tags do say "kids"


def test_three_adult_dishdashas_are_all_there_is_to_find_and_each_has_one_price(
    store: StoreConfig,
) -> None:
    """The honest picture of this store for a men's thobe search: 3 adult dishdashas, each KWD 9,
    in 30 distinct records seen over four queries. Everything else adult is underwear or
    nightwear."""
    raw = raw_by_handle()
    adult_dishdashas = {
        handle
        for handle, item in raw.items()
        if item["type"] == MENS_TYPE and "dishdasha" in item["title"].lower()
    }
    kept = {handle_of(p): p for p in distinct_products(store)}

    assert adult_dishdashas == set(ADULT_DISHDASHAS)
    for handle, middle in ADULT_DISHDASHAS.items():
        product = kept[handle]
        assert product.title == f"Men{APOSTROPHE}s {middle} by Al Jazeera"
        assert product.price == ADULT_DISHDASHA_PRICE
        assert product.gender is Gender.MEN
        assert product.in_stock is True


def test_the_matched_variants_of_the_adult_dishdashas_are_sizes_at_the_same_price() -> None:
    """Quirk: where a men's dishdasha lists a variant it is "White / M / 52" (colour, size M,
    a length in inches) at the product price, so the sizes carry no surcharge."""
    raw = raw_by_handle()
    listed = {
        handle: raw[handle]["variants"][0] for handle in ADULT_DISHDASHAS if raw[handle]["variants"]
    }

    assert {v["title"] for v in listed.values()} == {"White / M / 52", "Gray / M / 52"}
    assert {v["price"] for v in listed.values()} == {"9.000"}


def test_most_of_a_dishdasha_answer_is_childrens_because_the_adult_range_is_small() -> None:
    """For each query: how many of the 10 records are an adult dishdasha. The adult share is 1 or 2
    in 10, so a search with a ten-product cap finds few men's dishdashas."""
    adult = {
        query: sum(
            1
            for item in raw_products(query)
            if item["type"] == MENS_TYPE and "dishdasha" in item["title"].lower()
        )
        for query in QUERIES
    }
    kids = {
        query: sum(1 for item in raw_products(query) if item["type"] == KIDS_TYPE)
        for query in QUERIES
    }

    assert adult == {"dishdasha": 1, "thobe": 1, "winter": 2, "men": 1}
    assert kids == {"dishdasha": 9, "thobe": 9, "winter": 8, "men": 0}


def test_the_men_query_answers_with_underwear_and_nightwear_not_dishdashas() -> None:
    titles = [item["title"] for item in raw_products("men")]
    dishdashas = [title for title in titles if "dishdasha" in title.lower()]

    assert len(titles) == 10
    assert len(dishdashas) == 1
    assert sum("Pajama" in t for t in titles) == 3
    assert sum("Pcs" in t for t in titles) == 4  # multipacks of undershirts, pants and innerwear


def test_the_nine_other_mens_records_are_all_tagged_as_under_garments() -> None:
    """Why ``categories`` is only ``dresses``: every adult record that is not a dishdasha (a
    thermal set, a pyjama set, a multipack of undershirts or pants) carries the tag "Under
    Garments", and none is a shirt, a pair of trousers or a jacket to wear outside."""
    others = [
        item
        for item in raw_by_handle().values()
        if item["type"] == MENS_TYPE and item["handle"] not in ADULT_DISHDASHAS
    ]

    assert len(others) == 9
    assert all("Under Garments" in item["tags"] for item in others)


# --------------------------------------------------------------------------------------------
# Other quirks of this store's data (docs/store-notes/al-jazeera-clothing.md)
# --------------------------------------------------------------------------------------------


def test_handles_do_not_always_match_titles_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: "Boys' Beige Summer Dishdasha" lives at ``beige-dishdasha-...-for-kids-ramadan-...``
    and "Boys' Beige Soft Winter Dishdasha" at ``boys-beige-light-winter-...`` ("Soft" against
    "light"). Rebuilding a link from the title would send the shopper to the wrong product."""
    link = {handle_of(p): p.product_url for p in distinct_products(store)}
    summer = "beige-dishdasha-al-jazeera-for-kids-ramadan-edition-with-name-embroidery"

    assert link[summer] == f"https://{HOST}{PRODUCT_FOLDER}{summer}"
    assert (
        raw_by_handle()[summer]["title"] == f"Boys{APOSTROPHE} Beige Summer Dishdasha by Al Jazeera"
    )


def test_the_tracking_and_variant_parameters_on_the_product_link_are_removed(
    store: StoreConfig,
) -> None:
    raw = raw_by_handle()
    assert all("_pos=" in item["url"] for item in raw.values())  # the store adds them
    assert sum("variant=" in item["url"] for item in raw.values()) == 5

    for product in distinct_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith(PRODUCT_FOLDER)


def test_title_typography_is_cleaned_but_the_words_are_the_stores(store: StoreConfig) -> None:
    """Quirk: one title has a double space ("Boys'  Winter Dishdasha") and one a stray straight
    apostrophe ("Youth' Stripes ..."); the adapter collapses the space and leaves the words."""
    raw = raw_by_handle()
    double_space = "al-jazeera-winter-dishdasha-for-boys-with-name-embroidery"
    kept = {handle_of(p): p for p in distinct_products(store)}

    assert "  " in raw[double_space]["title"]
    assert kept[double_space].title == "Boys' Winter Dishdasha by Al Jazeera"
    youth = "youth-stripes-v-neck-half-sleeve-sleeping-dishdasha-by-al-jazeera-mix-colors"
    assert kept[youth].title.startswith("Youth' Stripes")


def test_every_product_carries_the_store_files_name_not_the_vendor(store: StoreConfig) -> None:
    """Quirk: ``vendor`` is the shouted word "JAZEERA" on all 30 records and is never shown."""
    assert {p.store for p in all_products(store)} == {DISPLAY_NAME}


def test_the_whole_catalogue_seen_is_in_stock(store: StoreConfig) -> None:
    """``available`` is true on all 30 records; stock is product-level only (no per-size read)."""
    assert {item["available"] for item in raw_by_handle().values()} == {True}
    assert {p.in_stock for p in all_products(store)} == {True}


# --------------------------------------------------------------------------------------------
# The locale quirk: the plain address is refused, the /en/ address answers
# --------------------------------------------------------------------------------------------


def test_the_refusal_to_the_plain_address_is_a_417_that_the_chain_cannot_read(
    store: StoreConfig,
) -> None:
    """The saved 86-byte body: ``{"status":417,"message":"Expectation Failed","description":
    "Unsupported buyer locale"}``. It is JSON but not a Shopify suggest response, so the chain
    reports an error and returns no products."""
    refusal = json.loads(fixture_text(LOCALE_REFUSAL))
    outcome = ExtractionChain(default_registry()).run(
        fixture_text(LOCALE_REFUSAL), store, UNSUPPORTED_LOCALE_URL.format(query="dishdasha")
    )

    assert refusal == {
        "status": 417,
        "message": "Expectation Failed",
        "description": "Unsupported buyer locale",
    }
    assert outcome.products == []
    assert outcome.strategy is None
    assert outcome.examined == 0
    assert outcome.ran_cleanly == 0
    [error] = outcome.errors
    assert error.startswith("shopify:")
    assert "not a Shopify suggest response" in error


async def test_the_engine_reports_the_417_as_an_error_not_a_block_and_asks_once(
    store: StoreConfig,
) -> None:
    """If the ``/en/`` prefix is lost the store answers every search with HTTP 417. That must read
    as a broken adapter (``error``, one request, no cooldown), not as the store blocking us."""
    seen: list[httpx.Request] = []
    robots = Protego.parse(fixture_text("robots.txt"))
    plain_url = UNSUPPORTED_LOCALE_URL.format(query="dishdasha")
    assert robots.can_fetch(plain_url, make_settings().user_agent)  # robots is not the reason

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                content=fixture_text("robots.txt").encode(),
                headers={"content-type": "text/plain"},
            )
        return httpx.Response(
            417,
            content=fixture_text(LOCALE_REFUSAL).encode(),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    plain_store = store.model_copy(
        update={
            "enabled": True,
            "search_url_template": (
                f"https://{HOST}/search/suggest.json?q={{query}}"
                "&resources[type]=product&resources[limit]=10"
            ),
        }
    )
    settings = make_settings(extra_store_countries=["KW"])
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=["dishdasha"]), [plain_store]
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.ERROR
    assert result.detail is not None
    assert "417" in result.detail
    assert result.products == []
    assert [str(request.url) for request in seen] == [f"https://{HOST}/robots.txt", plain_url]


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
    store: StoreConfig,
) -> None:
    sent = QUERIES[:2]  # a store is sent at most two keyword variants, never a third
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
    # The second variant is sent only when the first gave fewer than second_variant_below products;
    # each saved answer has ten, so raise the setting to see both requests.
    settings = make_settings(extra_store_countries=["KW"], second_variant_below=50)
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=sent),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert result.dropped == {"missing_price": 5}  # 3 + 2: the records with several prices
    assert {product.currency for product in result.products} == {CURRENCY}
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[SEARCH_URL.format(query=query) for query in sent],
    ]
    assert {urlsplit(str(request.url)).path for request in seen[1:]} == {"/en/search/suggest.json"}
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
