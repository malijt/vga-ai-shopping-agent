"""Nautica UAE offline fixture test (plan 12.2.1 and 12.2.2): no network.

The four files in ``fixtures/`` are real ``/search/suggest.json`` responses, saved on 2026-10-08
from a live run through ``StoreSearchEngine`` (honest User-Agent, robots.txt checked, 1 request/s).
Nothing in them was edited except that each product's ``body`` (the HTML description) is cut to 300
characters. Every product of every response is kept. The tests replay them through the real
registry, the real ``shopify`` extractor and the real validation.

How many products they hold, and how many survive validation (table below)::

    men shirt    10 products, 10 survive
    jacket       10 products, 10 survive
    trousers     10 products,  8 survive   (3 colours of "Women's Trouser" share a title and price)
    women dress  10 products,  3 survive   (4 colours of one shirt, 2 of one trouser, 4 of one top)
    total        40 products, 31 survive

Shopify's suggest endpoint returns at most 10 products per call, so the plan's "at least 20
products" (12.2.2) is met by the four responses together, not by one.
"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from vga.models import StoreConfig, Tier
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.normalise import DropReason
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"

# query, file, products in the saved response, products that survive validation
SAVED = [
    ("men shirt", "suggest-men-shirt.json", 10, 10),
    ("jacket", "suggest-jacket.json", 10, 10),
    ("trousers", "suggest-trousers.json", 10, 8),
    ("women dress", "suggest-women-dress.json", 10, 3),
]
TOTAL_PRODUCTS = 40
TOTAL_SURVIVORS = 31

DOCUMENTED_TEMPLATE = (
    "https://nautica-ae.com/search/suggest.json?q={query}"
    "&resources[type]=product&resources[limit]=10"
)


def saved_products(file: str) -> list[dict[str, Any]]:
    data = json.loads((FIXTURES / file).read_text(encoding="utf-8"))
    products: list[dict[str, Any]] = data["resources"]["results"]["products"]
    return products


def replay(store: StoreConfig, query: str, file: str) -> Any:
    """The saved response through the real extraction chain, as the engine would run it."""
    body = (FIXTURES / file).read_text(encoding="utf-8")
    return ExtractionChain(default_registry()).run(body, store, build_search_url(store, query))


# --------------------------------------------------------------------------------------------
# The store file (12.2.1)
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_with_the_expected_settings(
    store: StoreConfig,
) -> None:
    assert store.id == "nautica-uae"
    assert store.display_name == "Nautica UAE"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.search_url_template == DOCUMENTED_TEMPLATE
    assert store.allowed_hosts == ["nautica-ae.com", "cdn.shopify.com"]
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]
    assert store.tier_hint is Tier.MID_RANGE


def test_genders_stay_unset_because_the_store_sells_women_s_clothing_too(
    store: StoreConfig,
) -> None:
    """The qualification report saw men's clothing and women's bags only. The query "women dress"
    (run on 2026-10-08) returned women's shirts, trousers and tops, so the store is not a men's
    store and a women's request must still reach it."""
    womens_clothing = [
        product
        for product in saved_products("suggest-women-dress.json")
        if "Women" in product["tags"]
        and product["type"] in {"Shirts", "Trousers", "Sleeveless top"}
    ]

    assert len(womens_clothing) == 10
    assert store.genders is None


# --------------------------------------------------------------------------------------------
# The saved responses (12.2.2)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("query", "file", "held", "survivors"), SAVED)
def test_each_saved_response_holds_and_keeps_the_stated_number_of_products(
    store: StoreConfig, query: str, file: str, held: int, survivors: int
) -> None:
    outcome = replay(store, query, file)

    assert len(saved_products(file)) == held
    assert outcome.examined == held
    assert len(outcome.products) == survivors
    assert outcome.strategy == "shopify"
    # Only repeats are dropped: nothing is lost to a missing field, a bad price or a foreign host.
    repeats = {DropReason.DUPLICATE_TITLE_PRICE.value, DropReason.DUPLICATE_URL.value}
    assert set(outcome.dropped) <= repeats
    assert sum(outcome.dropped.values()) == held - survivors


@pytest.mark.parametrize(("query", "file", "held", "survivors"), SAVED)
def test_every_surviving_product_has_the_six_required_fields_in_aed_on_allowed_hosts(
    store: StoreConfig, query: str, file: str, held: int, survivors: int
) -> None:
    outcome = replay(store, query, file)

    assert len(outcome.products) == survivors
    for product in outcome.products:
        assert product.title.strip()
        assert product.store == "Nautica UAE"
        assert product.currency == "AED"
        assert product.price > 0
        for url in (product.product_url, product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https"
            assert parts.hostname in store.allowed_hosts
        assert urlsplit(product.product_url).hostname == "nautica-ae.com"
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert parse_qs(urlsplit(product.image_url).query)["width"] == ["400"]


@pytest.mark.parametrize(("query", "file", "held", "survivors"), SAVED)
def test_product_links_are_clean_store_product_pages_without_tracking_parameters(
    store: StoreConfig, query: str, file: str, held: int, survivors: int
) -> None:
    outcome = replay(store, query, file)

    assert len(outcome.products) == survivors
    for product in outcome.products:
        parts = urlsplit(product.product_url)
        assert parts.path.startswith("/products/")
        assert parts.query == ""  # Shopify's _pos, _psq, _psid and _ss are dropped
        assert product.in_stock is True


def test_the_four_responses_together_meet_the_plan_s_twenty_products(store: StoreConfig) -> None:
    held = sum(len(saved_products(file)) for _query, file, _held, _survivors in SAVED)
    survivors = sum(len(replay(store, query, file).products) for query, file, _h, _s in SAVED)

    assert held == TOTAL_PRODUCTS
    assert survivors == TOTAL_SURVIVORS
    assert survivors >= 20


def test_a_neutral_query_returns_women_s_items_too_and_the_product_has_no_gender_field(
    store: StoreConfig,
) -> None:
    """Quirk: "trousers" also returns three women's trousers. The only sign of gender is the title
    ("Women's ...", here; the tags in the raw response say it too), so ranking has to read the
    title."""
    outcome = replay(store, "trousers", "suggest-trousers.json")

    womens = [product for product in outcome.products if product.title.startswith("Women's")]

    assert len(womens) == 1  # three colours share one title and price, so one survives
    assert len(outcome.products) - len(womens) == 7
