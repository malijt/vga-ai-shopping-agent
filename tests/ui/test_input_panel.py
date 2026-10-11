"""The input panel (plan 10.1.2): what can be searched, what is refused, and what survives."""

import pytest
from streamlit.testing.v1 import AppTest

from app import runner
from app.components.input_panel import (
    ALLOWED_PHOTO_TYPES,
    MAX_PHOTO_MB,
    MESSAGE_WRONG_TYPE,
    InputState,
    check_photo,
    message_too_large,
    sniff_image_kind,
)
from app.copy import NOTE_PHOTO
from tests.factories import make_image_bytes
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import PHOTO, SEARCH_BUTTON, TEXT_BOX, search
from vga.errors import InvalidInputError
from vga.models import MAX_TEXT_CHARS


def search_button(at: AppTest):
    return at.button(key=SEARCH_BUTTON)


class TestSearchButton:
    def test_an_empty_submit_is_impossible_because_the_button_starts_disabled(
        self, at: AppTest
    ) -> None:
        at.run()

        assert search_button(at).disabled is True
        assert search_button(at).label == "Search stores"

    def test_typing_a_description_enables_the_button(self, at: AppTest) -> None:
        at.run()

        at.text_input(key=TEXT_BOX).set_value("black blazer").run()

        assert search_button(at).disabled is False

    @pytest.mark.parametrize("blank", ["", " ", "   \n\t  "])
    def test_blank_text_does_not_count_as_input(self, at: AppTest, blank: str) -> None:
        at.run()

        at.text_input(key=TEXT_BOX).set_value(blank).run()

        assert search_button(at).disabled is True

    def test_clearing_the_text_disables_the_button_again(self, at: AppTest) -> None:
        at.run()
        at.text_input(key=TEXT_BOX).set_value("black blazer").run()

        at.text_input(key=TEXT_BOX).set_value("").run()

        assert search_button(at).disabled is True

    @pytest.mark.parametrize(
        ("fmt", "filename", "mime"),
        [
            ("PNG", "look.png", "image/png"),
            ("JPEG", "look.jpg", "image/jpeg"),
            ("WEBP", "look.webp", "image/webp"),
        ],
    )
    def test_a_photo_alone_is_enough(self, at: AppTest, fmt: str, filename: str, mime: str) -> None:
        at.run()

        at.file_uploader(key=PHOTO).set_value((filename, make_image_bytes(fmt), mime)).run()

        assert search_button(at).disabled is False
        assert not at.error

    def test_the_controls_are_disabled_while_a_search_runs(self) -> None:
        def script() -> None:
            from app.components.input_panel import render_input_panel

            render_input_panel(disabled=True, max_photo_bytes=8_000_000)

        at = AppTest.from_function(script).run()

        assert at.button(key=SEARCH_BUTTON).disabled is True
        assert at.text_input(key=TEXT_BOX).disabled is True
        assert at.file_uploader(key=PHOTO).disabled is True


class TestDescriptionBox:
    """A one-line box that sends what is typed after a short pause (plan 10.1.2). A text area only
    sends on blur or Ctrl+Enter, so the first click on the still-disabled button was lost."""

    def test_it_is_a_single_line_input_not_a_text_area(self, at: AppTest) -> None:
        at.run()

        assert not at.text_area
        assert at.text_input(key=TEXT_BOX).label == "Description (optional)"

    def test_it_sends_the_text_while_typing_after_a_short_pause(self, at: AppTest) -> None:
        at.run()

        assert 0 < at.text_input(key=TEXT_BOX).proto.live_debounce_ms <= 500

    def test_the_old_confirm_hint_is_gone_because_it_is_no_longer_needed(self, at: AppTest) -> None:
        at.run()

        assert not any("Ctrl+Enter" in markdown.value for markdown in at.markdown)

    def test_the_text_direction_rule_covers_the_box_so_arabic_lines_up(self, at: AppTest) -> None:
        at.run()

        (rule,) = [str(node.proto.body) for node in at.get("html")]
        assert 'input[type="text"]' in rule
        assert "unicode-bidi: plaintext" in rule


class TestPhotoChecks:
    """Streamlit itself refuses a file whose extension is not in the allowed list, before the page
    code runs (the browser shows its own "File type not allowed" next to the uploader). These tests
    cover what gets past that: an allowed extension on content that is not an image."""

    def test_the_uploader_offers_only_png_jpg_and_webp(self, at: AppTest) -> None:
        at.run()

        offered = {kind.lstrip(".").lower() for kind in at.file_uploader(key=PHOTO).allowed_type}

        assert offered == set(ALLOWED_PHOTO_TYPES)

    def test_the_photo_notice_is_next_to_the_uploader(self, at: AppTest) -> None:
        at.run()

        assert NOTE_PHOTO in [markdown.value for markdown in at.markdown]

    def test_the_photo_notice_says_where_the_photo_goes_and_how_long_a_copy_stays(self) -> None:
        # Owner's decision 2026-10-08: a small copy stays on the page. The old sentence ("is not
        # stored by us") would now be untrue, so the notice says what stays, for how long, and
        # that nothing is saved.
        assert "sent to OpenAI" in NOTE_PHOTO
        assert "small copy stays on this page" in NOTE_PHOTO
        assert "refresh the page or start a new search" in NOTE_PHOTO
        assert "do not save your photo" in NOTE_PHOTO
        assert "not stored by us" not in NOTE_PHOTO

    @pytest.mark.parametrize(
        ("filename", "data", "mime"),
        [
            ("renamed.jpg", b"this is text renamed to .jpg", "image/jpeg"),
            ("scan.png", b"%PDF-1.7 a pdf renamed to .png", "image/png"),
            ("empty.png", b"", "image/png"),
            ("moving.webp", b"GIF89a a gif renamed to .webp", "image/webp"),
        ],
    )
    def test_a_file_that_is_not_an_image_shows_a_message_and_blocks_search(
        self, at: AppTest, filename: str, data: bytes, mime: str
    ) -> None:
        at.run()

        at.file_uploader(key=PHOTO).set_value((filename, data, mime)).run()

        assert [error.value for error in at.error] == [MESSAGE_WRONG_TYPE]
        assert search_button(at).disabled is True

    def test_an_oversized_photo_shows_a_message_and_blocks_search(self, at: AppTest) -> None:
        at.run()
        limit = runner.load_ui_settings().max_image_bytes
        too_big = b"\x89PNG\r\n\x1a\n" + b"0" * limit

        at.file_uploader(key=PHOTO).set_value(("big.png", too_big, "image/png")).run()

        assert [error.value for error in at.error] == [message_too_large(limit)]
        assert search_button(at).disabled is True

    def test_the_limit_is_the_one_in_the_settings_not_the_uploaders_outer_limit(
        self, at: AppTest
    ) -> None:
        # 8,100,000 bytes is under the uploader's 8 MB (mebibyte) cap but over the pipeline's
        # max_image_bytes, so the pipeline would refuse it: the page must refuse it first.
        at.run()
        limit = runner.load_ui_settings().max_image_bytes
        between = b"\x89PNG\r\n\x1a\n" + b"0" * (limit + 100_000)
        assert len(between) < MAX_PHOTO_MB * 1024 * 1024

        at.file_uploader(key=PHOTO).set_value(("big.png", between, "image/png")).run()

        assert [error.value for error in at.error] == [message_too_large(limit)]
        assert search_button(at).disabled is True

    def test_the_message_names_the_limit_in_plain_megabytes(self) -> None:
        assert message_too_large(8_000_000) == (
            "That photo is larger than 8 MB. Choose a smaller PNG, JPG or WebP photo."
        )
        assert "2.5 MB" in message_too_large(2_500_000)

    def test_a_bad_photo_blocks_search_even_when_there_is_text(self, at: AppTest) -> None:
        at.run()
        at.text_input(key=TEXT_BOX).set_value("black blazer").run()

        at.file_uploader(key=PHOTO).set_value(("x.jpg", b"hello", "image/jpeg")).run()

        assert search_button(at).disabled is True
        assert at.text_input(key=TEXT_BOX).value == "black blazer"

    def test_a_png_renamed_to_jpg_is_accepted_because_the_bytes_decide_not_the_name(
        self, at: AppTest
    ) -> None:
        at.run()

        at.file_uploader(key=PHOTO).set_value(
            ("really-a-png.jpg", make_image_bytes("PNG"), "image/jpeg")
        ).run()

        assert not at.error
        assert search_button(at).disabled is False

    def test_the_size_cap_matches_the_server_setting(self) -> None:
        import tomllib
        from pathlib import Path

        config = tomllib.loads(
            (Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml").read_text()
        )

        assert config["server"]["maxUploadSize"] == MAX_PHOTO_MB


class TestCheckPhotoUnit:
    @pytest.mark.parametrize(("fmt", "kind"), [("PNG", "png"), ("JPEG", "jpeg"), ("WEBP", "webp")])
    def test_real_images_are_recognised_by_their_first_bytes(self, fmt: str, kind: str) -> None:
        assert sniff_image_kind(make_image_bytes(fmt)) == kind

    @pytest.mark.parametrize("data", [b"", b"GIF89a....", b"RIFF1234WAVE", b"plain text"])
    def test_other_data_is_not_an_image(self, data: bytes) -> None:
        assert sniff_image_kind(data) is None
        assert check_photo(data, 8_000_000) == MESSAGE_WRONG_TYPE

    def test_a_photo_exactly_at_the_cap_is_accepted_and_one_byte_more_is_not(self) -> None:
        cap = 1_000_000
        at_cap = b"\x89PNG\r\n\x1a\n" + b"0" * (cap - 8)

        assert check_photo(at_cap, cap) is None
        assert check_photo(at_cap + b"0", cap) == message_too_large(cap)

    def test_input_needs_text_or_a_photo_and_no_photo_problem(self) -> None:
        assert not InputState().is_valid
        assert InputState(text="blazer").is_valid
        assert InputState(photo=b"x").is_valid
        assert not InputState(text="blazer", photo_error="bad photo").is_valid


class TestInputSurvivesErrors:
    def test_the_text_is_still_there_after_a_failed_search(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(error=InvalidInputError("Please add a clearer description."))
        at.run()

        search(at, "black oversized blazer")

        assert at.text_input(key=TEXT_BOX).value == "black oversized blazer"
        assert search_button(at).disabled is False

    def test_long_text_at_the_limit_is_accepted_by_the_box(self, at: AppTest) -> None:
        at.run()

        assert at.text_input(key=TEXT_BOX).max_chars == MAX_TEXT_CHARS

    def test_arabic_text_round_trips_unchanged(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        arabic = "جاكيت أسود للرجال بأقل من 400 درهم."
        fake = install_pipeline()
        at.run()

        search(at, arabic)

        assert at.text_input(key=TEXT_BOX).value == arabic
        assert fake.calls[-1].req.text == arabic
