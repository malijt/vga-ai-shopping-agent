"""Keyword rebuilding and the stated-gender rule (plan 5.3.3, 5.3.4)."""

import pytest

from tests.factories import make_item_intent
from vga.models import Category, Gender, GenderSource
from vga.understand.keywords import (
    applied_gender_word,
    dedupe_keywords,
    rebuild_keywords,
    with_stated_gender,
)


def test_keywords_are_rebuilt_from_the_items_fields_most_specific_first() -> None:
    item = make_item_intent(colour="black", material="leather", style="biker jacket")

    assert rebuild_keywords(item) == [
        "black leather biker jacket",
        "black biker jacket",
        "biker jacket",
    ]


def test_changing_the_colour_changes_the_keywords() -> None:
    item = make_item_intent(colour="dark brown", style="oversized blazer")

    assert rebuild_keywords(item) == ["dark brown oversized blazer", "oversized blazer"]


def test_without_a_colour_or_material_there_is_one_variant() -> None:
    assert rebuild_keywords(make_item_intent(colour=None, style="wide-leg jeans")) == [
        "wide-leg jeans"
    ]


@pytest.mark.parametrize(
    ("category", "noun"),
    [
        (Category.TOPS, "top"),
        (Category.OUTERWEAR, "jacket"),
        (Category.BOTTOMS, "pants"),
        (Category.SHOES, "shoes"),
        (Category.DRESSES, "dress"),
    ],
)
def test_an_item_without_a_style_falls_back_to_a_noun_for_its_category(
    category: Category, noun: str
) -> None:
    item = make_item_intent(category=category, colour="navy", style=None)

    assert rebuild_keywords(item) == [f"navy {noun}", noun]


def test_a_chip_edit_to_the_colour_of_an_abaya_keeps_the_garments_own_word() -> None:
    # The keywords are rebuilt from colour and style with no model call, so "abaya" must survive
    # in the style: a store that sells abayas finds nothing for "dress".
    item = make_item_intent(
        category=Category.DRESSES, colour="burgundy", style="open front abaya", material=None
    )

    assert rebuild_keywords(item) == ["burgundy open front abaya", "open front abaya"]


def test_a_word_repeated_across_colour_and_style_appears_once() -> None:
    item = make_item_intent(colour="black", style="black blazer")

    assert rebuild_keywords(item) == ["black blazer"]


def test_price_words_in_a_style_never_come_back_into_the_keywords() -> None:
    item = make_item_intent(colour="black", style="cheap blazer")

    assert all("cheap" not in keyword for keyword in rebuild_keywords(item))


def test_a_stated_gender_is_added_to_the_first_variant_only() -> None:
    item = make_item_intent(
        colour="black", style="blazer", gender=Gender.MEN, gender_source=GenderSource.EXPLICIT
    )

    assert rebuild_keywords(item) == ["black blazer men", "blazer"]


def test_an_inferred_gender_is_not_used_in_the_keywords() -> None:
    item = make_item_intent(
        colour="black", style="blazer", gender=Gender.WOMEN, gender_source=GenderSource.INFERRED
    )

    assert rebuild_keywords(item) == ["black blazer", "blazer"]


def test_unisex_adds_no_word() -> None:
    item = make_item_intent(
        colour="black", style="hoodie", gender=Gender.UNISEX, gender_source=GenderSource.EXPLICIT
    )

    assert rebuild_keywords(item) == ["black hoodie", "hoodie"]


@pytest.mark.parametrize(
    ("gender", "source", "word"),
    [
        (Gender.MEN, GenderSource.EXPLICIT, "men"),
        (Gender.WOMEN, GenderSource.EXPLICIT, "women"),
        (Gender.UNISEX, GenderSource.EXPLICIT, None),
        (Gender.MEN, GenderSource.INFERRED, None),
        (None, GenderSource.NONE, None),
    ],
)
def test_only_a_stated_gender_becomes_a_word(
    gender: Gender | None, source: GenderSource, word: str | None
) -> None:
    assert applied_gender_word(gender, source) == word


def test_a_gender_word_that_would_overflow_the_keyword_is_skipped() -> None:
    long_keyword = "a" * 79

    assert with_stated_gender([long_keyword], Gender.MEN, GenderSource.EXPLICIT) == [long_keyword]


def test_dedupe_keeps_order_ignores_case_and_empties_and_respects_the_limit() -> None:
    assert dedupe_keywords(["b", "", "B", "a", "c", "d"]) == ["b", "a", "c"]
    assert dedupe_keywords(["x", "y"], limit=1) == ["x"]
