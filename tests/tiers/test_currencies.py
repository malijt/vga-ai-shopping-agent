"""Price ranges across currencies (Kuwaiti dinar, 2026-10-08 decision).

Every product that has a base-currency figure is shaped together: the borders, each range's span
and the over-budget flags are all measured in the base currency (AED), the figure is stored on the
result as ``base_price``, and a product whose currency has no rate is left out with a warning.

The rate in most of these tests is a round 1 KWD = 10 AED, so the expected numbers can be checked
by eye. ``test_walking_a_mixed_list_...`` at the end uses the shipped rate, 11.92.
"""

import logging

import pytest

from tests.factories import make_item_intent, make_product, make_scored_product, make_settings
from tests.tiers.helpers import (
    LUXURY_STORE,
    assert_invariants,
    make_pool,
    make_prd_pool,
    tier_counts,
)
from vga.models import TIER_ORDER, Budget, Category, Flag, Product, ScoredProduct, Tier
from vga.money import format_price
from vga.rank import prefilter_and_score
from vga.tiers import PriceBorders, ShapeResult, build_group, shape

FX = make_settings(fx_rates={"KWD": 10.0})
STORES = (LUXURY_STORE,)


def mixed_pool() -> list[ScoredProduct]:
    """Four AED and four KWD products, best first. In AED the eight prices are 100, 200, 250,
    300, 350, 400, 450 and 550 (the dinar ones are 250, 350, 450 and 550)."""
    aed = make_pool([100.0, 200.0, 300.0, 400.0], start=1)
    kwd = make_pool([25.0, 35.0, 45.0, 55.0], currency="KWD", start=11)
    return [*aed, *kwd]


def shown(result: ShapeResult) -> dict[float, ScoredProduct]:
    """The shown products by their own price (unique in these pools, KWD ones too)."""
    return {p.product.price: p for p in result.products}


# --------------------------------------------------------------------------------------------
# Shaped together, in the base currency
# --------------------------------------------------------------------------------------------


def test_aed_and_dinar_products_are_shaped_together_in_dirhams() -> None:
    pool = mixed_pool()

    result = shape(pool, FX, None, STORES, total=8)

    assert result.currency == "AED"
    assert result.warnings == []
    assert tier_counts(result) == (2, 2, 2, 2)
    assert {p.product.currency for p in result.products} == {"AED", "KWD"}
    assert_invariants(result, pool, FX, total=8, stores=STORES)


def test_the_borders_are_quartiles_of_the_dirham_figures() -> None:
    result = shape(mixed_pool(), FX, None, STORES, total=8)

    # Sorted in AED: 100, 200, 250, 300, 350, 400, 450, 550. Nearest-rank quartiles are the 2nd,
    # 4th and 6th: 200, 300 and 400. In raw numbers the dinar products (25 to 55) would all sit
    # in Budget.
    assert result.borders == PriceBorders(200.0, 300.0, 400.0)


def test_each_product_lands_in_the_range_its_dirham_figure_belongs_to() -> None:
    result = shape(mixed_pool(), FX, None, STORES, total=8)

    by_price = shown(result)
    assert by_price[25.0].tier is Tier.MID_RANGE  # KWD 25 is AED 250
    assert by_price[35.0].tier is Tier.PREMIUM
    assert by_price[45.0].tier is Tier.LUXURY
    assert by_price[100.0].tier is Tier.BUDGET  # an AED price keeps its own figure
    assert by_price[300.0].tier is Tier.MID_RANGE


def test_a_product_exactly_on_a_border_in_dirhams_goes_to_the_cheaper_range() -> None:
    # KWD 30 is exactly AED 300, which is the second border: the tie rule applies across currencies.
    aed = make_pool([100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0], start=1)
    kwd = make_pool([30.0], currency="KWD", start=21)

    result = shape([*aed, *kwd], FX, None, STORES, total=8)

    by_tier = {tier.name: {p.product.price for p in tier.results} for tier in result.tiers}
    assert result.borders == PriceBorders(200.0, 300.0, 500.0)
    assert {30.0, 300.0} <= by_tier[Tier.MID_RANGE]


def test_the_span_of_each_range_is_in_dirhams_and_the_header_says_so() -> None:
    result = shape(mixed_pool(), FX, None, STORES, total=8)

    assert [(t.price_min, t.price_max) for t in result.tiers] == [
        (100.0, 200.0),
        (250.0, 300.0),
        (350.0, 400.0),
        (450.0, 550.0),
    ]
    assert all(t.currency == "AED" for t in result.tiers)
    assert [t.display_label for t in result.tiers] == [
        "Budget · 100-200 AED · 2 results",
        "Mid-range · 250-300 AED · 2 results",
        "Premium · 350-400 AED · 2 results",
        "Luxury · 450-550 AED · 2 results",
    ]


def test_a_range_holding_a_converted_product_widens_its_span_to_whole_dirhams() -> None:
    # KWD 25.55 is AED 255.50 and KWD 32.17 is AED 321.70: a header must not claim cents from a
    # fixed approximate rate, and the span must still cover every product in it.
    aed = make_pool([100.0, 200.0, 400.0, 500.0, 600.0, 700.0], start=1)
    kwd = make_pool([25.55, 32.17], currency="KWD", start=21)

    result = shape([*aed, *kwd], FX, None, STORES, total=8)

    mid = result.tiers[1]
    assert sorted(
        p.base_price if p.base_price is not None else p.product.price for p in mid.results
    ) == [255.5, 321.7]
    assert (mid.price_min, mid.price_max) == (255.0, 322.0)
    assert mid.display_label == "Mid-range · 255-322 AED · 2 results"


def test_a_range_with_only_dirham_products_keeps_its_exact_span() -> None:
    aed = make_pool([89.5, 120.25, 250.0, 300.0, 350.0, 400.0, 450.0, 550.0])
    kwd: list[ScoredProduct] = []

    result = shape([*aed, *kwd], FX, None, STORES, total=8)

    assert (result.tiers[0].price_min, result.tiers[0].price_max) == (89.5, 120.25)


def test_a_converted_price_under_one_dirham_keeps_a_valid_span() -> None:
    cheap = make_pool([0.05], currency="KWD", start=1)  # AED 0.50

    result = shape(cheap, FX, None, STORES, total=8)

    [low] = result.tiers[0].results
    assert low.base_price == 0.5
    assert (result.tiers[0].price_min, result.tiers[0].price_max) == (0.5, 1.0)


# --------------------------------------------------------------------------------------------
# The result carries the figure
# --------------------------------------------------------------------------------------------


def test_a_converted_product_carries_its_dirham_figure_and_an_aed_product_carries_none() -> None:
    result = shape(mixed_pool(), FX, None, STORES, total=8)

    by_price = shown(result)
    assert by_price[25.0].base_price == 250.0
    assert by_price[55.0].base_price == 550.0
    assert by_price[100.0].base_price is None
    assert by_price[400.0].base_price is None


def test_the_product_keeps_its_own_price_and_currency() -> None:
    result = shape(mixed_pool(), FX, None, STORES, total=8)

    kwd = shown(result)[25.0].product
    assert (kwd.price, kwd.currency) == (25.0, "KWD")


def test_shaping_again_recomputes_the_figure_from_the_current_rate() -> None:
    first = shape(mixed_pool(), FX, None, STORES, total=8)
    shaped = first.products
    new_rates = make_settings(fx_rates={"KWD": 12.0})

    again = shape(shaped, new_rates, None, STORES, total=8)

    assert shown(again)[25.0].base_price == 300.0


def test_a_stale_figure_on_an_aed_product_is_cleared() -> None:
    stale = make_scored_product(make_product(1, price=100.0), base_price=999.0)

    result = shape([stale], FX, None, STORES, total=8)

    assert result.products[0].base_price is None


def test_the_shown_prices_read_as_the_shopper_should_see_them() -> None:
    result = shape(mixed_pool(), FX, None, STORES, total=8)

    lines = {
        p.product.price: format_price(
            p.product.price,
            p.product.currency,
            base_price=p.base_price,
            base_currency=FX.base_currency,
        )
        for p in result.products
    }

    assert lines[100.0] == "100 AED"
    assert lines[25.0] == "25.000 KWD (about 250 AED)"
    assert lines[55.0] == "55.000 KWD (about 550 AED)"


# --------------------------------------------------------------------------------------------
# A currency with no rate
# --------------------------------------------------------------------------------------------


def test_a_product_in_a_currency_with_no_rate_is_left_out_and_the_caller_is_told() -> None:
    sar = make_pool([60.0, 80.0], currency="SAR", start=50)

    result = shape([*sar, *mixed_pool()], FX, None, STORES, total=8)

    assert {p.product.currency for p in result.products} == {"AED", "KWD"}
    assert len(result.warnings) == 1
    assert "SAR" in result.warnings[0]
    assert "2" in result.warnings[0]
    assert "tier" not in result.warnings[0].lower()
    assert result.currency == "AED"


def test_the_warning_names_every_currency_that_was_left_out() -> None:
    sar = make_pool([60.0], currency="SAR", start=50)
    usd = make_pool([70.0, 90.0, 95.0], currency="USD", start=60)

    result = shape([*sar, *usd, *mixed_pool()], FX, None, STORES, total=8)

    [warning] = result.warnings
    assert "SAR" in warning
    assert "USD" in warning
    assert "KWD" not in warning


def test_a_currency_with_no_rate_is_left_out_even_when_it_scores_best() -> None:
    usd = [
        p.model_copy(update={"scores": p.scores.model_copy(update={"total": 0.99})})
        for p in make_pool([100.0, 200.0], currency="USD", start=50)
    ]

    result = shape([*usd, *mixed_pool()], FX, None, STORES, total=8)

    assert {p.product.currency for p in result.products} == {"AED", "KWD"}
    assert result.currency == "AED"


def test_leaving_a_product_out_for_a_missing_rate_is_logged_as_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sar = make_pool([60.0], currency="SAR", start=50)

    with caplog.at_level(logging.WARNING, logger="vga.tiers"):
        shape([*sar, *mixed_pool()], FX, None, STORES, total=8)

    assert any("no exchange rate" in record.getMessage() for record in caplog.records)


def test_without_any_rates_a_dinar_product_is_left_out_as_before() -> None:
    result = shape(mixed_pool(), make_settings(), None, STORES, total=8)

    assert {p.product.currency for p in result.products} == {"AED"}
    assert any("KWD" in warning for warning in result.warnings)


def test_a_list_with_nothing_convertible_gives_four_empty_ranges() -> None:
    sar = make_pool([60.0, 80.0], currency="SAR", start=50)

    result = shape(sar, FX, None, STORES, total=8)

    assert tier_counts(result) == (0, 0, 0, 0)
    assert result.currency is None
    assert result.borders is None
    assert [t.name for t in result.tiers] == list(TIER_ORDER)
    assert len(result.warnings) == 1


def test_a_run_of_dinar_products_alone_is_shaped_in_dirhams() -> None:
    kwd = make_pool([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0], currency="KWD")

    result = shape(kwd, FX, None, STORES, total=8)

    assert result.currency == "AED"
    assert result.borders == PriceBorders(200.0, 400.0, 600.0)
    assert [t.currency for t in result.tiers] == ["AED"] * 4
    assert result.warnings == []


# --------------------------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------------------------


def over_budget(result: ShapeResult) -> set[float]:
    return {p.product.price for p in result.products if Flag.OVER_BUDGET in p.flags}


def test_the_over_budget_flag_follows_the_converted_figure() -> None:
    # Budget AED 360. KWD 45 and 55 are 450 and 550 in dirhams: over, though 45 and 55 are far
    # below 360 as bare numbers.
    budget = Budget(max_price=360, currency="AED")

    result = shape(mixed_pool(), FX, budget, STORES, total=8)

    assert over_budget(result) == {45.0, 55.0, 400.0}
    assert shown(result)[35.0].flags == []  # KWD 35 is AED 350, within 360
    assert_invariants(result, mixed_pool(), FX, total=8, budget=budget, stores=STORES)


def test_budget_and_mid_range_hold_only_products_within_the_converted_budget() -> None:
    budget = Budget(max_price=360, currency="AED")

    result = shape(mixed_pool(), FX, budget, STORES, total=8)

    for tier in result.tiers[:2]:
        for scored in tier.results:
            base = scored.base_price if scored.base_price is not None else scored.product.price
            assert base <= 360


def test_a_budget_in_dinars_is_converted_too() -> None:
    budget = Budget(max_price=36, currency="KWD")  # AED 360

    result = shape(mixed_pool(), FX, budget, STORES, total=8)

    assert over_budget(result) == {45.0, 55.0, 400.0}
    assert result.warnings == []


def test_a_budget_in_a_currency_with_no_rate_is_not_applied_and_the_caller_is_told() -> None:
    result = shape(mixed_pool(), FX, Budget(max_price=50, currency="USD"), STORES, total=8)

    assert over_budget(result) == set()
    assert result.warnings == [
        "Your budget is in USD but the prices found are in AED, so the budget was not applied."
    ]


def test_a_budget_in_a_third_currency_with_a_rate_is_applied() -> None:
    rates = make_settings(fx_rates={"KWD": 10.0, "USD": 4.0})
    budget = Budget(max_price=90, currency="USD")  # AED 360

    result = shape(mixed_pool(), rates, budget, STORES, total=8)

    assert over_budget(result) == {45.0, 55.0, 400.0}
    assert result.warnings == []


# --------------------------------------------------------------------------------------------
# An AED-only run is untouched
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("budget", [None, Budget(max_price=300, currency="AED")])
def test_an_aed_only_run_is_the_same_with_or_without_rates_in_settings(
    budget: Budget | None,
) -> None:
    pool = make_prd_pool()

    without = shape(pool, make_settings(), budget, STORES)
    with_rates = shape(pool, FX, budget, STORES)

    assert with_rates == without
    assert all(p.base_price is None for p in with_rates.products)
    assert [(t.price_min, t.price_max) for t in with_rates.tiers] == [
        (45.0, 139.0),
        (140.0, 299.0),
        (300.0, 699.0),
        (700.0, 2400.0),
    ]


# --------------------------------------------------------------------------------------------
# The store cap still counts across currencies
# --------------------------------------------------------------------------------------------


def test_the_per_store_cap_applies_to_a_dinar_store_like_any_other() -> None:
    settings = make_settings(fx_rates={"KWD": 10.0}, max_per_store=2)
    kwd = make_pool([float(n) for n in range(10, 50, 4)], currency="KWD", stores=("Hamsa",))
    aed = make_pool([100.0 * n for n in range(1, 9)], stores=("Souq Atelier", "Gulf Threads"))

    result = shape([*kwd, *aed], settings, None, STORES, total=8)

    hamsa = [p for p in result.products if p.product.store == "Hamsa"]
    assert len(hamsa) == 2


# --------------------------------------------------------------------------------------------
# The whole path: scoring, then the price ranges
# --------------------------------------------------------------------------------------------

REAL_RATE = make_settings(fx_rates={"KWD": 11.92})
ITEM = make_item_intent()  # black oversized blazer


def real_mixed_products() -> list[Product]:
    """Eight AED and eight dinar products. In dirhams, at 11.92: AED 80, 150, 220, 310, 480, 650,
    900, 1,500 and KWD 5, 10, 20, 29, 45, 55, 85, 245 = 59.60, 119.20, 238.40, 345.68, 536.40,
    655.60, 1,013.20, 2,920.40 (the KWD prices are real ones from the qualification samples)."""
    aed_prices = [80.0, 150.0, 220.0, 310.0, 480.0, 650.0, 900.0, 1500.0]
    kwd_prices = [5.0, 10.0, 20.0, 29.0, 45.0, 55.0, 85.0, 245.0]
    aed_stores = ("Souq Atelier", "Gulf Threads")
    kwd_stores = ("Hamsa", "Manal Smaoui")
    products = [
        make_product(index, price=price, store=aed_stores[index % 2], category=Category.OUTERWEAR)
        for index, price in enumerate(aed_prices, start=1)
    ]
    products += [
        make_product(
            index,
            price=price,
            currency="KWD",
            store=kwd_stores[index % 2],
            category=Category.OUTERWEAR,
        )
        for index, price in enumerate(kwd_prices, start=21)
    ]
    return products


def test_walking_a_mixed_list_through_scoring_and_the_price_ranges() -> None:
    budget = Budget(max_price=540, currency="AED")
    products = real_mixed_products()

    scored = prefilter_and_score(ITEM, products, budget, REAL_RATE)
    built = build_group(
        scored,
        REAL_RATE,
        budget,
        STORES,
        item_index=0,
        category=Category.OUTERWEAR,
        total=16,
    )

    # Scoring kept all 16 and flagged, before any shaping, exactly the products above 540 AED:
    # KWD 55 (AED 655.60) and 85 and 245 and AED 650, 900 and 1,500. KWD 45 (AED 536.40) is within.
    assert len(scored) == 16
    flagged_by_scoring = {
        (s.product.currency, s.product.price) for s in scored if Flag.OVER_BUDGET in s.flags
    }
    assert flagged_by_scoring == {
        ("KWD", 55.0),
        ("KWD", 85.0),
        ("KWD", 245.0),
        ("AED", 650.0),
        ("AED", 900.0),
        ("AED", 1500.0),
    }

    # The borders are the 4th, 8th and 12th cheapest of the 16 dirham figures.
    shaped = shape(scored, REAL_RATE, budget, STORES, total=16)
    assert shaped.borders == PriceBorders(150.0, 345.68, 655.6)
    assert built.warnings == []
    tiers = {tier.name: tier for tier in built.group.tiers}
    assert [tier.count for tier in built.group.tiers] == [4, 4, 4, 4]
    assert all(tier.currency == "AED" for tier in built.group.tiers)

    def members(tier: Tier) -> list[tuple[str, float]]:
        return sorted((s.product.currency, s.product.price) for s in tiers[tier].results)

    assert members(Tier.BUDGET) == [("AED", 80.0), ("AED", 150.0), ("KWD", 5.0), ("KWD", 10.0)]
    assert members(Tier.MID_RANGE) == [
        ("AED", 220.0),
        ("AED", 310.0),
        ("KWD", 20.0),
        ("KWD", 29.0),
    ]
    assert members(Tier.PREMIUM) == [
        ("AED", 480.0),
        ("AED", 650.0),
        ("KWD", 45.0),
        ("KWD", 55.0),
    ]
    assert members(Tier.LUXURY) == [
        ("AED", 900.0),
        ("AED", 1500.0),
        ("KWD", 85.0),
        ("KWD", 245.0),
    ]

    # Spans are in dirhams, widened outward to whole dirhams because each range holds a dinar
    # product: 59.60 to 150, 220 to 345.68, 480 to 655.60 and 900 to 2,920.40.
    assert [tier.display_label for tier in built.group.tiers] == [
        "Budget · 59-150 AED · 4 results",
        "Mid-range · 220-346 AED · 4 results",
        "Premium · 480-656 AED · 4 results",
        "Luxury · 900-2,921 AED · 4 results",
    ]

    # The shaper's flags are the scorer's: KWD 55 is over 540 AED though 55 is below 540.
    flagged_by_shaping = {
        (s.product.currency, s.product.price)
        for tier in built.group.tiers
        for s in tier.results
        if Flag.OVER_BUDGET in s.flags
    }
    assert flagged_by_shaping == flagged_by_scoring
    assert [
        sum(Flag.OVER_BUDGET in s.flags for s in tier.results) for tier in built.group.tiers
    ] == [0, 0, 2, 4]

    # The reason sentence agrees with the flag.
    for tier in built.group.tiers:
        for s in tier.results:
            wording = "Above" if Flag.OVER_BUDGET in s.flags else "Within"
            assert f"{wording} your 540 AED budget." in s.reason

    # The figure travels on the result, and the prices read as the shopper should see them.
    lines = {
        (s.product.currency, s.product.price): format_price(
            s.product.price,
            s.product.currency,
            base_price=s.base_price,
            base_currency=REAL_RATE.base_currency,
        )
        for tier in built.group.tiers
        for s in tier.results
    }
    assert lines[("AED", 650.0)] == "650 AED"
    assert lines[("KWD", 5.0)] == "5.000 KWD (about 60 AED)"
    assert lines[("KWD", 29.0)] == "29.000 KWD (about 350 AED)"
    assert lines[("KWD", 45.0)] == "45.000 KWD (about 540 AED)"
    assert lines[("KWD", 55.0)] == "55.000 KWD (about 660 AED)"
    assert lines[("KWD", 245.0)] == "245.000 KWD (about 2,920 AED)"
    base_prices = {
        (s.product.currency, s.product.price): s.base_price
        for tier in built.group.tiers
        for s in tier.results
    }
    assert base_prices[("KWD", 245.0)] == 2920.4
    assert base_prices[("KWD", 55.0)] == 655.6
    assert base_prices[("AED", 650.0)] is None
