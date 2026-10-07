"""Empty states (plan 10.1.2 and 10.2.5): the first screen, and a search that found nothing.

Both say what to try next instead of leaving a dead end.
"""

from collections.abc import Sequence

import streamlit as st
from app import state
from app.copy import EXAMPLE_QUERIES, NO_RESULTS_HEADLINE, NO_RESULTS_TIPS
from app.safe_text import plain_text

from vga.models import SearchResponse, StoreReport

REASON_MAX_CHARS = 200


def use_example(text: str) -> None:
    """``on_click`` of an example: put the query in the description box (the shopper then presses
    "Search stores", so they see what will be searched)."""
    st.session_state[state.TEXT_KEY] = text


def render_welcome(*, disabled: bool) -> None:
    """The first screen: what to do, with example queries to click."""
    st.header("Start your search", anchor=False)
    st.markdown(
        "Add a photo of a garment or an outfit, describe what you want in English or Arabic, "
        "or both. Not sure what to type? Click an example to fill the description box, "
        "then press **Search stores**."
    )
    for index, example in enumerate(EXAMPLE_QUERIES):
        st.button(
            example,
            key=f"example_{index}",
            on_click=use_example,
            args=(example,),
            disabled=disabled,
            width="stretch",
        )


def _skipped_reasons(skipped: Sequence[StoreReport]) -> list[str]:
    return [
        f"- {plain_text(report.store_id, 60)}: {plain_text(report.reason, REASON_MAX_CHARS)}"
        for report in skipped
    ]


def render_no_results(response: SearchResponse) -> None:
    """The search finished but nothing can be shown: say why, and what to try."""
    st.header(NO_RESULTS_HEADLINE, anchor=False)
    reasons = _skipped_reasons(response.stores_skipped)
    st.markdown("**Why**")
    if reasons:
        st.text("\n".join(reasons))
    else:
        st.text("No store returned products that match this search.")
    st.markdown("**What to try**")
    st.markdown("\n".join(f"- {tip}" for tip in NO_RESULTS_TIPS))
