"""The page's one error boundary (plan 10.1.4).

Anything that goes wrong while the page runs ends up here. A ``VgaError`` shows its
``user_message``; any other exception shows the generic message from ``vga.errors``. The traceback
goes to the log, with the request id when a search was running, and never to the browser. The
shopper's text and photo stay in their boxes: they are widgets the page already drew.

If a search was running, the page reruns so the buttons come back and the message shows near the
input. If the error came from drawing the page itself, the message is shown where it happened and
the stored results are dropped, so the next interaction starts clean instead of failing again.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from app import state
from app.components.status import render_error
from vga.errors import user_message_for
from vga.log import get_logger

log = get_logger(__name__)


@contextmanager
def error_boundary() -> Iterator[None]:
    """Wrap the page body. Streamlit's own control flow (``st.rerun``, ``st.stop``) is not an
    ``Exception`` and passes straight through."""
    try:
        yield
    except Exception as exc:
        log.exception(
            "page error",
            extra={"request_id": state.active_request_id(), "error_type": type(exc).__name__},
        )
        message = user_message_for(exc)
        if state.record_error(message):
            st.rerun()
        state.drop_response()
        render_error(message)
