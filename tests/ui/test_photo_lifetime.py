"""The photo's lifetime (plan 15.1.2, BRD Rule 4, and the owner's exception of 2026-10-08).

The upload is sent with the first search and then let go. After a search nothing the page
remembers holds the original, and a search again works from the photo's embedding (a list of
numbers), never from the photo. One thing of the photo stays: a small preview (at most 512 pixels,
a new JPEG with no metadata) that is drawn with the results until the page is refreshed or a new
search starts (ADR 0005, update). It is made once, kept in the session only, and goes with the
results it belongs to.
"""

import io
import logging
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from app import runner
from app.components.input_panel import MESSAGE_PHOTO_USED, message_too_large
from app.copy import SUMMARY_HEADING, SUMMARY_NO_PHOTO_COPY
from app.photo_preview import PREVIEW_MAX_EDGE_PX
from app.state import PendingSearch
from tests.factories import (
    load_sample_response,
    make_image_bytes,
    make_item_intent,
    make_understand_result,
)
from tests.fakes import FakePipeline, FakeUnderstander
from tests.guards.privacy.jpeg import PICTURE_ONLY, names_of, segments_of
from tests.guards.privacy.photos import PrivatePhoto, make_private_photo
from tests.guards.privacy.traces import find, forms_of, signs_of_an_image, traces_of_photo
from tests.guards.privacy.watch import RawLogs, Watch
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
        """ "The photo" is the upload itself: its bytes, as they were sent. What the page keeps
        instead is a different, re-encoded picture (``TestThePreview``)."""
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

    def test_the_shopper_is_told_the_photo_was_used_and_that_only_a_small_copy_stays(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()
        assert MESSAGE_PHOTO_USED not in markdown_values(at)

        upload(at, photo)

        assert MESSAGE_PHOTO_USED in markdown_values(at)
        assert "small copy stays on this page" in MESSAGE_PHOTO_USED
        assert "refresh the page or start a new search" in MESSAGE_PHOTO_USED
        assert "Nothing is saved" in MESSAGE_PHOTO_USED
        assert "removed" not in MESSAGE_PHOTO_USED  # it would no longer be the whole truth

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


# --------------------------------------------------------------------------------------------
# The preview that stays (owner's decision 2026-10-08, ADR 0005 update)
# --------------------------------------------------------------------------------------------


@pytest.fixture
def noisy_photo() -> PrivatePhoto:
    """A large photo that hides a marker in its EXIF block, GPS position, colour profile, XMP
    packet, comment and trailing bytes. Noise, so no piece of it is in any other file."""
    return make_private_photo(
        "JPEG", size=(900, 700), carriers={"exif", "gps", "icc", "xmp", "comment", "tail"}
    )


def preview_in(at: AppTest) -> bytes:
    preview = at.session_state["photo_preview"]
    assert isinstance(preview, bytes)
    return preview


def has_summary(at: AppTest) -> bool:
    return SUMMARY_HEADING in [header.value for header in at.header]


def opened(jpeg: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(jpeg))
    image.load()
    return image


class TestThePreview:
    def test_after_a_photo_search_the_session_holds_a_preview_and_not_the_original(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto
    ) -> None:
        at.run()

        upload(at, noisy_photo.data)

        preview = preview_in(at)
        assert preview != noisy_photo.data
        assert not session_holds_bytes(at, noisy_photo.data)
        for trace in traces_of_photo(noisy_photo.data, noisy_photo.marker):
            assert not session_holds_bytes(at, trace.needle), trace.label

    def test_the_scan_would_notice_the_preview_if_it_were_there(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto
    ) -> None:
        # The check above only means something if the same scan finds the preview, which the
        # session does hold.
        at.run()
        upload(at, noisy_photo.data)

        assert session_holds_bytes(at, preview_in(at))

    def test_the_preview_is_at_most_512_pixels_on_its_longest_side(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto
    ) -> None:
        at.run()

        upload(at, noisy_photo.data)

        width, height = opened(preview_in(at)).size
        assert max(width, height) == PREVIEW_MAX_EDGE_PX == 512
        assert (width, height) != (900, 700)

    def test_the_preview_carries_no_exif_gps_profile_or_comment(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto
    ) -> None:
        picture = Image.open(io.BytesIO(noisy_photo.data))
        assert picture.getexif().get_ifd(0x8825), "the test photo must carry a GPS position"
        assert noisy_photo.marker in noisy_photo.data
        at.run()

        upload(at, noisy_photo.data)

        preview = preview_in(at)
        shown = opened(preview)
        assert dict(shown.getexif()) == {}
        assert not shown.getexif().get_ifd(0x8825)
        assert not {"icc_profile", "exif", "xmp", "comment"} & set(shown.info)
        assert noisy_photo.marker not in preview
        extra = [
            n for n in names_of(segments_of(preview)) if n not in names_of(sorted(PICTURE_ONLY))
        ]
        assert extra == []

    def test_it_stays_with_the_results_through_every_kind_of_search_again(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto
    ) -> None:
        at.run()
        upload(at, noisy_photo.data)
        kept = preview_in(at)

        at.button(key=APPLY).click().run()
        assert preview_in(at) == kept
        assert has_summary(at)

        at.sidebar.radio(key="mix_preset").set_value(MixPreset.VALUE_FIRST).run()
        assert preview_in(at) == kept
        assert has_summary(at)

        at.button(key="gender_women").click().run()  # the answer to "Who is this for?"
        assert len(pipeline.calls) == 4
        assert preview_in(at) == kept
        assert has_summary(at)
        assert not session_holds_bytes(at, noisy_photo.data)

    def test_a_new_search_with_another_photo_replaces_it(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        first = make_image_bytes("JPEG", (300, 200), (200, 10, 10))
        second = make_image_bytes("JPEG", (300, 200), (10, 10, 200))
        at.run()
        upload(at, first)
        before = preview_in(at)

        upload(at, second)

        after = preview_in(at)
        assert after != before
        assert opened(before).getpixel((50, 50))[0] > 150  # red
        assert opened(after).getpixel((50, 50))[2] > 150  # blue

    def test_a_new_search_without_a_photo_removes_it_and_the_block_that_shows_it(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()
        upload(at, photo, "black blazer")
        assert has_summary(at)

        at.button(key=SEARCH_BUTTON).click().run()  # the same description, no photo this time

        assert "photo_preview" not in at.session_state
        assert not has_summary(at)
        assert len(at.image) == len(SAMPLE.products)  # only the product pictures are left

    def test_dropping_the_results_removes_it(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        at.run()
        upload(at, photo)
        assert "photo_preview" in at.session_state

        def broken(*_args: object, **_kwargs: object) -> None:
            message = "a store sent something the page cannot draw"
            raise ValueError(message)

        with monkeypatch.context() as breakage:
            breakage.setattr("app.components.chips.render_chips", broken)
            at.run()  # the page fails while drawing the chips and drops the results
        at.run()

        assert at.session_state["response"] is None
        assert "photo_preview" not in at.session_state
        assert not has_summary(at)

    def test_a_new_session_starts_without_one(self, at: AppTest, pipeline: FakePipeline) -> None:
        # What a page refresh gives: a session with nothing in it.
        at.run()

        assert "photo_preview" not in at.session_state
        assert not has_summary(at)

    def test_a_search_that_fails_leaves_the_preview_as_it_was(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        install_pipeline()
        at.run()
        upload(at, photo, "black blazer")
        kept = preview_in(at)
        install_pipeline(error=LlmError())

        at.button(key=SEARCH_BUTTON).click().run()

        assert at.error
        assert preview_in(at) == kept
        assert has_summary(at)

    def test_a_first_search_that_fails_leaves_no_preview(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        install_pipeline(error=LlmError())
        at.run()

        upload(at, photo)

        assert at.error
        assert "photo_preview" not in at.session_state
        assert not has_summary(at)

    def test_a_photo_that_cannot_be_drawn_again_gives_the_results_and_no_preview(
        self,
        at: AppTest,
        pipeline: FakePipeline,
        photo: bytes,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Starts like a PNG, so the page lets it through; it is not a picture. The fake pipeline
        # accepts anything, so the search succeeds and only the preview fails.
        broken = b"\x89PNG\r\n\x1a\n" + b"VGA-PRIVATE-PHOTO not really a picture"
        at.run()
        upload(at, photo)
        assert "photo_preview" in at.session_state

        with caplog.at_level(logging.WARNING):
            upload(at, broken)

        assert not at.exception
        assert not at.error
        assert pipeline.calls[-1].req.image == broken
        assert "photo_preview" not in at.session_state  # the earlier photo's is not left behind
        assert has_summary(at)
        assert SUMMARY_NO_PHOTO_COPY in plain_texts(at)
        warnings = [r for r in caplog.records if "preview" in r.getMessage()]
        assert len(warnings) == 1
        assert "VGA-PRIVATE-PHOTO" not in f"{warnings[0].getMessage()} {warnings[0].__dict__}"

    def test_it_is_not_in_the_response_and_not_sent_to_the_pipeline(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto
    ) -> None:
        at.run()
        upload(at, noisy_photo.data)
        at.button(key=APPLY).click().run()
        preview = preview_in(at)

        assert not holds_bytes(response_of(at), preview)
        assert len(pipeline.calls) == 2
        for call in pipeline.calls:
            assert not holds_bytes(call, preview)
        assert pipeline.calls[0].req.image == noisy_photo.data  # the original went, once
        assert pipeline.calls[1].req.image is None

    def test_it_is_written_to_no_file(
        self, at: AppTest, pipeline: FakePipeline, noisy_photo: PrivatePhoto, tmp_path: Path
    ) -> None:
        at.run()

        with Watch([tmp_path]) as watch:
            upload(at, noisy_photo.data)
            at.button(key=APPLY).click().run()

        preview = preview_in(at)
        outside_the_log = [
            str(opened.path)
            for opened in watch.activity.file_writes
            if (tmp_path / "logs") not in opened.path.parents
        ]
        assert outside_the_log == []
        traces = [
            *traces_of_photo(noisy_photo.data, noisy_photo.marker),
            *forms_of(preview, "preview"),
        ]
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert find(path.read_bytes(), traces) == [], str(path)


class TestThePreviewWithTheRealPipeline:
    """The preview next to the real validation, hand-off to the model and re-run cache."""

    def test_a_chip_edit_changes_the_summary_and_keeps_the_same_preview(
        self, at: AppTest, install_live: InstallLive, noisy_photo: PrivatePhoto
    ) -> None:
        install_live(TestWithTheRealPipeline.photo_search())
        at.run()
        upload(at, noisy_photo.data, "black oversized blazer")
        kept = preview_in(at)
        assert any("Colour: black." in text for text in plain_texts(at))

        chip_colour(at, 0).set_value("navy").run()
        at.button(key=APPLY).click().run()

        assert not at.exception
        assert preview_in(at) == kept
        assert any("Colour: navy." in text for text in plain_texts(at))
        assert not any("Colour: black." in text for text in plain_texts(at))
        assert not session_holds_bytes(at, noisy_photo.data)

    def test_the_log_calls_of_a_search_with_a_photo_hold_no_image_bytes(
        self,
        at: AppTest,
        install_live: InstallLive,
        noisy_photo: PrivatePhoto,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The app's own level at DEBUG, so every log call the page and the pipeline make is made
        # (and seen by the watch), then a search with a photo and a search again.
        monkeypatch.setenv("VGA_LOG_LEVEL", "DEBUG")
        install_live(TestWithTheRealPipeline.photo_search())
        at.run()

        with RawLogs() as logs:
            upload(at, noisy_photo.data, "black oversized blazer")
            chip_colour(at, 0).set_value("navy").run()
            at.button(key=APPLY).click().run()

        assert not at.exception
        preview = preview_in(at)
        text = "\n".join(logs.lines)
        assert len(logs.lines) > 5, "the check means nothing if the search logged nothing"
        traces = [
            *traces_of_photo(noisy_photo.data, noisy_photo.marker),
            *forms_of(preview, "preview"),
        ]
        assert find(text, traces) == []
        assert signs_of_an_image(text) == []
