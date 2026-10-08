"""Daraat store adapter, offline (plan 12.14).

The fixtures in ``fixtures/`` are real answers from 2026-10-08, recorded by the orchestrator's
qualification script (honest User-Agent, robots.txt first, at least one second apart): one full
Shopify ``/search/suggest.json`` response each for ``kaftan``, ``daraa``, ``abaya`` and ``dress``.
Shopify caps the answer at 10 products and every product is kept; only each ``body`` (the HTML
description) was cut to 300 characters to keep the files small. ``robots.txt`` is the store's file,
byte for byte.

Everything here runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation and search engine.

This store prices in Kuwaiti dinars with three decimals (``"17.000"``); the response has no
currency, so ``currency: KWD`` comes from the store file (ADR 0006). Unlike Hamsa, every record has
one price (``price_min`` equals ``price_max``), so the store file sets no price option; a test pins
that, so a change in a later recording shows up.
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
from vga.rank.category import OUT_OF_SCOPE, classify_title
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
QUERIES = ["kaftan", "daraa", "abaya", "dress"]
"""One saved answer per query: ``fixtures/suggest-<query>.json``."""
FULL_FIXTURES = [f"suggest-{query}.json" for query in QUERIES]
PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
RECORDS_IN_ALL_FIXTURES = 40
DISTINCT_PRODUCTS_IN_ALL_FIXTURES = 28
"""The same product answers several queries: 40 records are 28 products."""

HOST = "www.daraat.com"
SEARCH_URL = (
    "https://www.daraat.com/search/suggest.json?q={query}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0710/6265/1110/files/"
"""Every image of the store is under this folder of the shared Shopify CDN."""
EN_DASH = chr(0x2013)

LONG_TITLE = (
    f"62 inch Tall Desert Rose Velvet Kaftan with Botanical Sleeves {EN_DASH} Limited Edition"
)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(name: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def distinct_raw() -> dict[str, dict[str, Any]]:
    """The 28 distinct raw records of the four answers, by handle, in first-seen order."""
    by_handle: dict[str, dict[str, Any]] = {}
    for name in FULL_FIXTURES:
        for record in raw_products(name):
            by_handle.setdefault(record["handle"], record)
    return by_handle


def raw_by_title() -> dict[str, dict[str, Any]]:
    return {record["title"]: record for record in distinct_raw().values()}


def replay(store: StoreConfig, name: str) -> ChainOutcome:
    """The saved response ``name`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(name), store, build_search_url(store, "kaftan")
    )


def all_products(store: StoreConfig) -> list[Product]:
    return [product for name in FULL_FIXTURES for product in replay(store, name).products]


def distinct_products(store: StoreConfig) -> dict[str, Product]:
    """The distinct valid products, by title (all 28 titles differ)."""
    distinct, _repeats = dedupe_products(all_products(store))
    return {product.title: product for product in distinct}


def handle_of(product: Product) -> str:
    return product.product_url.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------------------------
# The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == "daraat"
    assert store.display_name == "Daraat"
    assert (store.country, store.currency) == ("KW", "KWD")
    assert store.tier_hint is Tier.BUDGET
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        "https://www.daraat.com/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black kaftan") == SEARCH_URL.format(query="black%20kaftan")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_the_store_file_sets_no_extractor_option(store: StoreConfig) -> None:
    """No price guard (every record has one price, see below) and the default gender reading
    (nothing names a gender). If a later recording needs ``max_price_spread``, this test and the
    store file change together (docs/store-notes/daraat.md)."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {}


def test_a_mens_request_is_not_sent_to_this_womens_store(store: StoreConfig) -> None:
    assert store.genders == frozenset({Gender.WOMEN})
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)
    assert store.sells_for_gender(Gender.UNISEX)
    assert not store.sells_for_gender(Gender.MEN)


def test_only_a_dresses_search_is_sent_to_this_kaftan_and_dress_store(store: StoreConfig) -> None:
    # Every product seen here is a kaftan or a dress by the store's own `type` (a jumpsuit and a
    # "Sherwal" are filed there too), so a search for shoes, jeans, tops or jackets would only
    # waste a request to it (docs/store-notes/daraat.md).
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
    assert not robots.can_fetch(f"https://{HOST}/checkout", agent)
    assert not robots.can_fetch(f"https://{HOST}/cart.js", agent)


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
        assert product.store == "Daraat"


@pytest.mark.parametrize("name", FULL_FIXTURES)
def test_prices_keep_their_three_decimals_and_sit_in_the_garment_range(
    store: StoreConfig, name: str
) -> None:
    by_title = {record["title"]: record for record in raw_products(name)}

    for product in replay(store, name).products:
        assert len(by_title[product.title]["price"].split(".")[1]) == 3
        # A unit slip (fils read as dinars, or a thousands separator) would be a factor of 1,000
        # out. The recordings run from KWD 8 to 29.
        assert 5 <= product.price <= 50


def test_a_three_decimal_dinar_price_is_read_as_that_many_dinars(store: StoreConfig) -> None:
    prices = {title: product.price for title, product in distinct_products(store).items()}
    raw = raw_by_title()

    assert raw["Pink and Black Zigzag Cotton Kaftan"]["price"] == "17.000"
    assert prices["Pink and Black Zigzag Cotton Kaftan"] == 17.0
    assert prices["Boho Orange Beach & Resort Dress"] == 8.0
    assert prices["Black Floral Velvet Free-Size Kaftan"] == 29.0
    assert Counter(prices.values()) == {
        25.0: 10,
        19.0: 4,
        12.0: 4,
        18.0: 3,
        8.0: 3,
        29.0: 2,
        17.0: 1,
        20.0: 1,
    }


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


def test_the_four_recordings_give_twenty_eight_distinct_valid_products(
    store: StoreConfig,
) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == RECORDS_IN_ALL_FIXTURES
    assert len(distinct) == DISTINCT_PRODUCTS_IN_ALL_FIXTURES
    assert len(distinct) >= 20  # plan 12.x.2
    assert repeats == {"duplicate_url": RECORDS_IN_ALL_FIXTURES - DISTINCT_PRODUCTS_IN_ALL_FIXTURES}


# --------------------------------------------------------------------------------------------
# The price: one price on every record, so the default is the garment's
# --------------------------------------------------------------------------------------------


def test_every_record_has_a_single_price_and_no_variant_list_so_no_guard_is_needed(
    store: StoreConfig,
) -> None:
    """The Hamsa trap (``price`` is the cheapest variant, a scarf) is absent here: on all 40
    records ``price_min``, ``price_max`` and ``price`` agree. The answer's ``variants`` list is
    empty on all of them, so nothing else could say otherwise. If this test fails on a new
    recording, add ``max_price_spread: 1`` to the store file (docs/store-notes/daraat.md)."""
    records = [record for name in FULL_FIXTURES for record in raw_products(name)]

    assert len(records) == RECORDS_IN_ALL_FIXTURES
    for record in records:
        assert record["price_min"] == record["price_max"] == record["price"]
        assert record["variants"] == []
    for name in FULL_FIXTURES:
        for product in replay(store, name).products:
            assert product.price == float(raw_by_title()[product.title]["price"])


def test_the_price_is_what_the_shopper_pays_when_a_pre_sale_price_exists(
    store: StoreConfig,
) -> None:
    """Quirk: 16 of the 28 products carry a struck-through price (KWD 20, 39, 49 or 69) above
    the real one; the other 12 have ``"0.000"``. The adapter uses ``price`` and never the
    pre-sale figure."""
    raw = raw_by_title()
    products = distinct_products(store)
    marked_down = [r for r in raw.values() if float(r["compare_at_price_max"]) > float(r["price"])]

    assert len(marked_down) == 16
    assert Counter(r["compare_at_price_max"] for r in raw.values()) == {
        "0.000": 12,
        "39.000": 9,
        "49.000": 4,
        "69.000": 2,
        "20.000": 1,
    }
    assert raw["Pink and Black Zigzag Cotton Kaftan"]["compare_at_price_max"] == "39.000"
    assert products["Pink and Black Zigzag Cotton Kaftan"].price == 17.0  # not the pre-sale 39
    assert raw["Cotton Kaftan 187"]["compare_at_price_max"] == "0.000"
    assert products["Cotton Kaftan 187"].price == 19.0


# --------------------------------------------------------------------------------------------
# Other quirks of this store's data (docs/store-notes/daraat.md), pinned by the real responses
# --------------------------------------------------------------------------------------------


def test_handles_do_not_match_titles_so_the_link_is_always_the_stores_own(
    store: StoreConfig,
) -> None:
    """Quirk: copied products keep the old handle. "Cotton Kaftan 310" lives at
    ``cotton-kaftan-320`` and "Flow A-Line cotton kaftan 1" at ``cotton-kaftan-322``. Rebuilding a
    link from the title would send the shopper to the wrong product or to none."""
    link = {title: p.product_url for title, p in distinct_products(store).items()}

    assert link["Cotton Kaftan 310"] == f"https://{HOST}/products/cotton-kaftan-320"
    assert link["Flow A-Line cotton kaftan 1"] == f"https://{HOST}/products/cotton-kaftan-322"
    assert link["Royal Amethyst Velvet Kaftan"] == (
        f"https://{HOST}/products/sea-mist-velvet-kaftan-copy"
    )
    assert link["Black & White Beach & Resort Sherwal"] == (
        f"https://{HOST}/products/black-white-beach-resort-dress"
    )
    assert link["Layers kaftan dress-1"] == f"https://{HOST}/products/muccii-kaftan-69"


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = [record for name in FULL_FIXTURES for record in raw_products(name)]
    assert all("_pos=" in record["url"] for record in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_the_type_is_dress_on_nearly_everything_so_it_cannot_tell_a_kaftan_from_a_dress() -> None:
    """Quirk: 27 of 28 products have ``type`` "Dress", kaftans included. Only the first kaftan
    has ``type`` "Kaftan". The word "Kaftan" is in the title (18 of 28) or the tags (5 of 28)."""
    records = distinct_raw().values()

    assert Counter(record["type"] for record in records) == {"Dress": 27, "Kaftan": 1}
    [kaftan_type] = [record for record in records if record["type"] == "Kaftan"]
    assert kaftan_type["title"] == "Pink and Black Zigzag Cotton Kaftan"
    assert sum("kaftan" in record["title"].lower() for record in records) == 18
    assert sum("Kaftan" in record["tags"] for record in records) == 5
    assert sum("dress" in record["title"].lower() for record in records) == 8


@pytest.mark.parametrize("query", ["daraa", "abaya"])
def test_a_daraa_or_abaya_search_finds_neither_only_kaftans(query: str) -> None:
    """Quirk: the search pads its answer. No title, handle, tag or description (first 300
    characters) holds the word asked for; 9 of the 10 products are kaftans and the tenth is a
    dress ("daraa") or a jumpsuit ("abaya"). The shared ranker, not this adapter, has to judge
    them (docs/store-notes/daraat.md)."""
    records = raw_products(f"suggest-{query}.json")
    text = " ".join(
        " ".join([r["title"], r["handle"], *r["tags"], r["body"]]).lower() for r in records
    )

    assert query not in text
    assert sum("kaftan" in record["title"].lower() for record in records) == 9


def test_the_same_product_answers_several_queries_and_is_collapsed_by_its_link(
    store: StoreConfig,
) -> None:
    """Quirk: "Flow A-Line cotton kaftan 11" is in the kaftan, daraa and abaya answers. The
    first three queries give 19 distinct products between them, ``dress`` adds 9 (one of its ten
    was already in the daraa answer), and the engine collapses repeats within one search."""
    handles = {name: [r["handle"] for r in raw_products(name)] for name in FULL_FIXTURES}
    flow_11 = "flow-a-line-cotton-kaftan-11"

    assert [flow_11 in handles[name] for name in FULL_FIXTURES] == [True, True, True, False]
    first_three = {h for name in FULL_FIXTURES[:3] for h in handles[name]}
    assert len(first_three) == 19
    assert len(set(handles["suggest-dress.json"]) - first_three) == 9
    assert len(distinct_products(store)) == DISTINCT_PRODUCTS_IN_ALL_FIXTURES


def test_numbered_titles_of_one_print_are_different_products_and_all_are_kept(
    store: StoreConfig,
) -> None:
    """Quirk: seven "Flow A-Line cotton kaftan N" products share one price (KWD 25) and differ
    only in their number, image and link. The title-and-price de-duplication must not merge
    them, because the numbers make the titles differ."""
    flow = [p for p in distinct_products(store).values() if p.title.startswith("Flow A-Line")]

    assert sorted(p.title for p in flow) == [
        f"Flow A-Line cotton kaftan {n}" for n in (1, 10, 11, 5, 7, 8, 9)
    ]
    assert {p.price for p in flow} == {25.0}
    assert len({p.product_url for p in flow}) == 7
    assert len({p.image_url for p in flow}) == 7


def test_a_jumpsuit_and_a_sherwal_are_filed_as_dresses_and_handed_over_as_they_are(
    store: StoreConfig,
) -> None:
    """Quirk: the store files a jumpsuit and a "Sherwal" under ``type`` "Dress". The adapter does
    not judge garments: it hands both over, and the shared title reader decides (the jumpsuit is
    out of scope for every request; the Sherwal names no garment it knows, so it has no
    category). The Sherwal's own description says "Beach & resort dress"."""
    products = distinct_products(store)
    raw = raw_by_title()
    jumpsuit = "White jumpsuit with embroidery belt"
    sherwal = "Black & White Beach & Resort Sherwal"

    assert raw[jumpsuit]["type"] == raw[sherwal]["type"] == "Dress"
    assert products[jumpsuit].price == 20.0
    assert products[sherwal].price == 8.0
    assert classify_title(jumpsuit) == OUT_OF_SCOPE
    assert classify_title(sherwal) is None
    assert "Beach &amp; resort dress" in raw[sherwal]["body"]  # the description is HTML


def test_the_titles_name_a_dress_category_garment_on_twenty_five_of_twenty_eight() -> None:
    """The ranker's reading of the 28 titles, the same one every request goes through: 25 are
    dresses (kaftans and dresses), the jumpsuit is out of scope, and two name no garment word
    ("Pink Orange Midi Long Sleeve" and the Sherwal) and are kept without a category."""
    kinds = Counter(classify_title(title) for title in raw_by_title())

    assert kinds == {Category.DRESSES: 25, OUT_OF_SCOPE: 1, None: 2}


def test_one_product_has_another_vendor_and_still_carries_the_stores_name(
    store: StoreConfig,
) -> None:
    """Quirk: "Layers kaftan dress-1" has ``vendor`` "Muccii Outlet" (27 of 28 say "Daraat"); its
    description ends "Layers kaftan store in Kuwait". The adapter does not read ``vendor``: every
    product carries the store file's display name."""
    raw = distinct_raw().values()
    products = distinct_products(store)

    assert Counter(record["vendor"] for record in raw) == {"Daraat": 27, "Muccii Outlet": 1}
    assert raw_by_title()["Layers kaftan dress-1"]["vendor"] == "Muccii Outlet"
    assert {product.store for product in products.values()} == {"Daraat"}


def test_nothing_in_the_type_or_tags_names_a_gender_so_the_store_file_carries_it(
    store: StoreConfig,
) -> None:
    """The store is women's wear, but it never says so in a field: every product's gender is
    unknown, and ``genders: [women]`` in the store file does the work."""
    assert {product.gender for product in all_products(store)} == {None}


def test_every_product_is_marked_in_stock_by_the_stores_own_flag(store: StoreConfig) -> None:
    """Stock is product-level only (``available``); a size can still be sold out."""
    assert all(record["available"] is True for record in distinct_raw().values())
    assert all(product.in_stock for product in all_products(store))


def test_images_may_be_png_or_jpg_and_both_are_accepted(store: StoreConfig) -> None:
    extensions = Counter(
        urlsplit(product.image_url).path.rsplit(".", 1)[-1]
        for product in distinct_products(store).values()
    )

    assert extensions == {"png": 15, "jpg": 13}


def test_a_long_title_with_a_leading_number_and_an_en_dash_is_kept_whole_and_as_written(
    store: StoreConfig,
) -> None:
    """Quirk: titles are free text. This one starts with a number and holds an en dash; another
    starts with a lower-case letter ("long Sleeve Pink Maxi Summer Dress"). The adapter does not
    re-case or shorten them."""
    titles = set(distinct_products(store))

    assert LONG_TITLE in titles
    assert len(LONG_TITLE) == 79
    assert "long Sleeve Pink Maxi Summer Dress" in titles
    assert all(title == title.strip() and "  " not in title for title in titles)


# --------------------------------------------------------------------------------------------
# The whole search engine on the saved answers (robots.txt, URL, honest User-Agent)
# --------------------------------------------------------------------------------------------


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
    store: StoreConfig,
) -> None:
    sent = ["kaftan", "dress"]  # a store is sent at most two keyword variants, never a third
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
            make_item_intent(search_keywords=sent),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 20  # the kaftan and dress answers share no product
    assert result.dropped == {}
    assert {product.currency for product in result.products} == {"KWD"}
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[SEARCH_URL.format(query=query) for query in sent],
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
