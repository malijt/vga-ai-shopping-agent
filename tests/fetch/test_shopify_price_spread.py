"""The ``shopify`` strategy's ``max_price_spread`` option: never show a price that may belong to a
cheaper add-on variant instead of the garment (plan 12.12, Hamsa).

Why it exists: Shopify's ``price`` is the lowest variant price. Hamsa sells a head scarf as a cheap
variant of the same product as an abaya, so on 5 of 10 abaya records ``price`` was KWD 20 to 95
while the abaya cost KWD 75 to 365. The option drops a record whose highest variant price
(``price_max``) is more than a set multiple of its lowest (``price_min``). The real Hamsa answers
are replayed in ``tests/stores/hamsa-kw``; the cases here use made-up records so each rule is
visible on its own.
"""

import logging
from typing import Any

import pytest

from tests.fetch.conftest import (
    OHPOLLY_BLAZER_URL,
    shopify_product,
    shopify_store,
    suggest_body,
)
from vga.models import StoreConfig, StrategyConfig
from vga.stores.extractors import ExtractionChain, ShopifyExtractor, default_registry


def store_with(**options: object) -> StoreConfig:
    return shopify_store(extraction={"strategies": [{"name": "shopify", "options": dict(options)}]})


def ranged(index: int, low: str, high: str, **overrides: Any) -> dict[str, Any]:
    """A product whose variants cost from ``low`` to ``high``; ``price`` is the lowest, as Shopify
    reports it."""
    return shopify_product(index, price=low, price_min=low, price_max=high, **overrides)


def run(store: StoreConfig, *products: dict[str, Any]) -> Any:
    return ExtractionChain(default_registry()).run(
        suggest_body(*products), store, OHPOLLY_BLAZER_URL
    )


# --------------------------------------------------------------------------------------------
# Off by default: the price stays the lowest variant's, as before
# --------------------------------------------------------------------------------------------


def test_without_the_option_a_record_keeps_its_lowest_variant_price() -> None:
    outcome = run(shopify_store(), ranged(1, "20.00", "80.00"))

    [product] = outcome.products
    assert product.price == 20.0
    assert outcome.dropped == {}


# --------------------------------------------------------------------------------------------
# On: a record is kept only when its variants stay within the multiple
# --------------------------------------------------------------------------------------------


def test_with_a_spread_of_one_only_products_whose_variants_cost_the_same_are_kept() -> None:
    same = shopify_product(1, price="135.00", price_min="135.00", price_max="135.00")
    scarf_and_abaya = ranged(2, "20.00", "80.00", title="Fire Works Abaya")

    outcome = run(store_with(max_price_spread=1), same, scarf_and_abaya)

    assert [p.title for p in outcome.products] == ["Blazer 1"]
    assert [p.price for p in outcome.products] == [135.0]
    assert outcome.examined == 2
    assert outcome.dropped == {"missing_price": 1}


def test_the_highest_price_is_not_substituted_for_the_dropped_records_price() -> None:
    """The record is dropped, not corrected: the maximum is not known to be the garment's (at
    Hamsa the KWD 75 abaya sat beside a KWD 95 maximum)."""
    store = store_with(max_price_spread=1)

    outcome = run(store, ranged(1, "20.00", "95.00", title="Tonal Abaya/Scarf"))

    assert outcome.products == []
    assert outcome.dropped == {"missing_price": 1}


@pytest.mark.parametrize(
    ("low", "high", "kept"),
    [
        ("100.00", "100.00", True),
        ("100.00", "120.00", True),
        ("100.00", "125.00", True),  # exactly the multiple: kept
        ("100.00", "125.01", False),  # one cent over: dropped
        ("100.00", "126.00", False),
        ("100.00", "400.00", False),
    ],
)
def test_the_multiple_is_an_inclusive_limit_checked_in_exact_decimals(
    low: str, high: str, kept: bool
) -> None:
    outcome = run(store_with(max_price_spread=1.25), ranged(1, low, high))

    assert len(outcome.products) == (1 if kept else 0)


def test_a_decimal_multiple_does_not_suffer_from_binary_floating_point() -> None:
    # 1.15 x 1.2 is 1.38 in decimals; as binary floats the product can land a hair below 1.38.
    outcome = run(store_with(max_price_spread=1.2), ranged(1, "1.15", "1.38"))

    assert len(outcome.products) == 1


def test_three_decimal_dinar_prices_are_compared_too() -> None:
    kwd = store_with(max_price_spread=1)
    kwd = kwd.model_copy(update={"currency": "KWD"})
    kept = ranged(1, "135.000", "135.000")
    dropped = ranged(2, "95.000", "365.000")

    outcome = run(kwd, kept, dropped)

    assert [p.price for p in outcome.products] == [135.0]
    assert outcome.dropped == {"missing_price": 1}


def test_a_dropped_record_does_not_hide_the_others_in_the_same_answer() -> None:
    products = [
        ranged(1, "20.00", "80.00"),
        shopify_product(2),
        ranged(3, "35.00", "95.00"),
        shopify_product(4),
    ]

    outcome = run(store_with(max_price_spread=1), *products)

    assert [p.title for p in outcome.products] == ["Blazer 2", "Blazer 4"]
    assert outcome.dropped == {"missing_price": 2}


def test_a_kept_record_is_exactly_what_it_is_without_the_option() -> None:
    body = suggest_body(shopify_product(1))
    without_option = ShopifyExtractor().extract(
        body, shopify_store(), StrategyConfig(name="shopify")
    )
    with_option = ShopifyExtractor().extract(
        body,
        store_with(max_price_spread=1),
        StrategyConfig(name="shopify", options={"max_price_spread": 1}),
    )

    assert with_option == without_option
    assert set(with_option[0]) == {
        "title",
        "price",
        "image_url",
        "product_url",
        "in_stock",
        "gender",
    }


# --------------------------------------------------------------------------------------------
# Fail closed: no figure to check means no trustworthy price
# --------------------------------------------------------------------------------------------


def without(product: dict[str, Any], *names: str) -> dict[str, Any]:
    return {key: value for key, value in product.items() if key not in names}


@pytest.mark.parametrize(
    "product",
    [
        without(shopify_product(1), "price_min"),
        without(shopify_product(1), "price_max"),
        without(shopify_product(1), "price_min", "price_max"),
        shopify_product(1, price_min=None),
        shopify_product(1, price_max=""),
        shopify_product(1, price_min="abc"),
        shopify_product(1, price_max="NaN"),
        shopify_product(1, price_max="Infinity"),
        shopify_product(1, price_min="0.00", price_max="0.00"),
        shopify_product(1, price_min="-5.00", price_max="-5.00"),
        shopify_product(1, price_min=101.0, price_max=101.0),  # numbers, not the text Shopify sends
    ],
)
def test_a_record_whose_lowest_or_highest_price_cannot_be_read_is_dropped(
    product: dict[str, Any],
) -> None:
    outcome = run(store_with(max_price_spread=1), product)

    assert outcome.products == []
    assert outcome.dropped == {"missing_price": 1}


def test_the_reason_is_logged_with_the_range_the_record_showed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="vga.stores.extractors.shopify"):
        run(store_with(max_price_spread=1), ranged(1, "20.00", "80.00", title="Fire Works Abaya"))

    [line] = [r for r in caplog.records if "no single trustworthy price" in r.getMessage()]
    assert (line.title, line.price_min, line.price_max) == (  # type: ignore[attr-defined]
        "Fire Works Abaya",
        "20.00",
        "80.00",
    )


# --------------------------------------------------------------------------------------------
# Store-file validation of the option
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 1.0, 1.25, 2, 3.5, 10])
def test_valid_spreads_pass(value: object) -> None:
    ShopifyExtractor().validate(StrategyConfig(name="shopify", options={"max_price_spread": value}))


@pytest.mark.parametrize(
    "value",
    [0, 0.99, -1, "1.5", True, False, None, [1], float("inf"), float("nan"), {"max": 1}],
)
def test_invalid_spreads_are_rejected_with_the_field_named(value: object) -> None:
    strategy = StrategyConfig(name="shopify", options={"max_price_spread": value})

    with pytest.raises(ValueError, match="max_price_spread"):
        ShopifyExtractor().validate(strategy)


def test_the_option_name_is_known_so_a_typo_is_still_caught() -> None:
    with pytest.raises(ValueError, match="max_price_sprd"):
        ShopifyExtractor().validate(StrategyConfig(name="shopify", options={"max_price_sprd": 1}))
