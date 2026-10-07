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


def test_a_very_high_price_scores_close_to_0() -> None:
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
    assert not is_over_budget(250.0, "AED", usd_budget, SETTINGS)


@pytest.mark.parametrize(
    ("price", "over"),
    [(399.99, False), (400.0, False), (400.01, True), (4000.0, True)],
)
def test_over_budget_means_strictly_above_the_budget(price: float, over: bool) -> None:
    assert is_over_budget(price, "AED", BUDGET, SETTINGS) is over


def test_without_a_budget_nothing_is_over_budget() -> None:
    assert not is_over_budget(1_000_000.0, "AED", None, SETTINGS)


# --------------------------------------------------------------------------------------------
# Prices and budgets in different currencies (Kuwaiti dinar, 2026-10-08 decision): both are
# converted into the base currency at the fixed rate in settings before they are compared.
# --------------------------------------------------------------------------------------------

# A round rate keeps the arithmetic readable: 1 KWD is 10 AED, 1 USD is 4 AED.
FX = make_settings(fx_rates={"KWD": 10.0, "USD": 4.0}, neutral_price_score=0.5)


def test_a_dinar_price_is_converted_before_it_is_compared_with_an_aed_budget() -> None:
    # KWD 35 is AED 350, within 400; KWD 45 is AED 450, over it. The raw numbers say the opposite
    # of what a naive comparison of 45 against 400 would.
    assert price_score(35.0, "KWD", BUDGET, FX) == 1.0
    assert not is_over_budget(35.0, "KWD", BUDGET, FX)
    assert is_over_budget(45.0, "KWD", BUDGET, FX)
    assert price_score(45.0, "KWD", BUDGET, FX) == pytest.approx(math.exp(-PRICE_DECAY * 0.125))


@pytest.mark.parametrize(
    ("price", "over"),
    [(39.999, False), (40.0, False), (40.001, True), (400.0, True)],
)
def test_a_dinar_price_exactly_at_the_budget_after_conversion_is_within_it(
    price: float, over: bool
) -> None:
    assert is_over_budget(price, "KWD", BUDGET, FX) is over


def test_a_dinar_price_against_a_dinar_budget_compares_in_the_base_currency() -> None:
    budget = make_budget(max_price=40, currency="KWD")

    assert price_score(40.0, "KWD", budget, FX) == 1.0
    assert not is_over_budget(40.0, "KWD", budget, FX)
    assert is_over_budget(41.0, "KWD", budget, FX)


def test_an_aed_price_against_a_dinar_budget_converts_the_budget_too() -> None:
    budget = make_budget(max_price=30, currency="KWD")  # AED 300

    assert not is_over_budget(300.0, "AED", budget, FX)
    assert is_over_budget(300.5, "AED", budget, FX)
    assert price_score(250.0, "AED", budget, FX) == 1.0


def test_a_budget_in_a_third_currency_with_a_rate_is_converted_as_well() -> None:
    budget = make_budget(max_price=100, currency="USD")  # AED 400

    assert not is_over_budget(40.0, "KWD", budget, FX)
    assert is_over_budget(41.0, "KWD", budget, FX)


def test_a_price_in_a_currency_with_no_rate_keeps_the_neutral_score_and_no_claim() -> None:
    assert price_score(1000.0, "SAR", BUDGET, FX) == FX.neutral_price_score
    assert not is_over_budget(1000.0, "SAR", BUDGET, FX)


def test_a_budget_in_a_currency_with_no_rate_cannot_be_compared() -> None:
    sar_budget = make_budget(max_price=100, currency="SAR")

    assert price_score(250.0, "AED", sar_budget, FX) == FX.neutral_price_score
    assert price_score(25.0, "KWD", sar_budget, FX) == FX.neutral_price_score
    assert not is_over_budget(250.0, "AED", sar_budget, FX)


def test_without_a_budget_a_dinar_price_is_neutral_and_never_over() -> None:
    assert price_score(25.0, "KWD", None, FX) == FX.neutral_price_score
    assert not is_over_budget(25_000.0, "KWD", None, FX)


def test_without_rates_a_dinar_product_cannot_be_compared_with_an_aed_budget() -> None:
    assert price_score(25.0, "KWD", BUDGET, SETTINGS) == SETTINGS.neutral_price_score
    assert not is_over_budget(25_000.0, "KWD", BUDGET, SETTINGS)


def test_an_aed_price_and_budget_score_exactly_as_before_whatever_rates_exist() -> None:
    for price in (250.0, 400.0, 440.0, 600.0, 4000.0):
        assert price_score(price, "AED", BUDGET, FX) == price_score(price, "AED", BUDGET, SETTINGS)
        assert is_over_budget(price, "AED", BUDGET, FX) == is_over_budget(
            price, "AED", BUDGET, SETTINGS
        )
