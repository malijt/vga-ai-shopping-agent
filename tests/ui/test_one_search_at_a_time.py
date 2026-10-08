"""What the page remembers belongs to one search (the rest of the stale-chips bug class).

``test_chips_across_searches.py`` covers the chips between two searches. These tests go through
everything else the page keeps or draws from a search, in a browser tab that holds widget values
like a real one (``tests/ui/browser.py``): the "Reset to detected" button, a search again after an
answer, the budget box, "Show both", the photo note, the notes about the results, and the
approximate-price sentence. Each either follows the search on the page or goes with it.
"""

import pytest
from streamlit.testing.v1 import AppTest

from app.components.input_panel import MESSAGE_PHOTO_USED
from app.copy import approximate_price_note
from tests.factories import make_search_response, make_understand_result
from tests.fakes import FakeUnderstander
from tests.ui.conftest import InstallLive, InstallPipeline
from tests.ui.helpers import (
    budget_shown,
    chip_budget,
    chip_category,
    chip_colour,
    chip_gender,
    chips_shown,
    markdown_bodies,
    photo_key,
    plain_texts,
    search,
)
from tests.ui.live import LiveSearch
from tests.ui.scenario import (
    ABAYA_PHOTO,
    APPLY,
    BOTH,
    DRESSES,
    KAFTAN_PHOTO,
    MEN,
    NOT_SET,
    RESET,
    WOMEN,
    answer,
    asks_who_it_is_for,
    costs,
    dress,
    response_of,
    search_with_photo,
)
from tests.ui.test_currencies import mixed_currency_response
from vga.models import Category, Gender, GenderSource

INFERRED_NOTE = "Gender (women) was guessed by the AI and is not applied until you confirm it."


class TestResetToDetected:
    def test_it_puts_back_every_chip_the_shopper_changed(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        detected = (chips_shown(at), budget_shown(at))
        chip_colour(at, 0).set_value("navy").run()
        chip_category(at, 1).set_value(Category.SHOES).run()
        chip_gender(at, 1).set_value("men").run()
        chip_budget(at).set_value(999.0).run()
        assert (chips_shown(at), budget_shown(at)) != detected

        at.button(key=RESET).click().run()

        assert not at.exception
        assert (chips_shown(at), budget_shown(at)) == detected

    def test_a_search_again_after_a_reset_sends_nothing_that_was_reset(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, KAFTAN_PHOTO)
        chip_colour(at, 2).set_value("green").run()
        at.button(key=RESET).click().run()
        before = costs(live)

        at.button(key=APPLY).click().run()

        assert not at.exception
        assert costs(live) == before  # nothing was edited, so no store is asked
        assert [colour for _, colour, _ in chips_shown(at)] == [
            "red",
            "blue",
            "black",
            "white",
        ]


class TestASearchAgainAfterAnAnswer:
    def test_it_keeps_the_answer_and_changes_only_what_was_edited(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        answer(at, WOMEN)
        asked_before = len(live.store_searches)

        chip_colour(at, 0).set_value("navy").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        items = response_of(at).understood.items
        assert [(i.colour, i.gender, i.gender_source) for i in items] == [
            ("navy", Gender.WOMEN, GenderSource.EXPLICIT),
            ("black", Gender.WOMEN, GenderSource.EXPLICIT),
        ]
        assert len(live.store_searches) - asked_before == 2  # the one edited item, two stores
        assert live.openai_calls == 1

    def test_a_second_search_after_an_answer_asks_who_it_is_for_again(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        answer(at, MEN)

        search_with_photo(at, KAFTAN_PHOTO)

        assert asks_who_it_is_for(at)
        assert {i.gender_source for i in response_of(at).understood.items} == {GenderSource.NONE}


class TestTheBudgetBox:
    def test_a_budget_removed_in_the_first_search_does_not_stay_removed_in_the_next(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)  # detects a budget of 400 AED
        chip_budget(at).set_value(None).run()

        search_with_photo(at, ABAYA_PHOTO)

        assert budget_shown(at) == 400.0

    def test_a_budget_typed_in_the_first_search_does_not_follow_into_the_next(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, KAFTAN_PHOTO)  # detects no budget
        chip_budget(at).set_value(250.0).run()

        search_with_photo(at, KAFTAN_PHOTO)

        assert budget_shown(at) is None

    def test_a_search_again_after_the_second_search_sends_no_budget_edit(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)  # budget 400
        search_with_photo(at, KAFTAN_PHOTO)  # no budget
        before = costs(live)

        at.button(key=APPLY).click().run()

        assert response_of(at).understood.budget is None
        assert costs(live) == before


class TestShowBoth:
    def test_it_closes_the_question_for_that_search_only(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        at.button(key=BOTH).click().run()
        assert not asks_who_it_is_for(at)

        search_with_photo(at, KAFTAN_PHOTO)

        assert asks_who_it_is_for(at)

    def test_it_stays_closed_through_a_search_again_of_the_same_search(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        search_with_photo(at, KAFTAN_PHOTO)
        at.button(key=BOTH).click().run()

        chip_colour(at, 0).set_value("green").run()
        at.button(key=APPLY).click().run()

        assert not asks_who_it_is_for(at)


class TestThePhotoNote:
    def test_it_goes_with_the_results_it_is_about(self, at: AppTest, live: LiveSearch) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        assert MESSAGE_PHOTO_USED in markdown_bodies(at)

        search(at, "red kaftans")  # a new search with no photo

        assert MESSAGE_PHOTO_USED not in markdown_bodies(at)

    def test_it_is_not_left_on_a_page_whose_results_were_dropped_after_a_page_error(
        self, at: AppTest, live: LiveSearch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        assert MESSAGE_PHOTO_USED in markdown_bodies(at)

        def broken(*_args: object, **_kwargs: object) -> None:
            message = "a store sent something the page cannot draw"
            raise ValueError(message)

        with monkeypatch.context() as breakage:
            breakage.setattr("app.components.chips.render_chips", broken)
            at.run()  # the page fails while drawing the chips and drops the results
        at.run()

        assert at.session_state["response"] is None
        assert not at.exception
        # "what the AI detected below": there is nothing below any more
        assert MESSAGE_PHOTO_USED not in markdown_bodies(at)


class TestNotesAboutTheResults:
    def test_the_notes_of_the_first_search_do_not_follow_into_the_second(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        guessed = make_understand_result(
            items=[
                dress("black", "abaya", gender=Gender.WOMEN, gender_source=GenderSource.INFERRED)
            ]
        )
        plain = make_understand_result(items=[dress("red", "kaftan")])
        live = install_live(
            FakeUnderstander(lambda req: guessed if req.image == ABAYA_PHOTO else plain)
        )
        at.run()
        search_with_photo(at, ABAYA_PHOTO)
        assert INFERRED_NOTE in " ".join(plain_texts(at))

        search_with_photo(at, KAFTAN_PHOTO)

        assert live.openai_calls == 2
        assert INFERRED_NOTE not in " ".join(plain_texts(at))
        assert chips_shown(at) == [(DRESSES, "red", NOT_SET)]


class TestTheApproximatePriceSentence:
    def test_it_is_said_only_while_the_results_on_the_page_have_such_a_price(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        sentence = approximate_price_note("AED")
        install_pipeline(mixed_currency_response())
        at.run()
        search(at)
        assert sentence in plain_texts(at)

        install_pipeline(make_search_response(understood=make_understand_result()))
        search(at, "black oversized blazer")

        assert sentence not in plain_texts(at)


class TestTheUploader:
    def test_each_photo_search_lets_go_of_its_photo_and_the_next_upload_starts_empty(
        self, at: AppTest, live: LiveSearch
    ) -> None:
        at.run()
        first_key = photo_key(at)
        search_with_photo(at, ABAYA_PHOTO)
        second_key = photo_key(at)

        assert second_key != first_key
        assert at.file_uploader(key=second_key).value is None

        search_with_photo(at, KAFTAN_PHOTO)

        assert photo_key(at) not in (first_key, second_key)
        assert at.file_uploader(key=photo_key(at)).value is None
        assert not at.exception
