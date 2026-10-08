"""The chips belong to one search (found in a manual test on the real page, 2026-10-08).

A shopper searched with a photo of black abayas, answered "Who is this for?" with Women, then
searched with a photo of red, blue, black and white kaftans. The chips of the second search showed
the first search's colours and gender, a search again then sent those stale values along, and the
gender answer that should have cost nothing started a long store search.

The cause: a chip is a keyed widget, and a browser keeps the value of a keyed widget for as long as
its id stays the same, whatever the page does with its own state. ``tests/ui/browser.py`` gives
``AppTest`` that one browser behaviour, so these tests see what the shopper saw. Everything else is
real: the pipeline, the store engine and the ranking run over fake stores, and the three boundaries
(store requests, OpenAI, the image model) are counted.
"""

import pytest
from streamlit.testing.v1 import AppTest

from tests.ui.helpers import (
    budget_shown,
    chip_category,
    chip_colour,
    chip_count,
    chip_gender,
    chips_shown,
    search,
)
from tests.ui.live import LiveSearch
from tests.ui.scenario import (
    ABAYA_PHOTO,
    APPLY,
    DRESSES,
    KAFTAN_PHOTO,
    MEN,
    NOT_SET,
    WOMEN,
    answer,
    asks_who_it_is_for,
    costs,
    response_of,
    search_with_photo,
)
from vga.models import (
    Category,
    Gender,
    GenderSource,
)


@pytest.fixture
def after_the_abayas_were_answered(at: AppTest, live: LiveSearch) -> AppTest:
    """First search (two black abayas, gender not stated), answered Women."""
    at.run()
    search_with_photo(at, ABAYA_PHOTO)
    assert asks_who_it_is_for(at)
    answer(at, WOMEN)
    return at


class TestANewSearchStartsWithCleanChips:
    def test_the_chips_show_what_the_second_photo_detected_not_what_the_first_search_left(
        self, after_the_abayas_were_answered: AppTest
    ) -> None:
        at = after_the_abayas_were_answered

        search_with_photo(at, KAFTAN_PHOTO)

        assert chips_shown(at) == [
            (DRESSES, "red", NOT_SET),
            (DRESSES, "blue", NOT_SET),
            (DRESSES, "black", NOT_SET),
            (DRESSES, "white", NOT_SET),
        ]
        assert asks_who_it_is_for(at)  # nothing was answered for this search

    def test_the_budget_of_the_first_search_is_not_kept_when_the_second_names_none(
        self, after_the_abayas_were_answered: AppTest
    ) -> None:
        at = after_the_abayas_were_answered
        assert budget_shown(at) == 400.0

        search_with_photo(at, KAFTAN_PHOTO)

        assert budget_shown(at) is None

    def test_a_colour_typed_in_a_chip_and_never_applied_does_not_follow_into_the_next_search(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        chip_colour(at, 0).set_value("navy").run()
        chip_category(at, 1).set_value(Category.SHOES).run()

        search_with_photo(at, KAFTAN_PHOTO)

        assert [colour for _, colour, _ in chips_shown(at)] == [
            "red",
            "blue",
            "black",
            "white",
        ]
        assert {category for category, _, _ in chips_shown(at)} == {DRESSES}

    def test_a_gender_chosen_in_a_chip_and_never_applied_does_not_follow_either(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        chip_gender(at, 0).set_value("men").run()

        search_with_photo(at, KAFTAN_PHOTO)

        assert [gender for _, _, gender in chips_shown(at)] == [NOT_SET] * 4

    def test_a_search_typed_in_words_after_a_photo_search_starts_clean_too(
        self, after_the_abayas_were_answered: AppTest
    ) -> None:
        at = after_the_abayas_were_answered

        search(at, "red, blue, black and white kaftans")

        assert chip_count(at) == 4  # the fake model finds the four kaftans for a typed request
        assert [colour for _, colour, _ in chips_shown(at)] == ["red", "blue", "black", "white"]
        assert [gender for _, _, gender in chips_shown(at)] == [NOT_SET] * 4
        assert budget_shown(at) is None

    def test_the_chips_still_show_what_the_shopper_applied_after_a_search_again(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, KAFTAN_PHOTO)
        chip_colour(at, 0).set_value("navy").run()

        at.button(key=APPLY).click().run()

        assert not at.exception
        assert chip_colour(at, 0).value == "navy"
        assert [colour for _, colour, _ in chips_shown(at)] == [
            "navy",
            "blue",
            "black",
            "white",
        ]


class TestTheGenderAnswerAfterASecondSearchCostsNothing:
    def test_it_makes_no_store_request_and_no_openai_call(
        self, after_the_abayas_were_answered: AppTest, live: LiveSearch
    ) -> None:
        at = after_the_abayas_were_answered
        search_with_photo(at, KAFTAN_PHOTO)
        before = costs(live)

        answer(at, WOMEN)

        assert costs(live) == before

    def test_it_changes_the_gender_of_every_item_and_nothing_else(
        self, after_the_abayas_were_answered: AppTest
    ) -> None:
        at = after_the_abayas_were_answered
        search_with_photo(at, KAFTAN_PHOTO)
        detected = response_of(at).understood.items

        answer(at, WOMEN)

        answered = response_of(at).understood.items
        assert [(i.category, i.colour, i.style, i.material) for i in answered] == [
            (i.category, i.colour, i.style, i.material) for i in detected
        ]
        assert [(i.gender, i.gender_source) for i in answered] == [
            (Gender.WOMEN, GenderSource.EXPLICIT)
        ] * 4
        assert response_of(at).understood.budget is None

    def test_it_costs_nothing_for_men_either(
        self, after_the_abayas_were_answered: AppTest, live: LiveSearch
    ) -> None:
        at = after_the_abayas_were_answered
        search_with_photo(at, KAFTAN_PHOTO)
        before = costs(live)

        answer(at, MEN)

        assert costs(live) == before
        assert {i.gender for i in response_of(at).understood.items} == {Gender.MEN}

    def test_a_search_again_right_after_the_second_search_changes_only_what_was_edited(
        self, after_the_abayas_were_answered: AppTest, live: LiveSearch
    ) -> None:
        at = after_the_abayas_were_answered
        search_with_photo(at, KAFTAN_PHOTO)
        asked_before = len(live.store_searches)

        chip_colour(at, 2).set_value("green").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert [colour for _, colour, _ in chips_shown(at)] == ["red", "blue", "green", "white"]
        assert len(live.store_searches) - asked_before == 2  # the one changed item, two stores
        assert live.openai_calls == 2  # the two photos, nothing for the search again
