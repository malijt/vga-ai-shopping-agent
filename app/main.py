"""The shopping page: layout only. Logic lives in ``app.components`` and ``app.flow``.

Run from the repository root:  ``uv run streamlit run app/main.py``  (add ``VGA_UI_FIXTURE=1`` to
see the page with sample results; there is no live search connected yet).

Page order, top to bottom: title and trust notes, the input panel, any error, what the AI
detected (chips), the search itself while it runs, then the results or the first-screen help.
"""
# ruff: noqa: E402  (the repository root is put on sys.path before the app imports below)

import sys
from pathlib import Path

# `streamlit run app/main.py` puts only this folder on the import path, so `import app...` needs
# the repository root added first. Harmless when it is already there (pytest, AppTest).
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

from app import flow, runner, state
from app.boundary import error_boundary
from app.components.chips import render_chips
from app.components.empty_state import render_no_results, render_welcome
from app.components.groups import render_groups
from app.components.input_panel import render_input_panel
from app.components.run_details import render_run_details
from app.components.sidebar import render_sidebar
from app.components.status import render_error, render_notes
from app.copy import APP_TITLE, NOTE_AI, NOTE_DEMO
from app.direction import apply_text_direction
from vga.log import configure_logging
from vga.settings import Settings


@st.cache_resource
def _configure_logging(level: str, log_dir: str) -> bool:
    """Install the JSON log handlers once per process (Streamlit reruns this script constantly)."""
    configure_logging(level=level, log_dir=log_dir)
    return True


def render_page() -> None:
    settings: Settings = runner.load_ui_settings()
    _configure_logging(settings.log_level, settings.log_dir)

    apply_text_direction()
    st.title(APP_TITLE, anchor=False)
    st.markdown(NOTE_DEMO)
    st.markdown(NOTE_AI)
    notice = runner.mode_notice(settings)
    if notice:
        st.info(notice)

    searching = state.is_searching()
    settings_override = render_sidebar(disabled=searching)
    inputs = render_input_panel(disabled=searching)

    error = state.last_error()
    if error:
        render_error(error)

    response = state.get_response()
    if response is not None:
        render_chips(response.understood, disabled=searching, can_search=inputs.is_valid)

    flow.run_pending_search(inputs, settings_override)

    if response is None:
        render_welcome(disabled=searching)
    elif response.result_count == 0:
        render_no_results(response)
        render_run_details(response)
    else:
        render_notes(response.warnings)
        render_groups(response)
        render_run_details(response)


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        layout="wide",
        initial_sidebar_state="auto",
    )
    # .streamlit/config.toml says the same, but Streamlit reads it from the folder the app was
    # started in. Setting it here keeps "never show a stack trace" true from any folder.
    st.set_option("client.showErrorDetails", "none")
    with error_boundary():
        render_page()


main()
