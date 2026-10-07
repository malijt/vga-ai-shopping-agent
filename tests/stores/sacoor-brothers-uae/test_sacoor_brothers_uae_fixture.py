"""Sacoor Brothers UAE adapter, offline (plan 12.3.1 and 12.3.2).

Two real ``/search/suggest.json`` responses, recorded on 2026-10-08 through ``StoreSearchEngine``
(only the long ``body`` description strings were cut to 300 characters; every product is kept), and
the store's real ``robots.txt``, are replayed through the real store registry, extraction chain,
validation and search engine. No test here touches the network.

What the fixtures hold:

- ``suggest-black-blazer.json``: 10 products (7 men's blazers, 2 women's suit blazers, 1 women's
  suit). 8 survive validation: Sacoor lists some products twice under different handles with the
  same title and price (a velvet tuxedo blazer and a "pied poule" blazer here), and validation
  keeps the first of each.
- ``suggest-men-shirt.json``: 10 products (all men's shirts). 8 survive for the same reason.
"""

import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from tests.factories import make_item_intent, make_settings
from tests.fakes import FakeClock

from vga.models import Gender, StoreConfig, StoreStatus, Tier
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.registry import load_store_configs

HERE = Path(__file__).parent
STORE_FILE = Path(__file__).resolve().parents[3] / "config" / "stores" / "sacoor-brothers-uae.yaml"

HOST = "ae.sacoorbrothers.com"
SEARCH_BASE_URL = f"https://{HOST}/search/suggest.json"
IMAGE_PATH_PREFIX = "/s/files/1/0561/5422/6743/"
"""Every image in the 40 records seen on 2026-10-07 and 2026-10-08 sits under this path."""

# (fixture file, products the fixture holds, products that survive validation)
FIXTURES = [
    ("suggest-black-blazer.json", 10, 8),
    ("suggest-men-shirt.json", 10, 8),
]
FIXTURE_IDS = [name for name, _, _ in FIXTURES]


def fixture_text(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def fixture_products(name: str) -> list[dict[str, object]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, object]] = data["resources"]["results"]["products"]
    return products


@pytest.fixture
def store(tmp_path: Path) -> StoreConfig:
    """The shipped store file, loaded by the real registry loader (from a copy, so a sibling
    store's file that is being written at the same time cannot break this test)."""
    shutil.copy(STORE_FILE, tmp_path / STORE_FILE.name)
    [loaded] = load_store_configs(tmp_path)
    return loaded


# --------------------------------------------------------------------------------------------
# 12.3.1 The store file
# --------------------------------------------------------------------------------------------


def test_the_store_file_loads_with_the_documented_shopify_shape(store: StoreConfig) -> None:
    assert store.id == "sacoor-brothers-uae"
    assert store.display_name == "Sacoor Brothers UAE"
    assert (store.country, store.currency) == ("AE", "AED")
    assert store.search_url_template == (
        f"https://{HOST}/search/suggest.json?q={{query}}&resources[type]=product&resources[limit]=10"
    )
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]
    assert store.tier_hint is Tier.PREMIUM


def test_genders_is_unset_because_the_store_sells_for_men_and_women(store: StoreConfig) -> None:
    # The types seen are "<season> / Man / <category>" and "<season> / Woman / <category>": 36 men's
    # and 4 women's records in the qualification run, and 3 of the 20 below.
    kinds = {
        str(product["type"]).split(" / ")[1]
        for name in FIXTURE_IDS
        for product in fixture_products(name)
    }

    assert kinds == {"Man", "Woman"}
    assert store.genders is None
    assert store.sells_for_gender(Gender.MEN) is True
    assert store.sells_for_gender(Gender.WOMEN) is True


# --------------------------------------------------------------------------------------------
# 12.3.2 The fixtures through the real extraction chain and validation
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "holds", "survive"), FIXTURES, ids=FIXTURE_IDS)
def test_each_fixture_holds_ten_products_and_eight_survive_validation(
    store: StoreConfig, name: str, holds: int, survive: int
) -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text(name), store, f"{SEARCH_BASE_URL}?q=x"
    )

    assert len(fixture_products(name)) == holds
    assert outcome.examined == holds
    assert outcome.strategy == "shopify"
    assert len(outcome.products) == survive
    # The two that did not survive are repeats of a kept product (same title, same price).
    assert outcome.dropped == {"duplicate_title_price": holds - survive}


def test_the_two_fixtures_together_hold_20_products_and_16_survive(store: StoreConfig) -> None:
    chain = ExtractionChain(default_registry())

    outcomes = [chain.run(fixture_text(name), store, SEARCH_BASE_URL) for name in FIXTURE_IDS]

    assert sum(len(fixture_products(name)) for name in FIXTURE_IDS) == 20
    assert sum(len(outcome.products) for outcome in outcomes) == 16


@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_every_product_has_all_six_required_fields_in_aed(store: StoreConfig, name: str) -> None:
    outcome = ExtractionChain(default_registry()).run(fixture_text(name), store, SEARCH_BASE_URL)

    assert outcome.products
    for product in outcome.products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == "AED"
        assert product.image_url
        assert product.product_url
        assert product.store == "Sacoor Brothers UAE"
        assert product.in_stock is True


@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_product_and_image_urls_are_https_and_on_the_allowed_hosts(
    store: StoreConfig, name: str
) -> None:
    outcome = ExtractionChain(default_registry()).run(fixture_text(name), store, SEARCH_BASE_URL)

    for product in outcome.products:
        link = urlsplit(product.product_url)
        assert link.scheme == "https"
        assert link.hostname == HOST
        assert link.path.startswith("/products/")
        assert link.query == "", "the _pos/_psq/_psid/_ss tracking parameters are dropped"

        image = urlsplit(product.image_url)
        assert image.scheme == "https"
        assert image.hostname in store.allowed_hosts
        assert image.hostname == "cdn.shopify.com"
        assert image.path.startswith(IMAGE_PATH_PREFIX)


@pytest.mark.parametrize("name", FIXTURE_IDS)
def test_image_urls_carry_width_400_next_to_the_version_parameter(
    store: StoreConfig, name: str
) -> None:
    outcome = ExtractionChain(default_registry()).run(fixture_text(name), store, SEARCH_BASE_URL)

    for product in outcome.products:
        params = parse_qs(urlsplit(product.image_url).query)
        assert params["width"] == ["400"]
        assert "v" in params, "the cache-busting version parameter is kept"


def test_the_price_is_what_the_shopper_pays_not_the_pre_sale_price(store: StoreConfig) -> None:
    # "Velvet tuxedo blazer" is AED 695.00 now, down from compare_at_price_max 2195.00.
    outcome = ExtractionChain(default_registry()).run(
        fixture_text("suggest-black-blazer.json"), store, SEARCH_BASE_URL
    )

    velvet = [p for p in outcome.products if p.title == "Velvet tuxedo blazer"]

    assert [p.price for p in velvet] == [695.0], "one record kept; the same-priced repeat dropped"


def test_a_product_listed_twice_under_two_handles_is_kept_once(store: StoreConfig) -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text("suggest-men-shirt.json"), store, SEARCH_BASE_URL
    )

    titles = [p.title for p in outcome.products]

    # The fixture has two handles (-185 and -199) for this title at AED 495.
    assert titles.count("Slim Fit Travel Poplin Shirt in Comfort Cotton") == 1
    assert len({p.product_url for p in outcome.products}) == len(outcome.products)


# --------------------------------------------------------------------------------------------
# The real engine, with the store's real robots.txt and a replayed response
# --------------------------------------------------------------------------------------------


async def test_the_real_engine_replays_the_fixture_after_checking_the_real_robots_file(
    store: StoreConfig,
) -> None:
    enabled = store.model_copy(update={"enabled": True})
    settings = make_settings()
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as router:
        robots_route = router.get(f"https://{HOST}/robots.txt").mock(
            return_value=httpx.Response(
                200,
                content=(HERE / "robots.txt").read_bytes(),
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        )
        search_route = router.get(url__startswith=SEARCH_BASE_URL).mock(
            return_value=httpx.Response(
                200,
                content=fixture_text("suggest-black-blazer.json").encode("utf-8"),
                headers={"content-type": "application/json; charset=utf-8"},
            )
        )
        engine = StoreSearchEngine(settings, clock=FakeClock())
        try:
            [result] = await engine.search(
                make_item_intent(search_keywords=["black blazer"]), [enabled]
            )
        finally:
            await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert len(result.products) == 8
    assert result.dropped == {"duplicate_title_price": 2}
    assert (robots_route.call_count, search_route.call_count) == (1, 1)
    [call] = search_route.calls
    assert str(call.request.url) == (
        f"{SEARCH_BASE_URL}?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10"
    )
    assert call.request.headers["user-agent"] == settings.user_agent
