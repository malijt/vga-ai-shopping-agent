"""Gul Ahmed UAE store adapter, offline (plan 12.19).

The files in ``fixtures/`` are real answers from 2026-10-08: ``suggest-<query>.json`` is one full
Shopify ``/search/suggest.json`` response per query (``shalwar kameez``, ``kurta``, ``kurti`` and
``printed shirt``; a space in the query is a hyphen in the file name). Shopify caps an answer at 10
products and every product is kept; only each ``body`` (the HTML description) was cut to 300
characters. ``robots.txt`` is the store's file, byte for byte. The orchestrator's qualification run
saved them; no network is used here.

Everything runs with no network: the store file goes through the real registry loader and the
fixtures through the real extraction chain, validation, the ranker's title reading and the search
engine.

This store is the UAE storefront of a Pakistani clothing house. Its data has several quirks, each
pinned below with real records (docs/store-notes/gul-ahmed-uae.md):

- Many different products share one title, so the app's "same title, same price" rule collapses 32
  products into 20.
- Every title starts with ``UAE-`` in three spellings, and some end with a style code.
- Some records have variants at two prices. It is the sale price against the full price of the same
  garment, not an add-on, so the store file does not set ``max_price_spread``.
- Gender is in ``type`` ("Men", "Women"), not in the title.
- A men's shalwar kameez is titled "Suits" (no category) and a women's kurti is titled "Shirt"
  (tops).
"""

import json
import re
from collections import Counter
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
    ItemIntent,
    Product,
    StoreConfig,
    StoreStatus,
    StrategyConfig,
    Tier,
)
from vga.rank.category import classify_title
from vga.rank.filters import DropReason, apply_hard_filters
from vga.rank.lexicon import tokenize
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
STORE_ID = "gul-ahmed-uae"
DISPLAY_NAME = "Gul Ahmed UAE"
HOST = "uae.gulahmedshop.com"
CURRENCY = "AED"
QUERIES = ["shalwar kameez", "kurta", "kurti", "printed shirt"]
"""One saved answer per query: ``fixtures/suggest-<query with hyphens>.json``."""

PRODUCTS_IN_EACH_FIXTURE = 10
"""Shopify's cap: each recorded response is a full answer."""
KEPT_AND_COLLAPSED = {
    "shalwar kameez": (8, 2),
    "kurta": (6, 4),
    "kurti": (7, 3),
    "printed shirt": (5, 5),
}
"""Per answer: records kept, and records collapsed as ``duplicate_title_price`` in that answer."""
RECORDS_IN_ALL_FIXTURES = 40
DISTINCT_HANDLES = 32
"""The 40 records are 32 different products (a handle is a product)."""
DISTINCT_PRODUCTS = 20
"""What the app keeps: the same normalised title at the same price counts as one product."""

SEARCH_URL = (
    f"https://{HOST}/search/suggest.json?q={{query}}"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)
IMAGE_FOLDER = "/s/files/1/0652/2100/1325/"
"""Every image of the store is under this folder of the shared Shopify CDN."""

# The five products whose variants cost two prices. For each: the lowest price (``price``), the
# highest (``price_max``) and the pre-sale price (``compare_at_price_max``), the same figure.
SPREAD_PRODUCTS = {
    "uae-regular-fit-embroidered-kurta-kr-emb25-028": ("53.50", "89.00", "89.00"),
    "uae-regular-fit-styling-kurta-kr-sty25-079": ("53.50", "89.00", "89.00"),
    "uae-regular-fit-styling-kurta-kr-sty25-084": ("53.50", "89.00", "89.00"),
    "uae-regular-fit-styling-suits-sk-bsc25-111": ("101.50", "169.00", "169.00"),
    "uae-regular-fit-styling-waist-coat-wc-sty25-018": ("101.50", "169.00", "169.00"),
}
SAME_TITLE_HANDLES = [
    "uae-regular-fit-styling-kurta-kr-sty25-079",
    "uae-regular-fit-styling-kurta-kr-sty25-084",
    "uae-regular-fit-styling-kurta-kr-sty25-086",
    "uae-regular-fit-styling-kurta-kr-sty25-001",
]
"""Four products with the title "UAE-Regular Fit Styling Kurta" at AED 53.50."""


def fixture_name(query: str) -> str:
    return f"suggest-{query.replace(' ', '-')}.json"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_products(query: str) -> list[dict[str, Any]]:
    data = json.loads(fixture_text(fixture_name(query)))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def all_raw() -> list[dict[str, Any]]:
    return [record for query in QUERIES for record in raw_products(query)]


def raw_by_handle() -> dict[str, dict[str, Any]]:
    return {record["handle"]: record for record in all_raw()}


def handle_of(product: Product) -> str:
    return urlsplit(product.product_url).path.rsplit("/", 1)[-1]


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


def with_options(store: StoreConfig, **options: Any) -> StoreConfig:
    """The same store with extra ``shopify`` options: what the file would do with another line."""
    [strategy] = store.extraction.strategies
    changed = StrategyConfig(name="shopify", options={**strategy.options, **options})
    return store.model_copy(update={"extraction": ExtractionConfig(strategies=[changed])})


def design_name(record: dict[str, Any]) -> str:
    """The design code the description starts with ("Design Name : KR-STY25-079")."""
    found = re.search(r"Design Name : ([A-Z0-9-]+)", record["body"])
    assert found, record["handle"]
    return found.group(1)


def request_for(category: Category, gender: Gender | None = None) -> ItemIntent:
    """A request for one garment of ``category``; ``gender`` is stated by the shopper if given."""
    return make_item_intent(
        category=category,
        colour=None,
        style=None,
        gender=gender,
        gender_source=GenderSource.EXPLICIT if gender else GenderSource.NONE,
        search_keywords=["kurta"],
    )


# --- The store file (plan 12.19.1) -------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == STORE_ID
    assert store.display_name == DISPLAY_NAME
    assert (store.country, store.currency) == ("AE", CURRENCY)
    assert store.tier_hint is Tier.BUDGET
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        f"https://{HOST}/search/suggest.json?q={{query}}&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "shalwar kameez") == SEARCH_URL.format(query="shalwar%20kameez")


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_the_store_file_decides_gender_from_type_then_tags_and_sets_no_price_guard(
    store: StoreConfig,
) -> None:
    """``max_price_spread`` is absent on purpose: the two-price records are a sale on the same
    garment (the price tests below), and the option would drop 7 of 40 records. If a real add-on
    variant ever shows up here, add the option and change this test (docs/store-notes)."""
    [strategy] = store.extraction.strategies

    assert strategy.options == {"gender_fields": ["type", "tags"]}


def test_the_store_is_searched_for_either_gender_because_it_sells_both(
    store: StoreConfig,
) -> None:
    assert store.genders is None
    assert store.sells_for_gender(Gender.MEN)
    assert store.sells_for_gender(Gender.WOMEN)
    assert store.sells_for_gender(None)


def test_only_dresses_and_tops_searches_are_sent_to_this_store(store: StoreConfig) -> None:
    # Kurtas and "Suits" are the dresses search; the women's kurtis (titled "Shirt") are tops.
    # No trousers, jackets or shoes were seen (docs/store-notes/gul-ahmed-uae.md); the one men's
    # waistcoat is read as outerwear by its title and is not searched for.
    assert store.categories == frozenset({Category.DRESSES, Category.TOPS})
    assert store.sells_category(Category.DRESSES)
    assert store.sells_category(Category.TOPS)
    for other in (Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES):
        assert not store.sells_category(other)


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart(store: StoreConfig) -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(build_search_url(store, query), agent)
    assert robots.can_fetch(f"https://{HOST}/products/uae-regular-fit-embroidered-suits", agent)
    assert not robots.can_fetch(f"https://{HOST}/cart/", agent)  # parsed, not allow-all
    assert not robots.can_fetch(f"https://{HOST}/checkout", agent)


# --- The saved answers through the real extraction chain (plan 12.19.2) ------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_saved_answer_is_read_in_full_and_repeats_inside_it_are_collapsed(
    store: StoreConfig, query: str
) -> None:
    kept, collapsed = KEPT_AND_COLLAPSED[query]
    outcome = replay(store, query)

    assert len(raw_products(query)) == PRODUCTS_IN_EACH_FIXTURE
    assert outcome.strategy == "shopify"
    assert outcome.examined == PRODUCTS_IN_EACH_FIXTURE
    assert len(outcome.products) == kept
    # Nothing is dropped for a missing field or a bad link: every loss is a repeat of an earlier
    # title at the same price (see the same-title test below).
    assert outcome.dropped == {"duplicate_title_price": collapsed}


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_the_six_required_fields_and_stays_on_allowed_hosts(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == CURRENCY
        assert product.store == DISPLAY_NAME
        assert product.in_stock is True
        assert urlsplit(product.product_url).scheme == "https"
        assert urlsplit(product.product_url).hostname == HOST
        assert urlsplit(product.product_url).path.startswith("/products/")
        assert urlsplit(product.product_url).query == ""  # tracking parameters removed
        assert urlsplit(product.image_url).scheme == "https"
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert urlsplit(product.image_url).path.startswith(IMAGE_FOLDER)
        assert parse_qs(urlsplit(product.image_url).query)["width"] == ["400"]
        assert "v" in parse_qs(urlsplit(product.image_url).query)


@pytest.mark.parametrize("query", QUERIES)
def test_prices_are_two_decimal_aed_amounts_in_a_plausible_range(
    store: StoreConfig, query: str
) -> None:
    raw = {record["handle"]: record for record in raw_products(query)}

    for product in replay(store, query).products:
        assert len(raw[handle_of(product)]["price"].split(".")[1]) == 2
        assert 41.5 <= product.price <= 149  # a unit slip would be far outside the garment range


def test_the_saved_answers_give_at_least_twenty_distinct_valid_products(
    store: StoreConfig,
) -> None:
    every_product = all_products(store)
    distinct, repeats = dedupe_products(every_product)

    assert len(every_product) == 26  # 40 records, 14 repeats collapsed inside the four answers
    assert len(distinct) == DISTINCT_PRODUCTS  # exactly the plan's floor of 20
    assert len(distinct) >= 20  # plan 12.19.2
    assert repeats == {"duplicate_url": 4, "duplicate_title_price": 2}


# --- Quirks of this store's data (docs/store-notes/gul-ahmed-uae.md), pinned with real records --


def test_many_different_products_share_one_title_and_the_app_collapses_them(
    store: StoreConfig,
) -> None:
    """Quirk 1. "UAE-Regular Fit Styling Kurta" at AED 53.50 is four products: four handles, four
    design codes, four pictures (lite green, sky blue, beige, green). The app's "same title, same
    price" rule keeps one of them, so 32 products come out as 20 and 12 real products never reach
    the shopper. The adapter cannot tell them apart: the title carries nothing that differs."""
    raw = raw_by_handle()
    same = [raw[handle] for handle in SAME_TITLE_HANDLES]

    assert {record["title"] for record in same} == {"UAE-Regular Fit Styling Kurta"}
    assert {record["price"] for record in same} == {"53.50"}
    assert len({record["image"].split("?")[0] for record in same}) == 4  # four different garments
    assert [design_name(record) for record in same] == [
        "KR-STY25-079",
        "KR-STY25-084",
        "KR-STY25-086",
        "KR-STY25-001",
    ]

    shown = [p for p in distinct_products(store) if p.title == "UAE-Regular Fit Styling Kurta"]
    assert len(raw) == DISTINCT_HANDLES
    assert len(shown) == 1
    assert handle_of(shown[0]) == "uae-regular-fit-styling-kurta-kr-sty25-079"
    assert DISTINCT_HANDLES - len(distinct_products(store)) == 12


def test_the_same_title_at_a_different_price_is_a_different_product_and_is_kept(
    store: StoreConfig,
) -> None:
    """The collapse needs the price to match too: "UAE-Regular Fit Styling Suits" is AED 101.50 on
    three handles (one is kept) and AED 83.50 on a fourth (kept as well)."""
    suits = [p for p in distinct_products(store) if p.title == "UAE-Regular Fit Styling Suits"]

    assert sorted(p.price for p in suits) == [83.5, 101.5]


def test_titles_start_with_uae_in_three_spellings_and_the_spelling_changes_what_collapses(
    store: StoreConfig,
) -> None:
    """Quirk 2. Of the 32 products, 19 start "UAE-", 12 "UAE- " (a space after) and 1 "UAE -" (a
    space before). The app compares the whitespace-folded title, so "UAE-Cambric Printed Shirt" and
    "UAE- Cambric Printed Shirt" at the same AED 79 stay two products."""
    titles = [record["title"] for record in raw_by_handle().values()]
    spelling = Counter(
        "UAE -" if t.startswith("UAE -") else "UAE- " if t.startswith("UAE- ") else "UAE-"
        for t in titles
    )
    shown = {p.title: p.price for p in distinct_products(store)}

    assert spelling == {"UAE-": 19, "UAE- ": 12, "UAE -": 1}
    assert all(title.startswith("UAE") for title in titles)
    assert shown["UAE-Cambric Printed Shirt"] == shown["UAE- Cambric Printed Shirt"] == 79.0


def test_the_ranker_cuts_the_prefix_and_the_style_code_into_harmless_words() -> None:
    """Quirk 2, the ranker's side. ``tokenize`` splits at hyphens, so the prefix is the word "uae"
    in all three spellings and a code such as KR-STY25-007 is "kr", "sty25" and "007". None of them
    is a garment, colour or gender word, and a request's words are looked up in the title, not the
    other way round, so they cost a product nothing."""
    assert tokenize("UAE-Regular Fit Styling Kurta")[:2] == ["uae", "regular"]
    assert tokenize("UAE- Regular Fit Styling Kurta") == tokenize("UAE-Regular Fit Styling Kurta")
    assert tokenize("UAE -Regular Fit Styling Kurta KP-STY25-010") == [
        "uae",
        "regular",
        "fit",
        "styling",
        "kurta",
        "kp",
        "sty25",
        "010",
    ]
    for title in (
        "UAE-Regular Fit Styling Kurta",
        "UAE- Regular Fit Styling Kurta",
        "UAE -Regular Fit Styling Kurta KP-STY25-010",
        "UAE-Regular Fit Styling Kurta KR-STY25-007",
    ):
        assert classify_title(title) is Category.DRESSES


def test_a_style_code_is_in_the_title_of_only_four_of_the_thirty_two_products(
    store: StoreConfig,
) -> None:
    """The other 28 carry their design code in the handle and the description only. The four coded
    titles are unique, so each is kept as its own product."""
    code = re.compile(r" [A-Z]{2}-[A-Z]{3}\d{2}-\d{3}$")
    coded = [r["title"] for r in raw_by_handle().values() if code.search(r["title"])]

    assert sorted(coded) == [
        "UAE -Regular Fit Styling Kurta KP-STY25-010",
        "UAE-Regular Fit Embroidered Suits SK-EMB25-025",
        "UAE-Regular Fit Styling Kurta KR-STY25-007",
        "UAE-Regular Fit Styling Suits KP-STY25-018",
    ]
    assert {p.title for p in distinct_products(store)} >= set(coded)


def test_five_products_have_variants_at_two_prices_and_the_higher_price_is_the_pre_sale_price(
    store: StoreConfig,
) -> None:
    """Quirk 3. ``price`` is the lowest variant price. On these five, ``price_max`` is 1.66 times
    higher and equals ``compare_at_price_max`` exactly: the full price of the same garment. The
    ratio of the two is 0.60, like every other product on sale, so some sizes are at the 40% sale
    price and some are not (the search answer lists no variants, so this cannot be confirmed here).
    This is not Hamsa's trap, where the low price belonged to a scarf (ADR 0012)."""
    raw = raw_by_handle()
    ranged = {
        handle: (r["price"], r["price_max"], r["compare_at_price_max"])
        for handle, r in raw.items()
        if r["price_min"] != r["price_max"]
    }

    assert ranged == SPREAD_PRODUCTS
    for low, high, pre_sale in ranged.values():
        assert high == pre_sale
        assert round(Decimal(low) / Decimal(high), 2) == Decimal("0.60")
        assert Decimal(high) / Decimal(low) < Decimal("1.7")
    assert all(r["price"] == r["price_min"] for r in all_raw())  # price is always the lowest


def test_every_product_on_sale_is_at_sixty_percent_of_its_pre_sale_price(
    store: StoreConfig,
) -> None:
    """Quirk 3, the sale. 18 of 32 products (23 of 40 records) have a pre-sale price above the
    price, all at 60.1%: the men's kurtas and suits. The women's kurtis carry
    ``compare_at_price_max`` of ``0.00``, nothing struck through. The adapter shows ``price``, what
    the shopper pays; the budget band will rise when the sale ends."""
    raw = raw_by_handle().values()
    on_sale = [r for r in raw if Decimal(r["compare_at_price_max"]) > 0]
    prices = {handle_of(p): p.price for p in all_products(store)}

    assert len(on_sale) == 18
    assert sum(Decimal(r["compare_at_price_max"]) > 0 for r in all_raw()) == 23
    assert {
        round(Decimal(r["price"]) / Decimal(r["compare_at_price_max"]), 3) for r in on_sale
    } <= {Decimal("0.601")}
    assert {r["type"] for r in on_sale} == {"Men"}
    assert {r["compare_at_price_max"] for r in raw if r["type"] == "Women"} == {"0.00"}
    # 14 of the 18 reach the validated products; 4 repeat a title and price inside their own answer.
    shown = [record for record in on_sale if record["handle"] in prices]
    assert len(shown) == 14
    for record in shown:
        assert prices[record["handle"]] == float(record["price"])  # never the pre-sale price


def test_a_price_guard_of_one_would_drop_seven_records_and_leave_eighteen_distinct_products(
    store: StoreConfig,
) -> None:
    """What the decision cost, so it can be revisited. With ``max_price_spread: 1`` (or 1.25) the
    five two-price products are dropped on all seven records that carry them and only 18 distinct
    products remain, under the plan's floor of 20. With 1.7 or more nothing is dropped."""
    guarded = with_options(store, max_price_spread=1)
    guarded_drops: Counter[str] = Counter()
    for query in QUERIES:
        guarded_drops.update(replay(guarded, query).dropped)

    assert guarded_drops["missing_price"] == 7
    assert len(distinct_products(guarded)) == 18
    assert len(distinct_products(with_options(store, max_price_spread=1.25))) == 18
    for loose in (1.7, 2):
        loose_store = with_options(store, max_price_spread=loose)
        assert all("missing_price" not in replay(loose_store, q).dropped for q in QUERIES)
        assert len(distinct_products(loose_store)) == DISTINCT_PRODUCTS


def test_the_search_answer_lists_no_variants_so_nothing_there_says_which_size_costs_what() -> None:
    assert all(record["variants"] == [] for record in all_raw())


def test_the_lowest_price_is_shown_for_a_two_price_product(store: StoreConfig) -> None:
    """Three of the five two-price products reach the shopper (the other two repeat the title and
    price of a product that came first). Each is shown at its lowest price."""
    prices = {handle_of(p): p.price for p in distinct_products(store)}
    reaching = {handle: prices[handle] for handle in SPREAD_PRODUCTS if handle in prices}

    assert reaching == {
        "uae-regular-fit-embroidered-kurta-kr-emb25-028": 53.5,
        "uae-regular-fit-styling-kurta-kr-sty25-079": 53.5,
        "uae-regular-fit-styling-waist-coat-wc-sty25-018": 101.5,
    }


def test_gender_comes_from_type_and_every_product_has_one(store: StoreConfig) -> None:
    """Quirk 4. ``type`` is "Men" on 27 records and "Women" on 13, and the title never says. With
    ``type`` read first, all 26 products the app keeps carry a gender; 14 distinct products are
    men's and 6 are women's."""
    raw = raw_by_handle()
    expected = {"Men": Gender.MEN, "Women": Gender.WOMEN}

    assert Counter(r["type"] for r in all_raw()) == {"Men": 27, "Women": 13}
    for product in all_products(store):
        assert product.gender is expected[raw[handle_of(product)]["type"]]
    assert Counter(p.gender for p in distinct_products(store)) == {Gender.MEN: 14, Gender.WOMEN: 6}


def test_gender_is_read_from_a_real_mens_record_and_a_real_womens_record(
    store: StoreConfig,
) -> None:
    by_handle = {handle_of(p): p for p in all_products(store)}
    raw = raw_by_handle()
    men = by_handle["uae-regular-fit-styling-kurta-kp-sty25-010"]
    women = by_handle["uae-cambric-printed-shirt-with-embroidered-and-dyed-trouser-ipst-77464"]

    assert (raw[handle_of(men)]["type"], raw[handle_of(men)]["tags"]) == ("Men", ["Mens Kurta"])
    assert men.gender is Gender.MEN  # the tag spells it "Mens"; the type says "Men"
    assert raw[handle_of(women)]["type"] == "Women"
    assert "Women Co-Ords" in raw[handle_of(women)]["tags"]
    assert women.gender is Gender.WOMEN


def test_the_tags_agree_with_type_where_they_name_a_gender_and_the_kurti_tag_names_none(
    store: StoreConfig,
) -> None:
    """Quirk 4. Read alone, the tags give the same gender as ``type`` on every product that they
    label and none to the women's kurtis, whose tag is just "Kurti". That is why ``type`` comes
    first: it labels all of them, the tags only the men's products and one women's co-ord set."""
    by_type = {handle_of(p): p.gender for p in all_products(store)}
    by_tags = {
        handle_of(p): p.gender for p in all_products(with_options(store, gender_fields=["tags"]))
    }
    unlabelled = [handle for handle, gender in by_tags.items() if gender is None]

    assert set(by_type) == set(by_tags)
    assert all(gender is not None for gender in by_type.values())
    assert all(gender is by_type[handle] for handle, gender in by_tags.items() if gender)
    assert unlabelled
    assert all(by_type[handle] is Gender.WOMEN for handle in unlabelled)
    assert all("Kurti" in raw_by_handle()[handle]["tags"] for handle in unlabelled)


def test_a_womens_request_drops_every_mens_product_and_a_mens_request_every_womens(
    store: StoreConfig,
) -> None:
    """Nothing in a title says who a product is for, so this works only because the adapter reads
    ``type``. The request names the product's own category so that only the gender can drop it."""
    distinct = distinct_products(store)

    for product in distinct:
        category = classify_title(product.title)
        own = category if isinstance(category, Category) else Category.DRESSES
        other = Gender.WOMEN if product.gender is Gender.MEN else Gender.MEN
        same = Gender.MEN if product.gender is Gender.MEN else Gender.WOMEN
        assert apply_hard_filters(request_for(own, other), product).reason is (
            DropReason.GENDER_MISMATCH
        )
        assert apply_hard_filters(request_for(own, same), product).keep


def test_a_shalwar_kameez_titled_suits_has_no_category_and_stays_for_a_dresses_request(
    store: StoreConfig,
) -> None:
    """Quirk 5. "Suit" is deliberately ambiguous in the lexicon, so the nine men's suits read as no
    category and are kept for any request. For the dresses request this store is searched for, that
    is right; it is also why a shoes or trousers search must not be sent here (``categories``)."""
    suits = [p for p in distinct_products(store) if "Suits" in p.title]

    assert len(suits) == 7  # 9 products, 2 collapsed by title and price
    assert {classify_title(p.title) for p in suits} == {None}
    assert {apply_hard_filters(request_for(Category.DRESSES), p).keep for p in suits} == {True}
    assert {apply_hard_filters(request_for(Category.SHOES), p).keep for p in suits} == {True}


def test_a_kurta_is_a_dress_and_a_kurti_titled_shirt_is_a_top(store: StoreConfig) -> None:
    """Quirk 5. The ranker reads the title: "Kurta" is the dresses category, "Printed Shirt" is
    tops. So the women's kurtis (all titled "Shirt", tag "Kurti") are shown for a tops request and
    dropped from a dresses request, which is why the store file lists both categories."""
    distinct = distinct_products(store)
    kurtas = [p for p in distinct if "Kurta" in p.title]
    kurtis = [p for p in distinct if p.gender is Gender.WOMEN]

    assert len(kurtas) == 6
    assert {classify_title(p.title) for p in kurtas} == {Category.DRESSES}
    assert len(kurtis) == 6
    assert {classify_title(p.title) for p in kurtis} == {Category.TOPS}
    assert {apply_hard_filters(request_for(Category.DRESSES), p).reason for p in kurtis} == {
        DropReason.WRONG_CATEGORY
    }
    assert {apply_hard_filters(request_for(Category.TOPS), p).keep for p in kurtis} == {True}


def test_a_kurti_search_finds_three_womens_kurtis_and_seven_mens_kurtas(
    store: StoreConfig,
) -> None:
    """Quirk 5, in the data. The query ``kurti`` returns 7 men's kurtas and only 3 women's kurtis
    (the printed-shirt query finds ten); a women's kurti is found by the word "shirt"."""
    kurti = raw_products("kurti")
    shirt = raw_products("printed shirt")

    assert Counter(r["type"] for r in kurti) == {"Men": 7, "Women": 3}
    assert Counter(r["type"] for r in shirt) == {"Women": 10}
    assert all(r["tags"][0] == "Kurti" for r in kurti if r["type"] == "Women")
    assert {classify_title(r["title"]) for r in shirt} == {Category.TOPS}


def test_a_shirt_and_trouser_set_is_listed_as_a_shirt_and_ranks_as_a_top(
    store: StoreConfig,
) -> None:
    """Quirk 5. "UAE- Cambric Printed Shirt With Embroidered And Dyed Trouser" (AED 149, tag "Women
    Co-Ords") is a two-piece set. The ranker reads the title up to "With", so it is a top."""
    [coord] = [p for p in distinct_products(store) if p.price == 149.0]

    assert coord.title.endswith("With Embroidered And Dyed Trouser")
    assert raw_by_handle()[handle_of(coord)]["tags"][-1] == "Women Co-Ords"
    assert classify_title(coord.title) is Category.TOPS


def test_a_waistcoat_is_in_the_shalwar_kameez_answer_and_reads_as_outerwear(
    store: StoreConfig,
) -> None:
    """The word "shalwar kameez" also finds a waistcoat (tag "Men Waistcoat", AED 101.50, a
    two-price product). Its title says "Waist Coat", so it is outerwear and is dropped from a
    dresses request. Outerwear is not in the store's categories, so a jacket search is not sent."""
    [waistcoat] = [p for p in distinct_products(store) if "Waist Coat" in p.title]

    assert handle_of(waistcoat) in {r["handle"] for r in raw_products("shalwar kameez")}
    assert classify_title(waistcoat.title) is Category.OUTERWEAR
    assert (
        apply_hard_filters(request_for(Category.DRESSES), waistcoat).reason
        is DropReason.WRONG_CATEGORY
    )


def test_vendor_has_two_values_and_is_not_read_every_product_carries_the_store_name(
    store: StoreConfig,
) -> None:
    vendors = Counter(r["vendor"] for r in raw_by_handle().values())

    assert vendors == {"GulAhmed Ideas PK": 27, "uae.gulahmedshop.com": 5}
    assert {product.store for product in all_products(store)} == {DISPLAY_NAME}


def test_the_tracking_parameters_on_the_product_link_are_removed(store: StoreConfig) -> None:
    raw = all_raw()
    assert all("_pos=" in record["url"] for record in raw)  # the store adds them

    for product in all_products(store):
        assert urlsplit(product.product_url).query == ""
        assert urlsplit(product.product_url).path.startswith("/products/")


def test_colour_is_not_a_field_it_is_in_the_picture_name_and_the_description(
    store: StoreConfig,
) -> None:
    """The colour sits in the image file name ("...Color-Sky-Blue...") and the description, never in
    the title, so ``Product.colour`` stays unset and a colour request cannot rank on it."""
    raw = raw_by_handle()["uae-regular-fit-styling-kurta-kr-sty25-084"]

    assert "Color-Sky-Blue" in raw["image"]
    assert "sky-blue color" in raw["body"]
    assert {product.colour for product in all_products(store)} == {None}


def test_some_descriptions_hold_replacement_characters_and_the_adapter_never_reads_them(
    store: StoreConfig,
) -> None:
    """The store's own response has U+FFFD in the ``body`` of 7 records (6 products). The adapter
    maps no description, so these products come through like the others."""
    damaged = {r["handle"]: r for r in all_raw() if "\ufffd" in r["body"]}
    shown = {product.title for product in all_products(store)}

    assert len(damaged) == 6
    assert {record["title"] for record in damaged.values()} <= shown
    assert not any("\ufffd" in product.title for product in all_products(store))


# --- The whole search engine on the saved answers ----------------------------------------------


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
            content=fixture_text(fixture_name(query)).encode(),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    # The second variant is sent only when the first gave fewer than second_variant_below
    # products; each saved answer has ten, so raise the setting to see both requests.
    settings = make_settings(second_variant_below=50)
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
    assert len(result.products) == 14  # 8 + 6; the other 6 of 20 records repeat a title and price
    assert result.dropped == {"duplicate_title_price": 6}
    assert {product.gender for product in result.products} == {Gender.MEN}
    assert {product.currency for product in result.products} == {CURRENCY}
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[build_search_url(store, query) for query in sent],
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
