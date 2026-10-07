"""Everything the page remembers between Streamlit reruns, behind small named functions.

Streamlit runs the whole script again after each click, so state lives in
``st.session_state``. Keeping the keys and the few operations on them here stops the components
from sharing magic strings.

What is kept: the last response, a pending search (set when a button is pressed, handled later in
the same rerun so the buttons can show as disabled while it runs), and the last error. The
uploaded photo is never copied here: the file uploader widget holds it, and the pipeline decides
how long the bytes live (plan 15.1.2).
"""

from dataclasses import dataclass

import streamlit as st

from vga.models import ChipEdits, SearchResponse

# Widget keys shared between components.
TEXT_KEY = "query_text"
PHOTO_KEY = "photo_upload"
SEARCH_KEY = "search_button"
MIX_KEY = "mix_preset"
SIDEBAR_BUDGET_KEY = "budget_amount"
CHIP_KEY_PREFIX = "chip_"

# Plain state keys.
_PENDING = "pending_search"
_RESPONSE = "response"
_ERROR = "last_error"
_ACTIVE_REQUEST_ID = "active_request_id"


@dataclass(frozen=True)
class PendingSearch:
    """A search the shopper asked for and the page has not run yet.

    ``chips`` is ``None`` for a new search and holds the shopper's edits for a search again.
    """

    chips: ChipEdits | None = None


def pending_search() -> PendingSearch | None:
    value = st.session_state.get(_PENDING)
    return value if isinstance(value, PendingSearch) else None


def is_searching() -> bool:
    return pending_search() is not None


def request_search(chips: ChipEdits | None = None) -> None:
    """Called from a button's ``on_click``: remember the request and forget the last error."""
    st.session_state[_ERROR] = None
    st.session_state[_PENDING] = PendingSearch(chips=chips)


def finish_search() -> None:
    st.session_state[_PENDING] = None
    st.session_state[_ACTIVE_REQUEST_ID] = None


def set_active_request_id(request_id: str) -> None:
    """Remember which request is running so an error can be logged with its id."""
    st.session_state[_ACTIVE_REQUEST_ID] = request_id


def active_request_id() -> str | None:
    value = st.session_state.get(_ACTIVE_REQUEST_ID)
    return value if isinstance(value, str) else None


def get_response() -> SearchResponse | None:
    value = st.session_state.get(_RESPONSE)
    return value if isinstance(value, SearchResponse) else None


def store_response(response: SearchResponse) -> None:
    """Keep a finished search. The chips start again from what this response detected, so any
    value the shopper edited in the chips of the previous response is dropped here."""
    st.session_state[_RESPONSE] = response
    st.session_state[_ERROR] = None
    clear_chip_state()
    finish_search()


def drop_response() -> None:
    st.session_state[_RESPONSE] = None
    clear_chip_state()


def last_error() -> str | None:
    value = st.session_state.get(_ERROR)
    return value if isinstance(value, str) else None


def record_error(message: str) -> bool:
    """Remember an error message for the next run. Returns whether a search was in progress
    (the caller then reruns the page so the buttons come back)."""
    was_searching = is_searching()
    st.session_state[_ERROR] = message
    finish_search()
    return was_searching


def clear_chip_state() -> None:
    """Forget the values in the chip widgets so they show what the response detected."""
    for key in [k for k in st.session_state if str(k).startswith(CHIP_KEY_PREFIX)]:
        del st.session_state[key]
