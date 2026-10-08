"""The photo's lifetime (plan 15.1.2, BRD Rule 4): it is sent with the first search and then let
go. After a search nothing the page remembers holds it, and a search again works from the
photo's embedding (a list of numbers), never from the photo.
"""

import pytest
from streamlit.testing.v1 import AppTest

from app import runner
from app.components.input_panel import MESSAGE_PHOTO_USED, message_too_large
from app.state import PendingSearch
from tests.factories import (
    load_sample_response,
    make_image_bytes,
    make_item_intent,
    make_understand_result,
)
from tests.fakes import FakePipeline, FakeUnderstander
from tests.ui.conftest import InstallLive, InstallPipeline
from tests.ui.helpers import (
    PHOTO,
    SEARCH_BUTTON,
    TEXT_BOX,
    chip_colour,
    holds_bytes,
    photo_key,
    plain_texts,
    session_holds_bytes,
)
from vga.errors import LlmError
from vga.models import InputType, MixPreset, SearchResponse

APPLY = "chips_apply"
EMBEDDING = [0.25, -0.5, 0.75]
SAMPLE = load_sample_response()


@pytest.fixture
def photo() -> bytes:
    return make_image_bytes("JPEG", (64, 64), (10, 120, 200))


def upload(at: AppTest, photo: bytes, text: str | None = None) -> AppTest:
    """Choose a photo (and optionally type a description), then press "Search stores"."""
    at.file_uploader(key=photo_key(at)).set_value(("look.jpg", photo, "image/jpeg")).run()
    if text is not None:
        at.text_input(key=TEXT_BOX).set_value(text).run()
    at.button(key=SEARCH_BUTTON).click().run()
    return at


def markdown_values(at: AppTest) -> list[str]:
    return [markdown.value for markdown in at.markdown]


def response_of(at: AppTest) -> SearchResponse:
    response = at.session_state["response"]
    assert isinstance(response, SearchResponse)
    return response


class TestThePhotoIsSentOnceAndThenLetGo:
    def test_the_first_search_sends_the_photo_to_the_pipeline(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()

        upload(at, photo)

        assert pipeline.calls[-1].req.image == photo

    def test_after_the_search_the_uploader_is_empty_and_has_a_new_key(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()
        key_before = photo_key(at)

        upload(at, photo)

        assert photo_key(at) != key_before
        assert at.file_uploader(key=photo_key(at)).value is None
        assert key_before not in at.session_state

    def test_after_the_search_nothing_the_page_remembers_holds_the_photo(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()

        upload(at, photo, "black blazer")

        assert not session_holds_bytes(at, photo)

    def test_the_scan_would_notice_a_photo_if_one_were_kept(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        # The check above is only worth something if it can fail: with the photo still in the
        # uploader (before the search) it must find it.
        at.run()
        at.file_uploader(key=PHOTO).set_value(("look.jpg", photo, "image/jpeg")).run()

        assert session_holds_bytes(at, photo)
        assert holds_bytes({"deep": [("x", photo)]}, photo)
        assert not holds_bytes({"deep": [("x", b"other")]}, photo)

    def test_the_stored_response_keeps_the_embedding_and_no_photo(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        install_pipeline(SAMPLE.model_copy(update={"query_embedding": EMBEDDING}))
        at.run()

        upload(at, photo)

        assert at.session_state["response"].query_embedding == EMBEDDING
        assert not session_holds_bytes(at, photo)

    def test_a_search_again_after_a_photo_search_sends_the_embedding_and_no_photo(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        fake = install_pipeline(SAMPLE.model_copy(update={"query_embedding": EMBEDDING}))
        at.run()
        upload(at, photo)

        at.button(key=APPLY).click().run()
        at.sidebar.radio(key="mix_preset").set_value(MixPreset.VALUE_FIRST).run()

        assert len(fake.calls) == 3
        for call in fake.calls[1:]:
            assert call.req.image is None
            assert call.overrides is not None
            assert call.overrides.query_embedding == EMBEDDING
        assert not session_holds_bytes(at, photo)

    def test_a_text_only_search_leaves_the_uploader_alone(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        key_before = photo_key(at)

        at.text_input(key=TEXT_BOX).set_value("black blazer").run()
        at.button(key=SEARCH_BUTTON).click().run()

        assert photo_key(at) == key_before

    def test_a_search_that_fails_keeps_the_photo_so_the_shopper_can_try_again(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        install_pipeline(error=LlmError())
        at.run()
        key_before = photo_key(at)

        upload(at, photo)

        assert at.error
        assert photo_key(at) == key_before
        assert at.file_uploader(key=key_before).value is not None
        assert at.button(key=SEARCH_BUTTON).disabled is False

    def test_the_shopper_is_told_the_photo_was_used_and_removed(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()
        assert MESSAGE_PHOTO_USED not in markdown_values(at)

        upload(at, photo)

        assert MESSAGE_PHOTO_USED in markdown_values(at)

    def test_the_note_goes_away_with_the_next_search_that_used_no_photo(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()
        upload(at, photo, "black blazer")

        at.button(key=SEARCH_BUTTON).click().run()  # same description, now without a photo

        assert pipeline.calls[-1].req.image is None
        assert MESSAGE_PHOTO_USED not in markdown_values(at)

    def test_a_second_photo_is_sent_and_let_go_in_the_same_way(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        second = make_image_bytes("PNG", (32, 32), (200, 10, 10))
        at.run()
        upload(at, photo)

        upload(at, second)

        assert pipeline.calls[-1].req.image == second
        assert not session_holds_bytes(at, photo)
        assert not session_holds_bytes(at, second)


class TestThePhotoSizeLimitIsEnforcedBeforeThePipelineIsCalled:
    def test_a_photo_over_the_limit_in_the_settings_never_reaches_the_pipeline(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        limit = runner.load_ui_settings().max_image_bytes
        too_big = b"\x89PNG\r\n\x1a\n" + b"0" * limit
        at.file_uploader(key=PHOTO).set_value(("big.png", too_big, "image/png")).run()
        # Even if a search were pending for some other reason, the page refuses to send it.
        at.session_state["pending_search"] = PendingSearch()

        at.run()

        assert not pipeline.calls
        assert message_too_large(limit) in [error.value for error in at.error]
        assert not at.exception


class TestWithTheRealPipeline:
    """Real validation, hand-off to the model, image step and re-run cache; only the boundaries
    are faked."""

    @staticmethod
    def photo_search() -> FakeUnderstander:
        return FakeUnderstander(
            make_understand_result(
                input_type=InputType.PHOTO_TEXT, items=[make_item_intent()], budget=None
            )
        )

    def test_the_photo_reaches_the_model_once_and_the_page_holds_only_numbers_afterwards(
        self, at: AppTest, install_live: InstallLive, photo: bytes
    ) -> None:
        live = install_live(self.photo_search())
        at.run()

        upload(at, photo, "black oversized blazer")

        assert not at.exception
        assert [call.image for call in live.understander.calls] == [photo]
        assert [call.had_photo for call in live.image_model_calls] == [True]
        assert at.session_state["response"].query_embedding == [0.1, 0.2, 0.3]
        assert not session_holds_bytes(at, photo)
        assert at.file_uploader(key=photo_key(at)).value is None

    def test_a_chip_edit_after_a_photo_search_uses_the_embedding_not_the_photo(
        self, at: AppTest, install_live: InstallLive, photo: bytes
    ) -> None:
        live = install_live(self.photo_search())
        at.run()
        upload(at, photo, "black oversized blazer")

        chip_colour(at, 0).set_value("navy").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        last = live.image_model_calls[-1]
        assert (last.had_photo, last.had_embedding) == (False, True)
        assert live.openai_calls == 1
        assert not session_holds_bytes(at, photo)

    def test_a_photo_only_search_can_be_edited_with_no_text_and_no_photo_left(
        self, at: AppTest, install_live: InstallLive, photo: bytes
    ) -> None:
        # The case the plan calls out (13.1.5 / A8): after a photo-only search there is neither
        # text nor photo to send, and the chip edit must still work.
        live = install_live(self.photo_search())
        at.run()
        upload(at, photo)
        assert live.understander.calls[0].text is None

        chip_colour(at, 0).set_value("navy").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert not at.error
        assert response_of(at).understood.items[0].colour == "navy"
        assert live.openai_calls == 1
        assert [call.had_photo for call in live.image_model_calls] == [True, False]

    def test_a_mix_change_after_a_photo_search_does_not_touch_the_image_model_again(
        self, at: AppTest, install_live: InstallLive, photo: bytes
    ) -> None:
        live = install_live(self.photo_search())
        at.run()
        upload(at, photo, "black oversized blazer")
        model_calls = len(live.image_model_calls)

        at.sidebar.radio(key="mix_preset").set_value(MixPreset.LUXURY_FIRST).run()

        assert len(live.image_model_calls) == model_calls
        assert "AI calls: 0" in " ".join(plain_texts(at))

    def test_the_pipeline_refuses_an_unreadable_photo_with_its_own_plain_message(
        self, at: AppTest, install_live: InstallLive
    ) -> None:
        # A photo the page lets through by its first bytes but that is not a picture.
        install_live(self.photo_search())
        broken = b"\x89PNG\r\n\x1a\n" + b"not really a picture"
        at.run()

        upload(at, broken)

        assert at.error
        assert any("couldn't read that photo" in text for text in plain_texts(at))
        assert not at.exception
