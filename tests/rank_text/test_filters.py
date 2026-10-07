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
        "Linen Jumpsuit",
        "Cotton Playsuit",
        "Cotton Nightdress",
        "Swim Dress",
        "Leather Tote Bag",
        "Chain Belt",
        "Wool Beanie Hat",
        "Silk Scarf",
        "Gold Hoop Earrings",
        "Black Chiffon Sheila",
        "Satin Hijab",
        "Aviator Sunglasses",
    ],
)
def test_a_garment_outside_the_five_categories_is_dropped_for_every_request(title: str) -> None:
    for category in Category:
        result = apply_hard_filters(make_item_intent(category=category), product(title))

        assert not result.keep
        assert result.reason is DropReason.OUT_OF_SCOPE


# --------------------------------------------------------------------------------------------
# Dresses and ethnic wear, the fifth category
# --------------------------------------------------------------------------------------------

DRESS_REQUEST = make_item_intent(category=Category.DRESSES)
OTHER_FOUR = [category for category in Category if category is not Category.DRESSES]

DRESS_LIKE_TITLES = [
    "Neda Plain Abaya Front Open with Buttons",
    "GIGI BURGUNDY ABAYA",
    "Printed Dress - AS26-92",
    "2 Piece - Embroidered Gown - FE26-128",
    "ZAHRA GOLD DRESS WITH CAPE",
    "Off-White Under Abaya Dress In Satin",
    "JALILA GREEN FLORAL KAFTAN",
    "Embroidered Kurta - NQ26-008",
]


@pytest.mark.parametrize("title", DRESS_LIKE_TITLES)
def test_a_request_for_dresses_keeps_dress_like_products_and_labels_them_dresses(
    title: str,
) -> None:
    result = apply_hard_filters(DRESS_REQUEST, product(title))

    assert result.keep
    assert result.category is Category.DRESSES


@pytest.mark.parametrize("title", DRESS_LIKE_TITLES)
@pytest.mark.parametrize("category", OTHER_FOUR)
def test_a_request_for_any_other_category_drops_dress_like_products(
    category: Category, title: str
) -> None:
    result = apply_hard_filters(make_item_intent(category=category), product(title))

    assert not result.keep
    assert result.reason is DropReason.WRONG_CATEGORY


@pytest.mark.parametrize(
    ("category", "title"),
    [
        pytest.param(Category.TOPS, "Linen Shirt Dress", id="a shirt dress is not a shirt"),
        pytest.param(Category.OUTERWEAR, "Blazer Mini Dress in Black", id="nor a blazer"),
        pytest.param(Category.TOPS, "Sweater Dress", id="a sweater dress is not a sweater"),
        pytest.param(Category.BOTTOMS, "Skirt Dress", id="a skirt dress is not a skirt"),
    ],
)
def test_a_dress_named_after_another_garment_is_not_offered_for_that_garment(
    category: Category, title: str
) -> None:
    result = apply_hard_filters(make_item_intent(category=category), product(title))

    assert not result.keep
    assert result.reason is DropReason.WRONG_CATEGORY


@pytest.mark.parametrize(
    "title",
    [
        "Black Cotton Shirt",
        "Wide-Leg Jeans",
        "Leather Chelsea Boots",
        "Oversized Blazer",
        "Dress Shirt",
        "Dress Pants",
        "Dress Shoes",
    ],
)
def test_a_request_for_dresses_drops_the_other_four_categories(title: str) -> None:
    result = apply_hard_filters(DRESS_REQUEST, product(title))

    assert not result.keep
    assert result.reason is DropReason.WRONG_CATEGORY


@pytest.mark.parametrize(
    "title",
    [
        "Black Chiffon Sheila - Custom Size",
        "Satin Hijab",
        "Silk Scarf",
        "Leather Tote Bag",
        "Gold Hoop Earrings",
    ],
)
def test_a_request_for_dresses_still_drops_accessories(title: str) -> None:
    result = apply_hard_filters(DRESS_REQUEST, product(title))

    assert not result.keep
    assert result.reason is DropReason.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "title",
    [
        "2 Piece - Embroidered Suit - FE26-130",  # Nishat Linen UAE: a South Asian suit
        "Single Breasted Black Suit In Wool Blend",  # Sacoor Brothers UAE: a men's suit
        "Grey Plain Inner",
    ],
)
def test_a_title_with_no_garment_noun_is_kept_for_dresses_without_a_category(title: str) -> None:
    # "suit" means different things at different stores, so it is not a dress word. Both kinds are
    # kept for a dresses request, with no category bonus; the gender filter can still remove a
    # men's suit when the shopper said "women".
    result = apply_hard_filters(DRESS_REQUEST, product(title))

    assert result.keep
    assert result.category is None


def test_the_gender_filter_removes_a_mens_suit_from_a_womens_dress_search() -> None:
    request = make_item_intent(
        category=Category.DRESSES, gender=Gender.WOMEN, gender_source=GenderSource.EXPLICIT
    )

    result = apply_hard_filters(
        request, product("Single Breasted Black Suit In Wool Blend", gender=Gender.MEN)
    )

    assert not result.keep
    assert result.reason is DropReason.GENDER_MISMATCH


def test_a_dress_the_store_files_under_jackets_is_kept_for_a_dress_request() -> None:
    # Oh Polly files "Blazer Mini Dress" under "Coats & Jackets"; the title decides.
    mislabelled = product("Single-Breasted Blazer Mini Dress in Black", category=Category.OUTERWEAR)

    result = apply_hard_filters(DRESS_REQUEST, mislabelled)

    assert result.keep
    assert result.category is Category.DRESSES


def test_a_skirt_is_bottoms_and_is_kept_for_a_bottoms_request() -> None:
    result = apply_hard_filters(
        make_item_intent(category=Category.BOTTOMS), product("Pleated Midi Skirt")
    )

    assert result.keep
    assert result.category is Category.BOTTOMS


def test_the_stores_label_does_not_save_a_dress_from_being_dropped() -> None:
    # Oh Polly files this under "Coats & Jackets".
    mislabelled = product("Single-Breasted Blazer Mini Dress in Black", category=Category.OUTERWEAR)

    result = apply_hard_filters(BLAZER_REQUEST, mislabelled)

    assert not result.keep
    assert result.reason is DropReason.WRONG_CATEGORY


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
# "Khakis" are trousers (found in the first real end-to-end search)
# --------------------------------------------------------------------------------------------

REAL_KHAKIS = [
    "Men Loose Straight Cotton Poplin Khakis",  # Giordano UAE
    "Men's Relaxed Stretch Twill Cargo Khakis",  # Giordano UAE
]


@pytest.mark.parametrize("title", REAL_KHAKIS)
@pytest.mark.parametrize("category", [c for c in Category if c is not Category.BOTTOMS])
def test_khakis_are_dropped_for_every_category_but_bottoms(category: Category, title: str) -> None:
    result = apply_hard_filters(make_item_intent(category=category), product(title))

    assert not result.keep
    assert result.reason is DropReason.WRONG_CATEGORY


@pytest.mark.parametrize("title", REAL_KHAKIS)
def test_khakis_are_kept_and_labelled_bottoms_for_a_bottoms_request(title: str) -> None:
    result = apply_hard_filters(make_item_intent(category=Category.BOTTOMS), product(title))

    assert result.keep
    assert result.category is Category.BOTTOMS


@pytest.mark.parametrize(
    "title", ["Khaki Bomber Jacket", "Khaki Green Trench Coat", "Khaki Utility Overshirt Jacket"]
)
def test_a_singular_khaki_is_a_colour_and_does_not_hide_an_outerwear_product(title: str) -> None:
    result = apply_hard_filters(BLAZER_REQUEST, product(title))

    assert result.keep
    assert result.category is Category.OUTERWEAR


# --------------------------------------------------------------------------------------------
# Children's items, when the shopper stated a gender (found in the first real end-to-end search)
# --------------------------------------------------------------------------------------------

SHIRT_FOR_MEN = make_item_intent(
    category=Category.TOPS, gender=Gender.MEN, gender_source=GenderSource.EXPLICIT
)


def test_a_boys_t_shirt_is_dropped_for_an_explicit_mens_shirt_request() -> None:
    """The real case: an Arabic request for a white cotton shirt for men, under 200 AED, returned
    this Nautica UAE title."""
    result = apply_hard_filters(SHIRT_FOR_MEN, product("Boys Crew Neck T-shirt - White"))

    assert not result.keep
    assert result.reason is DropReason.CHILDRENS_ITEM


@pytest.mark.parametrize(
    "title",
    [
        "Boys Crew Neck T-shirt - White",
        "Boy's Cotton Shirt",
        "Girls Cotton Shirt",
        "Kids Cotton Shirt",
        "Kid's Cotton Shirt",
        "Baby Cotton Shirt",
        "Toddler Cotton Shirt",
        "Infant Cotton Shirt",
        "Junior Cotton Shirt",
        "Cotton Shirt for Kids",
    ],
)
@pytest.mark.parametrize("gender", [Gender.MEN, Gender.WOMEN])
def test_a_childrens_title_is_dropped_when_the_shoppers_gender_is_explicit(
    gender: Gender, title: str
) -> None:
    request = make_item_intent(
        category=Category.TOPS, gender=gender, gender_source=GenderSource.EXPLICIT
    )

    result = apply_hard_filters(request, product(title))

    assert not result.keep
    assert result.reason is DropReason.CHILDRENS_ITEM


@pytest.mark.parametrize(
    ("gender", "source"),
    [
        pytest.param(Gender.MEN, GenderSource.INFERRED, id="inferred men"),
        pytest.param(Gender.WOMEN, GenderSource.INFERRED, id="inferred women"),
        pytest.param(None, GenderSource.NONE, id="no gender"),
        pytest.param(Gender.UNISEX, GenderSource.EXPLICIT, id="unisex"),
    ],
)
def test_a_childrens_title_is_kept_when_the_gender_is_only_inferred_absent_or_unisex(
    gender: Gender | None, source: GenderSource
) -> None:
    # Rule 8: an inferred gender is shown, not applied, so it must not remove anything.
    request = make_item_intent(category=Category.TOPS, gender=gender, gender_source=source)

    result = apply_hard_filters(request, product("Boys Crew Neck T-shirt - White"))

    assert result.keep


@pytest.mark.parametrize(
    "title",
    [
        "Baby Blue Oxford Shirt",  # a colour
        "Baby Pink Cotton Shirt",  # a colour
        "Baby Yellow Cotton Shirt",  # "baby" before any colour word is a shade, not a child
        "Baby Doll Cotton Shirt",  # a style
        "Men's Boyfriend Fit Shirt",  # a different word that contains "boy"
        "Kidskin Leather Shirt",  # a material that starts with "kid"
    ],
)
def test_words_that_only_look_like_a_childrens_marker_do_not_drop_an_adult_product(
    title: str,
) -> None:
    result = apply_hard_filters(SHIRT_FOR_MEN, product(title))

    assert result.keep


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
