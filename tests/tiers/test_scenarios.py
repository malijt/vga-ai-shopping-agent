"""9.3.3 Table-driven edge suite: named scenarios, each stating expected counts and flags.

Every scenario below says in its docstring-like comment WHY the expected numbers are what they are.
The numbers were worked out by hand from the rules in ``vga.tiers.shaper``, not copied from output.

Reading the tables: counts and flags are in display order Budget, Mid-range, Premium, Luxury.
"F" means the range carries ``few_options``, "R" means ``relative_range``. The default stores
contain one luxury store, so ``relative_range`` only shows where a scenario says so.
Default settings: 30 results, at most 6 per store, even mix (targets 8/8/7/7).
"""

from dataclasses import dataclass, field

import pytest

from tests.factories import (
    make_product,
    make_scored_product,
    make_scores,
    make_settings,
    make_store_config,
)
from tests.tiers.helpers import (
    LUXURY_STORE,
    PLAIN_STORE,
    PRD_PRICES,
    assert_invariants,
    default_total,
    flags_of,
    make_pool,
    make_prd_pool,
    over_budget_counts,
    store_loads,
    tier_counts,
    tier_flags,
    tier_prices,
)
from vga.models import Budget, Flag, MixPreset, ScoredProduct, StoreConfig, TierMix
from vga.tiers import shape

F, R = Flag.FEW_OPTIONS, Flag.RELATIVE_RANGE
NONE = flags_of()
FEW = flags_of(F)
BIG_STORES = tuple(f"Store {n:02d}" for n in range(1, 13))


@dataclass(frozen=True)
class Scenario:
    name: str
    products: list[ScoredProduct]
    counts: tuple[int, int, int, int]
    flags: tuple[frozenset[Flag], frozenset[Flag], frozenset[Flag], frozenset[Flag]]
    budget: Budget | None = None
    stores: tuple[StoreConfig, ...] = (LUXURY_STORE,)
    total: int | None = None
    mix: TierMix | None = None
    over_budget: tuple[int, int, int, int] = (0, 0, 0, 0)
    """Products carrying ``over_budget`` in each range."""
    warnings: int = 0
    """How many warnings the caller should receive."""
    labels: tuple[str, ...] | None = None
    prices: tuple[tuple[float, ...], ...] | None = None
    """Exact prices shown in each range, best first."""
    extra: dict[str, int] = field(default_factory=dict)
    """Store name to the number of its products that must be shown."""


def _single_store_30() -> list[ScoredProduct]:
    return make_pool([10.0 * n for n in range(1, 31)], stores=("Solo",))


def _dominant_store_30() -> list[ScoredProduct]:
    # Positions 2, 5, 8, ... (10 of 30) belong to five small stores, two each; the other 20
    # belong to "Big Store". Prices rise with the position.
    small = [f"Small {n}" for n in range(1, 6)]
    stores = ["Big Store" if i % 3 != 2 else small[(i // 3) % 5] for i in range(30)]
    return [
        make_scored_product(
            make_product(i + 1, price=10.0 * (i + 1), store=store),
            scores=make_scores(total=default_total(i)),
        )
        for i, store in enumerate(stores)
    ]


def _thin_luxury_pool() -> list[ScoredProduct]:
    # Six candidates share the price 700, which is the third border, so all six are Premium
    # and the Luxury range is left with only 800, 1,500 and 2,400.
    prices = [
        *PRD_PRICES[:16],  # Budget and Mid-range as in the PRD example
        *(300, 349, 399, 449, 499, 549, 629),  # 7 Premium
        *([700] * 6),  # ties on the border
        *(800, 1500, 2400),  # 3 Luxury
    ]
    return make_pool(prices)


def _mixed_currency_pool() -> list[ScoredProduct]:
    aed = make_pool([30.0 * n for n in range(1, 21)], totals={})
    usd = make_pool([80.0, 120.0, 400.0, 900.0, 1500.0], currency="USD", start=101)
    # The USD products score best of all, to show currency decides, not score.
    best = [p.model_copy(update={"scores": make_scores(total=0.99)}) for p in usd]
    return [*best, *aed]


def _with_duplicates() -> list[ScoredProduct]:
    pool = make_prd_pool()
    duplicates = [p.model_copy(update={"scores": make_scores(total=0.5)}) for p in pool[:5]]
    return [*pool, *duplicates]


SCENARIOS = [
    Scenario(
        # 8 products in each quarter; each range wants 8/8/7/7, so Premium and Luxury drop their
        # worst (449 and 1,350). With a 300 budget the Premium product at 300 is NOT over budget;
        # the other 6 Premium and all 7 Luxury are.
        name="prd_example_budget_300",
        products=make_prd_pool(),
        budget=Budget(max_price=300, currency="AED"),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, NONE),
        over_budget=(0, 0, 6, 7),
        labels=(
            "Budget · 45-139 AED · 8 results",
            "Mid-range · 140-299 AED · 8 results",
            "Premium · 300-699 AED · 7 results",
            "Luxury · 700-2,400 AED · 7 results",
        ),
    ),
    Scenario(
        # The same pool without a budget: nothing is over budget, same counts and spans.
        name="prd_example_no_budget",
        products=make_prd_pool(),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, NONE),
        labels=(
            "Budget · 45-139 AED · 8 results",
            "Mid-range · 140-299 AED · 8 results",
            "Premium · 300-699 AED · 7 results",
            "Luxury · 700-2,400 AED · 7 results",
        ),
    ),
    Scenario(
        # One store, cap 6: only 6 products can be shown. The ranges take turns by fill ratio:
        # Budget, Mid-range, Premium, Luxury, then Budget and Mid-range again. All four fall short
        # of their targets (F). No luxury store is in play, so Luxury also gets R.
        name="one_store_only",
        products=_single_store_30(),
        stores=(PLAIN_STORE,),
        counts=(2, 2, 1, 1),
        flags=(FEW, FEW, FEW, flags_of(F, R)),
        prices=((10.0, 20.0), (90.0, 100.0), (160.0,), (240.0,)),
        extra={"Solo": 6},
    ),
    Scenario(
        # Full pool of 32 but no luxury store among the stores: counts are unchanged, only the
        # Luxury range is marked as "most expensive found" (R).
        name="no_luxury_store",
        products=make_prd_pool(),
        stores=(PLAIN_STORE,),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, flags_of(R)),
    ),
    Scenario(
        # A luxury store that is switched off does not count as a luxury store.
        name="luxury_store_disabled_counts_as_none",
        products=make_prd_pool(),
        stores=(
            make_store_config(id="lux-off", name="Lux Off", tier_hint="luxury", enabled=False),
        ),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, flags_of(R)),
    ),
    Scenario(
        # 30 products all at 150 AED: every border is 150, so all are Budget. Budget takes its 8.
        # Mid-range has no products of its own (F) and borrows 8 from its neighbour Budget.
        # Premium and Luxury have none of their own (F) and their neighbours (Mid-range, Luxury,
        # Premium) have nothing spare, so they stay empty: Budget's other 14 products are two or
        # more steps away and are not used. 16 results in all.
        name="all_prices_equal",
        products=make_pool([150.0] * 30),
        counts=(8, 8, 0, 0),
        flags=(NONE, FEW, FEW, FEW),
        labels=(
            "Budget · 150 AED · 8 results",
            "Mid-range · 150 AED · 8 results",
            "Premium · no results",
            "Luxury · no results",
        ),
    ),
    Scenario(
        # Budget 40 AED is below the cheapest product (45). Budget and Mid-range may hold nothing
        # over budget, so both are empty (F) and cannot be filled. Premium and Luxury keep their
        # 7 each, all flagged over_budget.
        name="budget_below_cheapest_product",
        products=make_prd_pool(),
        budget=Budget(max_price=40, currency="AED"),
        counts=(0, 0, 7, 7),
        flags=(FEW, FEW, NONE, NONE),
        over_budget=(0, 0, 7, 7),
        labels=(
            "Budget · no results",
            "Mid-range · no results",
            "Premium · 300-699 AED · 7 results",
            "Luxury · 700-2,400 AED · 7 results",
        ),
    ),
    Scenario(
        # Budget 150 AED sits inside the Mid-range quarter: only the product at 140 is within it,
        # so Mid-range shows 1 (F) and its other 7 slots cannot be filled (every other product is
        # over budget). Premium and Luxury show 7 each, all over budget.
        name="budget_between_borders",
        products=make_prd_pool(),
        budget=Budget(max_price=150, currency="AED"),
        counts=(8, 1, 7, 7),
        flags=(NONE, FEW, NONE, NONE),
        over_budget=(0, 0, 7, 7),
    ),
    Scenario(
        # One product: it is Budget. Every range is short of its target (F).
        name="tiny_pool_1_product",
        products=make_pool([120.0]),
        counts=(1, 0, 0, 0),
        flags=(FEW, FEW, FEW, FEW),
        prices=((120.0,), (), (), ()),
    ),
    Scenario(
        # Two products are Budget and Premium (see vga.tiers.borders). Mid-range and Luxury are
        # empty and nothing is left to borrow.
        name="tiny_pool_2_products",
        products=make_pool([100.0, 500.0]),
        counts=(1, 0, 1, 0),
        flags=(FEW, FEW, FEW, FEW),
        prices=((100.0,), (), (500.0,), ()),
    ),
    Scenario(
        # Three products are Budget, Mid-range and Premium; Luxury needs at least 4 candidates.
        name="tiny_pool_3_products",
        products=make_pool([100.0, 300.0, 900.0]),
        counts=(1, 1, 1, 0),
        flags=(FEW, FEW, FEW, FEW),
        prices=((100.0,), (300.0,), (900.0,), ()),
    ),
    Scenario(
        # The same 3 products for a list of only 3 (mix 25% each gives 1/1/1/0): every target is
        # met, so no range is flagged. Flags are about the target, not about the pool.
        name="tiny_pool_3_products_total_3",
        products=make_pool([100.0, 300.0, 900.0]),
        total=3,
        counts=(1, 1, 1, 0),
        flags=(NONE, NONE, NONE, NONE),
    ),
    Scenario(
        # 20 products from "Big Store" and 2 each from five small stores. Big Store may supply 6;
        # the five small stores supply all 10; 16 products in all. The ranges take turns, so Big
        # Store's 6 slots end up spread (2, 1, 2, 1) and each range gets 4. All four are short (F).
        name="one_dominant_store",
        products=_dominant_store_30(),
        counts=(4, 4, 4, 4),
        flags=(FEW, FEW, FEW, FEW),
        extra={
            "Big Store": 6,
            "Small 1": 2,
            "Small 2": 2,
            "Small 3": 2,
            "Small 4": 2,
            "Small 5": 2,
        },
    ),
    Scenario(
        # Ties on the third border leave Luxury with 3 products of its own. Premium has 13 and
        # needs 7, so Luxury (F) borrows 4 of Premium's 6 spare, the four best: all at 700 AED.
        name="thin_luxury_range",
        products=_thin_luxury_pool(),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, FEW),
        prices=(
            tuple(float(p) for p in PRD_PRICES[:8]),
            tuple(float(p) for p in PRD_PRICES[8:16]),
            (300.0, 349.0, 399.0, 449.0, 499.0, 549.0, 629.0),
            (700.0, 700.0, 700.0, 700.0, 800.0, 1500.0, 2400.0),
        ),
    ),
    Scenario(
        # Exactly 30 candidates for a list of 30: quarters of 8/7/8/7 against targets 8/8/7/7.
        # Mid-range is one short (F) and takes Premium's spare product, so all 30 are shown.
        name="exactly_30_results",
        products=make_pool([20.0 * n for n in range(1, 31)]),
        counts=(8, 8, 7, 7),
        flags=(NONE, FEW, NONE, NONE),
    ),
    Scenario(
        # An outfit-photo garment: 12 candidates for a list of 12, quarters of 3 each.
        name="exactly_12_results_outfit_garment",
        products=make_pool([30.0 * n for n in range(1, 13)]),
        total=12,
        counts=(3, 3, 3, 3),
        flags=(NONE, NONE, NONE, NONE),
    ),
    Scenario(
        # Preset "Value first" 40/30/20/10 with 60 candidates (15 per quarter, 12 stores so the
        # cap never bites): every range fills from its own quarter.
        name="value_first_preset",
        products=make_pool([10.0 * n for n in range(1, 61)], stores=BIG_STORES),
        mix=MixPreset.VALUE_FIRST.mix,
        counts=(12, 9, 6, 3),
        flags=(NONE, NONE, NONE, NONE),
    ),
    Scenario(
        # Preset "Luxury first" 10/20/30/40, same pool.
        name="luxury_first_preset",
        products=make_pool([10.0 * n for n in range(1, 61)], stores=BIG_STORES),
        mix=MixPreset.LUXURY_FIRST.mix,
        counts=(3, 6, 9, 12),
        flags=(NONE, NONE, NONE, NONE),
    ),
    Scenario(
        # "Value first" on the PRD pool (8 per quarter): Budget wants 12 and Mid-range 9 but own
        # only 8 each (F). Budget's only neighbour, Mid-range, has nothing spare, and Premium's 2
        # spare products are two steps away, so Budget stays at 8. Mid-range takes the best of
        # Premium's spare (699). 8/9/6/3 = 26 of the 32 products.
        name="value_first_preset_thin_fill",
        products=make_prd_pool(),
        mix=MixPreset.VALUE_FIRST.mix,
        counts=(8, 9, 6, 3),
        flags=(FEW, FEW, NONE, NONE),
        prices=(
            (45.0, 59.0, 72.0, 89.0, 99.0, 112.0, 125.0, 139.0),
            (140.0, 169.0, 189.0, 209.0, 229.0, 249.0, 279.0, 299.0, 699.0),
            (300.0, 349.0, 399.0, 499.0, 549.0, 629.0),
            (700.0, 890.0, 1100.0),
        ),
    ),
    Scenario(
        # Mix 60/10/10/20 of 30 = targets 18/3/3/6 on the PRD prices without score tweaks. Budget
        # owns 8 and wants 18. Its only neighbour, Mid-range, has 5 spare (209-299 AED) and lends
        # them: 13. Premium has 5 spare (449-699 AED) and Luxury 2, but they are two and three
        # steps away, so Budget stays 5 short (F) and no product over 299 AED appears in it.
        name="product_two_ranges_away_is_not_borrowed",
        products=make_pool(PRD_PRICES),
        mix=TierMix(budget=60, mid_range=10, premium=10, luxury=20),
        counts=(13, 3, 3, 6),
        flags=(FEW, NONE, NONE, NONE),
        prices=(
            (45.0, 59.0, 72.0, 89.0, 99.0, 112.0, 125.0, 139.0, 209.0, 229.0, 249.0, 279.0, 299.0),
            (140.0, 169.0, 189.0),
            (300.0, 349.0, 399.0),
            (700.0, 890.0, 1100.0, 1350.0, 1600.0, 1900.0),
        ),
    ),
    Scenario(
        # A 0% share is allowed: 0/0/50/50 of 30 gives targets 0/0/15/15. Budget and Mid-range
        # are not flagged (nothing was wanted from them). Premium owns 8 and borrows 7 of
        # Mid-range's 8 spare. Luxury owns 8 and its only neighbour, Premium, has nothing spare,
        # so it stays at 8 (F); Budget's products are three steps away.
        name="zero_share_ranges_lend_upwards",
        products=make_prd_pool(),
        mix=TierMix(budget=0, mid_range=0, premium=50, luxury=50),
        counts=(0, 0, 15, 8),
        flags=(NONE, NONE, FEW, FEW),
    ),
    Scenario(
        # 20 AED products and 5 USD products that score best. Only the AED ones are shaped (5 per
        # quarter, all four ranges short of 8/8/7/7), and the caller gets one warning.
        name="mixed_currencies_shape_the_most_common",
        products=_mixed_currency_pool(),
        counts=(5, 5, 5, 5),
        flags=(FEW, FEW, FEW, FEW),
        warnings=1,
    ),
    Scenario(
        # Every product scores below the minimum (0.2): nothing may be shown, so four empty
        # ranges, all short of their targets (F).
        name="nothing_above_the_threshold",
        products=make_pool([100.0, 200.0, 300.0, 400.0], totals=dict.fromkeys(range(4), 0.1)),
        counts=(0, 0, 0, 0),
        flags=(FEW, FEW, FEW, FEW),
    ),
    Scenario(
        # A budget in USD cannot be compared with AED prices: it is not applied and the caller
        # gets one warning. The result equals "prd_example_no_budget".
        name="budget_in_another_currency_is_ignored",
        products=make_prd_pool(),
        budget=Budget(max_price=300, currency="USD"),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, NONE),
        warnings=1,
    ),
    Scenario(
        # The same product three times under different scores counts once (the best copy), so
        # the result equals "prd_example_no_budget".
        name="duplicate_products_count_once",
        products=_with_duplicates(),
        counts=(8, 8, 7, 7),
        flags=(NONE, NONE, NONE, NONE),
    ),
    Scenario(
        name="no_products_at_all",
        products=[],
        counts=(0, 0, 0, 0),
        flags=(FEW, FEW, FEW, flags_of(F, R)),
        stores=(),
    ),
]


def test_there_are_at_least_twelve_named_scenarios() -> None:
    names = [scenario.name for scenario in SCENARIOS]
    assert len(names) >= 12
    assert len(names) == len(set(names))


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_scenario(scenario: Scenario) -> None:
    # Arrange
    overrides = {"tier_mix": scenario.mix} if scenario.mix is not None else {}
    settings = make_settings(**overrides)
    before = list(scenario.products)

    # Act
    result = shape(
        scenario.products, settings, scenario.budget, scenario.stores, total=scenario.total
    )

    # Assert: the scenario's stated outcome ...
    assert tier_counts(result) == scenario.counts
    assert tier_flags(result) == scenario.flags
    assert over_budget_counts(result) == scenario.over_budget
    assert len(result.warnings) == scenario.warnings
    if scenario.labels is not None:
        assert tuple(tier.display_label for tier in result.tiers) == scenario.labels
    if scenario.prices is not None:
        assert tier_prices(result) == scenario.prices
    for store, number in scenario.extra.items():
        assert store_loads(result)[store] == number
    # ... and the rules that hold for every call.
    assert_invariants(
        result,
        scenario.products,
        settings,
        total=scenario.total,
        budget=scenario.budget,
        stores=scenario.stores,
    )
    assert scenario.products == before, "shape must not change its input"


def test_scenarios_with_the_same_pool_agree() -> None:
    """The duplicate pool and the no-budget pool show exactly the same products."""
    settings = make_settings()
    plain = shape(make_prd_pool(), settings, None, (LUXURY_STORE,))
    with_duplicates = shape(_with_duplicates(), settings, None, (LUXURY_STORE,))
    assert [p.product.key for p in plain.products] == [
        p.product.key for p in with_duplicates.products
    ]
    assert [p.scores.total for p in plain.products] == [
        p.scores.total for p in with_duplicates.products
    ]
