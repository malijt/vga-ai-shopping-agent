"""Chip overrides and the gender policy (plan 5.3.3, 5.3.4): pure code, no model call."""

import pytest

from tests.factories import make_budget, make_chip_edits, make_item_intent, make_understand_result
from vga.errors import InvalidInputError
from vga.models import Category, Gender, GenderSource
from vga.understand import apply_overrides, effective_gender, rebuild_keywords


def _result(*items):
    return make_understand_result(items=list(items) or [make_item_intent()])


def _edits(**fields):
    return make_chip_edits(**fields)


# --------------------------------------------------------------------------------------------
# apply_overrides
# --------------------------------------------------------------------------------------------


def test_a_colour_edit_changes_the_field_and_the_keywords_with_no_model_call() -> None:
    result = _result(make_item_intent(colour="black", style="oversized blazer"))

    out = apply_overrides(result, _edits(items=[{"index": 0, "colour": "dark brown"}]))

    [item] = out.items
    assert item.colour == "dark brown"
    assert item.search_keywords == ["dark brown oversized blazer", "oversized blazer"]


def test_clearing_the_colour_removes_it_from_the_keywords() -> None:
    result = _result(make_item_intent(colour="black", style="oversized blazer"))

    [item] = apply_overrides(result, _edits(items=[{"index": 0, "colour": ""}])).items

    assert item.colour is None
    assert item.search_keywords == ["oversized blazer"]


def test_the_colour_chip_is_cleaned_like_any_other_text() -> None:
    result = _result(make_item_intent(colour="black", style="blazer"))

    [item] = apply_overrides(
        result, _edits(items=[{"index": 0, "colour": "<b>navy</b> http://evil.example"}])
    ).items

    assert item.colour == "b navy b"


def test_a_category_edit_replaces_the_category_and_drops_the_stale_style() -> None:
    result = _result(
        make_item_intent(category=Category.OUTERWEAR, colour="black", style="bomber jacket")
    )

    [item] = apply_overrides(result, _edits(items=[{"index": 0, "category": "tops"}])).items

    assert item.category is Category.TOPS
    assert item.style is None
    assert item.search_keywords == ["black top", "top"]


def test_an_edit_that_changes_nothing_keeps_the_models_own_keywords() -> None:
    item = make_item_intent(colour="black", search_keywords=["black oversized blazer", "blazer x"])

    [out] = apply_overrides(
        _result(item), _edits(items=[{"index": 0, "colour": "black", "category": "outerwear"}])
    ).items

    assert out == item


def test_only_the_edited_item_changes() -> None:
    top = make_item_intent(category=Category.TOPS, colour="white", style="shirt")
    shoes = make_item_intent(category=Category.SHOES, colour="black", style="sneakers")

    out = apply_overrides(_result(top, shoes), _edits(items=[{"index": 1, "colour": "red"}]))

    assert out.items[0] == top
    assert out.items[1].colour == "red"
    assert out.items[1].search_keywords[0] == "red sneakers"


def test_a_gender_chosen_in_the_chips_is_confirmed_and_becomes_explicit() -> None:
    inferred = make_item_intent(
        colour="black",
        style="blazer",
        gender=Gender.WOMEN,
        gender_source=GenderSource.INFERRED,
        search_keywords=["black blazer"],
    )

    [out] = apply_overrides(
        _result(inferred), _edits(items=[{"index": 0, "gender": "women"}])
    ).items

    assert out.gender is Gender.WOMEN
    assert out.gender_source is GenderSource.EXPLICIT
    assert out.search_keywords == ["black blazer women", "blazer"]


def test_changing_the_gender_chip_to_the_other_gender_is_applied() -> None:
    inferred = make_item_intent(gender=Gender.WOMEN, gender_source=GenderSource.INFERRED)

    [out] = apply_overrides(_result(inferred), _edits(items=[{"index": 0, "gender": "men"}])).items

    assert (out.gender, out.gender_source) == (Gender.MEN, GenderSource.EXPLICIT)
    assert out.search_keywords[0].endswith(" men")


def test_the_budget_is_replaced_or_cleared_for_the_whole_request() -> None:
    result = make_understand_result(budget=make_budget(max_price=400))

    assert apply_overrides(result, _edits(budget={"max_price": 250, "currency": "AED"})).budget == (
        make_budget(max_price=250)
    )
    assert apply_overrides(result, _edits(clear_budget=True)).budget is None
    assert apply_overrides(result, _edits()).budget == result.budget


def test_no_edits_returns_an_equal_result() -> None:
    result = _result()

    assert apply_overrides(result, _edits()) == result


def test_the_input_result_is_never_changed() -> None:
    result = _result(make_item_intent(colour="black"))
    snapshot = result.model_dump()

    apply_overrides(result, _edits(items=[{"index": 0, "colour": "red"}], clear_budget=True))

    assert result.model_dump() == snapshot


def test_everything_apart_from_items_and_budget_is_carried_over() -> None:
    result = make_understand_result(warnings=["a note"], edits=["cheaper"], language="ar")

    out = apply_overrides(result, _edits(items=[{"index": 0, "colour": "red"}]))

    assert (out.warnings, out.edits, out.language) == (["a note"], ["cheaper"], "ar")
    assert (out.model, out.prompt_version, out.usage) == (
        result.model,
        result.prompt_version,
        result.usage,
    )


def test_an_edit_for_an_item_that_does_not_exist_is_a_plain_error() -> None:
    with pytest.raises(InvalidInputError) as caught:
        apply_overrides(_result(), _edits(items=[{"index": 2, "colour": "red"}]))

    assert "item 2" in (caught.value.detail or "")


# --------------------------------------------------------------------------------------------
# The gender policy
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gender", "source", "expected"),
    [
        (Gender.MEN, GenderSource.EXPLICIT, Gender.MEN),
        (Gender.WOMEN, GenderSource.EXPLICIT, Gender.WOMEN),
        (Gender.UNISEX, GenderSource.EXPLICIT, Gender.UNISEX),
        (Gender.MEN, GenderSource.INFERRED, None),
        (None, GenderSource.NONE, None),
    ],
)
def test_only_an_explicit_gender_may_be_used_for_filtering(
    gender: Gender | None, source: GenderSource, expected: Gender | None
) -> None:
    item = make_item_intent(gender=gender, gender_source=source)

    assert effective_gender(item) is expected


def test_an_inferred_gender_stays_out_of_rebuilt_keywords_until_confirmed() -> None:
    inferred = make_item_intent(
        colour="black", style="blazer", gender=Gender.MEN, gender_source=GenderSource.INFERRED
    )
    explicit = inferred.model_copy(update={"gender_source": GenderSource.EXPLICIT})

    assert rebuild_keywords(inferred) == ["black blazer", "blazer"]
    assert rebuild_keywords(explicit) == ["black blazer men", "blazer"]
