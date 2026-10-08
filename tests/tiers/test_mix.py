"""9.1.2 Mix to counts: largest-remainder rounding that always sums to the total."""

import pytest

from vga.models import MixPreset, Tier, TierMix
from vga.tiers.mix import mix_to_counts


def counts_tuple(mix: TierMix, total: int) -> tuple[int, ...]:
    return tuple(mix_to_counts(mix, total)[tier] for tier in Tier)


@pytest.mark.parametrize(
    ("preset", "total", "expected"),
    [
        pytest.param(MixPreset.EVEN, 30, (8, 8, 7, 7), id="even_30"),
        pytest.param(MixPreset.VALUE_FIRST, 30, (12, 9, 6, 3), id="value_first_30"),
        pytest.param(MixPreset.LUXURY_FIRST, 30, (3, 6, 9, 12), id="luxury_first_30"),
        pytest.param(MixPreset.EVEN, 12, (3, 3, 3, 3), id="even_12_outfit_total"),
        pytest.param(MixPreset.VALUE_FIRST, 12, (5, 4, 2, 1), id="value_first_12_outfit_total"),
        pytest.param(MixPreset.LUXURY_FIRST, 12, (1, 2, 4, 5), id="luxury_first_12_outfit_total"),
    ],
)
def test_presets_give_the_prd_counts(
    preset: MixPreset, total: int, expected: tuple[int, ...]
) -> None:
    assert counts_tuple(preset.mix, total) == expected


@pytest.mark.parametrize("preset", list(MixPreset))
@pytest.mark.parametrize("total", range(0, 101))
def test_counts_always_sum_to_the_total(preset: MixPreset, total: int) -> None:
    assert sum(mix_to_counts(preset.mix, total).values()) == total


@pytest.mark.parametrize(
    ("mix", "total", "expected"),
    [
        pytest.param(
            TierMix(budget=25, mid_range=25, premium=25, luxury=25), 1, (1, 0, 0, 0), id="1"
        ),
        pytest.param(
            TierMix(budget=25, mid_range=25, premium=25, luxury=25), 2, (1, 1, 0, 0), id="2"
        ),
        pytest.param(
            TierMix(budget=25, mid_range=25, premium=25, luxury=25), 3, (1, 1, 1, 0), id="3"
        ),
        pytest.param(
            TierMix(budget=25, mid_range=25, premium=25, luxury=25), 0, (0, 0, 0, 0), id="0"
        ),
        pytest.param(
            TierMix(budget=0, mid_range=0, premium=50, luxury=50), 7, (0, 0, 4, 3), id="zero_shares"
        ),
        pytest.param(
            TierMix(budget=100, mid_range=0, premium=0, luxury=0),
            30,
            (30, 0, 0, 0),
            id="all_budget",
        ),
        pytest.param(
            TierMix(budget=33, mid_range=33, premium=33, luxury=1),
            10,
            (4, 3, 3, 0),
            id="remainder_order",
        ),
    ],
)
def test_small_totals_and_odd_mixes(mix: TierMix, total: int, expected: tuple[int, ...]) -> None:
    assert counts_tuple(mix, total) == expected


def test_ties_go_to_the_cheaper_range() -> None:
    # 7.5 each: the two spare results go to Budget and Mid-range, not to Premium and Luxury.
    counts = mix_to_counts(MixPreset.EVEN.mix, 30)
    assert counts[Tier.BUDGET] == counts[Tier.MID_RANGE] == 8
    assert counts[Tier.PREMIUM] == counts[Tier.LUXURY] == 7


def test_the_spare_results_go_to_the_largest_remainders_then_the_cheapest() -> None:
    # 10 results of 33/33/33/1: exact 3.3 / 3.3 / 3.3 / 0.1, so the spare one goes to Budget.
    mix = TierMix(budget=33, mid_range=33, premium=33, luxury=1)
    assert counts_tuple(mix, 10) == (4, 3, 3, 0)
    # 11 results: exact 3.63 / 3.63 / 3.63 / 0.11; floors 3/3/3/0 leave 2 for the cheapest two.
    assert counts_tuple(mix, 11) == (4, 4, 3, 0)


def test_a_zero_share_never_receives_a_result() -> None:
    mix = TierMix(budget=0, mid_range=50, premium=50, luxury=0)
    for total in range(0, 60):
        counts = mix_to_counts(mix, total)
        assert counts[Tier.BUDGET] == 0
        assert counts[Tier.LUXURY] == 0


def test_the_result_is_in_display_order() -> None:
    assert list(mix_to_counts(MixPreset.EVEN.mix, 30)) == list(Tier)


def test_a_negative_total_is_an_error() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        mix_to_counts(MixPreset.EVEN.mix, -1)
