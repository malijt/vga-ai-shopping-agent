"""9.1.1 Quartile borders: 1, 2, 3, 4 and 100 candidates, equal prices, ties, determinism."""

import random
from collections import Counter

import pytest

from vga.models import Tier
from vga.tiers.borders import PriceBorders, compute_borders

B, M, P, L = Tier.BUDGET, Tier.MID_RANGE, Tier.PREMIUM, Tier.LUXURY


def tiers_of(prices: list[float]) -> list[Tier]:
    borders = compute_borders(prices)
    return [borders.tier_for(price) for price in prices]


@pytest.mark.parametrize(
    ("prices", "expected"),
    [
        pytest.param([120.0], [B], id="one_candidate_is_budget"),
        pytest.param([100.0, 500.0], [B, P], id="two_candidates_are_budget_and_premium"),
        pytest.param([100.0, 300.0, 900.0], [B, M, P], id="three_candidates_skip_luxury"),
        pytest.param([100.0, 200.0, 300.0, 400.0], [B, M, P, L], id="four_candidates_one_each"),
        pytest.param(
            [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
            [B, B, M, M, P, P, L, L],
            id="eight_candidates_two_each",
        ),
    ],
)
def test_small_pools_get_a_deterministic_split(prices: list[float], expected: list[Tier]) -> None:
    assert tiers_of(prices) == expected


def test_one_hundred_candidates_split_into_four_quarters_of_25() -> None:
    prices = [float(price) for price in range(1, 101)]
    counts = Counter(tiers_of(prices))
    assert [counts[tier] for tier in Tier] == [25, 25, 25, 25]


def test_one_hundred_candidates_borders_are_the_25th_50th_and_75th_cheapest_price() -> None:
    borders = compute_borders([float(price) for price in range(1, 101)])
    assert borders == PriceBorders(budget_max=25.0, mid_range_max=50.0, premium_max=75.0)


def test_thirty_candidates_split_8_7_8_7() -> None:
    counts = Counter(tiers_of([float(price) for price in range(1, 31)]))
    assert [counts[tier] for tier in Tier] == [8, 7, 8, 7]


def test_prd_example_prices_put_the_borders_at_139_299_and_699() -> None:
    prices = [
        *(45, 59, 72, 89, 99, 112, 125, 139),
        *(140, 169, 189, 209, 229, 249, 279, 299),
        *(300, 349, 399, 449, 499, 549, 629, 699),
        *(700, 890, 1100, 1350, 1600, 1900, 2150, 2400),
    ]
    borders = compute_borders([float(price) for price in prices])
    assert borders == PriceBorders(139.0, 299.0, 699.0)


def test_all_equal_prices_land_in_budget_because_a_tie_goes_to_the_cheaper_range() -> None:
    assert set(tiers_of([150.0] * 20)) == {B}


def test_equal_prices_never_straddle_two_ranges() -> None:
    # Four 100s then four distinct higher prices: the 100s cover the first two quarters of the
    # sorted list, but all four stay in Budget instead of being split between Budget and Mid-range.
    prices = [100.0, 100.0, 100.0, 100.0, 500.0, 600.0, 700.0, 800.0]
    assert tiers_of(prices) == [B, B, B, B, P, P, L, L]


def test_a_price_equal_to_a_border_belongs_to_the_cheaper_range() -> None:
    borders = PriceBorders(budget_max=100.0, mid_range_max=200.0, premium_max=300.0)
    assert [borders.tier_for(price) for price in (100.0, 100.01, 200.0, 300.0, 300.01)] == [
        B,
        M,
        M,
        P,
        L,
    ]


def test_input_order_does_not_change_the_borders() -> None:
    prices = [float(price) for price in range(10, 330, 7)]
    shuffled = prices[:]
    random.Random(7).shuffle(shuffled)
    assert compute_borders(shuffled) == compute_borders(prices)


def test_borders_are_deterministic() -> None:
    prices = [99.0, 45.0, 45.0, 320.0, 140.0, 140.0, 140.0, 2400.0, 80.0]
    assert compute_borders(prices) == compute_borders(list(prices))


def test_borders_never_decrease() -> None:
    rng = random.Random(11)
    for _ in range(50):
        prices = [
            float(rng.choice([10, 20, 20, 35, 90, 90, 400])) for _ in range(rng.randint(1, 40))
        ]
        borders = compute_borders(prices)
        assert borders.budget_max <= borders.mid_range_max <= borders.premium_max


def test_every_border_is_the_price_of_a_candidate() -> None:
    prices = [13.5, 80.0, 80.0, 99.9, 120.0, 340.0, 2200.0]
    borders = compute_borders(prices)
    assert {borders.budget_max, borders.mid_range_max, borders.premium_max} <= set(prices)


def test_no_prices_is_an_error() -> None:
    with pytest.raises(ValueError, match="at least one price"):
        compute_borders([])


@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf")])
def test_a_price_that_is_not_positive_and_finite_is_an_error(bad: float) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        compute_borders([100.0, bad])
