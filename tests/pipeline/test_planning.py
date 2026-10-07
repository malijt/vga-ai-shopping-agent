"""The pure decisions made before any store is asked (budget order, mix, items, stores)."""

import pytest

from tests.factories import (
    make_budget,
    make_chip_edits,
    make_item_intent,
    make_settings,
    make_store_config,
    make_understand_result,
)
from vga.models import (
    Category,
    Gender,
    GenderSource,
    MixPreset,
    RunOverrides,
    SettingsOverride,
)
from vga.pipeline.planning import (
    MAX_OUTFIT_KEYWORDS,
    items_to_search,
    resolve_budget,
    settings_for_run,
    stores_for_item,
    wants_cheaper,
)

UNDERSTOOD_300 = make_understand_result(budget=make_budget(max_price=300))


# --------------------------------------------------------------------------------------------
# Budget: chips, then the sidebar, then what was understood
# --------------------------------------------------------------------------------------------


def test_the_understood_budget_is_used_when_nothing_overrides_it() -> None:
    assert resolve_budget(UNDERSTOOD_300, None) == make_budget(max_price=300)
    assert resolve_budget(make_understand_result(), None) is None


def test_the_sidebar_budget_beats_the_understood_one() -> None:
    sidebar = RunOverrides(settings=SettingsOverride(budget=make_budget(max_price=200)))

    assert resolve_budget(UNDERSTOOD_300, sidebar) == make_budget(max_price=200)


def test_a_chip_budget_beats_the_sidebar_budget() -> None:
    overrides = RunOverrides(
        settings=SettingsOverride(budget=make_budget(max_price=200)),
        chips=make_chip_edits(budget=make_budget(max_price=150)),
    )

    assert resolve_budget(UNDERSTOOD_300, overrides) == make_budget(max_price=150)


def test_a_removed_budget_chip_beats_the_sidebar_budget() -> None:
    overrides = RunOverrides(
        settings=SettingsOverride(budget=make_budget(max_price=200)),
        chips=make_chip_edits(clear_budget=True),
    )

    assert resolve_budget(UNDERSTOOD_300, overrides) is None


def test_chips_that_do_not_touch_the_budget_leave_the_order_alone() -> None:
    overrides = RunOverrides(
        settings=SettingsOverride(budget=make_budget(max_price=200)), chips=make_chip_edits()
    )

    assert resolve_budget(UNDERSTOOD_300, overrides) == make_budget(max_price=200)


# --------------------------------------------------------------------------------------------
# "Cheaper" and the mix
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "edit", ["cheaper", "Cheaper", "a bit cheaper", "less expensive", "more affordable"]
)
def test_these_edits_ask_for_something_cheaper(edit: str) -> None:
    assert wants_cheaper(make_understand_result(edits=["dark brown", edit]))


@pytest.mark.parametrize("edit", ["dark brown", "cheap", "expensive", "longer", "pricier"])
def test_these_edits_do_not(edit: str) -> None:
    assert not wants_cheaper(make_understand_result(edits=[edit]))


def test_cheaper_without_a_budget_chooses_the_value_first_mix() -> None:
    understood = make_understand_result(edits=["cheaper"])

    run_settings, switched = settings_for_run(make_settings(), None, understood, None)

    assert switched
    assert run_settings.tier_mix == MixPreset.VALUE_FIRST.mix


def test_cheaper_with_a_budget_changes_nothing() -> None:
    understood = make_understand_result(edits=["cheaper"], budget=make_budget())

    run_settings, switched = settings_for_run(make_settings(), None, understood, make_budget())

    assert not switched
    assert run_settings.tier_mix == MixPreset.EVEN.mix


def test_a_mix_picked_in_the_sidebar_wins_over_cheaper() -> None:
    understood = make_understand_result(edits=["cheaper"])
    overrides = RunOverrides(settings=SettingsOverride(tier_mix=MixPreset.LUXURY_FIRST.mix))

    run_settings, switched = settings_for_run(make_settings(), overrides, understood, None)

    assert not switched
    assert run_settings.tier_mix == MixPreset.LUXURY_FIRST.mix


def test_the_sidebar_mix_is_applied_to_the_run_settings() -> None:
    overrides = RunOverrides(settings=SettingsOverride(tier_mix=MixPreset.VALUE_FIRST.mix))

    run_settings, switched = settings_for_run(
        make_settings(), overrides, make_understand_result(), None
    )

    assert run_settings.tier_mix == MixPreset.VALUE_FIRST.mix
    assert not switched  # the shopper chose it; nothing was decided for them


def test_the_settings_object_passed_in_is_never_changed() -> None:
    settings = make_settings()

    settings_for_run(settings, None, make_understand_result(edits=["cheaper"]), None)

    assert settings.tier_mix == MixPreset.EVEN.mix


# --------------------------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------------------------


def test_one_item_keeps_all_its_keywords() -> None:
    item = make_item_intent(search_keywords=["a", "b", "c"])

    assert items_to_search(make_understand_result(items=[item])) == [item]


def test_every_garment_of_an_outfit_keeps_two_keywords_at_most() -> None:
    items = [make_item_intent(search_keywords=["a", "b", "c"]) for _ in range(4)]

    searched = items_to_search(make_understand_result(items=items))

    assert [item.search_keywords for item in searched] == [["a", "b"]] * 4
    assert MAX_OUTFIT_KEYWORDS == 2


def test_trimming_keywords_changes_nothing_else_about_the_item() -> None:
    items = [make_item_intent(colour="red", search_keywords=["a", "b", "c"]), make_item_intent()]

    first = items_to_search(make_understand_result(items=items))[0]

    assert first.colour == "red"
    assert first.category == items[0].category


# --------------------------------------------------------------------------------------------
# Stores follow a STATED gender only
# --------------------------------------------------------------------------------------------


def stores() -> list:
    return [
        make_store_config(id="everyone", name="Everyone"),
        make_store_config(
            id="women-only",
            name="Women Only",
            search_url_template="https://www.demo-store.example/w?q={query}",
            genders=frozenset({Gender.WOMEN}),
        ),
        make_store_config(
            id="men-only",
            name="Men Only",
            search_url_template="https://www.demo-store.example/m?q={query}",
            genders=frozenset({Gender.MEN}),
        ),
    ]


def ids(configs: list) -> list[str]:
    return [store.id for store in configs]


def test_a_stated_men_request_skips_the_women_only_store() -> None:
    item = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)

    searched, skipped = stores_for_item(stores(), item)

    assert ids(searched) == ["everyone", "men-only"]
    assert ids(skipped) == ["women-only"]


def test_a_stated_women_request_skips_the_men_only_store() -> None:
    item = make_item_intent(gender=Gender.WOMEN, gender_source=GenderSource.EXPLICIT)

    searched, skipped = stores_for_item(stores(), item)

    assert ids(searched) == ["everyone", "women-only"]
    assert ids(skipped) == ["men-only"]


def test_a_guessed_gender_excludes_no_store() -> None:
    item = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.INFERRED)

    searched, skipped = stores_for_item(stores(), item)

    assert ids(searched) == ["everyone", "women-only", "men-only"]
    assert skipped == []


def test_no_gender_and_unisex_exclude_no_store() -> None:
    unisex = make_item_intent(gender=Gender.UNISEX, gender_source=GenderSource.EXPLICIT)

    assert stores_for_item(stores(), make_item_intent())[1] == []
    assert stores_for_item(stores(), unisex)[1] == []


# --------------------------------------------------------------------------------------------
# Stores follow the item's category
# --------------------------------------------------------------------------------------------


def category_stores() -> list:
    return [
        make_store_config(id="everything", name="Everything"),
        make_store_config(
            id="dresses-only",
            name="Dresses Only",
            search_url_template="https://www.demo-store.example/d?q={query}",
            categories=frozenset({Category.DRESSES}),
        ),
        make_store_config(
            id="tops-and-bottoms",
            name="Tops And Bottoms",
            search_url_template="https://www.demo-store.example/tb?q={query}",
            categories=frozenset({Category.TOPS, Category.BOTTOMS}),
        ),
    ]


def test_a_shoes_item_is_not_searched_at_a_dresses_only_store() -> None:
    item = make_item_intent(category=Category.SHOES)

    searched, skipped = stores_for_item(category_stores(), item)

    assert ids(searched) == ["everything"]
    assert ids(skipped) == ["dresses-only", "tops-and-bottoms"]


def test_a_dresses_item_is_searched_at_the_dresses_only_store() -> None:
    item = make_item_intent(category=Category.DRESSES)

    searched, skipped = stores_for_item(category_stores(), item)

    assert ids(searched) == ["everything", "dresses-only"]
    assert ids(skipped) == ["tops-and-bottoms"]


def test_a_store_that_lists_several_categories_is_searched_for_each_of_them() -> None:
    for category in (Category.TOPS, Category.BOTTOMS):
        searched, _ = stores_for_item(category_stores(), make_item_intent(category=category))

        assert "tops-and-bottoms" in ids(searched)


def test_a_store_must_pass_both_the_category_and_the_gender_check() -> None:
    womens_dresses = make_store_config(
        id="womens-dresses",
        name="Womens Dresses",
        search_url_template="https://www.demo-store.example/wd?q={query}",
        genders=frozenset({Gender.WOMEN}),
        categories=frozenset({Category.DRESSES}),
    )

    def searched_for(category: Category, gender: Gender) -> bool:
        item = make_item_intent(
            category=category, gender=gender, gender_source=GenderSource.EXPLICIT
        )
        return "womens-dresses" in ids(stores_for_item([womens_dresses], item)[0])

    assert searched_for(Category.DRESSES, Gender.WOMEN)
    assert not searched_for(Category.DRESSES, Gender.MEN)  # right garment, wrong audience
    assert not searched_for(Category.SHOES, Gender.WOMEN)  # right audience, wrong garment


def test_a_guessed_gender_does_not_change_the_category_rule() -> None:
    item = make_item_intent(
        category=Category.SHOES, gender=Gender.WOMEN, gender_source=GenderSource.INFERRED
    )

    searched, skipped = stores_for_item(category_stores(), item)

    assert ids(searched) == ["everything"]
    assert ids(skipped) == ["dresses-only", "tops-and-bottoms"]
