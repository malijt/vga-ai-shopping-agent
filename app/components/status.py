"""Status the shopper sees: progress while a search runs, errors, and notes about the results.

Progress comes from the pipeline's ``Step`` enum (plan 13.1.2). Each line starts with a word
(``Done`` or ``In progress``), so the state never depends on colour or an icon alone. Errors show
a short headline and then the message as plain text: a ``VgaError.user_message`` is written by our
code, but nothing here trusts that enough to hand it to a function that reads markdown.
"""

from collections.abc import Sequence

import streamlit as st
from app.copy import ERROR_HEADLINE, STEP_LABELS
from app.safe_text import plain_text
from streamlit.delta_generator import DeltaGenerator

from vga.models import Step

WARNING_MAX_CHARS = 300


def progress_lines(steps: Sequence[Step], *, finished: bool) -> list[str]:
    """One line per step seen so far. The newest is "In progress" until the search finishes."""
    lines: list[str] = []
    for position, step in enumerate(steps):
        is_last = position == len(steps) - 1
        state = "In progress" if is_last and not finished else "Done"
        lines.append(f"{state}: {STEP_LABELS[step]}")
    return lines


class StepProgress:
    """A callback for ``run_search(on_step=...)`` that shows each step as it starts."""

    def __init__(self, placeholder: DeltaGenerator) -> None:
        self._placeholder = placeholder
        self._steps: list[Step] = []

    def __call__(self, step: Step) -> None:
        self._steps.append(step)
        self._draw(finished=False)

    def finish(self) -> None:
        self._draw(finished=True)

    def _draw(self, *, finished: bool) -> None:
        self._placeholder.text("\n".join(progress_lines(self._steps, finished=finished)))


def render_error(message: str) -> None:
    """Show an error: a headline, then the plain-language message and what to do next."""
    st.error(ERROR_HEADLINE)
    st.text(message)


def render_notes(warnings: Sequence[str]) -> None:
    """Show the pipeline's warnings about this result list. They can name stores or repeat the
    shopper's words, so each is plain text."""
    if not warnings:
        return
    with st.container(border=True, key="result_notes"):
        st.markdown("**Notes about these results**")
        st.text("\n".join(f"- {plain_text(note, WARNING_MAX_CHARS)}" for note in warnings))
