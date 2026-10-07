"""Builders and invariant checks shared by the price-range tests.

Prices rise with the index and the default scores fall with it: the product at index 0 is both
the cheapest and the best match. That makes the expected picks easy to work out by hand: inside a
range the best match is always the cheapest product still available.
"""

from collections import Counter
from collections.abc import Sequence

from tests.factories import make_product, make_scored_product, make_scores, make_store_config
from vga.models import (
    TIER_ORDER,
    Budget,
    Flag,
    ScoredProduct,
    StoreConfig,
    Tier,
    TierResult,
)
from vga.settings import Settings
from vga.tiers.shaper import ShapeResult

STORE_NAMES = (
    "Souq Atelier",
    "Gulf Threads",
    "Marina Mode",
    "Oasis Luxe",
    "Desert Rose",
    "Palm Row",
)

LUXURY_STORE = make_store_config(id="luxury-store", name="Luxury Store", tier_hint=Tier.LUXURY)
PLAIN_STORE = make_store_config(id="plain-store", name="Plain Store")

PRD_PRICES = (
    *(45, 59, 72, 89, 99, 112, 125, 139),  # Budget quarter
    *(140, 169, 189, 209, 229, 249, 279, 299),  # Mid-range quarter
    *(300, 349, 399, 449, 499, 549, 629, 699),  # Premium quarter
    *(700, 890, 1100, 1350, 1600, 1900, 2150, 2400),  # Luxury quarter
)
"""32 candidates whose quartiles are the PRD example's: 45-139, 140-299, 300-699, 700-2,400."""


def default_total(index: int) -> float:
    """Scores fall as the index rises: 0.95, 0.945, ... (never below 0.45 for 100 products)."""
    return round(0.95 - 0.005 * index, 4)


def make_pool(
    prices: Sequence[float],
    *,
    stores: Sequence[str] = STORE_NAMES,
    totals: dict[int, float] | None = None,
    currency: str = "AED",
    start: int = 1,
) -> list[ScoredProduct]:
    """One scored product per price, best first. Stores rotate through ``stores``.

    ``totals`` maps an index (0-based, position in ``prices``) to a score that replaces the default.
    """
    overrides = totals or {}
    pool: list[ScoredProduct] = []
    for position, price in enumerate(prices):
        product = make_product(
            start + position,
            price=float(price),
            store=stores[position % len(stores)],
            currency=currency,
        )
        total = overrides.get(position, default_total(position))
        pool.append(make_scored_product(product, scores=make_scores(total=total)))
    return pool


def make_prd_pool(stores: Sequence[str] = STORE_NAMES) -> list[ScoredProduct]:
    """The 32-product PRD example pool. The Premium product at 449 and the Luxury product at 1,350
    score lowest in their ranges, so they are the ones left out when each range wants 7 of 8."""
    totals = {PRD_PRICES.index(449): 0.30, PRD_PRICES.index(1350): 0.31}
    return make_pool(PRD_PRICES, stores=stores, totals=totals)


def tier_counts(result: ShapeResult) -> tuple[int, ...]:
    return tuple(tier.count for tier in result.tiers)


def tier_flags(result: ShapeResult) -> tuple[frozenset[Flag], ...]:
    return tuple(frozenset(tier.flags) for tier in result.tiers)


def tier_prices(result: ShapeResult) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(r.product.price for r in tier.results) for tier in result.tiers)


def over_budget_counts(result: ShapeResult) -> tuple[int, ...]:
    return tuple(
        sum(Flag.OVER_BUDGET in scored.flags for scored in tier.results) for tier in result.tiers
    )


def store_loads(result: ShapeResult) -> Counter[str]:
    return Counter(scored.product.store for scored in result.products)


def flags_of(*names: Flag) -> frozenset[Flag]:
    return frozenset(names)


def assert_invariants(
    result: ShapeResult,
    inputs: Sequence[ScoredProduct],
    settings: Settings,
    *,
    total: int | None = None,
    budget: Budget | None = None,
    stores: Sequence[StoreConfig] = (),
) -> None:
    """Rules that hold for every call of ``shape``, whatever the data."""
    wanted = settings.results if total is None else total
    tiers: list[TierResult] = result.tiers
    assert [tier.name for tier in tiers] == list(TIER_ORDER)
    assert sum(tier.target_count for tier in tiers) == wanted

    given: dict[str, list[ScoredProduct]] = {}
    for scored in inputs:
        given.setdefault(scored.product.key, []).append(scored)
    shown_keys = [scored.product.key for scored in result.products]
    assert len(shown_keys) == len(set(shown_keys)), "a product appears twice"
    assert set(shown_keys) <= set(given), "a product was shown that was not given"
    assert len(shown_keys) <= wanted

    assert max(store_loads(result).values(), default=0) <= settings.max_per_store

    has_luxury_store = any(s.enabled and s.tier_hint is Tier.LUXURY for s in stores)
    ceiling = (
        budget.max_price if budget is not None and budget.currency == result.currency else None
    )
    for tier in tiers:
        assert tier.count == len(tier.results) <= tier.target_count
        if tier.count < tier.target_count:
            assert Flag.FEW_OPTIONS in tier.flags
        assert (Flag.RELATIVE_RANGE in tier.flags) == (
            tier.name is Tier.LUXURY and not has_luxury_store
        )
        assert Flag.OVER_BUDGET not in tier.flags
        totals = [scored.scores.total for scored in tier.results]
        assert totals == sorted(totals, reverse=True), "range is not best first"
        for scored in tier.results:
            # The same product may have been given more than once, with different scores.
            originals = given[scored.product.key]
            assert any(scored.product == o.product and scored.scores == o.scores for o in originals)
            assert scored.scores.total >= settings.min_match_score
            assert scored.tier is tier.name
            assert scored.product.currency == result.currency
            over = ceiling is not None and scored.product.price > ceiling
            assert (Flag.OVER_BUDGET in scored.flags) == over
            if ceiling is not None and tier.name in (Tier.BUDGET, Tier.MID_RANGE):
                assert scored.product.price <= ceiling
