"""9.2.x and 9.3.1: selection, store cap, thin ranges, budget, flags and the output summary."""

import logging
import random
from collections.abc import Sequence

import pytest

from tests.factories import make_product, make_scored_product, make_scores, make_settings
from tests.tiers.helpers import (
    LUXURY_STORE,
    PLAIN_STORE,
    PRD_PRICES,
    STORE_NAMES,
    assert_invariants,
    default_total,
    make_pool,
    make_prd_pool,
    tier_counts,
    tier_prices,
)
from vga.models import TIER_ORDER, Budget, Flag, StoreConfig, Tier, TierMix
from vga.tiers import compute_borders, shape

BIG_STORES = tuple(f"Store {n:02d}" for n in range(1, 13))


# --- 9.2.1 best first, with a store cap ---------------------------------------------------------


def test_inside_a_range_the_best_scoring_products_come_first() -> None:
    # 64 products, 16 per quarter, scores that have nothing to do with price. Each range must hold
    # exactly the best-scoring products of its own quarter.
    prices = [10.0 * n for n in range(1, 65)]
    rng = random.Random(5)
    totals = {i: round(rng.uniform(0.3, 0.99), 4) for i in range(64)}
    pool = make_pool(prices, stores=BIG_STORES, totals=totals)
    settings = make_settings()

    result = shape(pool, settings, None, (LUXURY_STORE,))

    borders = compute_borders(prices)
    for tier, target in zip(TIER_ORDER, (8, 8, 7, 7), strict=True):
        natural = [p for p in pool if borders.tier_for(p.product.price) is tier]
        best = sorted(natural, key=lambda p: -p.scores.total)[:target]
        shown = next(t for t in result.tiers if t.name is tier).results
        assert {p.product.key for p in shown} == {p.product.key for p in best}
        assert [p.scores.total for p in shown] == sorted(
            (p.scores.total for p in best), reverse=True
        )


def test_equal_scores_keep_the_order_the_products_came_in() -> None:
    prices = [10.0 * n for n in range(1, 65)]
    pool = make_pool(prices, stores=BIG_STORES, totals=dict.fromkeys(range(64), 0.7))

    result = shape(pool, make_settings(), None, (LUXURY_STORE,))

    # Same score everywhere, so each range takes the first products of its quarter in input order.
    assert tier_prices(result)[0] == tuple(prices[:8])
    assert tier_prices(result)[1] == tuple(prices[16:24])
    assert tier_prices(result)[2] == tuple(prices[32:39])
    assert tier_prices(result)[3] == tuple(prices[48:55])


def test_input_order_does_not_matter_when_scores_differ() -> None:
    pool = make_prd_pool()
    shuffled = pool[:]
    random.Random(3).shuffle(shuffled)

    first = shape(pool, make_settings(), None, (LUXURY_STORE,))
    second = shape(shuffled, make_settings(), None, (LUXURY_STORE,))

    assert first == second


def test_no_store_exceeds_the_cap_even_when_it_has_the_best_products() -> None:
    # "Big Store" owns the 12 best-scoring products of 32; the cap of 6 still holds.
    pool = make_pool(
        PRD_PRICES,
        stores=("Big Store",) * 12 + STORE_NAMES * 4,
    )[:32]
    result = shape(pool, make_settings(), None, (LUXURY_STORE,))
    shown_from_big = [p for p in result.products if p.product.store == "Big Store"]
    assert len(shown_from_big) == 6
    assert_invariants(result, pool, make_settings(), stores=(LUXURY_STORE,))


def test_the_cap_is_a_setting() -> None:
    pool = make_pool([10.0 * n for n in range(1, 31)], stores=("Solo",))
    result = shape(pool, make_settings(max_per_store=3), None, (LUXURY_STORE,))
    assert sum(tier_counts(result)) == 3


def test_when_the_cap_forces_a_choice_every_range_gets_a_share() -> None:
    # One store, cap 6, 30 candidates: the 6 slots are not all spent on the cheapest range.
    pool = make_pool([10.0 * n for n in range(1, 31)], stores=("Solo",))
    result = shape(pool, make_settings(), None, (PLAIN_STORE,))
    assert all(count >= 1 for count in tier_counts(result))


def test_a_store_is_keyed_by_its_display_name() -> None:
    # Two products with the same store name count against the same cap even from different URLs.
    pool = [
        make_scored_product(
            make_product(n, price=10.0 * n, store="Same Name"),
            scores=make_scores(total=default_total(n)),
        )
        for n in range(1, 11)
    ]
    result = shape(pool, make_settings(max_per_store=4), None, (LUXURY_STORE,))
    assert sum(tier_counts(result)) == 4


# --- 9.2.2 thin ranges: which range lends, and in which order ----------------------------------


def test_a_thin_range_borrows_from_the_cheaper_side_first_when_both_sides_are_equally_near() -> (
    None
):
    # Mix 10/40/10/40 of 30 = targets 3/12/3/12. Mid-range has 8 products of its own and needs 4
    # more. Budget (one step below) and Premium (one step above) both have spare products; the
    # cheaper side lends first, best score first: the Budget products at 89, 99, 112 and 125.
    mix = TierMix(budget=10, mid_range=40, premium=10, luxury=40)
    pool = make_pool(PRD_PRICES)
    result = shape(pool, make_settings(tier_mix=mix), None, (LUXURY_STORE,))

    budget, mid, premium, luxury = result.tiers
    assert tier_counts(result) == (3, 12, 3, 12)
    borrowed_then_own = [89.0, 99.0, 112.0, 125.0, 140.0, 169.0, 189.0, 209.0, 229.0, 249.0]
    assert [p.product.price for p in mid.results] == [*borrowed_then_own, 279.0, 299.0]
    assert Flag.FEW_OPTIONS in mid.flags
    assert Flag.FEW_OPTIONS in luxury.flags  # Luxury is thin too and borrows from Premium
    assert [p.product.price for p in budget.results] == [45.0, 59.0, 72.0]
    assert [p.product.price for p in premium.results] == [300.0, 349.0, 399.0]


def test_a_thin_range_never_borrows_from_a_range_two_or_more_steps_away() -> None:
    # Mix 25/35/25/15 of 30 = targets 8/11/7/4. Mid-range owns 8 and needs 3 more. Budget has no
    # spare product (8 of 8 used), Premium has 1 (699), and Luxury has 4 spare (1,600 AED and
    # up) but is two steps away. Mid-range takes only Premium's one: 9 of 11, flagged.
    mix = TierMix(budget=25, mid_range=35, premium=25, luxury=15)
    pool = make_pool(PRD_PRICES)
    result = shape(pool, make_settings(tier_mix=mix), None, (LUXURY_STORE,))

    _, mid, _, _ = result.tiers
    assert tier_counts(result) == (8, 9, 7, 4)
    assert [p.product.price for p in mid.results][-2:] == [299.0, 699.0]
    assert mid.price_max == 699.0
    assert Flag.FEW_OPTIONS in mid.flags


@pytest.mark.parametrize(
    ("mix", "thin_index", "lender_index"),
    [
        pytest.param(TierMix(budget=60, mid_range=10, premium=10, luxury=20), 0, 1, id="budget"),
        pytest.param(TierMix(budget=10, mid_range=10, premium=10, luxury=70), 3, 2, id="luxury"),
    ],
)
def test_budget_borrows_only_from_mid_range_and_luxury_only_from_premium(
    mix: TierMix, thin_index: int, lender_index: int
) -> None:
    result = shape(make_pool(PRD_PRICES), make_settings(tier_mix=mix), None, (LUXURY_STORE,))
    borders = result.borders
    assert borders is not None
    thin = result.tiers[thin_index]
    assert Flag.FEW_OPTIONS in thin.flags
    assert thin.count < thin.target_count  # the gap is not closed from farther away
    for scored in thin.results:
        natural = list(TIER_ORDER).index(borders.tier_for(scored.product.price))
        assert abs(natural - thin_index) <= 1


def test_a_range_that_borrowed_enough_is_still_flagged_few_options() -> None:
    # The flag says the range did not have enough products of its own, whether or not the gap
    # could be closed. "exactly_30_results" is the same case: Mid-range reaches 8 by borrowing.
    pool = make_pool([20.0 * n for n in range(1, 31)])
    result = shape(pool, make_settings(), None, (LUXURY_STORE,))
    mid = result.tiers[1]
    assert mid.count == mid.target_count == 8
    assert Flag.FEW_OPTIONS in mid.flags


def test_a_borrowed_product_is_shown_in_the_range_it_fills_and_widens_its_price_span() -> None:
    mix = TierMix(budget=25, mid_range=35, premium=25, luxury=15)
    result = shape(make_pool(PRD_PRICES), make_settings(tier_mix=mix), None, (LUXURY_STORE,))
    mid = result.tiers[1]
    assert all(p.tier is Tier.MID_RANGE for p in mid.results)
    assert (mid.price_min, mid.price_max) == (140.0, 699.0)
    assert mid.display_label == "Mid-range · 140-699 AED · 9 results"


def test_thin_ranges_are_served_cheapest_first() -> None:
    # Mix 30/10/30/30 of 30 = targets 9/3/9/9. Budget and Premium each own 8 and are one short;
    # both neighbour Mid-range, which owns 8 and needs only 3, so it has 5 spare (209, 229, ...).
    # Budget is served first and takes the best spare (209); Premium then takes the next (229).
    mix = TierMix(budget=30, mid_range=10, premium=30, luxury=30)
    result = shape(make_pool(PRD_PRICES), make_settings(tier_mix=mix), None, (LUXURY_STORE,))
    budget, _, premium, _ = result.tiers
    assert tier_counts(result) == (9, 3, 9, 8)
    assert budget.results[-1].product.price == 209.0
    assert premium.results[0].product.price == 229.0


def test_an_empty_range_has_no_price_span_and_the_few_options_flag() -> None:
    result = shape(make_pool([120.0]), make_settings(), None, (LUXURY_STORE,))
    mid = result.tiers[1]
    assert mid.count == 0
    assert (mid.price_min, mid.price_max, mid.currency) == (None, None, None)
    assert mid.flags == [Flag.FEW_OPTIONS]
    assert mid.display_label == "Mid-range · no results"


def test_products_below_the_minimum_match_score_are_never_used() -> None:
    low = 0.19
    pool = make_pool([100.0, 200.0, 300.0, 400.0], totals={1: low, 3: low})
    result = shape(pool, make_settings(min_match_score=0.2), None, (LUXURY_STORE,))
    shown = {p.product.price for p in result.products}
    assert shown == {100.0, 300.0}


def test_a_product_scoring_exactly_the_minimum_is_kept() -> None:
    pool = make_pool([100.0, 200.0], totals={0: 0.2, 1: 0.2})
    result = shape(pool, make_settings(min_match_score=0.2), None, (LUXURY_STORE,))
    assert sum(tier_counts(result)) == 2


# --- 9.2.3 budget -------------------------------------------------------------------------------


def test_a_product_at_exactly_the_budget_is_within_it() -> None:
    # The PRD example's Premium range starts at 300, and the budget is 300.
    budget = Budget(max_price=300, currency="AED")
    result = shape(make_prd_pool(), make_settings(), budget, (LUXURY_STORE,))
    premium = result.tiers[2]
    at_budget = next(p for p in premium.results if p.product.price == 300.0)
    assert Flag.OVER_BUDGET not in at_budget.flags
    over = [p for p in premium.results if p.product.price > 300.0]
    assert over
    assert all(Flag.OVER_BUDGET in p.flags for p in over)


def test_budget_and_mid_range_never_hold_a_product_over_budget() -> None:
    for max_price in (40, 100, 150, 250, 299, 300, 5000):
        budget = Budget(max_price=max_price, currency="AED")
        result = shape(make_prd_pool(), make_settings(), budget, (LUXURY_STORE,))
        for tier in result.tiers[:2]:
            assert all(p.product.price <= max_price for p in tier.results), max_price


def test_over_budget_products_may_fill_a_thin_premium_or_luxury_range() -> None:
    # Mix 10/10/10/70 of 30 with a budget of 100 AED: Luxury wants 21 and owns 8, and borrows
    # Premium's 5 spare products (449-699 AED, over budget and flagged). Mid-range's products are
    # two steps away, so Luxury stops at 13. Whatever the source, the flag follows the price.
    budget = Budget(max_price=100, currency="AED")
    mix = TierMix(budget=10, mid_range=10, premium=10, luxury=70)
    result = shape(make_pool(PRD_PRICES), make_settings(tier_mix=mix), budget, (LUXURY_STORE,))
    luxury = result.tiers[3]
    assert luxury.count == 13
    for scored in luxury.results:
        assert (Flag.OVER_BUDGET in scored.flags) == (scored.product.price > 100)


def test_borders_are_computed_over_every_candidate_including_over_budget_ones() -> None:
    pool = make_prd_pool()
    with_budget = shape(pool, make_settings(), Budget(max_price=100, currency="AED"), ())
    without = shape(pool, make_settings(), None, ())
    assert with_budget.borders == without.borders == compute_borders([float(p) for p in PRD_PRICES])


def test_the_shaper_owns_the_over_budget_flag() -> None:
    stale = make_scored_product(
        make_product(1, price=150.0),
        scores=make_scores(total=0.9),
        flags=[Flag.OVER_BUDGET],
    )
    other = make_scored_product(
        make_product(2, price=900.0, store="Gulf Threads"),
        scores=make_scores(total=0.8),
        flags=[Flag.FEW_OPTIONS],
    )
    # No budget given now: a flag left over from an earlier step is removed, other flags stay.
    result = shape([stale, other], make_settings(), None, (LUXURY_STORE,))
    shown = {p.product.price: p for p in result.products}
    assert shown[150.0].flags == []
    assert shown[900.0].flags == [Flag.FEW_OPTIONS]
    # A budget of 500 flags the 900 product and leaves the 150 one alone.
    result = shape(
        [stale, other], make_settings(), Budget(max_price=500, currency="AED"), (LUXURY_STORE,)
    )
    shown = {p.product.price: p for p in result.products}
    assert shown[150.0].flags == []
    assert shown[900.0].flags == [Flag.FEW_OPTIONS, Flag.OVER_BUDGET]


def test_a_budget_in_another_currency_is_not_applied_and_the_caller_is_told() -> None:
    result = shape(
        make_prd_pool(), make_settings(), Budget(max_price=50, currency="USD"), (LUXURY_STORE,)
    )
    assert tier_counts(result) == (8, 8, 7, 7)
    assert result.warnings == [
        "Your budget is in USD but the prices found are in AED, so the budget was not applied."
    ]


# --- 9.2.4 relative range -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stores", "flagged"),
    [
        pytest.param((LUXURY_STORE,), False, id="a_luxury_store_is_enabled"),
        pytest.param((PLAIN_STORE,), True, id="no_luxury_store"),
        pytest.param((PLAIN_STORE, LUXURY_STORE), False, id="luxury_among_others"),
        pytest.param((), True, id="no_stores_passed"),
    ],
)
def test_relative_range_flag_on_luxury(stores: Sequence[StoreConfig], flagged: bool) -> None:
    result = shape(make_prd_pool(), make_settings(), None, stores)
    for tier in result.tiers:
        expected = flagged and tier.name is Tier.LUXURY
        assert (Flag.RELATIVE_RANGE in tier.flags) is expected


def test_relative_range_is_set_even_when_luxury_is_empty() -> None:
    result = shape(make_pool([100.0]), make_settings(), None, (PLAIN_STORE,))
    assert result.tiers[3].count == 0
    assert Flag.RELATIVE_RANGE in result.tiers[3].flags


# --- currency -----------------------------------------------------------------------------------


def test_the_most_common_currency_is_shaped_and_the_rest_reported() -> None:
    # Since the Kuwaiti stores the AED products are shaped because they are in the base currency
    # and the USD ones have no rate (see tests/tiers/test_currencies.py), not because AED is the
    # more common; the outcome for this data is the same.
    aed = make_pool([100.0, 200.0, 300.0, 400.0, 500.0])
    usd = make_pool([50.0, 60.0], currency="USD", start=50)
    result = shape([*usd, *aed], make_settings(), None, (LUXURY_STORE,))
    assert result.currency == "AED"
    assert {p.product.currency for p in result.products} == {"AED"}
    assert len(result.warnings) == 1
    assert "USD" in result.warnings[0]
    assert "tier" not in result.warnings[0].lower()


def test_a_currency_tie_no_longer_decides_anything_a_currency_with_no_rate_is_left_out() -> None:
    # Before the Kuwaiti stores the most common currency won, and a tie went to the currency of the
    # best-scoring product (here USD). Now every product with a base-currency figure is shaped, and
    # USD has no rate in these settings, so the better-scoring USD products are left out.
    usd = make_pool([100.0, 200.0], currency="USD", start=50, totals={0: 0.9, 1: 0.9})
    aed = make_pool([100.0, 200.0], currency="AED", start=60, totals={0: 0.5, 1: 0.5})
    result = shape([*aed, *usd], make_settings(), None, (LUXURY_STORE,))
    assert result.currency == "AED"
    assert {p.product.currency for p in result.products} == {"AED"}


def test_leaving_products_out_for_currency_is_logged_as_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    usd = make_pool([50.0], currency="USD", start=50)
    aed = make_pool([100.0, 200.0])
    with caplog.at_level(logging.WARNING, logger="vga.tiers"):
        shape([*usd, *aed], make_settings(), None, (LUXURY_STORE,))
    assert any("other currencies" in record.getMessage() for record in caplog.records)


# --- 9.3.1 output summary -----------------------------------------------------------------------


def test_the_labels_follow_the_prd_format() -> None:
    result = shape(make_prd_pool(), make_settings(), None, (LUXURY_STORE,))
    assert result.tiers[0].display_label == "Budget · 45-139 AED · 8 results"


def test_a_single_result_is_singular_and_a_single_price_has_no_dash() -> None:
    result = shape(make_pool([349.0]), make_settings(), None, (LUXURY_STORE,))
    assert result.tiers[0].display_label == "Budget · 349 AED · 1 result"


def test_each_range_reports_its_real_minimum_and_maximum() -> None:
    result = shape(make_prd_pool(), make_settings(), None, (LUXURY_STORE,))
    spans = [(t.price_min, t.price_max) for t in result.tiers]
    assert spans == [(45.0, 139.0), (140.0, 299.0), (300.0, 699.0), (700.0, 2400.0)]
    assert [t.target_count for t in result.tiers] == [8, 8, 7, 7]
    assert all(t.currency == "AED" for t in result.tiers)


def test_the_four_ranges_come_in_display_order_even_with_no_products() -> None:
    result = shape([], make_settings(), None, ())
    assert [t.name for t in result.tiers] == list(TIER_ORDER)
    assert result.borders is None
    assert result.currency is None


def test_the_result_is_deterministic() -> None:
    pool = make_prd_pool()
    settings = make_settings()
    assert shape(pool, settings, None, (LUXURY_STORE,)) == shape(
        pool, settings, None, (LUXURY_STORE,)
    )


def test_a_negative_total_is_an_error() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        shape(make_prd_pool(), make_settings(), None, (), total=-1)


def test_total_defaults_to_the_results_setting() -> None:
    pool = make_pool([10.0 * n for n in range(1, 101)], stores=BIG_STORES * 2)
    default = shape(pool, make_settings(results=20), None, (LUXURY_STORE,))
    explicit = shape(pool, make_settings(results=30), None, (LUXURY_STORE,), total=20)
    assert tier_counts(default) == tier_counts(explicit) == (5, 5, 5, 5)
