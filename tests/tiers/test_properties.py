"""Property-style checks over many seeded random requests (plain parametrised tests, no new
dependency). Each seed builds a different pool, mix, cap, budget and total; the same seed always
builds the same case, so a failure names the seed to replay.
"""

import random
from collections import Counter
from dataclasses import dataclass

import pytest

from tests.factories import make_product, make_scored_product, make_scores, make_settings
from tests.tiers.helpers import LUXURY_STORE, PLAIN_STORE, assert_invariants
from vga.models import TIER_ORDER, Budget, ScoredProduct, StoreConfig, TierMix
from vga.settings import Settings
from vga.tiers import ShapeResult, mix_to_counts, shape

SEEDS = range(250)
POOL_SIZES = (0, 1, 2, 3, 4, 5, 7, 8, 12, 13, 20, 30, 32, 45, 70, 100)
PRICE_LEVELS = (None, (100.0, 250.0), (60.0, 90.0, 400.0, 1500.0), (99.0,))


@dataclass(frozen=True)
class Case:
    products: list[ScoredProduct]
    settings: Settings
    budget: Budget | None
    stores: tuple[StoreConfig, ...]
    total: int


def random_mix(rng: random.Random) -> TierMix:
    if rng.random() < 0.5:
        shares = rng.choice([(25, 25, 25, 25), (40, 30, 20, 10), (10, 20, 30, 40)])
    else:
        cuts = sorted(rng.randint(0, 100) for _ in range(3))
        shares = (cuts[0], cuts[1] - cuts[0], cuts[2] - cuts[1], 100 - cuts[2])
    return TierMix(budget=shares[0], mid_range=shares[1], premium=shares[2], luxury=shares[3])


def random_case(seed: int, *, single_currency: bool = False, with_budget: bool = True) -> Case:
    rng = random.Random(seed)
    size = rng.choice(POOL_SIZES)
    levels = rng.choice(PRICE_LEVELS)
    store_names = [f"Store {n}" for n in range(1, rng.randint(1, 8) + 1)]
    products: list[ScoredProduct] = []
    for index in range(size):
        price = rng.choice(levels) if levels else round(rng.uniform(10, 2400), 2)
        currency = "USD" if not single_currency and rng.random() < 0.1 else "AED"
        product = make_product(
            index + 1, price=price, currency=currency, store=rng.choice(store_names)
        )
        total = round(rng.uniform(0.1, 1.0), 4)  # some fall below the 0.2 minimum
        products.append(make_scored_product(product, scores=make_scores(total=total)))
    if products and rng.random() < 0.2:  # the same product again, scoring differently
        again = rng.choice(products)
        products.append(again.model_copy(update={"scores": make_scores(total=0.55)}))
    rng.shuffle(products)  # the shaper must not rely on the caller's order
    budget = None
    if with_budget and rng.random() < 0.5:
        currency = "USD" if rng.random() < 0.1 else "AED"
        budget = Budget(max_price=round(rng.uniform(20, 2500), 2), currency=currency)
    settings = make_settings(tier_mix=random_mix(rng), max_per_store=rng.choice([1, 2, 6, 6, 10]))
    stores = rng.choice([(LUXURY_STORE,), (PLAIN_STORE,), (), (PLAIN_STORE, LUXURY_STORE)])
    return Case(
        products, settings, budget, stores, total=rng.choice([1, 12, 30, rng.randint(1, 45)])
    )


def run(case: Case) -> ShapeResult:
    return shape(case.products, case.settings, case.budget, case.stores, total=case.total)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_rule_holds_for_a_random_request(seed: int) -> None:
    case = random_case(seed)
    result = run(case)
    assert_invariants(
        result,
        case.products,
        case.settings,
        total=case.total,
        budget=case.budget,
        stores=case.stores,
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_targets_always_sum_to_the_total(seed: int) -> None:
    case = random_case(seed)
    targets = [tier.target_count for tier in run(case).tiers]
    assert sum(targets) == case.total
    assert targets == list(mix_to_counts(case.settings.tier_mix, case.total).values())


def usable_products(case: Case) -> dict[str, ScoredProduct]:
    """Each distinct product once, with its best copy that clears the minimum match score."""
    best: dict[str, ScoredProduct] = {}
    for scored in case.products:
        key = scored.product.key
        if scored.scores.total < case.settings.min_match_score:
            continue
        if key not in best or scored.scores.total > best[key].scores.total:
            best[key] = scored
    return best


@pytest.mark.parametrize("seed", SEEDS)
def test_the_count_is_never_more_than_the_total_or_than_the_cap_allows(seed: int) -> None:
    case = random_case(seed, single_currency=True, with_budget=False)
    result = run(case)
    per_store = Counter(scored.product.store for scored in usable_products(case).values())
    available = sum(min(case.settings.max_per_store, count) for count in per_store.values())
    assert sum(tier.count for tier in result.tiers) <= min(case.total, available)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_product_sits_in_its_own_price_range_or_a_neighbouring_one(seed: int) -> None:
    case = random_case(seed, single_currency=True)
    result = run(case)
    if result.borders is None:
        assert not result.products
        return
    for position, tier in enumerate(result.tiers):
        for scored in tier.results:
            natural = TIER_ORDER.index(result.borders.tier_for(scored.product.price))
            assert abs(natural - position) <= 1, (scored.product.price, tier.name)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_short_range_leaves_no_product_it_may_borrow_unused(seed: int) -> None:
    # A range that ends below its target must have used every product of its own range and of
    # the ranges next to it that it was allowed to take. Whatever it did not take must be
    # blocked: its store is at the cap, or it is over the budget and the range is Budget or
    # Mid-range. The shaper must not give up early.
    case = random_case(seed, single_currency=True)
    result = run(case)
    if result.borders is None:
        return
    shown = {scored.product.key for scored in result.products}
    loads = Counter(scored.product.store for scored in result.products)
    ceiling = None
    if case.budget is not None and case.budget.currency == result.currency:
        ceiling = case.budget.max_price
    for position, tier in enumerate(result.tiers):
        if tier.count >= tier.target_count:
            continue
        for key, scored in usable_products(case).items():
            natural = TIER_ORDER.index(result.borders.tier_for(scored.product.price))
            if key in shown or abs(natural - position) > 1:
                continue
            at_cap = loads[scored.product.store] >= case.settings.max_per_store
            over_for_this_range = (
                ceiling is not None and scored.product.price > ceiling and position < 2
            )
            assert at_cap or over_for_this_range, (tier.name, scored.product.price)


@pytest.mark.parametrize("seed", SEEDS)
def test_no_store_exceeds_the_cap(seed: int) -> None:
    case = random_case(seed)
    loads = Counter(scored.product.store for scored in run(case).products)
    assert all(count <= case.settings.max_per_store for count in loads.values())


@pytest.mark.parametrize("seed", SEEDS)
def test_every_shown_product_was_given_and_none_appears_twice(seed: int) -> None:
    case = random_case(seed)
    shown = [scored.product.key for scored in run(case).products]
    assert len(shown) == len(set(shown))
    assert set(shown) <= {scored.product.key for scored in case.products}


@pytest.mark.parametrize("seed", SEEDS)
def test_the_same_request_gives_the_same_answer(seed: int) -> None:
    case = random_case(seed)
    assert run(case) == run(case)
