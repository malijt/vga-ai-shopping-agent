"""The page as a whole (plan 10.1.1): it starts, says what it is, and uses the shopper's words."""

import re

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Markdown

from app import runner
from app.copy import (
    APP_TITLE,
    ERROR_HEADLINE,
    EXAMPLE_QUERIES,
    NO_RESULTS_HEADLINE,
    NOTE_AI,
    NOTE_DEMO,
    NOTE_PHOTO,
    SETUP_HEADLINE,
    SUMMARY_HEADING,
)
from tests.factories import make_image_bytes, make_search_response, make_store_report
from tests.fakes import FakePipeline
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import SEARCH_BUTTON, TEXT_BOX, nodes, plain_texts, search, visible_strings
from tests.ui.scenario import search_with_photo
from vga.errors import LlmError
from vga.models import StoreStatus
from vga.understand.understander import API_KEY_MISSING_MESSAGE, MODEL_NOT_SET_MESSAGE


class TestStartup:
    def test_page_starts_in_fixture_mode_without_any_error(self, at: AppTest) -> None:
        at.run()

        assert not at.exception
        assert [title.value for title in at.title] == [APP_TITLE]

    def test_trust_notes_are_shown_before_any_search(self, at: AppTest) -> None:
        at.run()

        shown = {markdown.value for markdown in at.markdown}
        assert {NOTE_DEMO, NOTE_AI, NOTE_PHOTO} <= shown

    def test_sample_mode_is_announced_so_fixed_results_are_not_mistaken_for_live_ones(
        self, at: AppTest
    ) -> None:
        at.run()

        assert [info.value for info in at.info] == [runner.FIXTURE_NOTICE]

    def test_a_configured_live_page_has_no_example_notice_and_no_setup_message(
        self, at: AppTest, live_mode: None
    ) -> None:
        at.run()

        assert not at.info
        assert not at.error
        assert at.button(key=SEARCH_BUTTON).disabled is True  # only because nothing is typed yet

    def test_without_a_key_the_page_says_what_to_set_up_before_any_search(
        self, at: AppTest, live_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY")

        at.run()

        assert [error.value for error in at.error] == [SETUP_HEADLINE]
        assert API_KEY_MISSING_MESSAGE in plain_texts(at)
        assert not at.exception

    def test_without_a_key_the_search_button_stays_off_even_with_text(
        self, at: AppTest, live_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY")
        at.run()

        at.text_input(key=TEXT_BOX).set_value("black blazer").run()

        assert at.button(key=SEARCH_BUTTON).disabled is True
        assert at.text_input(key=TEXT_BOX).value == "black blazer"  # what was typed is kept

    def test_without_a_model_the_page_says_what_to_set_up(
        self, at: AppTest, live_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        without_model = runner.load_ui_settings().model_copy(update={"openai_model": None})
        monkeypatch.setattr(runner, "load_ui_settings", lambda: without_model)

        at.run()

        assert [error.value for error in at.error] == [SETUP_HEADLINE]
        assert MODEL_NOT_SET_MESSAGE in plain_texts(at)

    def test_fixture_mode_needs_no_key_and_shows_no_setup_message(
        self, at: AppTest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        at.run()

        assert not at.error
        assert [info.value for info in at.info] == [runner.FIXTURE_NOTICE]


class TestWords:
    def test_the_page_says_price_range_and_never_tier(self, results_at: AppTest) -> None:
        shown = " ".join(visible_strings(results_at)).lower()

        assert "price range" in shown
        assert not re.search(r"\btiers?\b", shown)

    def test_buttons_say_what_they_do(self, results_at: AppTest) -> None:
        labels = {button.label for button in results_at.button}

        assert {"Search stores", "Apply changes and search again", "Reset to detected"} <= labels


class TestSafeRendering:
    def test_no_markdown_element_allows_html(self, results_at: AppTest) -> None:
        markdown = [node for node in nodes(results_at) if isinstance(node, Markdown)]

        assert markdown, "the page should contain markdown elements"
        assert not any(node.allow_html for node in markdown)

    def test_the_only_style_rule_is_the_text_direction_rule_and_holds_no_script(
        self, at: AppTest
    ) -> None:
        at.run()

        bodies = [str(node.proto.body) for node in at.get("html")]

        assert len(bodies) == 1
        assert "unicode-bidi: plaintext" in bodies[0]
        assert "<script" not in bodies[0].lower()


class TestEmptyState:
    def test_first_screen_offers_example_queries(self, at: AppTest) -> None:
        at.run()

        examples = [button.label for button in at.button if button.key.startswith("example_")]
        assert examples == list(EXAMPLE_QUERIES)

    def test_one_example_is_arabic(self, at: AppTest) -> None:
        at.run()

        assert any(re.search("[؀-ۿ]", example) for example in EXAMPLE_QUERIES)

    def test_clicking_an_example_fills_the_description_box_and_enables_search(
        self, at: AppTest
    ) -> None:
        at.run()

        at.button(key="example_2").click().run()

        assert at.text_input(key=TEXT_BOX).value == EXAMPLE_QUERIES[2]
        assert at.button(key=SEARCH_BUTTON).disabled is False

    def test_first_screen_disappears_once_there_are_results(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()

        search(at)

        assert not [button for button in at.button if button.key.startswith("example_")]


def position_of(at: AppTest, kind: str, text: str) -> int:
    """Where on the page (top to bottom) the first element of this kind with this text is. The
    text is the element's value or, for a widget, its label."""
    for position, node in enumerate(nodes(at)):
        if getattr(node, "type", "") != kind:
            continue
        if text in (getattr(node, "value", None), getattr(node, "label", None)):
            return position
    msg = f"no {kind} with the text {text!r} on the page"
    raise AssertionError(msg)


def details_position(at: AppTest) -> int:
    """Where the search details start: the line "Stores searched: N. ..."."""
    for position, node in enumerate(nodes(at)):
        if getattr(node, "type", "") == "text" and str(node.value).startswith("Stores searched:"):
            return position
    msg = "no search details on the page"
    raise AssertionError(msg)


class TestPageOrder:
    """Owner's request 2026-10-08: the search details sit at the top, under the summary of the
    photo, not under all the results."""

    def test_with_a_photo_the_order_is_input_summary_details_chips_then_results(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()

        search_with_photo(at, make_image_bytes())

        order = [
            position_of(at, "button", "Search stores"),
            position_of(at, "header", SUMMARY_HEADING),
            details_position(at),
            position_of(at, "header", "Detected by AI"),
            position_of(at, "header", "Item 1: Outerwear"),  # the first group of the results
        ]
        assert order == sorted(order)
        assert len(set(order)) == len(order)

    def test_the_details_sit_directly_under_the_summary_with_nothing_between(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        search_with_photo(at, make_image_bytes())

        start, end = position_of(at, "header", SUMMARY_HEADING), details_position(at)
        between = [getattr(node, "type", "") for node in list(nodes(at))[start + 1 : end]]

        # The summary's own pieces only: its intro, the picture in its column, and its lines.
        assert set(between) <= {"markdown", "flex_container", "column", "image", "text"}
        assert "header" not in between

    def test_with_text_only_the_details_come_right_after_the_input_panel_and_before_the_chips(
        self, results_at: AppTest
    ) -> None:
        order = [
            position_of(results_at, "button", "Search stores"),
            details_position(results_at),
            position_of(results_at, "header", "Detected by AI"),
            position_of(results_at, "header", "Item 1: Outerwear"),
        ]

        assert order == sorted(order)
        assert SUMMARY_HEADING not in [header.value for header in results_at.header]

    def test_the_details_are_no_longer_under_the_results(self, results_at: AppTest) -> None:
        last_price_range = max(
            position
            for position, node in enumerate(nodes(results_at))
            if getattr(node, "type", "") == "subheader"
        )

        assert details_position(results_at) < last_price_range

    def test_the_two_expanders_are_still_there_closed_and_with_their_keys(
        self, results_at: AppTest
    ) -> None:
        expanders = {node.key: node for node in results_at.get("expander")}

        assert set(expanders) == {"skipped_stores", "timings_usage"}
        assert not any(node.proto.expanded for node in expanders.values())

    def test_a_search_with_no_results_has_the_details_at_the_top_too(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(
            make_search_response(
                groups=[],
                stores_used=[],
                stores_skipped=[make_store_report(StoreStatus.BLOCKED, store_id="alpha")],
            )
        )
        at.run()

        search_with_photo(at, make_image_bytes())

        order = [
            position_of(at, "button", "Search stores"),
            position_of(at, "header", SUMMARY_HEADING),
            details_position(at),
            position_of(at, "header", "Detected by AI"),
            position_of(at, "header", NO_RESULTS_HEADLINE),
        ]
        assert order == sorted(order)
        assert len(set(order)) == len(order)
        assert {"skipped_stores", "timings_usage"} <= {n.key for n in at.get("expander")}

    def test_a_search_with_no_results_and_no_photo_has_no_summary_and_the_details_on_top(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(make_search_response(groups=[], stores_used=[], stores_skipped=[]))
        at.run()

        search(at)

        order = [
            position_of(at, "button", "Search stores"),
            details_position(at),
            position_of(at, "header", "Detected by AI"),
            position_of(at, "header", NO_RESULTS_HEADLINE),
        ]
        assert order == sorted(order)

    def test_an_error_stays_directly_under_the_input_panel_above_the_details(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline()
        at.run()
        search(at)
        install_pipeline(error=LlmError())

        at.button(key=SEARCH_BUTTON).click().run()  # fails; the earlier results stay on the page

        assert position_of(at, "button", "Search stores") < position_of(at, "error", ERROR_HEADLINE)
        assert position_of(at, "error", ERROR_HEADLINE) < details_position(at)
