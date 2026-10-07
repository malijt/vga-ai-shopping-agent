"""The three Kuwaiti stores together (plan 12.11 to 12.13): Bazza Alzouman, Hamsa and Manal Smaoui.

Each store has its own tests next to its recorded answers. This file checks what only the shipped
files can show together: that ``config/settings.yaml`` (Kuwait among the extra store countries, a
dinar rate) and the three store files in ``config/stores/`` make the stores active, and that a
dinar product from each of them, read from its saved answer, goes through scoring and the price
ranges at the shipped rate and comes out with an approximate dirham figure and a price line the
shopper reads as ``245.000 KWD (about 2,920 AED)`` (ADR 0006).

No network: the products come from the saved answers in each store's ``fixtures/`` folder.
"""

from pathlib import Path

import pytest
from tests.factories import make_item_intent

from vga.models import Budget, Category, Flag, Product, ScoredProduct, Tier
from vga.money import format_price
from vga.rank import prefilter_and_score
from vga.settings import Settings, load_settings
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.registry import StoreRegistry
from vga.stores.urls import build_search_url
from vga.tiers import build_group

HERE = Path(__file__).parent
KUWAITI_IDS = ("bazza-alzouman", "hamsa-kw", "manal-smaoui")
ITEM = make_item_intent(
    category=Category.DRESSES, colour=None, style=None, search_keywords=["dress"]
)


@pytest.fixture(scope="module")
def settings() -> Settings:
    """The shipped ``config/settings.yaml``, read with no environment and no ``.env``."""
    return load_settings(env={})


@pytest.fixture(scope="module")
def registry() -> StoreRegistry:
    """Every shipped store file, through the real loader."""
    return StoreRegistry.from_directory()


def saved_products(registry: StoreRegistry, store_id: str, *answers: str) -> list[Product]:
    """The valid products of a store's saved answers, through its real store file."""
    store = registry.get(store_id)
    assert store is not None, store_id
    chain = ExtractionChain(default_registry())
    products: list[Product] = []
    for name in answers:
        text = (HERE / store_id / "fixtures" / name).read_text(encoding="utf-8")
        products += chain.run(text, store, build_search_url(store, "dress")).products
    return products


def pick(products: list[Product], *titles: str) -> list[Product]:
    by_title = {product.title: product for product in products}
    return [by_title[title] for title in titles]


def kuwaiti_pool(registry: StoreRegistry) -> list[Product]:
    """Twelve real dinar products, four from each store, as the stores answered on 2026-10-08."""
    bazza = saved_products(registry, "bazza-alzouman", "suggest-gown.json")
    hamsa = saved_products(registry, "hamsa-kw", "suggest-kaftan.json")
    manal = saved_products(registry, "manal-smaoui", "suggest-dress.json", "suggest-kaftan.json")
    return [
        *pick(
            bazza,
            "Slim Cut Crepe Gown With Gathered Tulle Illusion Neckline And Sleeve",
            "Strapless Gown With Side Organza Ruched Drape",
            "Off-Shoulder Crepe Gown With Wrap Skirt",
            "One Shoulder Crepe Gown With Gathered Tulle At Neck",
        ),
        *pick(hamsa, "Amber Kaftan", "Long Cord Kaftan", "Riwaq Kaftan", "Rania Kaftan"),
        *pick(
            manal,
            "THE BELLE DRESS - BLACK (LIMITED EDITION)",
            "THE BELLE DRESS - WHITE (LIMITED EDITION)",
            "AICHA KAFTAN - BROWN",
            "AICHA KAFTAN - ROYAL GREEN",
        ),
    ]


def shown_products(
    registry: StoreRegistry, settings: Settings, budget: Budget | None = None
) -> tuple[list[ScoredProduct], list[ScoredProduct]]:
    """The pool scored for a dress request, and what the price ranges then show of it."""
    pool = kuwaiti_pool(registry)
    scored = prefilter_and_score(ITEM, pool, budget, settings)
    stores = [store for store in registry.active(settings) if store.id in KUWAITI_IDS]
    built = build_group(
        scored,
        settings,
        budget,
        stores,
        item_index=0,
        category=Category.DRESSES,
        total=len(pool),
    )
    shown = [s for tier in built.group.tiers for s in tier.results]
    return scored, shown


def line(scored: ScoredProduct, settings: Settings) -> str:
    return format_price(
        scored.product.price,
        scored.product.currency,
        base_price=scored.base_price,
        base_currency=settings.base_currency,
    )


# --------------------------------------------------------------------------------------------
# The shipped settings and store files make the Kuwaiti stores active
# --------------------------------------------------------------------------------------------


def test_the_shipped_settings_search_the_home_market_and_kuwait(settings: Settings) -> None:
    assert settings.country == "AE"
    assert settings.extra_store_countries == ["KW"]
    assert settings.base_currency == "AED"
    assert settings.fx_rates == {"KWD": 11.92}


def test_the_three_kuwaiti_stores_are_active_next_to_the_dirham_stores(
    registry: StoreRegistry, settings: Settings
) -> None:
    active = {store.id: store for store in registry.active(settings)}

    assert set(KUWAITI_IDS) <= set(active)
    assert {(active[i].country, active[i].currency, active[i].enabled) for i in KUWAITI_IDS} == {
        ("KW", "KWD", True)
    }
    assert any(store.currency == "AED" for store in active.values())  # the home stores still run


def test_without_kuwait_in_the_settings_none_of_the_three_is_used(
    registry: StoreRegistry, settings: Settings
) -> None:
    home_only = settings.model_copy(update={"extra_store_countries": []})

    assert not {store.id for store in registry.active(home_only)} & set(KUWAITI_IDS)


def test_every_active_store_prices_in_a_currency_the_settings_can_convert(
    registry: StoreRegistry, settings: Settings
) -> None:
    for store in registry.active(settings):
        assert store.currency == settings.base_currency or store.currency in settings.fx_rates, (
            store.id
        )


def test_each_kuwaiti_store_file_is_a_dinar_store_on_its_own_host_and_the_image_cdn(
    registry: StoreRegistry,
) -> None:
    hosts = {
        "bazza-alzouman": "bazzaalzouman.com",
        "hamsa-kw": "hamsakw.com",
        "manal-smaoui": "manalsmaoui.com",
    }

    for store_id, host in hosts.items():
        store = registry.get(store_id)
        assert store is not None
        assert store.allowed_hosts == [host, "cdn.shopify.com"]
        assert store.search_url_template.startswith(f"https://{host}/search/suggest.json?")


# --------------------------------------------------------------------------------------------
# A dinar product from each store, through scoring and the price ranges at the shipped rate
# --------------------------------------------------------------------------------------------


def test_dinar_products_from_the_three_stores_all_reach_the_price_ranges_in_dirhams(
    registry: StoreRegistry, settings: Settings
) -> None:
    scored, shown = shown_products(registry, settings)

    assert len(scored) == 12  # every one is a dress or a kaftan: the dress filter keeps them all
    assert len(shown) == 12
    assert {s.product.store for s in shown} == {"Bazza Alzouman", "Hamsa", "Manal Smaoui"}
    assert {s.product.currency for s in shown} == {"KWD"}
    for item in shown:
        assert item.base_price == pytest.approx(item.product.price * 11.92, abs=0.005)


def test_each_range_is_measured_in_dirhams_and_every_range_holds_something(
    registry: StoreRegistry, settings: Settings
) -> None:
    pool = kuwaiti_pool(registry)
    scored = prefilter_and_score(ITEM, pool, None, settings)
    stores = [store for store in registry.active(settings) if store.id in KUWAITI_IDS]
    built = build_group(
        scored, settings, None, stores, item_index=0, category=Category.DRESSES, total=12
    )

    assert [tier.name for tier in built.group.tiers] == list(Tier)
    assert {tier.currency for tier in built.group.tiers} == {"AED"}
    assert [tier.count for tier in built.group.tiers] == [3, 3, 3, 3]
    # The cheapest range starts at KWD 55 (Amber Kaftan, Belle Dress): 655.60 AED, widened to a
    # whole dirham in the header. In raw numbers the dinar prices (55 to 320) would all look cheap.
    assert built.group.tiers[0].price_min == 655.0


@pytest.mark.parametrize(
    ("store_id", "answer", "title", "expected"),
    [
        (
            "bazza-alzouman",
            "suggest-gown.json",
            "Strapless Gown With Side Organza Ruched Drape",
            "245.000 KWD (about 2,920 AED)",
        ),
        ("hamsa-kw", "suggest-kaftan.json", "Riwaq Kaftan", "95.000 KWD (about 1,130 AED)"),
        (
            "manal-smaoui",
            "suggest-kaftan.json",
            "AICHA KAFTAN - BROWN",
            "85.000 KWD (about 1,010 AED)",
        ),
    ],
)
def test_a_dinar_product_from_each_store_reads_as_its_price_and_an_approximate_dirham_figure(
    registry: StoreRegistry,
    settings: Settings,
    store_id: str,
    answer: str,
    title: str,
    expected: str,
) -> None:
    [product] = pick(saved_products(registry, store_id, answer), title)
    _scored, shown = shown_products(registry, settings)
    by_title = {s.product.title: s for s in shown}

    assert line(by_title[title], settings) == expected
    # The store's own price, currency and link are untouched by scoring and the conversion.
    kept = by_title[title].product
    assert (kept.price, kept.currency, kept.product_url, kept.store) == (
        product.price,
        product.currency,
        product.product_url,
        product.store,
    )


def test_the_dirham_figure_is_what_the_budget_is_judged_by(
    registry: StoreRegistry, settings: Settings
) -> None:
    """A 2,500 AED budget: KWD 245 (2,920 AED) is over it, though 245 is less than 2,500, and KWD
    85 (1,013 AED) is within it. The flag, the reason sentence and the shown figure agree."""
    budget = Budget(max_price=2500, currency="AED")

    scored, shown = shown_products(registry, settings, budget)

    by_title = {s.product.title: s for s in shown}
    over = {s.product.title for s in scored if Flag.OVER_BUDGET in s.flags}
    assert "Strapless Gown With Side Organza Ruched Drape" in over
    assert "Rania Kaftan" in over  # KWD 320 is 3,814 AED
    assert "AICHA KAFTAN - BROWN" not in over
    assert "Riwaq Kaftan" not in over
    for title, wording in (
        ("Strapless Gown With Side Organza Ruched Drape", "Above"),
        ("AICHA KAFTAN - BROWN", "Within"),
    ):
        assert f"{wording} your" in by_title[title].reason
        assert (Flag.OVER_BUDGET in by_title[title].flags) is (wording == "Above")
