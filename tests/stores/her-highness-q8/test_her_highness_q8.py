"""Her Highness Q8 store adapter, offline (plan 12.16).

The fixtures in ``fixtures/`` are real answers from 2026-10-08, saved by the qualification script
(honest User-Agent, robots.txt first, one request per second): one full Shopify
``/search/suggest.json`` response each for ``daraa``, ``kaftan`` and ``abaya``. Shopify caps the
answer at 10 products and every product is kept; only each ``body`` (the HTML description, in
Arabic or English) was cut to 300 characters to keep the files small. ``robots.txt`` is the store's
file, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"45.000"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006). The data is thin on labels:
11 of the 21 distinct titles name no garment ("Crescent", "Crystal Black", one is just "2"),
``type`` is mostly empty, ``tags`` and ``variants`` are empty and no field names a gender. Four of
the 21 products are girls' pieces. Its store file therefore sets ``genders`` and ``categories``
from the range, and no extractor option (``max_price_spread`` is off: no record has an add-on
variant). The tests below pin each of those claims with the real records.
"""

import json
from decimal import Decimal
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
    GenderSource,
    Product,
    StoreConfig,
    StoreStatus,
    StrategyConfig,
    Tier,
)
from vga.rank.category import classify_title
from vga.rank.filters import DropReason, apply_hard_filters
from vga.rank.lexicon import is_childrens_title
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
STORE_ID = "her-highness-q8"
DISPLAY_NAME = "Her Highness Q8"
HOST = "herhighnessq8.com"
QUERIES = ["daraa", "kaftan", "abaya"]
"""One saved answer per query: ``fixtures/suggest-<query>.json``."""
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
DISTINCT_PRODUCTS = 21
"""30 records over the three queries; nine of them are repeats of another record."""

SEARCH_URL = (
    f"https://{HOST}/search/suggest.json?q={{query}}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0695/4631/1733/files/"
"""Every image of the store is under this folder of the shared Shopify CDN."""

MZIANA = "MZIANA \u2013 Moroccan"
"""The title as the store writes it, with an en dash (U+2013)."""
MZIANA_KIDS = f"{MZIANA} Kids"

GIRLS_PIECES = {
    "Kids Olive Kaftan": 28.5,
    "Kids Burgundy Kaftan": 28.5,
    "Crescent Kids": 35.0,
    MZIANA_KIDS: 40.0,
}
"""The four titles with the word "Kids", with the price the adapter shows for each."""
GIRLS_PIECES_WITH_SIZE_PRICES = {
    "Crescent Kids": ("35.000", "37.000"),
    MZIANA_KIDS: ("40.000", "43.000"),
}
"""The only two records whose variants differ in price: lowest and highest, as the store writes
them."""


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(query: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(f"suggest-{query}.json"))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def raw_distinct() -> dict[str, dict[str, Any]]:
    """Every distinct record of the three answers, by its (clean) title. A repeat is the same
    handle, so the first one seen is kept."""
    by_handle: dict[str, dict[str, Any]] = {}
    for query in QUERIES:
        for item in raw_products(query):
            by_handle.setdefault(item["handle"], item)
    return {" ".join(item["title"].split()): item for item in by_handle.values()}


def replay(store: StoreConfig, query: str) -> ChainOutcome:
    """The saved answer for ``query`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(f"suggest-{query}.json"), store, build_search_url(store, query)
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for query in QUERIES for product in replay(store, query).products]


def distinct_by_title(store: StoreConfig) -> dict[str, Product]:
    distinct, _repeats = dedupe_products(all_products(store))
    return {product.title: product for product in distinct}


def with_price_spread(store: StoreConfig, spread: float) -> StoreConfig:
    """The same store with ``max_price_spread`` set: what the file would do with that line."""
    strategy = StrategyConfig(name="shopify", options={"max_price_spread": spread})
    return store.model_copy(update={"extraction": ExtractionConfig(strategies=[strategy])})


# --------------------------------------------------------------------------------------------
# The store file (plan 12.16.1)
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == STORE_ID
    assert store.display_name == DISPLAY_NAME
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.MID_RANGE
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        f"https://{HOST}/search/suggest.json?q={{query}}&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black kaftan") == SEARCH_URL.format(query="black%20kaftan")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_the_store_file_sets_no_extractor_option_because_the_data_needs_none(
    store: StoreConfig,
) -> None:
    """No ``max_price_spread`` (no add-on variants, see the price tests below) and no
    ``gender_fields`` (no gender in any field). If the store starts listing add-ons, the price
    tests fail first and the option is added (docs/store-notes/her-highness-q8.md)."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {}


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_daraa_kaftan_and_dress_store(
    store: StoreConfig,
) -> None:
    # 14 of the 21 distinct records are daraas, kaftans or dresses
    # (docs/store-notes/her-highness-q8.md), so a search for shoes or jeans would only waste a
    # request to it. The one top and the three suits seen are not enough to list tops, outerwear
    # or bottoms (their titles do not say so).
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
# The saved answers through the real extraction chain (plan 12.16.2)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_saved_answer_is_read_in_full(store: StoreConfig, query: str) -> None:
    outcome = replay(store, query)

    assert len(raw_products(query)) == PRODUCTS_IN_EACH_FIXTURE
    assert outcome.strategy == "shopify"
    assert outcome.examined == PRODUCTS_IN_EACH_FIXTURE
    assert len(outcome.products) == outcome.examined
    assert outcome.dropped == {}


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_the_six_required_fields_and_stays_on_allowed_hosts(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "KWD"
        assert product.store == DISPLAY_NAME
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == HOST
        assert urlsplit(product.product_url).query == ""  # tracking parameters removed
        assert urlsplit(product.product_url).path.startswith("/products/")
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert urlsplit(product.image_url).path.startswith(IMAGE_FOLDER)
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params


def test_the_saved_answers_give_twenty_one_distinct_valid_products(store: StoreConfig) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 30  # 3 answers of 10; nothing is dropped on validation
    assert len(distinct) == DISTINCT_PRODUCTS
    assert len(distinct) >= 20  # plan 12.16.2
    assert repeats == {"duplicate_url": 9}


def test_the_store_pads_its_answers_with_products_that_do_not_match_the_word(
    store: StoreConfig,
) -> None:
    """Quirk: the word is matched loosely. "abaya" returns no title with "abaya" in it (the word is
    in none of the 21 titles), "daraa" returns one "Dara'a" among nine other pieces, and "kaftan"
    returns four kaftans among dresses and a daraa."""
    titles = {query: [p.title for p in replay(store, query).products] for query in QUERIES}

    assert not [t for t in titles["abaya"] if "abaya" in t.lower()]
    assert [t for t in titles["daraa"] if "dara" in t.lower()] == ["Dara'a 2026"]
    assert [t for t in titles["kaftan"] if "kaftan" in t.lower()] == [
        "Burgundy Kaftan",
        "Plum Kaftan",
        "Kids Olive Kaftan",
        "Kids Burgundy Kaftan",
    ]


# --------------------------------------------------------------------------------------------
# Price: dinars with three decimals, no add-on variant, sale prices
# --------------------------------------------------------------------------------------------


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    raw = raw_distinct()
    products = distinct_by_title(store)

    assert raw["Pearl Dress"]["price"] == "45.000"
    assert products["Pearl Dress"].price == 45.0
    assert raw["Beige strips Sets"]["price"] == "46.800"
    assert products["Beige strips Sets"].price == 46.8
    assert raw["Sahara Oversized Top"]["price"] == "38.750"
    assert products["Sahara Oversized Top"].price == 38.75
    assert raw["2"]["price"] == "85.000"
    assert products["2"].price == 85.0


def test_prices_keep_their_three_decimals_and_sit_in_the_garment_range(
    store: StoreConfig,
) -> None:
    raw = raw_distinct()
    products = distinct_by_title(store)

    assert all(len(item["price"].split(".")[1]) == 3 for item in raw.values())
    # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000 out.
    assert all(28 <= product.price <= 85 for product in products.values())
    assert min(p.price for p in products.values()) == 28.5
    assert max(p.price for p in products.values()) == 85.0


def test_no_record_has_an_add_on_variant_so_the_default_price_is_the_garments() -> None:
    """Unlike Hamsa, no record here pairs a cheap add-on with the garment: ``variants`` is an empty
    list on all 21 distinct records and ``price`` is ``price_min`` on every one. If the store ever
    lists add-ons this test fails, and ``max_price_spread`` needs a second look (ADR 0012)."""
    raw = raw_distinct()

    assert len(raw) == DISTINCT_PRODUCTS
    for item in raw.values():
        assert item["variants"] == []
        assert item["price"] == item["price_min"]


def test_only_two_records_have_variants_at_different_prices_and_both_are_girls_sizes() -> None:
    """The only spread in the data: a size surcharge on two girls' pieces, 35 to 37 and 40 to 43
    dinars, a ratio of 1.06 and 1.08. The other 19 records have one price."""
    ranged = {
        title: (item["price_min"], item["price_max"])
        for title, item in raw_distinct().items()
        if item["price_min"] != item["price_max"]
    }

    assert ranged == GIRLS_PIECES_WITH_SIZE_PRICES
    for low, high in ranged.values():
        assert Decimal(high) / Decimal(low) < Decimal("1.1")


def test_a_girls_piece_with_sizes_at_two_prices_is_shown_at_its_smallest_size(
    store: StoreConfig,
) -> None:
    products = distinct_by_title(store)

    assert products["Crescent Kids"].price == 35.0  # sizes cost 35 to 37
    assert products[MZIANA_KIDS].price == 40.0  # sizes cost 40 to 43


def test_the_price_option_would_drop_nothing_at_1_25_and_only_those_two_girls_pieces_at_1(
    store: StoreConfig,
) -> None:
    """Why the file leaves ``max_price_spread`` off (ADR 0012): at ``1`` it would drop the two
    girls' pieces for no gain, and at ``1.25`` it would drop nothing seen, so it would only add a
    way for the store to fail (every record is dropped if Shopify stops sending ``price_min``)."""
    strict = [replay(with_price_spread(store, 1), query) for query in QUERIES]
    tolerant = [replay(with_price_spread(store, 1.25), query) for query in QUERIES]

    assert [outcome.dropped for outcome in strict] == [{}, {}, {"missing_price": 2}]
    dropped = {p.title for p in all_products(store)} - {
        p.title for outcome in strict for p in outcome.products
    }
    assert dropped == set(GIRLS_PIECES_WITH_SIZE_PRICES)
    assert [outcome.dropped for outcome in tolerant] == [{}, {}, {}]


def test_a_sale_shows_the_price_paid_not_the_struck_through_one(store: StoreConfig) -> None:
    """Three records carry a pre-sale price above their price; the other 18 carry "0.000" (no
    sale). The adapter uses ``price``."""
    raw = raw_distinct()
    products = distinct_by_title(store)

    on_sale = {
        title: (item["price"], item["compare_at_price_max"])
        for title, item in raw.items()
        if Decimal(item["compare_at_price_max"]) > Decimal(item["price"])
    }
    assert on_sale == {
        "Burgundy Kaftan": ("36.500", "39.500"),
        "Plum Kaftan": ("42.000", "48.000"),
        "Olive Garden": ("36.500", "39.500"),
    }
    assert {item["compare_at_price_max"] for t, item in raw.items() if t not in on_sale} == {
        "0.000"
    }
    assert products["Plum Kaftan"].price == 42.0
    assert products["Burgundy Kaftan"].price == 36.5


# --------------------------------------------------------------------------------------------
# Other quirks of this store's data (docs/store-notes/her-highness-q8.md), pinned by real records
# --------------------------------------------------------------------------------------------


def test_eleven_of_the_twenty_one_titles_name_no_garment_so_the_ranker_cannot_read_them(
    store: StoreConfig,
) -> None:
    """Quirk: many titles are only a name ("Crescent", "Olive Garden", "Crystal Black") and one is
    just "2". The adapter hands them over as they are; the ranker reads a category only from a
    garment word, so these have none and are kept for a dresses search."""
    kinds = {title: classify_title(title) for title in distinct_by_title(store)}
    unnamed = {title for title, kind in kinds.items() if kind is None}

    assert unnamed == {
        "Beige strips Sets",
        "Crystal Dark Beige",
        "Desert Palm Luxury",
        "2",
        "Olive Garden",
        "Crescent",
        "Crystal Black",
        "Royal Midnight Full set",
        "Crescent Kids",
        MZIANA,
        MZIANA_KIDS,
    }


def test_the_ranker_reads_dresses_and_kaftans_and_the_one_top_from_their_titles(
    store: StoreConfig,
) -> None:
    """Needs "daraa" among the dresses words in ``src/vga/rank/lexicon.py``: "Dara'a" is "daraa"
    once the apostrophe is dropped."""
    kinds = {title: classify_title(title) for title in distinct_by_title(store)}

    assert {title for title, kind in kinds.items() if kind is Category.DRESSES} == {
        "Dara'a 2026",
        "Aura Dress",
        "Ivory Glow Dress",
        "Pearl Dress",
        "Brown Mist Dress",
        "Burgundy Kaftan",
        "Plum Kaftan",
        "Kids Olive Kaftan",
        "Kids Burgundy Kaftan",
    }
    assert kinds["Sahara Oversized Top"] is Category.TOPS


def test_three_pieces_that_are_suits_by_their_description_have_a_title_with_no_garment(
    store: StoreConfig,
) -> None:
    """Quirk: "Crystal Dark Beige", "Crystal Black" and "Royal Midnight Full set" are a blazer with
    wide trousers (their description, in Arabic, says so), but the title says nothing. The
    adapter does not read ``body`` (store-supplied HTML, never used), so they come back as
    products of unknown category and a dresses search keeps them. "Crystal Black" is the second
    result for ``abaya``."""
    raw = raw_distinct()
    suits = ("Crystal Dark Beige", "Crystal Black", "Royal Midnight Full set")

    for title in suits:
        assert "بليزر" in raw[title]["body"]  # "blazer"
        assert "بنطلون" in raw[title]["body"]  # "trousers"
        assert classify_title(title) is None
    assert [p.title for p in replay(store, "abaya").products][:3] == [
        "Crescent",
        "Crystal Black",
        "Royal Midnight Full set",
    ]


def test_four_girls_pieces_are_sold_beside_the_womens_and_the_adapter_does_not_drop_them(
    store: StoreConfig,
) -> None:
    """Quirk: "Kids Olive Kaftan", "Kids Burgundy Kaftan", "Crescent Kids" and "MZIANA - Moroccan
    Kids" (KWD 28.5 to 40, the cheapest in the store) come back for the same words as the women's
    pieces. The adapter has no rule for them: dropping children's items is the ranker's job."""
    products = distinct_by_title(store)

    assert {title: products[title].price for title in GIRLS_PIECES} == GIRLS_PIECES
    assert {title for title, p in products.items() if is_childrens_title(p.title)} == set(
        GIRLS_PIECES
    )


def test_the_ranker_drops_the_girls_pieces_only_when_the_shopper_stated_a_gender(
    store: StoreConfig,
) -> None:
    """Why this store's cheapest products are a risk: with no stated gender (or one that is only
    inferred, BRD Rule 8) the four girls' pieces pass the hard filters and sit at the low end of
    the price range. With a stated gender the ranker drops them by title."""
    products = distinct_by_title(store)
    stated = make_item_intent(
        category=Category.DRESSES, gender=Gender.WOMEN, gender_source=GenderSource.EXPLICIT
    )
    unstated = make_item_intent(category=Category.DRESSES)

    for title in GIRLS_PIECES:
        assert apply_hard_filters(unstated, products[title]).keep
        result = apply_hard_filters(stated, products[title])
        assert not result.keep
        assert result.reason is DropReason.CHILDRENS_ITEM
    assert apply_hard_filters(stated, products["Plum Kaftan"]).keep


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear (and girls'), but it never says so in a field: ``type`` is empty on
    17 of the 21 records ("Dress" on 3, "set" on 1), ``tags`` is empty on all, and every product's
    gender is unknown. ``genders: [women]`` in the store file does the work."""
    raw = raw_distinct()

    assert sorted(item["type"] for item in raw.values()).count("") == 17
    assert {item["type"] for item in raw.values()} == {"", "Dress", "set"}
    assert all(item["tags"] == [] for item in raw.values())
    assert {product.gender for product in all_products(store)} == {None}


def test_handles_do_not_match_titles_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: "Crystal Black" lives at ``new2-mar-6``, a girls' kaftan at
    ``untitled-nov22_19-25`` and the piece titled "2" at ``2-1``. Rebuilding a link from the title
    would send the shopper to the wrong product, or nowhere."""
    link = {title: p.product_url for title, p in distinct_by_title(store).items()}

    assert link["Crystal Black"] == f"https://{HOST}/products/new2-mar-6"
    assert link["Crystal Dark Beige"] == f"https://{HOST}/products/new2-mar-7"
    assert link["Kids Olive Kaftan"] == f"https://{HOST}/products/untitled-nov22_19-25"
    assert link[MZIANA_KIDS] == f"https://{HOST}/products/untitled-dec19_22-35"
    assert link["Royal Midnight Full set"] == f"https://{HOST}/products/new-set-17-2"
    assert link["2"] == f"https://{HOST}/products/2-1"


def test_the_tracking_parameters_on_the_product_link_are_removed() -> None:
    for query in QUERIES:
        assert all("_pos=" in item["url"] for item in raw_products(query))  # the store adds them


def test_a_title_with_a_double_space_is_cleaned_to_single_spaces(store: StoreConfig) -> None:
    """Quirk: the store writes "Kids Olive  Kaftan" with two spaces."""
    raw_titles = {item["title"] for query in QUERIES for item in raw_products(query)}

    assert "Kids Olive  Kaftan" in raw_titles
    assert "Kids Olive Kaftan" in distinct_by_title(store)
    assert all(title == " ".join(title.split()) for title in distinct_by_title(store))


def test_the_vendor_is_the_brand_and_the_shoppers_store_name_is_the_display_name(
    store: StoreConfig,
) -> None:
    """The adapter does not read ``vendor`` (``herhighnessq8`` on all 21); every product carries the
    store file's display name."""
    assert {item["vendor"] for item in raw_distinct().values()} == {"herhighnessq8"}
    assert {product.store for product in all_products(store)} == {DISPLAY_NAME}


def test_stock_is_product_level_and_every_record_is_in_stock(store: StoreConfig) -> None:
    assert {item["available"] for item in raw_distinct().values()} == {True}
    assert {product.in_stock for product in all_products(store)} == {True}


def test_titles_with_an_apostrophe_and_a_dash_arrive_as_the_store_wrote_them(
    store: StoreConfig,
) -> None:
    """The store writes "Dara'a 2026" with a straight apostrophe and "MZIANA - Moroccan" with an en
    dash; both are kept verbatim."""
    titles = set(distinct_by_title(store))

    assert "Dara'a 2026" in titles
    assert MZIANA in titles


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
    store: StoreConfig,
) -> None:
    sent = ["daraa", "kaftan"]  # a store is sent at most two keyword variants, never a third
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
    # The second variant is sent only when the first gave fewer than second_variant_below
    # products; each saved answer has ten, so raise the setting to see both requests.
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
    assert result.dropped == {}
    assert {product.currency for product in result.products} == {"KWD"}
    # 20 records over the two answers; five "kaftan" records repeat a "daraa" one, and the engine
    # collapses repeats.
    assert len(result.products) == 15
    assert len({product.product_url for product in result.products}) == 15
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[SEARCH_URL.format(query=query) for query in sent],
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
