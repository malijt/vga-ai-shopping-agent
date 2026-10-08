"""Everything the page remembers between Streamlit reruns, behind small named functions.

Streamlit runs the whole script again after each click, so state lives in
``st.session_state``. Keeping the keys and the few operations on them here stops the components
from sharing magic strings.

What is kept: the last response, a pending search (set when a button is pressed, handled later in
the same rerun so the buttons can show as disabled while it runs), and the last error.

The uploaded photo is never copied here. Only the file uploader widget holds it, and once a search
that used it has finished the page drops it: the uploader is given a new key, so Streamlit lets go
of the old widget and the file with it (BRD Rule 4, plan 15.1.2). What stays for a search again is
the response, which carries the photo's embedding (a list of numbers, assumption A8) and never the
photo.
"""

from dataclasses import dataclass

import streamlit as st

from vga.models import ChipEdits, SearchResponse

# Widget keys shared between components.
TEXT_KEY = "query_text"
PHOTO_KEY = "photo_upload"
SEARCH_KEY = "search_button"
MIX_KEY = "mix_preset"
CHIP_KEY_PREFIX = "chip_"

# Plain state keys.
_PENDING = "pending_search"
_RESPONSE = "response"
_ERROR = "last_error"
_ACTIVE_REQUEST_ID = "active_request_id"
_PHOTO_GENERATION = "photo_generation"
_PHOTO_RELEASED = "photo_released"
_GENDER_DISMISSED = "gender_question_dismissed"
_CHIPS_GENERATION = "chips_generation"


@dataclass(frozen=True)
class PendingSearch:
    """A search the shopper asked for and the page has not run yet.

    ``chips`` is ``None`` for a new search from the boxes. It is set for a search again from the
    last response, and holds the shopper's chip edits (empty when only the price-range mix
    changed). ``keep_chips`` is true when the shopper's unapplied chip edits must survive the
    answer, which is the case when only the price-range mix changed.
    """

    chips: ChipEdits | None = None
    keep_chips: bool = False


def pending_search() -> PendingSearch | None:
    value = st.session_state.get(_PENDING)
    return value if isinstance(value, PendingSearch) else None


def is_searching() -> bool:
    return pending_search() is not None


def is_changing_mix() -> bool:
    """True while the pending search is only the price-range mix changing."""
    pending = pending_search()
    return pending is not None and pending.keep_chips


def request_search(chips: ChipEdits | None = None) -> None:
    """Called from a button's ``on_click``: remember the request and forget the last error."""
    st.session_state[_ERROR] = None
    st.session_state[_PENDING] = PendingSearch(chips=chips)


def request_mix_change() -> None:
    """Called when the price-range mix changes. With results on the page, show the same results
    in the new mix: a search again with no chip edits, which asks no store and no AI. With no
    results yet there is nothing to change; the next search reads the mix."""
    if get_response() is None:
        return
    st.session_state[_ERROR] = None
    st.session_state[_PENDING] = PendingSearch(chips=ChipEdits(), keep_chips=True)


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


def store_response(response: SearchResponse, *, keep_chips: bool = False) -> None:
    """Keep a finished search. The chips start again from what this response detected, so any
    value the shopper edited in the chips of the previous response is dropped here, unless
    ``keep_chips`` says the detection did not change."""
    st.session_state[_RESPONSE] = response
    st.session_state[_ERROR] = None
    if not keep_chips:
        clear_chip_state()
    finish_search()


def drop_response() -> None:
    st.session_state[_RESPONSE] = None
    clear_chip_state()
    reopen_gender_question()


def gender_question_dismissed() -> bool:
    """True once the shopper answered "Show both" for the search on the page. Answering Women or
    Men needs no flag: the gender is then explicit and the question has nothing left to ask."""
    return st.session_state.get(_GENDER_DISMISSED) is True


def dismiss_gender_question() -> None:
    st.session_state[_GENDER_DISMISSED] = True


def reopen_gender_question() -> None:
    """A new search from the boxes asks again, if it needs to. A search again from the chips or
    the price-range mix does not: it is the same search."""
    st.session_state[_GENDER_DISMISSED] = False


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


def chips_generation() -> int:
    value = st.session_state.get(_CHIPS_GENERATION, 0)
    return value if isinstance(value, int) else 0


def chip_key(name: str) -> str:
    """The widget key of one chip, for the chips that are on the page now: ``chip_g2_0_colour``.

    The number after ``g`` is the generation of the chips. Streamlit gives a keyed widget an id
    made from its key, and a browser keeps the value it holds for an id, whatever default the
    page gives the widget later. Deleting the key from the session state does not change that.
    The only way to make the chips show a new detection is to give them new ids: every time the
    chips are to start again, the generation goes up, so every chip is a new widget."""
    return f"{CHIP_KEY_PREFIX}g{chips_generation()}_{name}"


def clear_chip_state() -> None:
    """Start the chips again from what the response on the page detected: a new generation, so
    new widgets (see ``chip_key``), and the old generation's values are dropped."""
    st.session_state[_CHIPS_GENERATION] = chips_generation() + 1
    for key in [k for k in st.session_state if str(k).startswith(CHIP_KEY_PREFIX)]:
        del st.session_state[key]


# --- The uploaded photo (plan 15.1.2) --------------------------------------------------------


def _generation() -> int:
    value = st.session_state.get(_PHOTO_GENERATION, 0)
    return value if isinstance(value, int) else 0


def photo_key() -> str:
    """The uploader's current widget key. The first one is ``PHOTO_KEY`` itself; each time the
    photo is released the number at the end goes up, which is a different widget to Streamlit."""
    generation = _generation()
    return PHOTO_KEY if generation == 0 else f"{PHOTO_KEY}_{generation}"


def release_photo() -> None:
    """Let go of the uploaded photo: the uploader gets a new key, so its old widget, and the file
    it held, are no longer kept. Nothing is copied before: only the response keeps the embedding."""
    old_key = photo_key()
    st.session_state[_PHOTO_GENERATION] = _generation() + 1
    st.session_state.pop(old_key, None)


def set_photo_released(released: bool) -> None:
    """Remember whether the results on the page came from a photo that has since been removed."""
    st.session_state[_PHOTO_RELEASED] = released


def photo_released() -> bool:
    return st.session_state.get(_PHOTO_RELEASED) is True
