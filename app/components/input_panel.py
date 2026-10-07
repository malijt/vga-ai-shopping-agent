"""The input panel: a photo, a one-line description, or both, and the "Search stores" button.

The button is disabled until there is valid input and while a search runs, so an empty or broken
request cannot be sent (prevent the error rather than report it). The browser already limits the
file picker to image types and sizes, but a determined or confused client can send anything, so the
photo is checked again here by its first bytes, not by its file name. The pipeline checks again at
its entry (plan 13.1.1); this check only gives the shopper a message next to the uploader.
"""

from dataclasses import dataclass

import streamlit as st

from app import state
from app.copy import BUTTON_SEARCH, NOTE_PHOTO
from vga.models import MAX_TEXT_CHARS

MAX_PHOTO_MB = 8
"""Largest photo accepted. ``.streamlit/config.toml`` sets the same number for the server."""
ALLOWED_PHOTO_TYPES = ["png", "jpg", "jpeg", "webp"]

TEXT_COMMIT_PAUSE = "250ms"
"""The description box sends what is typed after this pause, so the button enables as soon as the
shopper has typed something. A text area would only send on blur or Ctrl+Enter, and a click on
the still-disabled button would be lost (seen in a browser). A request is short, so one line is
enough."""

MESSAGE_WRONG_TYPE = "That file is not a PNG, JPG or WebP photo. Choose another file."
MESSAGE_TOO_LARGE = (
    f"That photo is larger than {MAX_PHOTO_MB} MB. Choose a smaller PNG, JPG or WebP photo."
)


@dataclass(frozen=True)
class InputState:
    """What the shopper has put in the panel right now."""

    text: str | None = None
    photo: bytes | None = None
    photo_error: str | None = None

    @property
    def is_valid(self) -> bool:
        """True when there is something to search with and nothing wrong with it."""
        return self.photo_error is None and (self.text is not None or self.photo is not None)


def sniff_image_kind(data: bytes) -> str | None:
    """``png``, ``jpeg`` or ``webp`` from the file's first bytes, or ``None`` for anything else."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def check_photo(data: bytes) -> str | None:
    """A plain-language message when the photo cannot be used, else ``None``."""
    if len(data) > MAX_PHOTO_MB * 1024 * 1024:
        return MESSAGE_TOO_LARGE
    if sniff_image_kind(data) is None:
        return MESSAGE_WRONG_TYPE
    return None


def render_input_panel(*, disabled: bool) -> InputState:
    """Draw the panel and return what is in it. ``disabled`` is true while a search runs."""
    photo_column, text_column = st.columns(2, gap="large")

    with photo_column:
        uploaded = st.file_uploader(
            "Photo (optional)",
            type=ALLOWED_PHOTO_TYPES,
            accept_multiple_files=False,
            max_upload_size=MAX_PHOTO_MB,
            key=state.PHOTO_KEY,
            disabled=disabled,
        )
        st.markdown(NOTE_PHOTO)
        photo: bytes | None = None
        photo_error: str | None = None
        if uploaded is not None:
            data = uploaded.getvalue()
            photo_error = check_photo(data)
            photo = None if photo_error else data
        if photo_error:
            st.error(photo_error)

    with text_column:
        raw_text = st.text_input(
            "Description (optional)",
            key=state.TEXT_KEY,
            max_chars=MAX_TEXT_CHARS,
            live=TEXT_COMMIT_PAUSE,
            placeholder="For example: black oversized blazer for men under 400 AED",
            disabled=disabled,
        )
        st.markdown("English or Arabic. Add a photo, a description, or both.")

    inputs = InputState(text=(raw_text or "").strip() or None, photo=photo, photo_error=photo_error)
    st.button(
        BUTTON_SEARCH,
        key=state.SEARCH_KEY,
        type="primary",
        disabled=disabled or not inputs.is_valid,
        on_click=state.request_search,
    )
    return inputs
