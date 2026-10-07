"""Converting a store's price into the base currency, and showing it to the shopper."""

import pytest

from tests.factories import make_settings
from vga.money import (
    approximate_amount,
    decimal_places,
    format_amount,
    format_price,
    to_base,
)

SETTINGS = make_settings(fx_rates={"KWD": 11.92, "BHD": 9.74})


class TestDecimalPlaces:
    @pytest.mark.parametrize("currency", ["KWD", "BHD", "OMR"])
    def test_the_three_decimal_gulf_currencies_have_three_places(self, currency: str) -> None:
        assert decimal_places(currency) == 3

    @pytest.mark.parametrize("currency", ["AED", "SAR", "QAR", "USD", "GBP", "EUR"])
    def test_other_currencies_have_two_places(self, currency: str) -> None:
        assert decimal_places(currency) == 2


class TestToBase:
    def test_an_amount_in_the_base_currency_is_returned_as_it_is(self) -> None:
        assert to_base(535.0, "AED", SETTINGS) == 535.0
        assert to_base(89.5, "AED", SETTINGS) == 89.5

    def test_a_dinar_amount_is_multiplied_by_the_fixed_rate(self) -> None:
        assert to_base(245.0, "KWD", SETTINGS) == 2920.4
        assert to_base(5.0, "KWD", SETTINGS) == 59.6

    def test_the_result_is_rounded_to_fils_so_it_carries_no_float_noise(self) -> None:
        # 29.000 * 11.92 is 345.67999999999995 in floating point.
        assert to_base(29.0, "KWD", SETTINGS) == 345.68
        assert to_base(0.333, "KWD", SETTINGS) == 3.97

    def test_a_currency_with_no_rate_is_not_converted_and_not_guessed(self) -> None:
        assert to_base(100.0, "USD", SETTINGS) is None
        assert to_base(100.0, "SAR", make_settings()) is None

    def test_without_any_rates_only_the_base_currency_converts(self) -> None:
        settings = make_settings()

        assert to_base(10.0, "AED", settings) == 10.0
        assert to_base(10.0, "KWD", settings) is None

    def test_the_rate_table_follows_the_configured_base_currency(self) -> None:
        settings = make_settings(base_currency="USD", fx_rates={"AED": 0.2723})

        assert to_base(100.0, "AED", settings) == 27.23
        assert to_base(100.0, "USD", settings) == 100.0
        assert to_base(100.0, "KWD", settings) is None

    def test_a_tiny_amount_never_rounds_to_nothing(self) -> None:
        settings = make_settings(base_currency="KWD", fx_rates={"AED": 0.0839})

        converted = to_base(0.05, "AED", settings)

        assert converted is not None
        assert converted > 0

    def test_a_rate_changed_in_settings_changes_the_result(self) -> None:
        assert to_base(100.0, "KWD", make_settings(fx_rates={"KWD": 12.0})) == 1200.0


class TestFormatAmount:
    @pytest.mark.parametrize(
        ("amount", "text"),
        [(535.0, "535"), (1499.0, "1,499"), (89.5, "89.50"), (0.5, "0.50"), (23698.0, "23,698")],
    )
    def test_a_dirham_amount_keeps_the_existing_form(self, amount: float, text: str) -> None:
        assert format_amount(amount, "AED") == text

    @pytest.mark.parametrize(
        ("amount", "text"),
        [
            (245.0, "245.000"),
            (260.0, "260.000"),
            (55.0, "55.000"),
            (5.0, "5.000"),
            (29.0, "29.000"),
            (0.5, "0.500"),
            (1245.5, "1,245.500"),
            (12.345, "12.345"),
        ],
    )
    def test_a_dinar_amount_always_shows_its_three_places(self, amount: float, text: str) -> None:
        assert format_amount(amount, "KWD") == text

    @pytest.mark.parametrize("currency", ["BHD", "OMR"])
    def test_the_other_three_decimal_currencies_show_three_places(self, currency: str) -> None:
        assert format_amount(19.0, currency) == "19.000"

    def test_a_currency_with_two_places_uses_the_dirham_form(self) -> None:
        assert format_amount(35.0, "GBP") == "35"
        assert format_amount(35.5, "GBP") == "35.50"


class TestApproximateAmount:
    """The "about" figure is rounded because the rate is fixed and approximate: steps of 10 from
    100 dirhams up, 5 from 20, 1 below, never down to zero."""

    @pytest.mark.parametrize(
        ("exact", "shown"),
        [
            (2920.4, 2920),
            (4545.0, 4550),
            (655.6, 660),
            (347.2, 350),
            (1019.9, 1020),
            (104.9, 100),
            (105.0, 110),
            (100.0, 100),
            (99.9, 100),
            (59.6, 60),
            (97.4, 95),
            (22.4, 20),
            (22.6, 25),
            (19.4, 19),
            (11.92, 12),
            (0.3, 1),
        ],
    )
    def test_it_rounds_to_a_step_that_grows_with_the_amount(self, exact: float, shown: int) -> None:
        assert approximate_amount(exact) == shown

    def test_it_never_returns_less_than_it_was_given_by_more_than_half_a_step(self) -> None:
        for exact in (12.0, 33.3, 120.4, 999.9, 12345.6):
            assert abs(approximate_amount(exact) - exact) <= 5.0


class TestFormatPrice:
    def test_a_dirham_price_is_the_plain_existing_form(self) -> None:
        assert format_price(535.0, "AED") == "535 AED"
        assert format_price(1499.0, "AED") == "1,499 AED"
        assert format_price(89.5, "AED") == "89.50 AED"

    def test_a_dinar_price_shows_its_own_amount_and_an_approximate_dirham_figure(self) -> None:
        assert (
            format_price(245.0, "KWD", base_price=2920.4, base_currency="AED")
            == "245.000 KWD (about 2,920 AED)"
        )

    @pytest.mark.parametrize(
        ("price", "base_price", "text"),
        [
            (260.0, 3099.2, "260.000 KWD (about 3,100 AED)"),
            (55.0, 655.6, "55.000 KWD (about 660 AED)"),
            (29.0, 345.68, "29.000 KWD (about 350 AED)"),
            (5.0, 59.6, "5.000 KWD (about 60 AED)"),
        ],
    )
    def test_the_real_sample_prices_read_well(
        self, price: float, base_price: float, text: str
    ) -> None:
        assert format_price(price, "KWD", base_price=base_price, base_currency="AED") == text

    def test_the_figure_is_the_one_stored_on_the_result_not_a_new_conversion(self) -> None:
        # A different stored figure gives a different line: nothing is recomputed here.
        assert (
            format_price(245.0, "KWD", base_price=3000.0, base_currency="AED")
            == "245.000 KWD (about 3,000 AED)"
        )

    def test_a_product_with_no_base_price_shows_only_its_own_price(self) -> None:
        assert format_price(245.0, "KWD") == "245.000 KWD"
        assert format_price(100.0, "USD") == "100 USD"

    def test_no_approximate_figure_is_added_when_the_price_is_already_in_the_base_currency(
        self,
    ) -> None:
        assert format_price(535.0, "AED", base_price=535.0, base_currency="AED") == "535 AED"

    def test_a_base_price_needs_its_currency(self) -> None:
        with pytest.raises(ValueError, match="base_currency"):
            format_price(245.0, "KWD", base_price=2920.4)

    def test_the_word_about_is_always_there_so_the_figure_is_not_read_as_exact(self) -> None:
        text = format_price(245.0, "KWD", base_price=2920.4, base_currency="AED")

        assert "about" in text
