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
from vga.stores.extractors.shopify import DEFAULT_IMAGE_WIDTH
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
        "image_url": "https://cdn.shopify.com/s/files/1/0001/0002/files/blazer-1.jpg?v=1&width=400",
        "product_url": "/products/blazer-1",
        "in_stock": True,
    }


def test_the_image_falls_back_to_the_featured_image() -> None:
    product = shopify_product(
        1, image=None, featured_image={"url": "https://cdn.shopify.com/f.jpg"}
    )

    [record] = records_of(suggest_body(product))

    assert record["image_url"] == "https://cdn.shopify.com/f.jpg?width=400"


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
# image_width: ask the CDN for a smaller picture (default 400)
# --------------------------------------------------------------------------------------------

CDN_IMAGE = "https://cdn.shopify.com/s/files/1/0757/9670/9661/files/14960-Black_Azelie_4.jpg"


def image_urls(image: object, **options: object) -> str:
    [record] = records_of(suggest_body(shopify_product(1, image=image)), **options)
    url = record["image_url"]
    assert isinstance(url, str)
    return url


def test_the_default_width_is_400() -> None:
    assert DEFAULT_IMAGE_WIDTH == 400
    assert image_urls(f"{CDN_IMAGE}?v=1762411731") == f"{CDN_IMAGE}?v=1762411731&width=400"


def test_a_url_without_a_query_gets_one() -> None:
    assert image_urls(CDN_IMAGE) == f"{CDN_IMAGE}?width=400"


def test_existing_parameters_are_kept_exactly_as_written() -> None:
    url = image_urls(f"{CDN_IMAGE}?v=1762411731&crop=center&format=pjpg%20x")

    assert url == f"{CDN_IMAGE}?v=1762411731&crop=center&format=pjpg%20x&width=400"


def test_an_existing_width_is_replaced_in_place() -> None:
    url = image_urls(f"{CDN_IMAGE}?v=1&width=2000&crop=center")

    assert url == f"{CDN_IMAGE}?v=1&width=400&crop=center"


def test_repeated_width_parameters_collapse_to_one() -> None:
    url = image_urls(f"{CDN_IMAGE}?width=100&v=1&width=2000")

    assert url == f"{CDN_IMAGE}?width=400&v=1"


def test_a_parameter_that_only_ends_in_width_is_not_mistaken_for_width() -> None:
    url = image_urls(f"{CDN_IMAGE}?v=1&maxwidth=900&width_x=1")

    assert url == f"{CDN_IMAGE}?v=1&maxwidth=900&width_x=1&width=400"


def test_a_fragment_is_kept() -> None:
    assert image_urls(f"{CDN_IMAGE}?v=1#top") == f"{CDN_IMAGE}?v=1&width=400#top"


def test_a_configured_width_is_used() -> None:
    assert image_urls(f"{CDN_IMAGE}?v=1", image_width=800) == f"{CDN_IMAGE}?v=1&width=800"


def test_null_leaves_the_url_untouched() -> None:
    original = f"{CDN_IMAGE}?v=1762411731&width=2000"

    assert image_urls(original, image_width=None) == original
    assert image_urls(CDN_IMAGE, image_width=None) == CDN_IMAGE


@pytest.mark.parametrize(
    ("image", "expected"), [(None, None), ("", None), (42, 42), (["x"], ["x"])]
)
def test_a_missing_or_odd_image_value_is_left_for_the_validator_to_drop(
    image: object, expected: object
) -> None:
    [record] = records_of(suggest_body(shopify_product(1, image=image)))

    assert record["image_url"] == expected


def test_the_width_applies_to_the_featured_image_fallback_too() -> None:
    product = shopify_product(1, image=None, featured_image={"url": f"{CDN_IMAGE}?v=3"})

    [record] = records_of(suggest_body(product), image_width=250)

    assert record["image_url"] == f"{CDN_IMAGE}?v=3&width=250"


def test_products_from_the_saved_samples_carry_the_width_by_default() -> None:
    raw = fixture_text("ohpolly-suggest-black-blazer.json")
    outcome = ExtractionChain(default_registry()).run(raw, shopify_store(), OHPOLLY_BLAZER_URL)

    assert outcome.products
    for product in outcome.products:
        assert product.image_url.startswith("https://cdn.shopify.com/s/files/")
        assert product.image_url.endswith("&width=400")
        assert product.image_url.count("width=") == 1
        assert "?v=" in product.image_url  # the sample's own version parameter survives


def test_the_widened_url_is_still_on_the_allow_list_and_the_product_url_is_unaffected() -> None:
    raw = fixture_text("ohpolly-suggest-black-blazer.json")
    outcome = ExtractionChain(default_registry()).run(raw, shopify_store(), OHPOLLY_BLAZER_URL)

    assert outcome.dropped == {}
    assert all("width" not in product.product_url for product in outcome.products)


def test_with_null_the_saved_samples_keep_their_original_image_urls() -> None:
    raw = fixture_text("ohpolly-suggest-black-blazer.json")
    store = shopify_store(
        extraction={"strategies": [{"name": "shopify", "options": {"image_width": None}}]}
    )

    outcome = ExtractionChain(default_registry()).run(raw, store, OHPOLLY_BLAZER_URL)

    originals = [p["image"] for p in saved_products("ohpolly-suggest-black-blazer.json")]
    assert [p.image_url for p in outcome.products] == originals


# --------------------------------------------------------------------------------------------
# Store-file validation of the strategy
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strategy",
    [
        StrategyConfig(name="shopify"),
        StrategyConfig(name="shopify", options={"name_field": "title"}),
        StrategyConfig(name="shopify", options={"name_field": "vendor"}),
        StrategyConfig(name="shopify", options={"image_width": 400}),
        StrategyConfig(name="shopify", options={"image_width": 1}),
        StrategyConfig(name="shopify", options={"image_width": None}),
        StrategyConfig(name="shopify", options={"name_field": "vendor", "image_width": 600}),
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
        (StrategyConfig(name="shopify", options={"image_width": 0}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_width": -400}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_width": 400.5}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_width": "400"}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_width": True}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_width": False}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_width": [400]}), "image_width"),
        (StrategyConfig(name="shopify", options={"image_widht": 400}), "image_widht"),
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
