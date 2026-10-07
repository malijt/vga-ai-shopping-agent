"""Price-fit score and the over-budget test (plan 7.2.3, assumption A4)."""

import math

import pytest

from tests.factories import make_budget, make_settings
from vga.rank import is_over_budget, price_score
from vga.rank.price import PRICE_DECAY

SETTINGS = make_settings(neutral_price_score=0.5)
BUDGET = make_budget(max_price=400, currency="AED")


def test_a_price_within_budget_scores_1() -> None:
    assert price_score(250.0, "AED", BUDGET, SETTINGS) == 1.0


def test_a_price_exactly_at_the_budget_scores_1() -> None:
    assert price_score(400.0, "AED", BUDGET, SETTINGS) == 1.0


def test_a_price_above_budget_scores_below_1() -> None:
    assert 0 < price_score(401.0, "AED", BUDGET, SETTINGS) < 1.0


def test_the_score_falls_the_further_above_the_budget() -> None:
    prices = [400.0, 440.0, 500.0, 600.0, 800.0, 4000.0]

    scores = [price_score(price, "AED", BUDGET, SETTINGS) for price in prices]

    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)


def test_the_decay_follows_the_documented_formula() -> None:
    ten_percent_over = price_score(440.0, "AED", BUDGET, SETTINGS)
    half_over = price_score(600.0, "AED", BUDGET, SETTINGS)

    assert ten_percent_over == pytest.approx(math.exp(-PRICE_DECAY * 0.1))
    assert half_over == pytest.approx(math.exp(-PRICE_DECAY * 0.5))


def test_a_very_high_price_scores_above_0_but_stays_low() -> None:
    score = price_score(40_000.0, "AED", BUDGET, SETTINGS)

    assert 0.0 <= score < 0.01


@pytest.mark.parametrize("neutral", [0.0, 0.3, 0.5, 1.0])
def test_without_a_budget_every_price_gets_the_neutral_value_from_settings(neutral: float) -> None:
    settings = make_settings(neutral_price_score=neutral)

    assert price_score(10.0, "AED", None, settings) == neutral
    assert price_score(10_000.0, "AED", None, settings) == neutral


def test_a_budget_in_another_currency_cannot_be_compared_and_is_neutral() -> None:
    usd_budget = make_budget(max_price=100, currency="USD")

    assert price_score(250.0, "AED", usd_budget, SETTINGS) == SETTINGS.neutral_price_score
    assert not is_over_budget(250.0, "AED", usd_budget)


@pytest.mark.parametrize(
    ("price", "over"),
    [(399.99, False), (400.0, False), (400.01, True), (4000.0, True)],
)
def test_over_budget_means_strictly_above_the_budget(price: float, over: bool) -> None:
    assert is_over_budget(price, "AED", BUDGET) is over


def test_without_a_budget_nothing_is_over_budget() -> None:
    assert not is_over_budget(1_000_000.0, "AED", None)
