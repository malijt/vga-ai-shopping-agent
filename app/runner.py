"""The only place in the UI that produces a ``SearchResponse``.

Phase 10 (this file): no backend yet. With fixture mode on (``VGA_UI_FIXTURE=1``, setting
``ui_fixture``) the shared ``FakePipeline`` answers every request with the bundled sample
response, so the page can be built and tested without a network. With fixture mode off the page
says plainly that the live search is not connected yet.

Phase 15 keeps ``run_search`` and ``mode_notice`` as they are and changes only ``get_pipeline``
to return the real pipeline.
"""

import asyncio
import sys
from collections.abc import Callable

from vga.errors import VgaError
from vga.interfaces import Pipeline
from vga.models import RunOverrides, SearchRequest, SearchResponse, Step
from vga.settings import PROJECT_ROOT, Settings, load_settings

StepCallback = Callable[[Step], None]

FIXTURE_NOTICE = (
    "Sample mode: the results below are a fixed example. They do not depend on what you type, "
    "and no store is searched."
)
NOT_CONNECTED_NOTICE = (
    "The live search is not connected yet. To see how the page works with example results, "
    "start the app with VGA_UI_FIXTURE=1."
)


class NotConnectedError(VgaError):
    """Search was pressed while no pipeline is connected (fixture mode off, before Phase 15)."""

    default_code = "not_connected"
    default_message = NOT_CONNECTED_NOTICE


def load_ui_settings() -> Settings:
    """Settings for this run of the page. Raises ``ConfigError`` (a ``VgaError``) when invalid."""
    return load_settings()


def mode_notice(settings: Settings) -> str | None:
    """A note shown at the top of the page while the page is not showing live results."""
    return FIXTURE_NOTICE if settings.ui_fixture else NOT_CONNECTED_NOTICE


def get_pipeline(settings: Settings) -> Pipeline:
    """The pipeline that answers a search. Tests replace this function with their own fake."""
    if not settings.ui_fixture:
        raise NotConnectedError()
    # `tests` is not an installed package, so `streamlit run` cannot import it from the script
    # folder. The root is added only here, only in fixture mode.
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tests.fakes import FakePipeline

    return FakePipeline()


def run_search(
    request: SearchRequest,
    overrides: RunOverrides | None = None,
    on_step: StepCallback | None = None,
) -> SearchResponse:
    """Run one search and return its response. Raises a ``VgaError`` for a problem the shopper
    can fix or understand; any other exception means a bug and is handled by the error boundary.

    ``on_step`` is called with each pipeline ``Step`` as it starts, so the page can show progress.
    """
    settings = load_ui_settings()
    pipeline = get_pipeline(settings)
    return asyncio.run(pipeline.run(request, settings, overrides, on_step))
