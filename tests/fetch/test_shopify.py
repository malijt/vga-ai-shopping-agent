"""The ``shopify`` strategy on the saved Oh Polly and Club L London responses (plan 6.4.2)."""

import json

import pytest

from tests.fetch.conftest import (
    OHPOLLY_BLAZER_URL,
    club_l_store,
    fixture_text,
    shopify_product,
    shopify_store,
    suggest_body,
)
from vga.models import StrategyConfig
from vga.stores.extractors import (
    ExtractionChain,
    ExtractionError,
    ShopifyExtractor,
    default_registry,
)
from vga.stores.normalise import normalise_records

SHOPIFY = StrategyConfig(name="shopify")


def saved_products(name: str) -> list[dict[str, object]]:
    data = json.loads(fixture_text(name))
    products: list[dict[str, object]] = data["resources"]["results"]["products"]
    return products


# --------------------------------------------------------------------------------------------
# The saved samples
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["ohpolly-suggest-black-blazer.json", "ohpolly-suggest-shoes.json"],
)
def test_oh_polly_samples_give_valid_products_with_absolute_https_links_in_aed(name: str) -> None:
    store = shopify_store()
    expected = len(saved_products(name))

    outcome = ExtractionChain(default_registry()).run(fixture_text(name), store, OHPOLLY_BLAZER_URL)

    # The samples hold the first 4 of the 10 products of each real response.
    assert expected == 4
    assert len(outcome.products) == expected
    assert outcome.strategy == "shopify"
    assert outcome.dropped == {}
    for product in outcome.products:
        assert product.product_url.startswith("https://ohpolly.ae/products/")
        assert product.image_url.startswith("https://cdn.shopify.com/")
        assert product.currency == "AED"
        assert product.store == "Oh Polly"
        assert product.price > 0
        assert product.in_stock is True


@pytest.mark.parametrize(
    "name",
    ["clubl-suggest-black-blazer.json", "clubl-suggest-shoes.json"],
)
def test_club_l_london_samples_give_valid_products(name: str) -> None:
    store = club_l_store()
    expected = len(saved_products(name))

    outcome = ExtractionChain(default_registry()).run(
        fixture_text(name), store, "https://www.clubllondon.ae/search/suggest.json?q=x"
    )

    assert len(outcome.products) == expected == 4
    for product in outcome.products:
        assert product.product_url.startswith("https://www.clubllondon.ae/products/")
        assert product.currency == "AED"
        assert product.store == "Club L London"


def test_prices_are_read_as_numbers_from_the_price_strings() -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text("clubl-suggest-black-blazer.json"),
        club_l_store(),
        "https://www.clubllondon.ae/search/suggest.json?q=x",
    )

    assert [p.price for p in outcome.products] == [650.0, 535.0, 1499.0, 1099.0]


def test_the_tracking_query_is_removed_from_product_links() -> None:
    raw = fixture_text("ohpolly-suggest-black-blazer.json")
    assert "_pos=" in raw  # the sample links really do carry tracking parameters

    outcome = ExtractionChain(default_registry()).run(raw, shopify_store(), OHPOLLY_BLAZER_URL)

    assert outcome.products
    for product in outcome.products:
        assert "?" not in product.product_url
        assert "_pos" not in product.product_url
    assert outcome.products[1].product_url == (
        "https://ohpolly.ae/products/edessa-oversized-single-breasted-blazer-soft-lilac"
    )


def test_the_response_has_no_currency_so_the_store_files_currency_is_used() -> None:
    raw = fixture_text("ohpolly-suggest-black-blazer.json")
    assert "AED" not in raw
    store = shopify_store(currency="SAR")

    outcome = ExtractionChain(default_registry()).run(raw, store, OHPOLLY_BLAZER_URL)

    assert {p.currency for p in outcome.products} == {"SAR"}


def test_the_compare_at_price_is_not_used_as_the_price() -> None:
    outcome = ExtractionChain(default_registry()).run(
        fixture_text("clubl-suggest-shoes.json"),
        club_l_store(),
        "https://www.clubllondon.ae/search/suggest.json?q=shoes",
    )

    covergirl = outcome.products[0]
    assert covergirl.price == 299.0  # compare_at_price_max was 999.00


# --------------------------------------------------------------------------------------------
# Record shapes
# --------------------------------------------------------------------------------------------


def records_of(body: str, **options: object) -> list[dict[str, object]]:
    strategy = StrategyConfig(name="shopify", options=dict(options))
    return [dict(r) for r in ShopifyExtractor().extract(body, shopify_store(), strategy)]


def test_a_record_carries_the_five_fields_the_normaliser_needs() -> None:
    [record] = records_of(suggest_body(shopify_product(1)))

    assert record == {
        "title": "Blazer 1",
        "price": "101.00",
        "image_url": "https://cdn.shopify.com/s/files/1/0001/0002/files/blazer-1.jpg?v=1",
        "product_url": "/products/blazer-1",
        "in_stock": True,
    }


def test_the_image_falls_back_to_the_featured_image() -> None:
    product = shopify_product(
        1, image=None, featured_image={"url": "https://cdn.shopify.com/f.jpg"}
    )

    [record] = records_of(suggest_body(product))

    assert record["image_url"] == "https://cdn.shopify.com/f.jpg"


def test_the_link_falls_back_to_the_handle() -> None:
    [record] = records_of(suggest_body(shopify_product(1, url=None)))

    assert record["product_url"] == "/products/blazer-1"


@pytest.mark.parametrize(("available", "expected"), [(True, True), (False, False), (None, None)])
def test_availability_maps_to_in_stock(available: object, expected: object) -> None:
    [record] = records_of(suggest_body(shopify_product(1, available=available)))

    assert record["in_stock"] is expected


def test_an_empty_product_list_is_a_clean_empty_result() -> None:
    assert records_of(suggest_body()) == []


def test_a_missing_products_key_is_an_empty_result() -> None:
    assert records_of(json.dumps({"resources": {"results": {}}})) == []


@pytest.mark.parametrize(
    "body",
    [
        "<html><body>not json</body></html>",
        "",
        "[]",
        '{"products": []}',
        '{"resources": []}',
        '{"resources": {"results": []}}',
        '{"resources": {"results": {"products": "x"}}}',
    ],
)
def test_a_body_that_is_not_a_suggest_response_is_an_extraction_error(body: str) -> None:
    with pytest.raises(ExtractionError):
        ShopifyExtractor().extract(body, shopify_store(), SHOPIFY)


def test_non_object_entries_in_the_product_list_are_ignored() -> None:
    body = json.dumps({"resources": {"results": {"products": [None, "x", 3, shopify_product(1)]}}})

    assert len(records_of(body)) == 1


# --------------------------------------------------------------------------------------------
# name_field (The Bear House keeps the readable name in `vendor`)
# --------------------------------------------------------------------------------------------

BEAR_HOUSE_PRODUCT = shopify_product(
    1,
    title="BOALI",
    vendor="Olive Checked Slim Fit Casual Shirt",
    handle="boali",
    price="59.00",
    url="/products/boali?_pos=1&_psq=shirt&_psid=a1&_ss=e",
)


def test_by_default_the_name_is_the_title() -> None:
    outcome = ExtractionChain(default_registry()).run(
        suggest_body(BEAR_HOUSE_PRODUCT), shopify_store(), OHPOLLY_BLAZER_URL
    )

    assert outcome.products[0].title == "BOALI"


def test_name_field_vendor_reads_the_readable_name_from_vendor() -> None:
    store = shopify_store(
        extraction={"strategies": [{"name": "shopify", "options": {"name_field": "vendor"}}]}
    )

    outcome = ExtractionChain(default_registry()).run(
        suggest_body(BEAR_HOUSE_PRODUCT), store, OHPOLLY_BLAZER_URL
    )

    [product] = outcome.products
    assert product.title == "Olive Checked Slim Fit Casual Shirt"
    assert product.price == 59.0
    assert product.product_url == "https://ohpolly.ae/products/boali"


def test_name_field_title_is_accepted_explicitly() -> None:
    store = shopify_store(
        extraction={"strategies": [{"name": "shopify", "options": {"name_field": "title"}}]}
    )

    outcome = ExtractionChain(default_registry()).run(
        suggest_body(BEAR_HOUSE_PRODUCT), store, OHPOLLY_BLAZER_URL
    )

    assert outcome.products[0].title == "BOALI"


def test_a_missing_name_in_the_chosen_field_drops_the_record_with_a_reason() -> None:
    store = shopify_store(
        extraction={"strategies": [{"name": "shopify", "options": {"name_field": "vendor"}}]}
    )
    nameless = shopify_product(2, vendor="")

    outcome = ExtractionChain(default_registry()).run(
        suggest_body(BEAR_HOUSE_PRODUCT, nameless), store, OHPOLLY_BLAZER_URL
    )

    assert len(outcome.products) == 1
    assert outcome.dropped == {"missing_title": 1}


# --------------------------------------------------------------------------------------------
# Store-file validation of the strategy
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strategy",
    [
        StrategyConfig(name="shopify"),
        StrategyConfig(name="shopify", options={"name_field": "title"}),
        StrategyConfig(name="shopify", options={"name_field": "vendor"}),
    ],
)
def test_valid_shopify_settings_pass(strategy: StrategyConfig) -> None:
    ShopifyExtractor().validate(strategy)


@pytest.mark.parametrize(
    ("strategy", "message"),
    [
        (StrategyConfig(name="shopify", options={"name_field": "tags"}), "name_field"),
        (StrategyConfig(name="shopify", options={"name_fied": "vendor"}), "name_fied"),
        (StrategyConfig(name="shopify", options={"limit": 10}), "limit"),
        (StrategyConfig(name="shopify", fields={"title": "name"}), "fixed field mapping"),
    ],
)
def test_invalid_shopify_settings_are_rejected_with_the_field_named(
    strategy: StrategyConfig, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ShopifyExtractor().validate(strategy)


# --------------------------------------------------------------------------------------------
# Untrusted store data
# --------------------------------------------------------------------------------------------


def test_off_domain_links_in_a_response_are_dropped_not_followed() -> None:
    hostile = shopify_product(
        3,
        url="https://evil.example/products/blazer-3",
        image="https://evil.example/img.jpg",
    )
    good = shopify_product(1)

    batch = normalise_records(
        records_of(suggest_body(hostile, good)), shopify_store(), "https://ohpolly.ae/search"
    )

    assert [p.title for p in batch.products] == ["Blazer 1"]
    assert batch.dropped == {"image_url_not_allowed": 1}


def test_store_supplied_html_in_titles_is_kept_as_text_and_never_interpreted() -> None:
    nasty = shopify_product(1, title='<script>alert("x")</script> Blazer\x00\x07')

    outcome = ExtractionChain(default_registry()).run(
        suggest_body(nasty), shopify_store(), OHPOLLY_BLAZER_URL
    )

    assert outcome.products[0].title == '<script>alert("x")</script> Blazer'
