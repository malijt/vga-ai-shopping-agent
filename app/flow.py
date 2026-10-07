"""What happens after the shopper presses "Search stores" or "Apply changes and search again".

A button press only records a pending search (``state.request_search``, in the button's
``on_click``). The page then redraws with every control disabled, and ``run_pending_search`` runs
the search while the progress shows. When it finishes the page reruns to show the results with the
controls enabled again. That is how the buttons are disabled "while a search runs" in Streamlit,
where a script cannot change a widget it has already drawn.
"""

import streamlit as st

from app import runner, state
from app.components.input_panel import InputState
from app.components.status import StepProgress
from vga.errors import InvalidInputError
from vga.models import RunOverrides, SearchRequest, SettingsOverride


def build_request(inputs: InputState) -> SearchRequest:
    """The request for what is in the input panel. Refuses input the panel already rejected."""
    if not inputs.is_valid:
        raise InvalidInputError()
    return SearchRequest(text=inputs.text, image=inputs.photo)


def build_overrides(pending: state.PendingSearch, settings: SettingsOverride) -> RunOverrides:
    """The sidebar's price-range mix. For a search again also the chip edits, the earlier detection
    (so the pipeline need not call OpenAI again) and the photo's embedding (A8)."""
    response = state.get_response()
    if pending.chips is None or response is None:
        return RunOverrides(settings=settings)
    return RunOverrides(
        settings=settings,
        chips=pending.chips,
        understood=response.understood,
        query_embedding=response.query_embedding,
    )


def run_pending_search(inputs: InputState, settings: SettingsOverride) -> None:
    """Run the pending search, if there is one, then rerun the page with the result.

    Errors are not handled here: they go to the page's one error boundary, which shows them and
    brings the buttons back. The shopper's text and photo stay in their boxes either way.
    """
    pending = state.pending_search()
    if pending is None:
        return
    request = build_request(inputs)
    state.set_active_request_id(request.request_id)
    overrides = build_overrides(pending, settings)

    with st.status("Working on your search", expanded=True) as status:
        progress = StepProgress(st.empty())
        response = runner.run_search(request, overrides, progress)
        progress.finish()
        status.update(label="Search finished", state="complete", expanded=False)

    state.store_response(response)
    st.rerun()
