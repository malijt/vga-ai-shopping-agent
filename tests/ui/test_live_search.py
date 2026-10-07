"""The page over the REAL search pipeline (plan Phase 15).

Everything between the page and the three boundaries is real: request validation, the store engine
and its extraction (over fake stores served by ``respx``), ranking, the price-range shaper, the
re-run cache. Only the stores' HTTP, OpenAI and the image model are faked, and each is counted, so
a test can say "this change made no store request and no OpenAI call".
"""

from dataclasses import dataclass

import pytest
from streamlit.testing.v1 import AppTest

from app.copy import CATEGORY_LABELS, FLAG_TEXT, NO_RESULTS_HEADLINE, NO_RESULTS_TIPS, STEP_LABELS
from tests.factories import make_image_bytes, make_item_intent, make_understand_result
from tests.fakes import FakeImageRanker, FakeUnderstander
from tests.pipeline.builders import OUTFIT, outfit_understander
from tests.pipeline.world import StoreWorld, store_for
from tests.ui.conftest import InstallLive
from tests.ui.helpers import (
    SEARCH_BUTTON,
    TEXT_BOX,
    link_buttons,
    plain_texts,
    search,
)
from tests.ui.live import LiveSearch
from vga.errors import CallBudgetExceededError, ConfigError, LlmError
from vga.models import (
    Category,
    Flag,
    Gender,
    GenderSource,
    InputType,
    MixPreset,
    SearchResponse,
    Step,
)
from vga.understand.understander import API_KEY_MISSING_MESSAGE

APPLY = "chips_apply"
MIX = "mix_preset"
BLAZER_QUERY = "black oversized blazer"


@dataclass(frozen=True)
class Costs:
    """Everything that costs something, read off the boundaries."""

    store_requests: int
    store_searches: int
    openai_calls: int
    image_model_calls: int


def costs(live: LiveSearch) -> Costs:
    return Costs(
        store_requests=live.store_requests,
        store_searches=len(live.store_searches),
        openai_calls=live.openai_calls,
        image_model_calls=len(live.image_model_calls),
    )


def response_of(at: AppTest) -> SearchResponse:
    response = at.session_state["response"]
    assert isinstance(response, SearchResponse)
    return response


def range_headers(at: AppTest) -> list[str]:
    return [subheader.value for subheader in at.subheader]


def targets(response: SearchResponse, group: int = 0) -> list[int]:
    return [tier.target_count for tier in response.groups[group].tiers]


def usage_line(at: AppTest) -> str:
    return next(
        line
        for text in plain_texts(at)
        for line in text.splitlines()
        if line.startswith("AI calls")
    )


def first_search(at: AppTest, live: LiveSearch, text: str = BLAZER_QUERY) -> AppTest:
    at.run()
    search(at, text)
    assert not at.exception
    return at


# --------------------------------------------------------------------------------------------
# The first search
# --------------------------------------------------------------------------------------------


class TestFirstSearch:
    def test_it_shows_live_results_in_four_price_ranges_with_links_to_the_stores(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()

        first_search(at, live)

        assert [header.split(" · ")[0] for header in range_headers(at)] == [
            "Budget",
            "Mid-range",
            "Premium",
            "Luxury",
        ]
        urls = [button.proto.url for button in link_buttons(at)]
        assert urls
        assert all(
            url.startswith(("https://alpha.example/", "https://beta.example/")) for url in urls
        )
        assert urls == [scored.product.product_url for scored in response_of(at).products]

    def test_it_sends_the_typed_text_as_a_new_search_and_asks_the_model_once(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()

        first_search(at, live)

        assert [call.text for call in live.understander.calls] == [BLAZER_QUERY]
        assert live.understander.calls[0].rerun_of is None
        assert costs(live).store_searches == 2  # one search per store
        assert costs(live).openai_calls == 1

    def test_the_page_is_live_so_it_carries_no_sample_notice(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        install_live()

        at.run()

        assert not at.info

    def test_the_token_use_of_the_search_is_shown(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()

        first_search(at, live)

        assert usage_line(at) == "AI calls: 1. Tokens in: 120, out: 40, total: 160."

    def test_a_second_search_from_the_boxes_is_a_new_search_that_asks_the_model_again(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)

        search(at, "black oversized blazer for women")

        assert costs(live).openai_calls == 2
        assert live.understander.calls[1].rerun_of is None
        assert not at.exception


def run_search_script() -> None:
    """A page that runs one search with the page's own progress display and shows what it drew."""
    import streamlit as st

    from app import runner
    from app.components.status import StepProgress
    from tests.factories import make_search_request

    progress = StepProgress(st.empty())
    runner.run_search(make_search_request(text="black oversized blazer"), None, progress)
    progress.finish()


class TestProgress:
    def test_each_step_the_real_pipeline_reports_is_shown_as_done(
        self, install_live: InstallLive
    ) -> None:
        install_live()

        at = AppTest.from_function(run_search_script, default_timeout=60).run()

        steps = [Step.VALIDATE, Step.UNDERSTAND, Step.SEARCH, Step.FILTER, Step.RANK]
        steps += [Step.SHAPE, Step.ASSEMBLE]
        assert at.text[0].value.splitlines() == [f"Done: {STEP_LABELS[step]}" for step in steps]


# --------------------------------------------------------------------------------------------
# A new mix: re-sorted, nothing asked
# --------------------------------------------------------------------------------------------


class TestAMixChangeAsksNobody:
    def test_it_makes_no_store_request_no_store_search_no_openai_call_and_no_image_call(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = costs(live)
        assert before.store_requests > 0

        at.sidebar.radio(key=MIX).set_value(MixPreset.LUXURY_FIRST).run()

        assert not at.exception
        assert costs(live) == before

    def test_it_re_sorts_the_same_products_into_the_new_shares(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        even = response_of(at)

        at.sidebar.radio(key=MIX).set_value(MixPreset.LUXURY_FIRST).run()

        luxury_first = response_of(at)
        assert luxury_first.request_id != even.request_id
        assert targets(even) == [8, 8, 7, 7]  # 30 results shared evenly
        assert targets(luxury_first) == [3, 6, 9, 12]  # the same 30, luxury first
        assert luxury_first.understood == even.understood

    def test_the_page_shows_the_new_ranges_and_the_cost_of_this_search_as_nothing(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = range_headers(at)

        at.sidebar.radio(key=MIX).set_value(MixPreset.VALUE_FIRST).run()

        assert range_headers(at) != before
        assert usage_line(at) == "AI calls: 0. Tokens in: 0, out: 0, total: 0."

    def test_changing_it_back_and_forth_still_costs_nothing(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = costs(live)

        for preset in (MixPreset.VALUE_FIRST, MixPreset.LUXURY_FIRST, MixPreset.EVEN):
            at.sidebar.radio(key=MIX).set_value(preset).run()

        assert costs(live) == before
        assert not at.exception

    def test_a_mix_picked_before_the_first_search_is_used_by_it(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        at.run()
        at.sidebar.radio(key=MIX).set_value(MixPreset.LUXURY_FIRST).run()
        assert costs(live).store_requests == 0  # nothing to re-sort yet

        search(at, BLAZER_QUERY)

        assert targets(response_of(at))[3] > targets(response_of(at))[0]


# --------------------------------------------------------------------------------------------
# Chip edits: searched again only where the searched item changed, never asking the model
# --------------------------------------------------------------------------------------------


class TestAChipEditAsksTheModelNothing:
    def test_a_budget_alone_makes_no_store_request_and_no_openai_call(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = costs(live)

        at.number_input(key="chip_budget").set_value(200.0).run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert costs(live) == before
        assert response_of(at).understood.budget is not None
        assert response_of(at).understood.budget.max_price == 200.0
        assert any(FLAG_TEXT[Flag.OVER_BUDGET] in text for text in plain_texts(at))

    def test_removing_the_budget_costs_nothing_either(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live(
            FakeUnderstander(make_understand_result(budget={"max_price": 200, "currency": "AED"}))
        )
        first_search(at, live)
        before = costs(live)
        assert any(FLAG_TEXT[Flag.OVER_BUDGET] in text for text in plain_texts(at))

        at.number_input(key="chip_budget").set_value(None).run()
        at.button(key=APPLY).click().run()

        assert costs(live) == before
        assert response_of(at).understood.budget is None
        assert not any(FLAG_TEXT[Flag.OVER_BUDGET] in text for text in plain_texts(at))

    def test_a_changed_colour_searches_the_stores_again_for_that_item_and_asks_no_model(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = costs(live)

        at.text_input(key="chip_0_colour").set_value("navy").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        after = costs(live)
        assert after.openai_calls == before.openai_calls == 1
        assert after.store_searches == before.store_searches + 2  # both stores, the changed item
        assert response_of(at).understood.items[0].colour == "navy"
        assert at.text_input(key="chip_0_colour").value == "navy"  # chips follow the new detection

    def test_a_changed_category_searches_again_and_the_group_follows(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = costs(live)

        at.selectbox(key="chip_0_category").set_value(Category.SHOES).run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert costs(live).openai_calls == before.openai_calls
        assert costs(live).store_searches == before.store_searches + 2
        assert response_of(at).groups[0].category is Category.SHOES

    def test_applying_nothing_changes_nothing_and_costs_nothing(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        before = costs(live)
        earlier = response_of(at)

        at.button(key=APPLY).click().run()

        assert costs(live) == before
        assert response_of(at).groups == earlier.groups

    def test_a_search_again_works_with_the_boxes_emptied_because_it_needs_neither(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        at.text_input(key=TEXT_BOX).set_value("").run()

        at.number_input(key="chip_budget").set_value(250.0).run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert not at.error
        assert response_of(at).understood.budget is not None
        assert costs(live).openai_calls == 1

    def test_the_mix_chosen_in_the_sidebar_travels_with_a_chip_edit(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live()
        first_search(at, live)
        at.sidebar.radio(key=MIX).set_value(MixPreset.LUXURY_FIRST).run()

        at.number_input(key="chip_budget").set_value(300.0).run()
        at.button(key=APPLY).click().run()

        assert targets(response_of(at))[3] > targets(response_of(at))[0]


# --------------------------------------------------------------------------------------------
# A guessed gender is shown, not applied (Rule 8)
# --------------------------------------------------------------------------------------------


GUESSED_MEN = make_understand_result(
    items=[
        make_item_intent(
            gender=Gender.MEN,
            gender_source=GenderSource.INFERRED,
            search_keywords=[BLAZER_QUERY],
        )
    ]
)


class TestAGuessedGenderIsNotAppliedUntilTheShopperPicksIt:
    @pytest.fixture
    def stores(self) -> list:
        return [
            store_for("alpha"),
            store_for("beta", genders=[Gender.MEN]),
            store_for("gamma", genders=[Gender.WOMEN]),
        ]

    def test_the_chip_is_empty_and_the_guess_is_explained(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_MEN), stores=stores)

        first_search(at, live)

        assert at.selectbox(key="chip_0_gender").value == "unset"
        shown = " ".join(markdown.value for markdown in at.markdown)
        assert "not confirmed. The AI guessed Men" in shown
        assert any(
            "Gender (men) was guessed by the AI and is not applied until you confirm it." in text
            for text in plain_texts(at)
        )

    def test_every_store_is_searched_while_the_guess_is_unconfirmed(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_MEN), stores=stores)

        first_search(at, live)

        searched = {store for call in live.store_searches for store in call.store_ids}
        assert searched == {"alpha", "beta", "gamma"}
        assert {report.store_id for report in response_of(at).stores_used} == searched

    def test_choosing_the_gender_leaves_out_the_stores_that_do_not_sell_for_it_and_says_so(
        self, at: AppTest, install_live: InstallLive, stores: list
    ) -> None:
        live = install_live(FakeUnderstander(GUESSED_MEN), stores=stores)
        first_search(at, live)

        at.selectbox(key="chip_0_gender").set_value("men").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert live.openai_calls == 1
        searched_again = {store for call in live.store_searches[3:] for store in call.store_ids}
        assert "gamma" not in searched_again
        skipped = {report.store_id: report.reason for report in response_of(at).stores_skipped}
        assert skipped == {"gamma": "Not searched: Gamma does not sell clothing for men."}
        expander = next(item for item in at.expander if item.label.startswith("Skipped stores"))
        assert (
            expander.text[0].value == "gamma: Not searched: Gamma does not sell clothing for men."
        )
        assert at.selectbox(key="chip_0_gender").value == "men"


# --------------------------------------------------------------------------------------------
# An outfit: one group per garment
# --------------------------------------------------------------------------------------------


class TestAnOutfitIsShownGarmentByGarment:
    def test_four_garments_make_four_groups_with_four_price_ranges_each(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live(outfit_understander())

        first_search(at, live, "the whole outfit")

        headings = [h.value for h in at.header if h.value.startswith("Item ")]
        assert headings == [
            f"Item {position}: {CATEGORY_LABELS[item.category]}"
            for position, item in enumerate(OUTFIT, start=1)
        ]
        assert len(range_headers(at)) == 16
        assert len({button.key for button in link_buttons(at)}) == len(link_buttons(at))
        assert [group.category for group in response_of(at).groups] == [
            item.category for item in OUTFIT
        ]

    def test_the_chips_have_a_unique_label_for_every_garment(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live(outfit_understander())

        first_search(at, live, "the whole outfit")

        labels = [box.label for box in at.selectbox] + [box.label for box in at.text_input]
        assert len(set(labels)) == len(labels)
        assert "Item 4 category" in labels
        assert "Item 4 colour" in labels

    def test_changing_one_garment_searches_the_stores_again_for_that_garment_only(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live(outfit_understander())
        first_search(at, live, "the whole outfit")
        before = costs(live)
        calls_before = len(live.store_searches)

        at.text_input(key="chip_1_colour").set_value("navy").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert costs(live).openai_calls == before.openai_calls == 1
        again = live.store_searches[calls_before:]
        assert {call.category for call in again} == {Category.TOPS}
        assert len(again) == 2  # the changed garment, once per store; the other three are reused
        assert len(response_of(at).groups) == 4

    def test_a_mix_change_re_sorts_every_garment_and_asks_nobody(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        live = install_live(outfit_understander())
        first_search(at, live, "the whole outfit")
        before = costs(live)

        at.sidebar.radio(key=MIX).set_value(MixPreset.VALUE_FIRST).run()

        assert costs(live) == before
        assert len(range_headers(at)) == 16


# --------------------------------------------------------------------------------------------
# Warnings, skipped stores and errors
# --------------------------------------------------------------------------------------------


class TestWarningsAndSkippedStores:
    def test_a_store_that_refused_is_listed_with_its_reason_and_named_in_the_notes(
        self, at: AppTest, install_live: InstallLive, world: StoreWorld
    ) -> None:
        live = install_live(stores=[store_for("alpha"), store_for("beta")])
        world.sites["alpha"].status = 403

        first_search(at, live)

        skipped = response_of(at).stores_skipped
        assert [report.store_id for report in skipped] == ["alpha"]
        expander = next(item for item in at.expander if item.label.startswith("Skipped stores"))
        assert expander.text[0].value == (
            "alpha: This store did not allow the search, so we skipped it."
        )
        assert any(
            "Alpha was skipped because it did not allow the search." in text
            for text in plain_texts(at)
        )
        assert range_headers(at)  # the other store still gave results

    def test_a_photo_search_without_image_similarity_says_so(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        photo_search = FakeUnderstander(
            make_understand_result(input_type=InputType.PHOTO_TEXT, items=[make_item_intent()])
        )
        install_live(photo_search, image_ranker=FakeImageRanker(error=RuntimeError("model gone")))
        at.run()
        at.file_uploader(key="photo_upload").set_value(
            ("look.jpg", make_image_bytes("JPEG", (64, 64)), "image/jpeg")
        ).run()

        at.button(key=SEARCH_BUTTON).click().run()

        assert not at.exception
        assert any("because image similarity was not available" in t for t in plain_texts(at))
        assert range_headers(at)  # the results are still there, ranked without the photo

    def test_the_notes_never_show_the_error_text_of_a_failed_part(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        secret = "model gone: secret internal detail"
        photo_search = FakeUnderstander(
            make_understand_result(input_type=InputType.PHOTO_TEXT, items=[make_item_intent()])
        )
        install_live(photo_search, image_ranker=FakeImageRanker(error=RuntimeError(secret)))
        at.run()
        at.file_uploader(key="photo_upload").set_value(
            ("look.jpg", make_image_bytes("JPEG", (64, 64)), "image/jpeg")
        ).run()
        at.button(key=SEARCH_BUTTON).click().run()

        assert "secret internal detail" not in " ".join(plain_texts(at))


class TestNoResults:
    def test_when_every_store_refuses_the_page_says_why_for_each_and_what_to_try(
        self, at: AppTest, install_live: InstallLive, world: StoreWorld
    ) -> None:
        live = install_live(stores=[store_for("alpha"), store_for("beta")])
        world.sites["alpha"].status = 403
        world.sites["beta"].status = 429

        first_search(at, live)

        assert NO_RESULTS_HEADLINE in [header.value for header in at.header]
        texts = "\n".join(plain_texts(at))
        assert "alpha: This store did not allow the search, so we skipped it." in texts
        assert "beta: This store did not allow the search, so we skipped it." in texts
        tips = " ".join(markdown.value for markdown in at.markdown)
        assert all(tip in tips for tip in NO_RESULTS_TIPS)
        assert not at.subheader
        assert "Stores searched: 2. 0 returned products, 2 skipped." in plain_texts(at)

    def test_the_pipelines_own_notes_are_shown_too(
        self, at: AppTest, install_live: InstallLive, world: StoreWorld
    ) -> None:
        live = install_live(stores=[store_for("alpha")])
        world.sites["alpha"].status = 403

        first_search(at, live)

        notes = next(
            node for node in at.get("container") if getattr(node, "key", None) == "result_notes"
        )
        shown = "\n".join(text.value for text in notes.text)
        assert "- Alpha was skipped because it did not allow the search." in shown
        assert "- No results right now: every store we tried was skipped" in shown

    def test_no_enabled_store_is_explained_instead_of_an_empty_page(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        install_live(stores=[])

        at.run()
        search(at)

        assert NO_RESULTS_HEADLINE in [header.value for header in at.header]
        assert any("No stores are set up to search right now" in text for text in plain_texts(at))


class TestFriendlyErrors:
    @pytest.mark.parametrize(
        "error",
        [LlmError(), CallBudgetExceededError(), ConfigError(API_KEY_MISSING_MESSAGE)],
        ids=["model failed", "daily limit", "no key"],
    )
    def test_a_plain_error_from_the_pipeline_shows_only_its_user_message(
        self, at: AppTest, install_live: InstallLive, error: Exception
    ) -> None:
        install_live(FakeUnderstander(error=error))
        at.run()

        search(at)

        assert len(at.error) == 1
        assert error.args[0] in plain_texts(at)
        assert not at.exception
        assert at.button(key=SEARCH_BUTTON).disabled is False
        assert at.text_input(key=TEXT_BOX).value == "black oversized blazer for men under 400 AED"

    def test_a_bug_in_the_model_step_is_a_plain_message_with_none_of_its_text(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        secret = "boom: secret internal detail at db.internal:5432"
        install_live(FakeUnderstander(error=RuntimeError(secret)))
        at.run()

        search(at)

        assert LlmError.default_message in plain_texts(at)
        page = " ".join(plain_texts(at))
        for leaked in ("secret internal detail", "db.internal", "Traceback", "RuntimeError"):
            assert leaked not in page
