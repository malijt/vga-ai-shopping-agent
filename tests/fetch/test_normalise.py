"""Validation of raw records (plan 6.5.1 and 6.5.2): what is kept, dropped and why."""

import logging
from typing import Any

import pytest

from tests.factories import make_product, make_store_config
from tests.fetch.conftest import CDN, HOST
from vga.stores.normalise import DropReason, dedupe_products, normalise_records, normalise_title

BASE = f"https://{HOST}/search?q=blazer"


def record(index: int = 1, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "title": f"Blazer {index}",
        "price": f"{100 + index}.00",
        "image_url": f"https://{CDN}/img/{index}.jpg",
        "product_url": f"/products/blazer-{index}",
        "colour": None,
        "in_stock": True,
    }
    return {**fields, **overrides}


def normalise(*records: dict[str, Any], **store_overrides: Any):
    return normalise_records(list(records), make_store_config(**store_overrides), BASE)


def test_a_complete_record_becomes_a_product_from_the_store() -> None:
    batch = normalise(record(1, colour="  Black "))

    [product] = batch.products
    assert product.title == "Blazer 1"
    assert product.price == 101.0
    assert product.currency == "AED"
    assert product.store == "Demo Store"
    assert product.colour == "Black"
    assert product.in_stock is True
    assert batch.dropped == {}
    assert batch.examined == 1


def test_relative_links_are_made_absolute_against_the_page() -> None:
    [product] = normalise(record(1, product_url="/products/x?variant=3#top")).products

    assert product.product_url == f"https://{HOST}/products/x?variant=3"


def test_protocol_relative_links_become_https() -> None:
    [product] = normalise(record(1, image_url=f"//{CDN}/img/a.jpg")).products

    assert product.image_url == f"https://{CDN}/img/a.jpg"


# --------------------------------------------------------------------------------------------
# Required fields
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("title", None, DropReason.MISSING_TITLE),
        ("title", "", DropReason.MISSING_TITLE),
        ("title", "   ", DropReason.MISSING_TITLE),
        ("title", 42, DropReason.MISSING_TITLE),
        ("price", None, DropReason.MISSING_PRICE),
        ("price", "", DropReason.MISSING_PRICE),
        ("image_url", None, DropReason.MISSING_IMAGE_URL),
        ("image_url", " ", DropReason.MISSING_IMAGE_URL),
        ("product_url", None, DropReason.MISSING_PRODUCT_URL),
        ("product_url", "", DropReason.MISSING_PRODUCT_URL),
    ],
)
def test_a_record_missing_a_required_field_is_dropped_with_that_reason(
    field: str, value: object, reason: DropReason
) -> None:
    batch = normalise(record(1, **{field: value}), record(2))

    assert [p.title for p in batch.products] == ["Blazer 2"]
    assert batch.dropped == {reason.value: 1}


def test_a_record_with_no_such_key_at_all_is_dropped_too() -> None:
    incomplete = {"title": "Blazer", "price": "100.00"}

    batch = normalise(incomplete)

    assert batch.products == []
    assert batch.dropped == {"missing_image_url": 1}


# --------------------------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("price", ["1.234,50", "AED1,200", "free", "from 100", 99, "0,5"])
def test_an_unknown_price_format_drops_the_record_and_logs_why(
    price: object, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    batch = normalise(record(1, price=price))

    assert batch.products == []
    assert batch.dropped == {"unknown_price_format": 1}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("price format not recognised" in r.getMessage() for r in warnings)
    assert any(
        "unrecognised price format" in str(getattr(r, "detail", ""))
        or "not text" in str(getattr(r, "detail", ""))
        for r in warnings
    )


def test_a_price_in_another_currency_than_the_stores_is_dropped() -> None:
    batch = normalise(record(1, price="USD 150"), record(2, price="AED 150"))

    assert [p.title for p in batch.products] == ["Blazer 2"]
    assert batch.dropped == {"currency_mismatch": 1}


def test_luxury_for_you_style_prices_are_read_with_the_stores_currency() -> None:
    bidi = chr(0x2066) + "AED" + chr(0x2069) + " 6,900" + chr(0x2069)

    [product] = normalise(record(1, price=bidi)).products

    assert (product.price, product.currency) == (6900.0, "AED")


def test_a_zero_price_is_dropped() -> None:
    batch = normalise(record(1, price="0.00"))

    assert batch.dropped == {"price_not_positive": 1}


# --------------------------------------------------------------------------------------------
# Links (R6, and the allow-list)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "product_url",
    [
        "https://evil.example/products/x",
        "https://www.demo-store.example.evil.example/p",
        "http://www.demo-store.example/p",
        "https://169.254.169.254/p",
        "https://127.0.0.1/p",
        "https://user:pw@www.demo-store.example/p",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://www.demo-store.example/p",
        "https://www.demo-store.example:8443/p",
    ],
)
def test_a_product_link_off_the_allow_list_or_not_https_is_dropped(product_url: str) -> None:
    batch = normalise(record(1, product_url=product_url), record(2))

    assert [p.title for p in batch.products] == ["Blazer 2"]
    assert batch.dropped == {"product_url_not_allowed": 1}


@pytest.mark.parametrize(
    "image_url",
    [
        "https://evil.example/img.jpg",
        "http://cdn.demo-store.example/img.jpg",
        "data:image/png;base64,iVBORw0KGgo=",
        "javascript:alert(1)",
        "https://[::1]/img.jpg",
    ],
)
def test_an_image_link_off_the_allow_list_or_not_https_is_dropped(image_url: str) -> None:
    batch = normalise(record(1, image_url=image_url), record(2))

    assert [p.title for p in batch.products] == ["Blazer 2"]
    assert batch.dropped == {"image_url_not_allowed": 1}


def test_an_image_on_the_stores_own_second_host_is_fine() -> None:
    batch = normalise(record(1, image_url=f"https://{HOST}/img/1.jpg"))

    assert len(batch.products) == 1


# --------------------------------------------------------------------------------------------
# Other fields
# --------------------------------------------------------------------------------------------


def test_in_stock_is_only_ever_a_real_boolean_or_none() -> None:
    batch = normalise(
        record(1, in_stock=False), record(2, in_stock="yes"), record(3, in_stock=None)
    )

    assert [p.in_stock for p in batch.products] == [False, None, None]


def test_a_very_long_colour_is_left_out_instead_of_dropping_the_record() -> None:
    [product] = normalise(record(1, colour="x" * 200)).products

    assert product.colour is None


def test_a_title_over_the_model_limit_is_dropped_as_an_invalid_record() -> None:
    batch = normalise(record(1, title="x" * 1001))

    assert batch.dropped == {"invalid_record": 1}


def test_white_space_and_control_characters_in_a_title_are_cleaned() -> None:
    [product] = normalise(record(1, title="  Wool \t\n Blazer\x00 ")).products

    assert product.title == "Wool Blazer"


# --------------------------------------------------------------------------------------------
# De-duplication
# --------------------------------------------------------------------------------------------


def test_the_same_product_url_twice_keeps_the_first() -> None:
    batch = normalise(
        record(1, title="First"),
        record(1, title="Second", price="999.00"),
    )

    assert [p.title for p in batch.products] == ["First"]
    assert batch.dropped == {"duplicate_url": 1}


def test_one_title_under_several_handles_at_the_same_price_collapses_to_the_first() -> None:
    """Giordano UAE: one shirt appeared seven times in a single response under different handles."""
    shirts = [
        record(n, title="Men's Linen Shirt", price="89.00", product_url=f"/products/linen-{n}")
        for n in range(1, 8)
    ]

    batch = normalise(*shirts, record(9, title="Other Shirt", price="89.00"))

    assert [p.product_url for p in batch.products] == [
        f"https://{HOST}/products/linen-1",
        f"https://{HOST}/products/blazer-9",
    ]
    assert batch.dropped == {"duplicate_title_price": 6}
    assert batch.examined == 8


def test_titles_are_compared_after_case_and_spacing_are_normalised() -> None:
    batch = normalise(
        record(1, title="Linen  Shirt", price="89.00"),
        record(2, title="LINEN SHIRT ", price="89.00"),
        record(3, title="linen shirt", price="89.00"),
    )

    assert len(batch.products) == 1
    assert batch.dropped == {"duplicate_title_price": 2}


def test_the_same_title_at_a_different_price_is_a_different_product() -> None:
    batch = normalise(
        record(1, title="Linen Shirt", price="89.00"),
        record(2, title="Linen Shirt", price="119.00"),
    )

    assert [p.price for p in batch.products] == [89.0, 119.0]
    assert batch.dropped == {}


def test_collapsing_is_logged_with_how_many_were_collapsed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    normalise(*(record(n, title="Same", price="50.00") for n in range(1, 5)))

    collapsed = [r for r in caplog.records if r.getMessage() == "repeated products collapsed"]
    assert len(collapsed) == 1
    assert collapsed[0].collapsed == 3  # type: ignore[attr-defined]
    assert collapsed[0].kept == 1  # type: ignore[attr-defined]
    assert collapsed[0].store == "demo-store"  # type: ignore[attr-defined]


def test_every_drop_is_logged_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    normalise(record(1, title=None), record(2, price="free"), record(3, image_url=None))

    reasons = [
        r.reason  # type: ignore[attr-defined]
        for r in caplog.records
        if r.getMessage() == "record dropped"
    ]
    assert sorted(reasons) == ["missing_image_url", "missing_title", "unknown_price_format"]


def test_dedupe_keeps_order_and_reports_what_it_collapsed() -> None:
    a = make_product(1, title="A", price=10.0)
    a_again = make_product(2, title="a", price=10.0)
    b = make_product(3, title="B", price=10.0)
    a_same_url = make_product(1, title="Different", price=99.0)

    kept, collapsed = dedupe_products([a, a_again, b, a_same_url])

    assert kept == [a, b]
    assert collapsed == {"duplicate_title_price": 1, "duplicate_url": 1}


def test_normalise_title() -> None:
    assert normalise_title("  Linen   SHIRT\t") == "linen shirt"
