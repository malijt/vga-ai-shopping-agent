"""Hard filters (plan 7.2.1, PRD R7): category, stock and explicit gender."""

import pytest

from tests.factories import make_item_intent, make_product
from vga.models import Category, Gender, GenderSource, ItemIntent, Product
from vga.rank import DropReason, apply_hard_filters


def product(title: str, index: int = 1, **overrides: object) -> Product:
    """A product with no store-supplied category unless one is given."""
    return make_product(index, title=title, **{"category": None, **overrides})


BLAZER_REQUEST = make_item_intent(category=Category.OUTERWEAR)


# --------------------------------------------------------------------------------------------
# Category
# --------------------------------------------------------------------------------------------


def test_a_product_of_the_requested_category_is_kept_with_its_category() -> None:
    result = apply_hard_filters(BLAZER_REQUEST, product("Black Oversized Blazer"))

    assert result.keep
    assert result.reason is None
    assert result.category is Category.OUTERWEAR


@pytest.mark.parametrize(
    "title",
    ["Black Cotton Shirt", "Wide-Leg Jeans", "Leather Chelsea Boots"],
)
def test_a_product_of_another_category_is_dropped(title: str) -> None:
    result = apply_hard_filters(BLAZER_REQUEST, product(title))

    assert not result.keep
    assert result.reason is DropReason.WRONG_CATEGORY


@pytest.mark.parametrize(
    "title",
    [
        "Satin Midi Dress",
        "Evening Gown",
        "Linen Jumpsuit",
        "Cotton Playsuit",
        "Leather Tote Bag",
        "Chain Belt",
        "Wool Beanie Hat",
        "Silk Scarf",
        "Gold Hoop Earrings",
    ],
)
def test_a_garment_outside_the_four_categories_is_dropped_for_every_request(title: str) -> None:
    for category in Category:
        result = apply_hard_filters(make_item_intent(category=category), product(title))

        assert not result.keep
        assert result.reason is DropReason.OUT_OF_SCOPE


def test_a_skirt_is_bottoms_and_is_kept_for_a_bottoms_request() -> None:
    result = apply_hard_filters(
        make_item_intent(category=Category.BOTTOMS), product("Pleated Midi Skirt")
    )

    assert result.keep
    assert result.category is Category.BOTTOMS


def test_the_stores_label_does_not_save_a_dress_from_being_dropped() -> None:
    # Oh Polly files this under "Coats & Jackets".
    mislabelled = product(
        "Single-Breasted Blazer Mini Dress in Black", category=Category.OUTERWEAR
    )

    result = apply_hard_filters(BLAZER_REQUEST, mislabelled)

    assert not result.keep
    assert result.reason is DropReason.OUT_OF_SCOPE


def test_a_product_whose_category_cannot_be_inferred_is_kept_without_a_category() -> None:
    result = apply_hard_filters(BLAZER_REQUEST, product("Black Oversized"))

    assert result.keep
    assert result.category is None


def test_the_stores_label_is_used_when_the_title_names_no_garment() -> None:
    vague = "Black Oversized"
    same = apply_hard_filters(BLAZER_REQUEST, product(vague, category=Category.OUTERWEAR))
    other = apply_hard_filters(BLAZER_REQUEST, product(vague, category=Category.SHOES))

    assert same.keep
    assert same.category is Category.OUTERWEAR
    assert not other.keep
    assert other.reason is DropReason.WRONG_CATEGORY


def test_nine_dresses_and_one_blazer_leave_only_the_blazer() -> None:
    """A real store search for "black blazer" returned 9 dresses and 1 blazer."""
    dress_titles = [
        "Carlin | Black Plunge-Neck Tailored Mini Dress With Button Detailing",
        "Angel | Black Plunge-Neck Tailored Mini Dress With Gold-Detailing",
        "Friya | Black Velvet Sweetheart-Neck Tailored Mini Dress",
    ]
    products = [product(dress_titles[i % 3], index=i + 1) for i in range(9)]
    products.append(product("Vergia | Black Lace Tailored-Blazer", index=10))

    kept = [p for p in products if apply_hard_filters(BLAZER_REQUEST, p).keep]

    assert [p.title for p in kept] == ["Vergia | Black Lace Tailored-Blazer"]


# --------------------------------------------------------------------------------------------
# Stock
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("in_stock", "kept"),
    [
        pytest.param(False, False, id="out of stock is dropped"),
        pytest.param(True, True, id="in stock is kept"),
        pytest.param(None, True, id="unknown stock is kept"),
    ],
)
def test_only_a_product_known_to_be_out_of_stock_is_dropped(
    in_stock: bool | None, kept: bool
) -> None:
    result = apply_hard_filters(BLAZER_REQUEST, product("Black Blazer", in_stock=in_stock))

    assert result.keep is kept
    if not kept:
        assert result.reason is DropReason.OUT_OF_STOCK


# --------------------------------------------------------------------------------------------
# Price and budget are not filter matters
# --------------------------------------------------------------------------------------------


def test_a_very_expensive_product_passes_the_filters() -> None:
    result = apply_hard_filters(BLAZER_REQUEST, product("Black Blazer", price=99999.0))

    assert result.keep


# --------------------------------------------------------------------------------------------
# Gender
# --------------------------------------------------------------------------------------------


def _request(gender: Gender | None, source: GenderSource) -> ItemIntent:
    return make_item_intent(gender=gender, gender_source=source)


@pytest.mark.parametrize(
    ("gender", "source", "title", "kept"),
    [
        pytest.param(Gender.MEN, GenderSource.EXPLICIT, "Women's Black Blazer", False, id="men"),
        pytest.param(Gender.WOMEN, GenderSource.EXPLICIT, "Men's Black Blazer", False, id="women"),
        pytest.param(Gender.MEN, GenderSource.EXPLICIT, "Black Blazer for Women", False, id="for"),
        pytest.param(Gender.MEN, GenderSource.EXPLICIT, "Men's Black Blazer", True, id="same"),
        pytest.param(Gender.MEN, GenderSource.EXPLICIT, "Black Blazer", True, id="no cue"),
        pytest.param(Gender.MEN, GenderSource.EXPLICIT, "Unisex Blazer", True, id="unisex"),
        pytest.param(
            Gender.MEN, GenderSource.EXPLICIT, "Men's & Women's Blazer", True, id="both cues"
        ),
        pytest.param(
            Gender.MEN, GenderSource.INFERRED, "Women's Black Blazer", True, id="inferred men"
        ),
        pytest.param(
            Gender.WOMEN, GenderSource.INFERRED, "Men's Black Blazer", True, id="inferred women"
        ),
        pytest.param(None, GenderSource.NONE, "Women's Black Blazer", True, id="no gender"),
        pytest.param(
            Gender.UNISEX, GenderSource.EXPLICIT, "Women's Black Blazer", True, id="unisex ask"
        ),
    ],
)
def test_gender_drops_a_product_only_when_explicit_and_the_title_clearly_says_otherwise(
    gender: Gender | None, source: GenderSource, title: str, kept: bool
) -> None:
    result = apply_hard_filters(_request(gender, source), product(title))

    assert result.keep is kept
    if not kept:
        assert result.reason is DropReason.GENDER_MISMATCH
