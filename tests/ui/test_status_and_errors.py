"""Status and errors (plan 10.1.4 and 10.2.5): progress, empty states, skipped stores, timings,
and the one error boundary that never shows a stack trace.
"""

import logging

import pytest
from app.components.run_details import timing_line
from app.components.status import progress_lines
from app.copy import (
    CATEGORY_LABELS,
    ERROR_HEADLINE,
    GENDER_LABELS,
    NO_RESULTS_HEADLINE,
    NO_RESULTS_TIPS,
    STEP_LABELS,
)
from app.state import PendingSearch
from streamlit.testing.v1 import AppTest

from tests.factories import (
    load_sample_response,
    make_search_response,
    make_store_report,
)
from tests.fakes import FakePipeline
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import SEARCH_BUTTON, TEXT_BOX, plain_texts, search, visible_strings
from vga.errors import GENERIC_USER_MESSAGE, InvalidInputError, LlmError
from vga.models import Category, Gender, Step, StepTiming, StoreStatus

SAMPLE = load_sample_response()
SECRET = "boom: secret internal detail at db.internal:5432"


def expander(at: AppTest, prefix: str):
    return next(item for item in at.expander if item.label.startswith(prefix))


class TestErrorBoundary:
    def test_a_vga_error_shows_its_own_user_message(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(error=LlmError())
        at.run()

        search(at)

        assert [error.value for error in at.error] == [ERROR_HEADLINE]
        assert LlmError.default_message in plain_texts(at)
        assert not at.exception

    def test_any_other_exception_shows_the_generic_message_and_none_of_its_text(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(error=RuntimeError(SECRET))
        at.run()

        search(at)

        assert [error.value for error in at.error] == [ERROR_HEADLINE]
        assert GENERIC_USER_MESSAGE in plain_texts(at)
        assert not at.exception
        page = " ".join(visible_strings(at))
        assert page  # the check below is meaningful: there is page text to search
        for leaked in ("secret internal detail", "db.internal", "Traceback", "RuntimeError"):
            assert leaked not in page

    def test_the_traceback_is_logged_with_the_request_id_not_shown(
        self, at: AppTest, install_pipeline: InstallPipeline, caplog: pytest.LogCaptureFixture
    ) -> None:
        fake = install_pipeline(error=RuntimeError(SECRET))
        at.run()

        with caplog.at_level(logging.ERROR, logger="vga"):
            search(at)

        records = [record for record in caplog.records if record.exc_info]
        assert len(records) == 1
        assert SECRET in caplog.text  # the detail is in the log for the developer
        assert getattr(records[0], "request_id", None) == fake.calls[-1].req.request_id

    def test_the_buttons_come_back_after_an_error(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(error=InvalidInputError())
        at.run()

        search(at)

        assert at.button(key=SEARCH_BUTTON).disabled is False
        assert at.text_input(key=TEXT_BOX).disabled is False

    def test_the_error_goes_away_when_the_next_search_succeeds(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(error=LlmError())
        at.run()
        search(at)
        install_pipeline()

        at.button(key=SEARCH_BUTTON).click().run()

        assert not at.error
        assert at.subheader

    def test_a_pending_search_with_nothing_to_search_shows_the_friendly_input_message(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        # The button cannot be pressed without input, but the page still refuses to send an empty
        # request if a search is pending for any other reason.
        at.run()
        at.session_state["pending_search"] = PendingSearch()

        at.run()

        assert [error.value for error in at.error] == [ERROR_HEADLINE]
        assert InvalidInputError.default_message in plain_texts(at)
        assert not pipeline.calls
        assert at.button(key=SEARCH_BUTTON).disabled is True  # nothing typed, so still blocked

    def test_an_error_while_drawing_the_page_is_caught_too_and_does_not_loop(self) -> None:
        def script() -> None:
            from app.boundary import error_boundary

            with error_boundary():
                message = "secret detail from a rendering bug"
                raise ValueError(message)

        at = AppTest.from_function(script).run()

        assert not at.exception
        assert [error.value for error in at.error] == [ERROR_HEADLINE]
        assert [text.value for text in at.text] == [GENERIC_USER_MESSAGE]
        assert "secret detail" not in " ".join(visible_strings(at))


class TestProgress:
    def test_every_pipeline_step_has_shopper_wording(self) -> None:
        assert set(STEP_LABELS) == set(Step)
        assert all(STEP_LABELS.values())

    def test_the_newest_step_is_in_progress_and_earlier_ones_are_done(self) -> None:
        lines = progress_lines([Step.VALIDATE, Step.UNDERSTAND, Step.SEARCH], finished=False)

        assert lines == [
            "Done: Checking your request",
            "Done: Understanding what you are looking for",
            "In progress: Searching the stores",
        ]

    def test_when_finished_every_step_is_done(self) -> None:
        lines = progress_lines([Step.SEARCH, Step.RANK], finished=True)

        assert all(line.startswith("Done: ") for line in lines)

    def test_state_is_words_not_colour_or_icon(self) -> None:
        lines = progress_lines(list(Step), finished=False)

        assert {line.split(":")[0] for line in lines} == {"Done", "In progress"}

    def test_the_callback_draws_each_step_as_it_arrives(self) -> None:
        def script() -> None:
            import streamlit as st
            from app.components.status import StepProgress

            from vga.models import Step

            progress = StepProgress(st.empty())
            progress(Step.VALIDATE)
            progress(Step.SEARCH)

        at = AppTest.from_function(script).run()

        assert [text.value for text in at.text] == [
            "Done: Checking your request\nIn progress: Searching the stores"
        ]

    def test_the_pipeline_receives_the_progress_callback(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        # The FakePipeline calls on_step for every step; if the page passed no callback, or one
        # that cannot take a Step, the search would fail.
        install_pipeline()
        at.run()

        search(at)

        assert not at.error
        assert not at.exception


class TestSkippedStores:
    def test_a_skipped_store_is_listed_with_its_reason(self, results_at: AppTest) -> None:
        box = expander(results_at, "Skipped stores")

        assert box.label == "Skipped stores (1)"
        assert [text.value for text in box.text] == [
            "desert-denim: This store did not allow the search, so we skipped it."
        ]

    def test_no_skipped_stores_means_no_expander(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(make_search_response())
        at.run()

        search(at)

        assert not [item for item in at.expander if item.label.startswith("Skipped")]

    def test_the_stores_searched_summary_counts_used_and_skipped(self, results_at: AppTest) -> None:
        assert "Stores searched: 5. 4 returned products, 1 skipped." in plain_texts(results_at)


class TestTimingsAndUsage:
    def test_the_expander_lists_time_per_step_and_token_use(self, results_at: AppTest) -> None:
        lines = expander(results_at, "Timings").text[0].value.splitlines()

        assert lines[0] == "Total time: 5.5 s"
        assert "understand: 1.8 s" in lines
        assert "fetch (desert-denim): 0.6 s, blocked" in lines
        assert lines[-1] == "AI calls: 1. Tokens in: 1,850, out: 210, total: 2,060."

    def test_a_timing_line_names_the_store_and_any_problem(self) -> None:
        timing = StepTiming(
            step="fetch", store="gulf-threads", duration_ms=2310.0, status="timeout"
        )

        assert timing_line(timing) == "fetch (gulf-threads): 2.3 s, timeout"


class TestNotesAndEmptyStates:
    def test_the_pipelines_warnings_are_shown_as_notes(self, results_at: AppTest) -> None:
        texts = "\n".join(plain_texts(results_at))

        for warning in SAMPLE.warnings:
            assert f"- {warning}" in texts

    def test_a_search_with_no_results_says_so_with_the_reason_and_what_to_try(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        response = make_search_response(
            groups=[],
            stores_used=[],
            stores_skipped=[
                make_store_report(
                    StoreStatus.TIMEOUT,
                    store_id="slow-store",
                    reason="This store did not respond in time.",
                )
            ],
        )
        install_pipeline(response)
        at.run()

        search(at)

        assert NO_RESULTS_HEADLINE in [header.value for header in at.header]
        assert "slow-store: This store did not respond in time." in "\n".join(plain_texts(at))
        tips = " ".join(markdown.value for markdown in at.markdown)
        assert all(tip in tips for tip in NO_RESULTS_TIPS)
        assert not at.subheader  # no price-range sections for an empty search

    def test_no_results_and_no_skipped_store_still_gives_a_reason(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(make_search_response(groups=[], stores_used=[], stores_skipped=[]))
        at.run()

        search(at)

        assert "No store returned products that match this search." in plain_texts(at)


class TestEveryEnumHasShopperWording:
    def test_every_category_has_a_label(self) -> None:
        assert set(CATEGORY_LABELS) == set(Category)

    def test_every_gender_has_a_label(self) -> None:
        assert set(GENDER_LABELS) == set(Gender)
