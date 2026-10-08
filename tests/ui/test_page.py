"""The page as a whole (plan 10.1.1): it starts, says what it is, and uses the shopper's words."""

import re

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Markdown

from app import runner
from app.copy import (
    APP_TITLE,
    EXAMPLE_QUERIES,
    NOTE_AI,
    NOTE_DEMO,
    NOTE_PHOTO,
    SETUP_HEADLINE,
)
from tests.fakes import FakePipeline
from tests.ui.helpers import SEARCH_BUTTON, TEXT_BOX, nodes, plain_texts, search, visible_strings
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
