"""The combiner (plan 7.2.4, PRD R8, ADR 0004)."""

import itertools

import pytest

from tests.factories import make_settings
from vga.models import Scores
from vga.rank import combine_scores
from vga.settings import RankingWeights

DEFAULT = RankingWeights()  # text 0.5, image 0.3, price 0.2 (config/settings.yaml)


def test_the_total_is_the_weighted_sum_of_the_three_scores() -> None:
    total = combine_scores(text=0.8, image=0.6, price=0.5, weights=DEFAULT)

    assert total == pytest.approx(0.5 * 0.8 + 0.3 * 0.6 + 0.2 * 0.5)


def test_without_an_image_score_the_image_weight_is_dropped_and_the_rest_renormalised() -> None:
    total = combine_scores(text=0.8, image=None, price=0.5, weights=DEFAULT)

    assert total == pytest.approx((0.5 * 0.8 + 0.2 * 0.5) / (0.5 + 0.2))


def test_dropping_the_image_weight_changes_the_total_predictably() -> None:
    with_image = combine_scores(text=0.8, image=0.8, price=0.5, weights=DEFAULT)
    without_image = combine_scores(text=0.8, image=None, price=0.5, weights=DEFAULT)

    # An image score equal to the text score leaves a text-and-price mix of the same shape...
    assert with_image == pytest.approx(0.5 * 0.8 + 0.3 * 0.8 + 0.2 * 0.5)
    # ...but without it the total is the renormalised mix, not the mix with a missing zero.
    assert without_image == pytest.approx(0.5 / 0.7 * 0.8 + 0.2 / 0.7 * 0.5)
    assert without_image != pytest.approx(combine_scores(0.8, 0.0, 0.5, DEFAULT))


def test_an_image_weight_has_no_effect_when_there_is_no_image_score() -> None:
    light = RankingWeights(text=0.5, image=0.0, price=0.2)
    heavy = RankingWeights(text=0.5, image=9.0, price=0.2)

    assert combine_scores(0.7, None, 0.4, light) == pytest.approx(
        combine_scores(0.7, None, 0.4, heavy)
    )


def test_weights_need_not_sum_to_1() -> None:
    scaled = RankingWeights(text=5, image=3, price=2)

    assert combine_scores(0.8, 0.6, 0.5, scaled) == pytest.approx(
        combine_scores(0.8, 0.6, 0.5, DEFAULT)
    )


def test_the_weights_come_from_settings() -> None:
    settings = make_settings(ranking_weights={"text": 1, "image": 0, "price": 3})

    total = combine_scores(0.8, 0.9, 0.2, settings.ranking_weights)

    assert total == pytest.approx((1 * 0.8 + 0 * 0.9 + 3 * 0.2) / 4)


@pytest.mark.parametrize("value", [0.0, 0.25, 0.5, 1.0])
def test_when_all_scores_are_equal_the_total_is_that_score_whatever_the_weights(
    value: float,
) -> None:
    for text, image, price in itertools.product([0.0, 0.1, 1.0, 7.0], repeat=3):
        if text + image + price == 0:
            continue
        weights = RankingWeights(text=text, image=image, price=price)

        assert combine_scores(value, value, value, weights) == pytest.approx(value)
        assert combine_scores(value, None, value, weights) == pytest.approx(value)


def test_with_only_the_image_weight_set_and_no_image_score_it_averages_what_exists() -> None:
    only_image = RankingWeights(text=0, image=1, price=0)

    assert combine_scores(0.8, None, 0.4, only_image) == pytest.approx(0.6)


def test_the_total_never_leaves_0_to_1_even_with_float_rounding() -> None:
    steps = [0.1, 0.2, 0.3, 0.7, 1 / 3]
    for text, image, price in itertools.product(steps, repeat=3):
        weights = RankingWeights(text=text, image=image, price=price)

        for image_score in (1.0, None):
            total = combine_scores(1.0, image_score, 1.0, weights)

            assert 0.0 <= total <= 1.0
            Scores(text=1.0, image=image_score, price=1.0, total=total)  # valid contract value


def test_the_total_rises_with_each_score() -> None:
    total = combine_scores(0.4, 0.4, 0.4, DEFAULT)

    assert combine_scores(0.5, 0.4, 0.4, DEFAULT) > total
    assert combine_scores(0.4, 0.5, 0.4, DEFAULT) > total
    assert combine_scores(0.4, 0.4, 0.5, DEFAULT) > total


def test_a_heavier_weight_makes_that_score_matter_more() -> None:
    text_heavy = RankingWeights(text=0.9, image=0.05, price=0.05)
    price_heavy = RankingWeights(text=0.05, image=0.05, price=0.9)
    good_text_bad_price = (0.9, None, 0.1)

    assert combine_scores(*good_text_bad_price, text_heavy) > combine_scores(
        *good_text_bad_price, price_heavy
    )
