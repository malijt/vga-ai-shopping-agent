"""Giordano UAE, offline (plan 12.1.1 and 12.1.2): the store file and a saved real response.

``fixtures/suggest-jacket.json`` is the whole, unedited answer of ``/search/suggest.json?q=jacket``
taken on 2026-10-08 by the live smoke test (see ``test_giordano_uae_live.py``). Its ``body`` strings
are already short (552 characters at most), so nothing was trimmed: the file is 14 KB.
``fixtures/robots.txt`` is the store's robots.txt from the same run.

Nothing here touches the network: HTTP is answered by ``respx`` and time by ``FakeClock``.
"""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from protego import Protego
from tests.fakes import FakeClock

from vga.models import Category, ItemIntent, StoreConfig, StoreStatus, Tier
from vga.settings import DEFAULT_STORES_DIR, Settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.registry import load_store_configs
from vga.stores.urls import build_search_url

STORE_ID = "giordano-uae"
FIXTURES = Path(__file__).parent / "fixtures"

# The saved response holds 10 products. This store lists one product under several handles (the
# colour variants), so some titles repeat at the same price; the pipeline keeps the first of each
# and drops the rest by design (reason "duplicate_title_price"). 6 distinct products survive.
FIXTURE_PRODUCTS = 10
SURVIVING_PRODUCTS = 6
COLLAPSED_REPEATS = FIXTURE_PRODUCTS - SURVIVING_PRODUCTS

ROBOTS_URL = "https://giordano.ae/robots.txt"
SEARCH_URL_FOR_JACKET = "https://giordano.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10"


@pytest.fixture
def store(tmp_path: Path) -> StoreConfig:
    """The shipped store file, loaded by the real registry. Only this store's file is copied into
    a temporary folder, so another store's file can never break this test."""
    shutil.copy(DEFAULT_STORES_DIR / f"{STORE_ID}.yaml", tmp_path / f"{STORE_ID}.yaml")
    [loaded] = load_store_configs(tmp_path)
    return loaded


@pytest.fixture
def suggest_text() -> str:
    return (FIXTURES / "suggest-jacket.json").read_text(encoding="utf-8")


def raw_products(text: str) -> list[dict[str, object]]:
    products: list[dict[str, object]] = json.loads(text)["resources"]["results"]["products"]
    return products


# --------------------------------------------------------------------------------------------
# 12.1.1 The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_with_the_documented_settings(
    store: StoreConfig,
) -> None:
    assert store.id == STORE_ID
    assert store.display_name == "Giordano UAE"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.allowed_hosts == ["giordano.ae", "cdn.shopify.com"]
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]
    assert store.tier_hint is Tier.BUDGET
    assert store.search_url_template == (
        "https://giordano.ae/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    )


def test_genders_is_unset_because_the_store_is_not_single_gender(store: StoreConfig) -> None:
    """Qualification saw men's and unisex items and a store that also sells women's and kids'
    wear. ``None`` means "all, or not known": a request for any gender is sent here."""
    assert store.genders is None


def test_the_search_url_is_the_one_the_qualification_report_saw_working(
    store: StoreConfig,
) -> None:
    assert build_search_url(store, "jacket") == SEARCH_URL_FOR_JACKET


# --------------------------------------------------------------------------------------------
# 12.1.2 The saved real response, through the real extraction chain and validation
# --------------------------------------------------------------------------------------------


def test_the_fixture_holds_ten_products_and_six_survive_validation(
    store: StoreConfig, suggest_text: str
) -> None:
    outcome = ExtractionChain(default_registry()).run(suggest_text, store, SEARCH_URL_FOR_JACKET)

    assert len(raw_products(suggest_text)) == FIXTURE_PRODUCTS == 10
    assert outcome.strategy == "shopify"
    assert outcome.examined == FIXTURE_PRODUCTS
    assert len(outcome.products) == SURVIVING_PRODUCTS == 6
    # The four dropped records are repeats of a title at the same price, nothing else.
    assert outcome.dropped == {"duplicate_title_price": COLLAPSED_REPEATS}


def test_every_surviving_product_has_all_six_required_fields(
    store: StoreConfig, suggest_text: str
) -> None:
    products = (
        ExtractionChain(default_registry()).run(suggest_text, store, SEARCH_URL_FOR_JACKET).products
    )

    for product in products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "AED"
        assert product.image_url
        assert product.product_url
        assert product.store == "Giordano UAE"
    assert len({product.product_url for product in products}) == len(products)


def test_prices_are_positive_aed_and_links_are_https_on_the_allow_list(
    store: StoreConfig, suggest_text: str
) -> None:
    products = (
        ExtractionChain(default_registry()).run(suggest_text, store, SEARCH_URL_FOR_JACKET).products
    )

    for product in products:
        assert product.currency == "AED"
        assert 0 < product.price < 1000
        product_url, image_url = urlsplit(product.product_url), urlsplit(product.image_url)
        assert product_url.scheme == image_url.scheme == "https"
        assert product_url.hostname == "giordano.ae"
        assert image_url.hostname in store.allowed_hosts
        assert product_url.path.startswith("/products/")
        assert not product_url.query  # Shopify's tracking parameters are removed


def test_image_urls_are_resized_thumbnails_with_the_version_kept(
    store: StoreConfig, suggest_text: str
) -> None:
    products = (
        ExtractionChain(default_registry()).run(suggest_text, store, SEARCH_URL_FOR_JACKET).products
    )

    for product in products:
        query = parse_qs(urlsplit(product.image_url).query)
        assert query["width"] == ["400"]
        assert "v" in query  # the store's cache-busting version is left as written


def test_a_price_is_the_current_price_not_the_pre_sale_price(
    store: StoreConfig, suggest_text: str
) -> None:
    """Every item was on sale (qualification and today): ``price`` is what the shopper pays and
    ``compare_at_price_*`` is the old price. The first jacket is AED 113.50, was AED 225.00."""
    [first, *_] = (
        ExtractionChain(default_registry()).run(suggest_text, store, SEARCH_URL_FOR_JACKET).products
    )

    assert first.price == 113.5
    assert raw_products(suggest_text)[0]["compare_at_price_max"] == "225.00"


# --------------------------------------------------------------------------------------------
# The same fixture through the real engine: robots.txt, URL, headers, host allow-list
# --------------------------------------------------------------------------------------------


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    """Answers every httpx request in the test; a request nobody mocked raises, so a test cannot
    reach the network by accident."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


async def test_the_engine_reads_the_fixture_after_checking_the_real_robots_txt(
    store: StoreConfig, suggest_text: str, router: respx.MockRouter
) -> None:
    router.get(ROBOTS_URL).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "robots.txt").read_text(encoding="utf-8"),
            headers={"content-type": "text/plain"},
        )
    )
    search = router.get(url__startswith="https://giordano.ae/search/suggest.json").mock(
        return_value=httpx.Response(
            200, text=suggest_text, headers={"content-type": "application/json"}
        )
    )
    settings = Settings()
    engine = StoreSearchEngine(settings, clock=FakeClock())
    item = ItemIntent(category=Category.OUTERWEAR, search_keywords=["jacket"])

    [result] = await engine.search(item, [store.model_copy(update={"enabled": True})])

    assert result.status is StoreStatus.OK
    assert len(result.products) == SURVIVING_PRODUCTS
    assert result.dropped == {"duplicate_title_price": COLLAPSED_REPEATS}
    assert [str(call.request.url) for call in router.calls] == [ROBOTS_URL, SEARCH_URL_FOR_JACKET]
    assert search.call_count == 1
    assert {call.request.headers["user-agent"] for call in router.calls} == {settings.user_agent}


def test_the_real_robots_txt_leaves_the_search_path_open_for_our_user_agent() -> None:
    """The saved robots.txt disallows carts, checkout and account pages, not the search path."""
    rules = Protego.parse((FIXTURES / "robots.txt").read_text(encoding="utf-8"))
    user_agent = Settings().user_agent

    assert rules.can_fetch(SEARCH_URL_FOR_JACKET, user_agent)
    assert not rules.can_fetch("https://giordano.ae/cart.js", user_agent)
    assert not rules.can_fetch("https://giordano.ae/checkout", user_agent)
