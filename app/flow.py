"""What happens after the shopper presses "Search stores", "Apply changes and search again", or
changes the price-range mix once results are on the page.

A button press only records a pending search (``state.request_search``, in the button's
``on_click``). The page then redraws with every control disabled, and ``run_pending_search`` runs
the search while the progress shows. When it finishes the page reruns to show the results with the
controls enabled again. That is how the buttons are disabled "while a search runs" in Streamlit,
where a script cannot change a widget it has already drawn.

Two kinds of search:

- A new search is built from the boxes: the description and the photo.
- A search again is built from the last response. It carries no text and no photo: the earlier
  detection (with the chip edits on top) and the photo's embedding travel in the overrides instead
  (assumption A8). The pipeline then asks OpenAI nothing, and asks the stores again only for a
  garment whose searched item changed.
"""

import streamlit as st

from app import runner, state
from app.components.input_panel import InputState
from app.components.status import StepProgress
from vga.errors import InvalidInputError
from vga.models import RunOverrides, SearchRequest, SearchResponse, SettingsOverride

MESSAGE_NOTHING_TO_SEARCH_AGAIN = (
    "The earlier results are no longer on the page, so there is nothing to search again. "
    "Add a photo or a description and press Search stores."
)


def build_request(
    pending: state.PendingSearch, inputs: InputState, earlier: SearchResponse | None
) -> SearchRequest:
    """The request for a pending search. Refuses input the panel already rejected."""
    if pending.chips is not None:
        if earlier is None:
            raise InvalidInputError(MESSAGE_NOTHING_TO_SEARCH_AGAIN, detail="no earlier response")
        return SearchRequest(rerun_of=earlier.request_id)
    if not inputs.is_valid:
        raise InvalidInputError()
    return SearchRequest(text=inputs.text, image=inputs.photo)


def build_overrides(
    pending: state.PendingSearch, settings: SettingsOverride, earlier: SearchResponse | None
) -> RunOverrides:
    """The sidebar's price-range mix. For a search again also the chip edits, the earlier detection
    (so the pipeline need not call OpenAI again) and the photo's embedding (A8)."""
    if pending.chips is None or earlier is None:
        return RunOverrides(settings=settings)
    return RunOverrides(
        settings=settings,
        chips=pending.chips,
        understood=earlier.understood,
        query_embedding=earlier.query_embedding,
    )


def run_pending_search(inputs: InputState, settings: SettingsOverride) -> None:
    """Run the pending search, if there is one, then rerun the page with the result.

    Errors are not handled here: they go to the page's one error boundary, which shows them and
    brings the buttons back. The shopper's text and photo stay in their boxes either way.
    """
    pending = state.pending_search()
    if pending is None:
        return
    earlier = state.get_response()
    request = build_request(pending, inputs, earlier)
    state.set_active_request_id(request.request_id)
    overrides = build_overrides(pending, settings, earlier)

    with st.status("Working on your search", expanded=True) as status:
        progress = StepProgress(st.empty())
        response = runner.run_search(request, overrides, progress)
        progress.finish()
        status.update(label="Search finished", state="complete", expanded=False)

    state.store_response(response, keep_chips=pending.keep_chips)
    if pending.chips is not None:
        state.note_gender_choices(pending.chips)
    else:
        # A new search may ask who it is for again, whatever was answered for the last one, and
        # nothing was chosen on the page for it yet.
        state.reopen_gender_question()
        state.forget_gender_choices()
        # A new search used the photo, if there was one. It is done with: let go of it.
        state.set_photo_released(request.image is not None)
        if request.image is not None:
            state.release_photo()
    st.rerun()
