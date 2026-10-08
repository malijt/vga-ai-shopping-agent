"""Shadow store adapter, offline (plan 12.15).

The fixtures in ``fixtures/`` are real answers from 2026-10-08: one full Shopify
``/search/suggest.json`` response each for ``abaya`` (10 products), ``kaftan`` (9), ``dress`` (5)
and ``black abaya`` (10; the file is ``suggest-black-abaya.json``, a hyphen where the query has a
space). Only each product's ``body`` (the HTML description) was cut to 300 characters to keep the
files small. ``robots.txt`` is the store's file, byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"69.000"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006). Unlike Hamsa, no record has
variants at different prices, so the file sets no price guard. Its real quirks are the padding
(a ``kaftan`` or ``dress`` search returns sheilas and caps, not kaftans or dresses), repeated
titles, and a pre-sale price that is below the price; the tests below pin each with a real record.
"""

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from protego import Protego
from tests.factories import make_item_intent, make_settings
from tests.fakes import FakeClock

from vga.models import Category, Gender, Product, StoreConfig, StoreStatus, Tier
from vga.rank import classify_title
from vga.rank.category import OUT_OF_SCOPE
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["abaya", "kaftan", "dress", "black abaya"]
"""One saved answer per query. A space in the query is a hyphen in the file name."""

RAW_RECORDS = {"abaya": 10, "kaftan": 9, "dress": 5, "black abaya": 10}
"""How many products each saved answer holds. Shopify caps an answer at 10; only ``kaftan`` and
``dress`` came back short, because the store had nothing else to match."""
KEPT_RECORDS = {"abaya": 9, "kaftan": 9, "dress": 5, "black abaya": 9}
"""How many survive validation. ``abaya`` and ``black abaya`` each hold one record that repeats an
earlier one (same title, same price, another handle); nothing else is dropped."""
DISTINCT_PRODUCTS = 24
"""34 records, 32 kept per answer, 24 once a product that answers two queries is counted once."""

HOST = "shadow.com.kw"
SEARCH_URL = (
    "https://shadow.com.kw/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0903/6224/9463/files/"
"""Every image of the store is under this folder of the shared Shopify CDN."""

SHEILAS = [
    "Special Chiffon Crystalized Shaila",
    "Sepcial Chiffon Crystalized Shaila",
    "Sepcial Chiffon Folding Shaila",
]
"""Three titles for four sheilas: "Special Chiffon Crystalized Shaila" is on two handles, at
KWD 18.9 and KWD 19."""
CAPS = ["Cotton Plain Taqiyah Triangle", "Cotton Plain Taqiyah Tie Plain"]
ACCESSORY_TITLES = [*SHEILAS, *CAPS]


def fixture_name(query: str) -> str:
    return f"suggest-{query.replace(' ', '-')}.json"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(query: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(fixture_name(query)))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def all_raw_records() -> list[dict[str, Any]]:
    return [item for query in QUERIES for item in raw_products(query)]


def raw_by_handle() -> dict[str, dict[str, Any]]:
    """The 26 distinct products the four answers hold, by handle."""
    return {item["handle"]: item for item in all_raw_records()}


def raw_of(product: Product) -> dict[str, Any]:
    """The saved record a product was read from, found by the handle at the end of its link."""
    return raw_by_handle()[product.product_url.rsplit("/", 1)[1]]


def replay(store: StoreConfig, query: str) -> ChainOutcome:
    """The saved answer for ``query`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(fixture_name(query)), store, build_search_url(store, query)
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for query in QUERIES for product in replay(store, query).products]


def distinct_products(store: StoreConfig) -> list[Product]:
    distinct, _repeats = dedupe_products(all_products(store))
    return distinct


# --------------------------------------------------------------------------------------------
# The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "shadow-kw"
    assert store.display_name == "Shadow"
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.MID_RANGE
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://shadow.com.kw/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black abaya") == SEARCH_URL.format(query="black%20abaya")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_the_store_file_sets_no_extractor_option(store: StoreConfig) -> None:
    """No price guard and no gender field are needed on this data (see the tests on the spread and
    on the gender below). If a later answer needs an option, this test names the change."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {}


def test_a_mens_request_is_not_sent_to_this_women_only_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_abaya_store(store: StoreConfig) -> None:
    # Every garment seen here is an abaya (20 of 26 distinct records; the other 6 are accessories),
    # so a search for shoes, jeans, tops or jackets would only waste a request to it.
    assert store.categories == frozenset({Category.DRESSES})
    assert store.sells_category(Category.DRESSES)
    for other in (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart(store: StoreConfig) -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(build_search_url(store, query), agent)
    assert not robots.can_fetch(f"https://{HOST}/cart/", agent)  # parsed, not allow-all
    assert not robots.can_fetch(f"https://{HOST}/checkout", agent)
    assert not robots.can_fetch(f"https://{HOST}/cart.js", agent)


# --------------------------------------------------------------------------------------------
# The fixtures through the real extraction chain
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_recording_is_read_in_full_by_the_shopify_strategy(
    store: StoreConfig, query: str
) -> None:
    outcome = replay(store, query)

    assert len(raw_products(query)) == RAW_RECORDS[query]
    assert outcome.strategy == "shopify"
    assert outcome.examined == RAW_RECORDS[query]
    assert len(outcome.products) == KEPT_RECORDS[query]


def test_the_only_records_dropped_repeat_an_earlier_one_in_the_same_answer(
    store: StoreConfig,
) -> None:
    dropped = {query: replay(store, query).dropped for query in QUERIES}

    assert dropped == {
        "abaya": {"duplicate_title_price": 1},
        "kaftan": {},
        "dress": {},
        "black abaya": {"duplicate_title_price": 1},
    }


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_all_six_required_fields_and_a_dinar_price(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "KWD"
        assert product.image_url
        assert product.product_url
        assert product.store == "Shadow"


@pytest.mark.parametrize("query", QUERIES)
def test_prices_keep_their_three_decimals_and_sit_in_the_range_seen(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        assert len(raw_of(product)["price"].split(".")[1]) == 3
        # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000
        # out. The records seen run from KWD 4 (a cap) to KWD 180 (an abaya).
        assert 4 <= product.price <= 180


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    products = replay(store, "abaya").products
    prices = {p.title: p.price for p in products}

    assert raw_by_handle()["sh11260126021"]["price"] == "69.000"
    assert prices["Sumou Abaya (Linen)"] == 69.0
    assert prices["BEIGE CREPE CRYSTALIZED OPEN ABAYA."] == 180.0
    assert prices["BLACK HAND EMBROIDERED KAMELIA CLOSE ABAYA"] == 39.0


def test_a_dinar_price_with_fils_keeps_them(store: StoreConfig) -> None:
    products = replay(store, "kaftan").products
    [sheila] = [p for p in products if p.product_url.endswith("/sh13240108534")]

    assert raw_of(sheila)["price"] == "18.900"
    assert sheila.price == 18.9
    assert {p.price for p in products if "Shaila" in p.title} == {13.0, 16.9, 18.9, 19.0}


def test_the_same_three_decimal_prices_are_refused_if_the_store_were_priced_in_dirhams(
    store: StoreConfig,
) -> None:
    """Why ``currency: KWD`` matters: ``"69.000"`` is a price only for a three-decimal currency.
    Read as dirhams it is refused (it more likely hides a thousands separator), so every record
    would be dropped, not shown at a price a thousand times out."""
    as_dirhams = store.model_copy(update={"currency": "AED"})

    outcome = replay(as_dirhams, "abaya")

    assert outcome.products == []
    assert outcome.dropped == {"unknown_price_format": 10}


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
def test_image_urls_carry_width_400_and_keep_the_version_parameter(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params


def test_the_four_recordings_give_at_least_twenty_distinct_valid_products(
    store: StoreConfig,
) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 32  # 34 records, 2 collapsed inside their own answer
    assert len(distinct) == DISTINCT_PRODUCTS
    assert len(distinct) >= 20  # plan 12.x.2
    assert repeats == {"duplicate_url": 8}  # the same handle answering two queries
    assert len(raw_by_handle()) == 26  # 34 records are 26 handles; 2 of them repeat a title


def test_18_of_the_24_distinct_products_are_abayas_and_6_are_accessories(
    store: StoreConfig,
) -> None:
    """The honest count behind the 20 distinct products: the store's garments are abayas only."""
    kinds = {item["handle"]: item["type"] for item in all_raw_records()}
    links = {p.product_url.rsplit("/", 1)[1] for p in distinct_products(store)}

    assert sorted(kinds[handle] for handle in links) == [
        *["ABAYA SET"] * 18,
        *["ACCESSORIES"] * 2,
        *["SHEILA"] * 4,
    ]


# --------------------------------------------------------------------------------------------
# Quirks of this store's data (docs/store-notes/shadow-kw.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_no_record_has_variants_at_different_prices_so_no_price_guard_is_needed() -> None:
    """The Hamsa trap, looked for and not found: on all 34 records ``price`` equals ``price_min``
    and ``price_max``, so the cheapest variant is the only price. The ``variants`` list in the
    answer is empty on every record, so the check rests on those two fields; the one product page
    read had 54 variant offers, all KWD 69."""
    records = all_raw_records()

    assert len(records) == 34
    for item in records:
        assert item["price"] == item["price_min"] == item["price_max"]
        assert item["variants"] == []


@pytest.mark.parametrize("query", ["kaftan", "dress"])
def test_a_kaftan_or_dress_search_is_padded_with_accessories_and_the_adapter_keeps_them(
    store: StoreConfig, query: str
) -> None:
    """Quirk: the store sells no kaftan and no dress. "kaftan" returns 9 products: 4 sheilas (head
    scarves, type SHEILA), 2 taqiyah caps (type ACCESSORIES) and 3 abayas. "dress" returns 3 of
    those sheilas and 2 of those abayas. The adapter makes no store-specific exclusion: dropping
    accessories is the ranker's job, for every store."""
    raw = raw_products(query)
    accessories = [p for p in raw if p["type"] in {"SHEILA", "ACCESSORIES"}]
    kept_handles = {p.product_url.rsplit("/", 1)[1] for p in replay(store, query).products}

    assert [p["type"] for p in raw].count("ABAYA SET") == {"kaftan": 3, "dress": 2}[query]
    assert len(accessories) == {"kaftan": 6, "dress": 3}[query]
    assert {p["handle"] for p in accessories} <= kept_handles
    assert kept_handles == {p["handle"] for p in raw}  # everything is handed over


def test_sheilas_and_caps_cost_far_less_than_any_abaya_so_they_would_distort_a_price_range(
    store: StoreConfig,
) -> None:
    """The four sheilas are KWD 13 to 19 (about AED 155 to 226) and the caps KWD 4 and 5; the
    cheapest abaya is KWD 39 (about AED 465)."""
    products = distinct_products(store)
    sheila_prices = {p.price for p in products if p.title in SHEILAS}
    cap_prices = {p.price for p in products if p.title in CAPS}
    abaya_prices = [p.price for p in products if p.title not in ACCESSORY_TITLES]

    assert sheila_prices == {13.0, 16.9, 18.9, 19.0}
    assert cap_prices == {4.0, 5.0}
    assert (min(abaya_prices), max(abaya_prices)) == (39.0, 180.0)
    assert max(sheila_prices) < min(abaya_prices)


def test_the_ranker_puts_every_sheila_and_cap_outside_the_five_categories() -> None:
    """Hanayen's "Sheila" was already in the ranker's accessory list; Shadow's spelling "Shaila"
    and its "Taqiyah" cap were added on 2026-10-08, when this store was qualified. Without them
    the ranker read these titles as "no category", and a product whose category cannot be read
    is kept for every request (ADR 0007)."""
    assert [classify_title(title) for title in ACCESSORY_TITLES] == [OUT_OF_SCOPE] * 5


def test_the_rankers_category_reader_reads_every_abaya_as_a_dress() -> None:
    """What ``categories: [dresses]`` relies on: the title word "abaya" is in the dresses list, so
    an abaya of this store passes the category filter for a dresses request."""
    abayas = [item for item in raw_by_handle().values() if item["type"] == "ABAYA SET"]

    assert len(abayas) == 20
    assert {classify_title(item["title"]) for item in abayas} == {Category.DRESSES}


def test_some_titles_repeat_across_handles_and_the_repeats_collapse_within_an_answer(
    store: StoreConfig,
) -> None:
    """Quirk: the abaya answer holds "BLACK TRENDY SOALON OPEN  ABAYA" twice, at KWD 59 under
    two handles; the black abaya answer holds "BLACK EMBROIDERED SOALON CLOSE ABAYA" at KWD 59 under
    two handles and again at KWD 63. Same title and price counts as one product; the KWD 63
    one is a different product and stays."""
    abaya = replay(store, "abaya")
    black = replay(store, "black abaya")
    raw_abaya = raw_products("abaya")
    raw_black = raw_products("black abaya")

    open_abayas = [p for p in raw_abaya if p["title"] == "BLACK TRENDY SOALON OPEN  ABAYA"]
    assert [p["price"] for p in open_abayas] == ["59.000", "59.000"]
    assert len({p["handle"] for p in open_abayas}) == 2
    assert [p.title for p in abaya.products].count("BLACK TRENDY SOALON OPEN ABAYA") == 1

    closed = [p for p in raw_black if p["title"] == "BLACK EMBROIDERED SOALON CLOSE ABAYA"]
    assert sorted(p["price"] for p in closed) == ["59.000", "59.000", "63.000"]
    kept_closed = sorted(
        p.price for p in black.products if p.title == "BLACK EMBROIDERED SOALON CLOSE ABAYA"
    )
    assert kept_closed == [59.0, 63.0]


def test_titles_are_single_spaced_but_otherwise_the_stores_own_with_its_typing_slips(
    store: StoreConfig,
) -> None:
    """Quirk: double spaces ("OPEN  ABAYA"), a trailing full stop ("ABAYA."), and misspellings that
    the store itself uses ("TRIBPLE", "GEOMERTIC EMBROIDEREY", "Sepcial"). Whitespace is cleaned by
    the normaliser; the spelling is not touched."""
    titles = {p.title for p in all_products(store)}

    assert "BLACK TRENDY SOALON OPEN ABAYA" in titles
    assert "BEIGE CREPE CRYSTALIZED OPEN ABAYA." in titles
    assert "BEIGE TRIBPLE CLOSH CREPE OPEN ABAYA" in titles
    assert "BLACK GEOMERTIC EMBROIDEREY SOALON ABAYA." in titles
    assert "Sepcial Chiffon Crystalized Shaila" in titles
    assert all("  " not in title for title in titles)


def test_a_pre_sale_price_is_never_above_the_price_so_nothing_here_is_a_discount(
    store: StoreConfig,
) -> None:
    """Quirk: ``compare_at_price_max`` is "0.000" on 20 of the 26 distinct products, equal to the
    price on 5 (KWD 49, 59, 59, 59 and 68) and KWD 75 on an abaya that costs KWD 129, which is
    below the price. None is above it, so there is no struck-through sale price to read. The
    adapter uses ``price`` only."""
    raw = list(raw_by_handle().values())
    prices = {p.title: p.price for p in replay(store, "abaya").products}

    assert sum(item["compare_at_price_max"] == "0.000" for item in raw) == 20
    assert sum(item["compare_at_price_max"] == item["price"] for item in raw) == 5
    assert [
        item["title"]
        for item in raw
        if item["compare_at_price_max"] != "0.000"
        and float(item["compare_at_price_max"]) != float(item["price"])
    ] == ["BLACK EMBROIDERED ROLEX OPEN ABAYA"]
    assert not any(float(item["compare_at_price_max"]) > float(item["price"]) for item in raw)
    assert raw_by_handle()["sh11250105688"]["compare_at_price_max"] == "75.000"
    assert prices["BLACK EMBROIDERED ROLEX OPEN ABAYA"] == 129.0


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    assert all("_pos=" in item["url"] for item in all_raw_records())  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_handles_are_style_codes_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: every handle is a code ("sh11260126021") that says nothing about the title, so a link
    can only come from the answer's ``url`` and never be rebuilt from a name."""
    links = {p.title: p.product_url for p in replay(store, "abaya").products}

    assert links["Sumou Abaya (Linen)"] == "https://shadow.com.kw/products/sh11260126021"
    assert links["BEIGE CREPE CRYSTALIZED OPEN ABAYA."] == (
        "https://shadow.com.kw/products/sh11210116181"
    )
    assert all(item["handle"].startswith("sh1") for item in all_raw_records())


def test_the_vendor_has_three_spellings_and_the_shoppers_store_name_is_one(
    store: StoreConfig,
) -> None:
    """Quirk: one brand, three ``vendor`` values ("Shadow", "Shadow KW", "SHADOW"). The adapter
    does not read ``vendor``; every product carries the store file's display name."""
    vendors = {item["vendor"] for item in all_raw_records()}

    assert vendors == {"Shadow", "Shadow KW", "SHADOW"}
    assert {product.store for product in all_products(store)} == {"Shadow"}


def test_a_linen_blazer_and_trousers_set_is_filed_and_titled_as_an_abaya(
    store: StoreConfig,
) -> None:
    """Quirk: "BEIGE LINEN TRENDY OPEN ABAYA" (type ABAYA SET, KWD 62) is described as "A BLAZER SET
    WITH PANT AND TOP". The title says abaya, so the ranker will read it as a dress; the adapter
    shows what the store titles."""
    [item] = [p for p in raw_products("abaya") if p["title"] == "BEIGE  LINEN TRENDY OPEN ABAYA"]
    prices = {p.title: p.price for p in replay(store, "abaya").products}

    assert item["type"] == "ABAYA SET"
    assert "BLAZER SET WITH PANT AND TOP" in item["body"]
    assert prices["BEIGE LINEN TRENDY OPEN ABAYA"] == 62.0


def test_an_abaya_is_sold_as_a_set_with_a_sheila_so_its_price_is_the_sets(
    store: StoreConfig,
) -> None:
    """Quirk: all 20 abaya records have type "ABAYA SET", and the descriptions say so: "ABAYA SET
    HAS SHAILA INCLUDED" (12 of the 20 in the full answers, 4 within the 300 characters kept in
    these files). The price is the set's. The sheilas sold on their own are separate records at
    KWD 13 to 19, which is why this is not the Hamsa trap of a scarf priced as a variant."""
    raw = raw_by_handle()
    abayas = [item for item in raw.values() if item["type"] == "ABAYA SET"]
    included = [
        item["handle"]
        for item in abayas
        if re.search(r"(?i)(sheila|shaila) included", re.sub(r"<[^>]+>", " ", item["body"]))
    ]
    products = {p.product_url.rsplit("/", 1)[1]: p for p in all_products(store)}

    assert len(abayas) == 20
    assert len(included) == 4
    assert "ABAYA SET HAS SHAILA INCLUDED" in raw["sh11240207616"]["body"]
    assert products["sh11240207616"].price == 39.0  # the set, sheila included


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field: every product's gender is
    unknown, and ``genders: [women]`` in the store file does the work."""
    types = {item["type"] for item in all_raw_records()}
    tags = {tag for item in all_raw_records() for tag in item["tags"]}

    assert types == {"ABAYA SET", "SHEILA", "ACCESSORIES"}
    assert tags == {"ABAYA SET", "SHEILA", "tag__new_new"}
    assert {product.gender for product in all_products(store)} == {None}


def test_every_record_is_marked_in_stock_at_product_level(store: StoreConfig) -> None:
    assert all(item["available"] is True for item in all_raw_records())
    assert {product.in_stock for product in all_products(store)} == {True}


def test_the_same_product_can_answer_two_queries_and_repeats_collapse(store: StoreConfig) -> None:
    kaftan = replay(store, "kaftan").products
    dress = replay(store, "dress").products

    distinct, repeats = dedupe_products([*kaftan, *dress])

    assert len(kaftan) + len(dress) == 14
    assert len(distinct) == 9  # the whole "dress" answer is a subset of the "kaftan" one
    assert repeats == {"duplicate_url": 5}


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


def answering_from_fixtures(seen: list[httpx.Request]) -> httpx.MockTransport:
    """A fake network that serves the saved robots.txt and the saved answer for each query."""

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

    return httpx.MockTransport(answer)


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
    store: StoreConfig,
) -> None:
    sent = ["abaya", "kaftan"]  # a store is sent at most two keyword variants, never a third
    seen: list[httpx.Request] = []

    # A Kuwaiti store is searched only when Kuwait is among the extra countries (settings.yaml).
    # The second variant is sent only when the first gave fewer than second_variant_below
    # products; each saved answer has about ten, so raise the setting to see both requests.
    settings = make_settings(extra_store_countries=["KW"], second_variant_below=50)
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=answering_from_fixtures(seen))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=sent),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 18  # 9 + 9, no product answers both
    assert result.dropped == {"duplicate_title_price": 1}
    assert {product.currency for product in result.products} == {"KWD"}
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[SEARCH_URL.format(query=query) for query in sent],
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}


async def test_a_two_word_query_is_sent_percent_encoded_and_answered_from_the_hyphenated_file(
    store: StoreConfig,
) -> None:
    seen: list[httpx.Request] = []
    settings = make_settings(extra_store_countries=["KW"])
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=answering_from_fixtures(seen))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=["black abaya"]),
            [store.model_copy(update={"enabled": True})],
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert len(result.products) == 9
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        SEARCH_URL.format(query="black%20abaya"),
    ]
