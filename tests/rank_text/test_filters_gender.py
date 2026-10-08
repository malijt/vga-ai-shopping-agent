"""The hard gender filter reads ``Product.gender`` (the store's own type and tags) before the title.

Why: Sacoor Brothers, Nautica and Maison D'Vie sell for men and women in one result list and say
which in fields the title does not repeat. A "black blazer" search at Sacoor returned 7 men's and
3 women's blazers, and Nautica titles such as "Nelson Pant - Black" carry no gender word at all, so
a shopper who asked "for men" was shown the other gender's items.

The rule under test (``vga.rank.filters``): when the request's gender is **explicit**, a product
whose ``gender`` is the other one is dropped; unisex and unknown are kept; and when ``gender`` is
``None`` the title decides exactly as before. An inferred gender is never used.

The real-response tests replay the saved ``/search/suggest.json`` responses of the stores (copied
under ``tests/fetch/fixtures/gender/``) through the real extraction chain.
"""

import pytest

from tests.factories import make_item_intent, make_product
from tests.fetch.conftest import gender_products
from vga.models import Category, Gender, GenderSource, ItemIntent, Product
from vga.rank import DropReason, FilterResult, apply_hard_filters
from vga.rank.lexicon import title_gender

MEN, WOMEN, UNISEX = Gender.MEN, Gender.WOMEN, Gender.UNISEX
EXPLICIT, INFERRED, NO_SOURCE = GenderSource.EXPLICIT, GenderSource.INFERRED, GenderSource.NONE


def request(
    gender: Gender | None, source: GenderSource, category: Category = Category.OUTERWEAR
) -> ItemIntent:
    return make_item_intent(category=category, gender=gender, gender_source=source)


def product(title: str, gender: Gender | None, **overrides: object) -> Product:
    """A product whose title names a blazer (so the category filter keeps it for outerwear)."""
    return make_product(1, title=title, gender=gender, **overrides)


def titles_where(results: list[tuple[Product, FilterResult]], *, keep: bool) -> list[str]:
    return [p.title for p, r in results if r.keep is keep]


def filtered(item: ItemIntent, products: list[Product]) -> list[tuple[Product, FilterResult]]:
    return [(p, apply_hard_filters(item, p)) for p in products]


# --------------------------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "product_gender", "kept"),
    [
        pytest.param(MEN, WOMEN, False, id="men ask, women's product"),
        pytest.param(WOMEN, MEN, False, id="women ask, men's product"),
        pytest.param(MEN, MEN, True, id="men ask, men's product"),
        pytest.param(WOMEN, WOMEN, True, id="women ask, women's product"),
        pytest.param(MEN, UNISEX, True, id="men ask, unisex product"),
        pytest.param(WOMEN, UNISEX, True, id="women ask, unisex product"),
        pytest.param(MEN, None, True, id="men ask, unknown product"),
        pytest.param(WOMEN, None, True, id="women ask, unknown product"),
    ],
)
def test_an_explicit_request_drops_only_a_product_for_the_other_gender(
    requested: Gender, product_gender: Gender | None, kept: bool
) -> None:
    result = apply_hard_filters(
        request(requested, EXPLICIT), product("Black Blazer", product_gender)
    )

    assert result.keep is kept
    if not kept:
        assert result.reason is DropReason.GENDER_MISMATCH
        assert result.category is None


@pytest.mark.parametrize("product_gender", [MEN, WOMEN, UNISEX, None])
@pytest.mark.parametrize(
    ("requested", "source"),
    [
        pytest.param(None, NO_SOURCE, id="no gender in the request"),
        pytest.param(MEN, INFERRED, id="inferred men"),
        pytest.param(WOMEN, INFERRED, id="inferred women"),
        pytest.param(UNISEX, EXPLICIT, id="explicit unisex"),
    ],
)
def test_without_an_explicit_men_or_women_request_nothing_is_dropped_for_gender(
    requested: Gender | None, source: GenderSource, product_gender: Gender | None
) -> None:
    result = apply_hard_filters(request(requested, source), product("Black Blazer", product_gender))

    assert result.keep
    assert result.reason is None


@pytest.mark.parametrize(
    ("requested", "title", "kept"),
    [
        pytest.param(MEN, "Women's Black Blazer", False, id="women's title, men ask"),
        pytest.param(WOMEN, "Men's Black Blazer", False, id="men's title, women ask"),
        pytest.param(MEN, "Black Blazer for Women", False, id="'for women' title"),
        pytest.param(MEN, "Men's Black Blazer", True, id="same gender"),
        pytest.param(MEN, "Black Blazer", True, id="no cue"),
        pytest.param(MEN, "Unisex Blazer", True, id="unisex title"),
        pytest.param(MEN, "Men's & Women's Blazer", True, id="title cues both"),
    ],
)
def test_when_the_gender_is_unknown_the_title_decides_as_before(
    requested: Gender, title: str, kept: bool
) -> None:
    result = apply_hard_filters(request(requested, EXPLICIT), product(title, None))

    assert result.keep is kept
    if not kept:
        assert result.reason is DropReason.GENDER_MISMATCH


def test_the_stores_gender_outranks_a_contradicting_title() -> None:
    men_ask = request(MEN, EXPLICIT)
    women_ask = request(WOMEN, EXPLICIT)

    # The store says women's although the title says "Men's": a men's request drops it.
    assert not apply_hard_filters(men_ask, product("Men's Black Blazer", WOMEN)).keep
    assert apply_hard_filters(women_ask, product("Men's Black Blazer", WOMEN)).keep
    # The store says men's although the title says "Women's": a men's request keeps it.
    assert apply_hard_filters(men_ask, product("Women's Black Blazer", MEN)).keep


def test_a_unisex_product_is_kept_even_when_its_title_names_the_other_gender() -> None:
    result = apply_hard_filters(request(MEN, EXPLICIT), product("Women's Black Blazer", UNISEX))

    assert result.keep


def test_the_gender_does_not_change_category_or_stock_filtering() -> None:
    men_ask = request(MEN, EXPLICIT)

    wrong_category = apply_hard_filters(men_ask, product("Black Cotton Shirt", MEN))
    sold_out = apply_hard_filters(men_ask, product("Black Blazer", MEN, in_stock=False))

    assert wrong_category.reason is DropReason.WRONG_CATEGORY
    assert sold_out.reason is DropReason.OUT_OF_STOCK


# --------------------------------------------------------------------------------------------
# Sacoor Brothers: the "black blazer" response
# --------------------------------------------------------------------------------------------

SACOOR_WOMENS_TITLES = [
    "Double-Breasted Blazer In High-performance Wool",
    "Single Breasted Black Suit In Wool Blend",
    "Regular Fit Blazer In Cotton And Linen Blend With Peak Lapel",
]


@pytest.fixture
def sacoor_blazers() -> list[Product]:
    """The 10 records of the real response, 8 after validation collapses two repeat listings:
    five men's blazers and the three women's pieces below."""
    products = gender_products("sacoor-brothers-uae", "suggest-black-blazer.json")
    assert len(products) == 8
    return products


def test_the_sacoor_titles_name_no_gender_so_only_the_stores_data_can_tell(
    sacoor_blazers: list[Product],
) -> None:
    assert {title_gender(p.title) for p in sacoor_blazers} == {None}


def test_a_mens_request_drops_the_sacoor_womens_items_and_keeps_the_mens(
    sacoor_blazers: list[Product],
) -> None:
    results = filtered(request(MEN, EXPLICIT), sacoor_blazers)

    dropped = [p for p, r in results if r.reason is DropReason.GENDER_MISMATCH]
    assert sorted(p.title for p in dropped) == sorted(SACOOR_WOMENS_TITLES)
    assert {p.gender for p in dropped} == {WOMEN}
    kept = [p for p, r in results if r.keep]
    assert len(kept) == 5
    assert {p.gender for p in kept} == {MEN}


def test_a_womens_request_drops_the_sacoor_mens_items_and_keeps_the_womens(
    sacoor_blazers: list[Product],
) -> None:
    results = filtered(request(WOMEN, EXPLICIT), sacoor_blazers)

    dropped = [p for p, r in results if r.reason is DropReason.GENDER_MISMATCH]
    assert len(dropped) == 5
    assert {p.gender for p in dropped} == {MEN}
    assert all(title_gender(p.title) is None for p in dropped)
    kept = [p for p, r in results if r.keep]
    assert sorted(p.title for p in kept) == sorted(SACOOR_WOMENS_TITLES)


@pytest.mark.parametrize(
    ("requested", "source"),
    [
        pytest.param(None, NO_SOURCE, id="no gender"),
        pytest.param(MEN, INFERRED, id="inferred men"),
        pytest.param(WOMEN, INFERRED, id="inferred women"),
    ],
)
def test_with_no_gender_or_an_inferred_one_nothing_at_sacoor_is_dropped_for_gender(
    sacoor_blazers: list[Product], requested: Gender | None, source: GenderSource
) -> None:
    results = filtered(request(requested, source), sacoor_blazers)

    assert not [r for _, r in results if r.reason is DropReason.GENDER_MISMATCH]
    assert len(titles_where(results, keep=True)) == 8


# --------------------------------------------------------------------------------------------
# Nautica: a title without a gender word, a "Mens" tag
# --------------------------------------------------------------------------------------------


@pytest.fixture
def nautica_trousers() -> list[Product]:
    return gender_products("nautica-uae", "suggest-trousers.json")


def nautica_nelson(products: list[Product]) -> Product:
    [nelson] = [p for p in products if p.title == "Nelson Pant - Black"]
    return nelson


def test_a_nautica_title_with_no_gender_word_is_kept_for_men_and_dropped_for_women(
    nautica_trousers: list[Product],
) -> None:
    nelson = nautica_nelson(nautica_trousers)
    assert title_gender(nelson.title) is None  # nothing in the title says "men"
    assert nelson.gender is MEN  # the store's "Mens" tag does

    for_men = apply_hard_filters(request(MEN, EXPLICIT, Category.BOTTOMS), nelson)
    for_women = apply_hard_filters(request(WOMEN, EXPLICIT, Category.BOTTOMS), nelson)

    assert for_men.keep
    assert for_men.category is Category.BOTTOMS
    assert not for_women.keep
    assert for_women.reason is DropReason.GENDER_MISMATCH


def test_without_the_stores_gender_the_same_nautica_title_is_shown_to_women() -> None:
    """What happened before ``Product.gender``: the title alone cannot tell, so it is kept."""
    nelson = nautica_nelson(gender_products("nautica-uae", "suggest-trousers.json"))

    result = apply_hard_filters(
        request(WOMEN, EXPLICIT, Category.BOTTOMS), nelson.model_copy(update={"gender": None})
    )

    assert result.keep


def test_a_nautica_trouser_search_splits_by_the_requested_gender(
    nautica_trousers: list[Product],
) -> None:
    men = filtered(request(MEN, EXPLICIT, Category.BOTTOMS), nautica_trousers)
    women = filtered(request(WOMEN, EXPLICIT, Category.BOTTOMS), nautica_trousers)

    # 10 records; validation collapses the three identical "Women's Trouser" listings into one.
    assert len(nautica_trousers) == 8
    assert sorted(titles_where(men, keep=True)) == sorted(
        p.title for p in nautica_trousers if p.gender is MEN
    )
    assert sorted(titles_where(women, keep=True)) == ["Women's Trouser"]
    assert len(titles_where(men, keep=True)) == 7
    assert {p.gender for p, r in men if r.keep} == {MEN}
    assert {p.gender for p, r in women if r.keep} == {WOMEN}
    assert {r.reason for p, r in men if p.gender is WOMEN} == {DropReason.GENDER_MISMATCH}
    assert {r.reason for p, r in women if p.gender is MEN} == {DropReason.GENDER_MISMATCH}


# --------------------------------------------------------------------------------------------
# A store whose type and tags are silent: the title still works
# --------------------------------------------------------------------------------------------


def test_a_title_only_cue_still_works_when_type_and_tags_are_silent() -> None:
    """Giordano writes "Men's ..." in every title and nothing in type or tags."""
    products = gender_products("giordano-uae", "suggest-jacket.json")
    assert products
    assert {p.gender for p in products} == {None}
    assert {title_gender(p.title) for p in products} == {MEN}

    for_women = filtered(request(WOMEN, EXPLICIT), products)
    for_men = filtered(request(MEN, EXPLICIT), products)

    assert not titles_where(for_women, keep=True)
    assert {r.reason for _, r in for_women} == {DropReason.GENDER_MISMATCH}
    assert len(titles_where(for_men, keep=True)) == len(products)


# --------------------------------------------------------------------------------------------
# Maison D'Vie: every product carries a Men or Women tag
# --------------------------------------------------------------------------------------------


def test_maison_dvie_shirts_split_by_the_requested_gender() -> None:
    products = gender_products("maison-dvie", "suggest-shirt.json")
    men = [p.title for p in products if p.gender is MEN]
    assert len(products) == 10
    assert len(men) == 3  # the three "Pamplona Linen Shirt Men ..." items

    kept_for_men = [
        p.title
        for p in products
        if apply_hard_filters(request(MEN, EXPLICIT, Category.TOPS), p).keep
    ]
    kept_for_women = [
        p.title
        for p in products
        if apply_hard_filters(request(WOMEN, EXPLICIT, Category.TOPS), p).keep
    ]

    assert sorted(kept_for_men) == sorted(men)
    assert len(kept_for_women) == 7
    assert not set(kept_for_women) & set(men)
