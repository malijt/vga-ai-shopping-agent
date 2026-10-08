"""What the AI saw in the shopper's photo: the reference photo beside a plain-language summary.

Shown under the input panel when the results on the page came from a search that used a photo (the
"Detected by AI" chips say the same for a text search, so none is drawn then). It adds no model
call and no prompt: every line is composed from the ``UnderstandResult`` the response already holds,
one line per garment, in the shopper's words::

    Item 1: Dresses and ethnic wear. Colour: dark teal. Style: long open-front abaya with a
    matching scarf. Material: crepe. Likely for: women (a guess, not applied).

A part the AI did not find is left out. A gender that was only guessed is said to be a guess that
is not applied (BRD Rule 8); one the shopper stated or confirmed is said plainly.

Everything the model returned derives from the shopper's photo and words, so it is untrusted: each
value goes through ``plain_text`` with a length cap and is drawn with ``st.text``, which reads
neither markdown nor HTML. Only the fixed phrases from ``app.copy`` go to ``st.markdown``. The
photo is the small preview from ``app.photo_preview`` (the owner's decision of 2026-10-08, ADR 0005
update), drawn at a fixed width with a visible caption and a text alternative of its own.
"""

import streamlit as st

from app.copy import (
    CATEGORY_LABELS,
    GENDER_LABELS,
    SUMMARY_GUESS_NOT_APPLIED,
    SUMMARY_HEADING,
    SUMMARY_INTRO,
    SUMMARY_LABEL_BUDGET,
    SUMMARY_LABEL_COLOUR,
    SUMMARY_LABEL_EDITS,
    SUMMARY_LABEL_GENDER_GUESSED,
    SUMMARY_LABEL_GENDER_STATED,
    SUMMARY_LABEL_MATERIAL,
    SUMMARY_LABEL_STYLE,
    SUMMARY_NO_PHOTO_COPY,
    SUMMARY_PHOTO_ALT,
    SUMMARY_PHOTO_CAPTION,
)
from app.safe_text import plain_text
from vga.models import Budget, GenderSource, ItemIntent, UnderstandResult
from vga.money import format_amount

CONTAINER_KEY = "search_summary"
PREVIEW_WIDTH_PX = 160
"""The width the preview is drawn at. The stored copy is larger (``app.photo_preview``); this keeps
the photo modest next to the text."""

COLOUR_MAX_CHARS = 60
STYLE_MAX_CHARS = 120
MATERIAL_MAX_CHARS = 60
EDIT_MAX_CHARS = 80
"""The caps for colour, style and material are the contract's own limits (``ItemIntent``), applied
again here because the page does not rely on a model's answer having been checked. The contract
sets none for a change asked for, so 80 is the page's own."""


def _sentence(*parts: str) -> str:
    """The parts joined into sentences: ``Tops. Colour: red.`` A part's own closing full stop is
    dropped first, so a value that ends in one does not give two."""
    return ". ".join(part.rstrip(".") for part in parts) + "."


def gender_part(item: ItemIntent) -> str | None:
    """``Likely for: women (a guess, not applied)`` for a guess, ``For: women`` when the shopper
    stated or confirmed it, and nothing when no gender was found."""
    if item.gender is None:
        return None
    gender = GENDER_LABELS[item.gender].lower()
    if item.gender_source is GenderSource.INFERRED:
        return f"{SUMMARY_LABEL_GENDER_GUESSED}: {gender} ({SUMMARY_GUESS_NOT_APPLIED})"
    return f"{SUMMARY_LABEL_GENDER_STATED}: {gender}"


def item_line(position: int, item: ItemIntent) -> str:
    """One garment in words: ``Item 2: Shoes. Colour: white. Style: low-top leather sneakers.``"""
    parts = [CATEGORY_LABELS[item.category]]
    for label, value, limit in (
        (SUMMARY_LABEL_COLOUR, item.colour, COLOUR_MAX_CHARS),
        (SUMMARY_LABEL_STYLE, item.style, STYLE_MAX_CHARS),
        (SUMMARY_LABEL_MATERIAL, item.material, MATERIAL_MAX_CHARS),
    ):
        text = plain_text(value, limit)
        if text:
            parts.append(f"{label}: {text}")
    gender = gender_part(item)
    if gender:
        parts.append(gender)
    return f"Item {position}: {_sentence(*parts)}"


def budget_line(budget: Budget) -> str:
    """``Budget: up to 400 AED.`` The currency is a checked three-letter code."""
    amount = format_amount(budget.max_price, budget.currency)
    return _sentence(f"{SUMMARY_LABEL_BUDGET}: up to {amount} {budget.currency}")


def edits_line(edits: list[str]) -> str | None:
    """``Changes you asked for: dark brown; cheaper.`` or nothing when there are none."""
    shown = [text for text in (plain_text(edit, EDIT_MAX_CHARS) for edit in edits) if text]
    if not shown:
        return None
    return _sentence(f"{SUMMARY_LABEL_EDITS}: {'; '.join(shown)}")


def summary_lines(understood: UnderstandResult) -> list[str]:
    """The summary, one line per garment, then the budget and the changes asked for if any."""
    lines = [item_line(position, item) for position, item in enumerate(understood.items, start=1)]
    if understood.budget is not None:
        lines.append(budget_line(understood.budget))
    changes = edits_line(understood.edits)
    if changes:
        lines.append(changes)
    return lines


def _render_lines(understood: UnderstandResult) -> None:
    for line in summary_lines(understood):
        st.text(line)


def render_search_summary(understood: UnderstandResult, preview: bytes | None) -> None:
    """Draw the photo (when a preview was kept) beside what the AI understood from it."""
    with st.container(border=True, key=CONTAINER_KEY):
        st.header(SUMMARY_HEADING, anchor=False)
        st.markdown(SUMMARY_INTRO)
        if preview is None:
            st.text(SUMMARY_NO_PHOTO_COPY)
            _render_lines(understood)
            return
        photo_column, text_column = st.columns([1, 3], gap="large")
        with photo_column:
            st.image(
                preview,
                caption=SUMMARY_PHOTO_CAPTION,
                width=PREVIEW_WIDTH_PX,
                alt=SUMMARY_PHOTO_ALT,
            )
        with text_column:
            _render_lines(understood)
