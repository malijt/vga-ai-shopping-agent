"""The question "Who is this for?" (BRD Rule 8, plan assumption A3).

A gender the AI only guessed is shown and not applied until the shopper says so. A chip and a note
were too easy to miss: a women's outfit photo also brought men's shoes. When a search has finished
and some garment's gender was guessed or not found, the page asks, above the results, with three
buttons: Women, Men, Show both. Women or Men goes through the chip re-search (no photo, no OpenAI
call); Show both only closes the question.

The page runs over the real pipeline with the three boundaries counted (``tests/ui/live.py``), so
"no OpenAI call" and "no store request" are read off the boundaries, not assumed.
"""

import pytest
from streamlit.testing.v1 import AppTest

from app.components.gender_question import edits_with_gender
from app.copy import GENDER_NOT_STATED, GENDER_QUESTION
from tests.factories import make_chip_edits, make_item_intent, make_understand_result
from tests.fakes import FakeUnderstander
from tests.pipeline.world import store_for
from tests.ui.conftest import InstallLive
from tests.ui.helpers import link_buttons, markdown_bodies, plain_texts, search
from tests.ui.live import LiveSearch
from vga.models import (
    Budget,
    Category,
    ChipEdits,
    Gender,
    GenderSource,
    InputType,
    ItemEdit,
    SearchResponse,
    UnderstandResult,
)

BLAZER_QUERY = "black oversized blazer"
WOMEN, MEN, BOTH = "gender_women", "gender_men", "gender_both"
QUESTION_KEYS = (WOMEN, MEN, BOTH)
MIX = "mix_preset"


def blazer(gender: Gender | None, source: GenderSource) -> UnderstandResult:
    item = make_item_intent(gender=gender, gender_source=source, search_keywords=[BLAZER_QUERY])
    return make_understand_result(items=[item])


GUESSED_WOMEN = blazer(Gender.WOMEN, GenderSource.INFERRED)
NO_GENDER = blazer(None, GenderSource.NONE)
STATED_WOMEN = blazer(Gender.WOMEN, GenderSource.EXPLICIT)


def outfit(first: tuple[Gender | None, GenderSource], second: tuple[Gender | None, GenderSource]):
    """A white shirt and blue jeans, with the given (gender, source) each."""
    shirt = make_item_intent(
        category=Category.TOPS,
        colour="white",
        style="shirt",
        gender=first[0],
        gender_source=first[1],
        search_keywords=["white shirt"],
    )
    jeans = make_item_intent(
        category=Category.BOTTOMS,
        colour="blue",
        style="jeans",
        gender=second[0],
        gender_source=second[1],
        search_keywords=["blue jeans"],
    )
    return make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=[shirt, jeans])


@pytest.fixture
def stores() -> list:
    """alpha sells for everyone, beta only for men, gamma only for women."""
    return [
        store_for("alpha"),
        store_for("beta", genders=[Gender.MEN]),
        store_for("gamma", genders=[Gender.WOMEN]),
    ]


def start(at: AppTest, live: LiveSearch, text: str = BLAZER_QUERY) -> AppTest:
    at.run()
    search(at, text)
    assert not at.exception
    return at


def response_of(at: AppTest) -> SearchResponse:
    response = at.session_state["response"]
    assert isinstance(response, SearchResponse)
    return response


def question_buttons(at: AppTest) -> list:
    return [button for button in at.button if button.key in QUESTION_KEYS]


def asked(at: AppTest) -> bool:
    return bool(question_buttons(at))


def searches_and_calls(live: LiveSearch) -> tuple[int, int]:
    return live.store_requests, live.openai_calls


class TestWhenTheQuestionIsAsked:
    def test_it_is_asked_when_the_ai_guessed_the_gender(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)

        start(at, live)

        assert [button.label for button in question_buttons(at)] == ["Women", "Men", "Show both"]
        assert GENDER_QUESTION in " ".join(markdown_bodies(at))
        assert "The AI guessed women from your description. It has not been applied." in (
            plain_texts(at)
        )

    def test_it_says_where_the_guess_came_from(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        photo = GUESSED_WOMEN.model_copy(update={"input_type": InputType.PRODUCT_PHOTO})
        live = install_live(FakeUnderstander(photo), stores=stores)

        start(at, live)

        assert "The AI guessed women from your photo. It has not been applied." in plain_texts(at)

    def test_it_says_when_the_guess_came_from_a_photo_and_words(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        both = GUESSED_WOMEN.model_copy(update={"input_type": InputType.PHOTO_TEXT})
        live = install_live(FakeUnderstander(both), stores=stores)

        start(at, live)

        assert "The AI guessed women from your photo and description. It has not been applied." in (
            plain_texts(at)
        )

    def test_it_is_asked_when_the_request_names_no_gender(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(NO_GENDER), stores=stores)

        start(at, live)

        assert asked(at)
        assert GENDER_NOT_STATED in plain_texts(at)
        assert not any(text.startswith("The AI guessed") for text in plain_texts(at))

    def test_it_is_not_asked_when_the_shopper_stated_the_gender(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(STATED_WOMEN), stores=stores)

        start(at, live)

        assert not asked(at)
        assert GENDER_QUESTION not in " ".join(markdown_bodies(at))

    def test_it_is_not_asked_when_there_is_nothing_to_show(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        unsold = make_item_intent(search_keywords=["unicorn costume"])
        live = install_live(FakeUnderstander(make_understand_result(items=[unsold])), stores=stores)

        start(at, live, "unicorn costume")

        assert response_of(at).result_count == 0
        assert not asked(at)

    def test_nothing_is_applied_and_the_results_are_shown_under_the_question(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)

        start(at, live)

        # Rule 8: every store was searched, the chip is still empty, and the results are there.
        searched = {store for call in live.store_searches for store in call.store_ids}
        assert searched == {"alpha", "beta", "gamma"}
        assert at.selectbox(key="chip_0_gender").value == "unset"
        assert link_buttons(at)
        page = list(at.main)
        question_at = [getattr(node, "key", None) for node in page].index(WOMEN)
        first_range_at = [getattr(node, "type", "") for node in page].index("subheader")
        assert question_at < first_range_at  # the question comes before the first price range

    def test_the_three_answers_are_ordinary_labelled_buttons_that_a_keyboard_reaches(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)

        start(at, live)

        buttons = question_buttons(at)
        assert [button.key for button in buttons] == list(QUESTION_KEYS)
        assert all(button.label.strip() and not button.disabled for button in buttons)
        # The answer is words on the button, so no status is carried by colour.
        assert len({button.label for button in buttons}) == 3


class TestAnsweringWomenOrMen:
    def test_women_re_searches_without_openai_and_leaves_out_the_stores_that_do_not_sell_for_them(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)
        first_search_count = len(live.store_searches)

        at.button(key=WOMEN).click().run()

        assert not at.exception
        assert live.openai_calls == 1  # the one call of the first search
        searched_again = {
            store for call in live.store_searches[first_search_count:] for store in call.store_ids
        }
        assert "beta" not in searched_again  # beta sells for men only
        skipped = {r.store_id: r.reason for r in response_of(at).stores_skipped}
        assert skipped == {"beta": "Not searched: Beta does not sell clothing for women."}
        assert "Beta" not in {s.product.store for s in response_of(at).products}

    def test_men_leaves_out_the_stores_that_sell_for_women_only(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)

        at.button(key=MEN).click().run()

        assert not at.exception
        assert live.openai_calls == 1
        skipped = {r.store_id: r.reason for r in response_of(at).stores_skipped}
        assert skipped == {"gamma": "Not searched: Gamma does not sell clothing for men."}
        assert "Gamma" not in {s.product.store for s in response_of(at).products}

    def test_the_answer_is_the_shoppers_own_and_the_question_goes_away(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)

        at.button(key=MEN).click().run()

        item = response_of(at).understood.items[0]
        assert (item.gender, item.gender_source) == (Gender.MEN, GenderSource.EXPLICIT)
        assert at.selectbox(key="chip_0_gender").value == "men"  # the guess was women: the choice
        assert not asked(at)
        assert GENDER_QUESTION not in " ".join(markdown_bodies(at))

    def test_a_chip_edit_not_yet_applied_is_not_lost_when_the_shopper_answers(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)
        at.text_input(key="chip_0_colour").set_value("white").run()

        at.button(key=WOMEN).click().run()

        assert not at.exception
        assert response_of(at).understood.items[0].colour == "white"
        assert live.openai_calls == 1

    def test_the_question_does_not_come_back_after_a_later_search_again(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)
        at.button(key=WOMEN).click().run()

        at.text_input(key="chip_0_colour").set_value("navy").run()
        at.button(key="chips_apply").click().run()

        assert not at.exception
        assert not asked(at)


class TestShowBoth:
    def test_it_asks_no_store_and_no_ai_and_changes_nothing(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)
        before = searches_and_calls(live)
        results_before = [s.product.product_url for s in response_of(at).products]

        at.button(key=BOTH).click().run()

        assert not at.exception
        assert searches_and_calls(live) == before
        assert [s.product.product_url for s in response_of(at).products] == results_before
        assert at.selectbox(key="chip_0_gender").value == "unset"  # still not applied
        assert not asked(at)
        assert link_buttons(at)

    def test_it_stays_closed_when_the_price_range_mix_changes(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)
        at.button(key=BOTH).click().run()

        at.sidebar.radio(key=MIX).set_value(at.sidebar.radio(key=MIX).options[-1]).run()

        assert not at.exception
        assert not asked(at)

    def test_a_new_search_asks_again(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_WOMEN), stores=stores)
        start(at, live)
        at.button(key=BOTH).click().run()
        assert not asked(at)

        search(at, "black blazer for the office")

        assert not at.exception
        assert asked(at)
        assert live.openai_calls == 2


class TestAnOutfit:
    GUESS = (Gender.WOMEN, GenderSource.INFERRED)

    def test_two_garments_are_asked_once_and_answered_for_both(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(outfit(self.GUESS, self.GUESS)), stores=stores)
        start(at, live, "the whole outfit")

        assert len(question_buttons(at)) == 3  # one question, not one per garment

        at.button(key=WOMEN).click().run()

        assert not at.exception
        assert live.openai_calls == 1
        items = response_of(at).understood.items
        assert [(i.gender, i.gender_source) for i in items] == [
            (Gender.WOMEN, GenderSource.EXPLICIT)
        ] * 2
        assert at.selectbox(key="chip_0_gender").value == "women"
        assert at.selectbox(key="chip_1_gender").value == "women"
        assert not asked(at)

    def test_a_garment_the_shopper_already_named_keeps_its_gender(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        stated_men = (Gender.MEN, GenderSource.EXPLICIT)
        live = install_live(FakeUnderstander(outfit(stated_men, self.GUESS)), stores=stores)
        start(at, live, "the whole outfit")
        assert asked(at)  # the second garment is still a guess

        at.button(key=WOMEN).click().run()

        assert not at.exception
        genders = [i.gender for i in response_of(at).understood.items]
        assert genders == [Gender.MEN, Gender.WOMEN]
        assert not asked(at)

    def test_it_is_not_asked_when_every_garment_was_named(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        named = (Gender.WOMEN, GenderSource.EXPLICIT)
        live = install_live(FakeUnderstander(outfit(named, named)), stores=stores)

        start(at, live, "the whole outfit")

        assert not asked(at)

    def test_the_guesses_of_two_garments_can_differ_and_the_question_says_so(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        other = (Gender.MEN, GenderSource.INFERRED)
        live = install_live(FakeUnderstander(outfit(self.GUESS, other)), stores=stores)

        start(at, live, "the whole outfit")

        assert asked(at)
        assert "The AI guessed different genders for different items." in " ".join(plain_texts(at))


class TestTheEditsAnAnswerSends:
    """``edits_with_gender``: the gender goes on every garment that is not explicit, on top of
    whatever the chips already hold."""

    def understood(self) -> UnderstandResult:
        return outfit((Gender.MEN, GenderSource.EXPLICIT), (Gender.WOMEN, GenderSource.INFERRED))

    def test_only_garments_that_are_not_explicit_get_the_gender(self) -> None:
        edits = edits_with_gender(self.understood(), ChipEdits(), Gender.WOMEN)

        assert edits.items == [ItemEdit(index=1, gender=Gender.WOMEN)]

    def test_the_chips_other_edits_and_budget_travel_with_it(self) -> None:
        pending = make_chip_edits(
            items=[ItemEdit(index=1, colour="navy"), ItemEdit(index=0, colour="red")],
            budget=Budget(max_price=300, currency="AED"),
        )

        edits = edits_with_gender(self.understood(), pending, Gender.MEN)

        assert edits.items == [
            ItemEdit(index=0, colour="red"),
            ItemEdit(index=1, colour="navy", gender=Gender.MEN),
        ]
        assert edits.budget == Budget(max_price=300, currency="AED")

    def test_the_answer_wins_over_a_gender_chosen_in_the_chip_but_not_applied(self) -> None:
        pending = make_chip_edits(items=[ItemEdit(index=1, gender=Gender.WOMEN)])

        edits = edits_with_gender(self.understood(), pending, Gender.MEN)

        assert edits.items == [ItemEdit(index=1, gender=Gender.MEN)]

    def test_a_removed_budget_stays_removed(self) -> None:
        pending = make_chip_edits(clear_budget=True)

        assert edits_with_gender(self.understood(), pending, Gender.MEN).clear_budget is True
