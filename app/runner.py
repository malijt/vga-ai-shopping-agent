"""The only place in the UI that produces a ``SearchResponse``: it builds the pipeline and calls it.

Two modes, chosen by the ``ui_fixture`` setting (``VGA_UI_FIXTURE=1``):

- Fixture mode: the shared ``FakePipeline`` answers every request with the bundled sample response,
  so the page can be built and tested without a network or a key.
- Live mode: the real ``SearchPipeline`` from ``build_pipeline``. It is built once per process and
  kept (``st.cache_resource``), because the re-run cache that makes a mix or chip change cheap
  lives on that one instance (plan 13.1.5). The page may not call it any other way.

Each search runs in its own event loop (``asyncio.run``): Streamlit runs the page in a plain worker
thread with no loop of its own. The pipeline is written for that (its HTTP client and its OpenAI
client are rebuilt per loop), and the connection pool is closed at the end of every search so no
socket outlives the loop it belongs to.

``setup_problem`` tells the page, before any search, when live mode cannot work (no API key, no
model), so the shopper reads what to do instead of discovering it on the first click.
"""

import asyncio
import os
import sys
from collections.abc import Callable

import streamlit as st

from vga.interfaces import Pipeline
from vga.log import get_logger
from vga.models import RunOverrides, SearchRequest, SearchResponse, Step
from vga.pipeline import SearchPipeline, build_pipeline
from vga.settings import PROJECT_ROOT, Settings, load_settings
from vga.understand.understander import API_KEY_MISSING_MESSAGE, MODEL_NOT_SET_MESSAGE

log = get_logger(__name__)

StepCallback = Callable[[Step], None]

GETTING_READY = "Getting ready: loading the image model. This takes a few seconds, once."

FIXTURE_NOTICE = (
    "Sample mode: the results below are a fixed example. They do not depend on what you type, "
    "and no store is searched."
)


def load_ui_settings() -> Settings:
    """Settings for this run of the page. Raises ``ConfigError`` (a ``VgaError``) when invalid."""
    return load_settings()


def mode_notice(settings: Settings) -> str | None:
    """A note shown at the top of the page while the results are only a fixed example."""
    return FIXTURE_NOTICE if settings.ui_fixture else None


def setup_problem(settings: Settings) -> str | None:
    """Plain words for what is missing when live mode cannot search yet, else ``None``.

    Fixture mode needs neither a key nor a model. The key is only looked for in the environment
    (``load_settings`` has already copied ``.env`` into it); it is never read into a setting, shown
    or logged.
    """
    if settings.ui_fixture:
        return None
    if not settings.openai_model:
        return MODEL_NOT_SET_MESSAGE
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return API_KEY_MISSING_MESSAGE
    return None


def _fixture_pipeline() -> Pipeline:
    # `tests` is not an installed package, so `streamlit run` cannot import it from the script
    # folder. The root is added only here, only in fixture mode.
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tests.fakes import FakePipeline

    return FakePipeline()


@st.cache_resource(show_spinner=GETTING_READY)
def _live_pipeline(_settings: Settings) -> SearchPipeline:
    """The one real pipeline of this process. ``_settings`` is not part of the cache key (the
    underscore tells Streamlit not to hash it): the stores, the HTTP client and the models are set
    up from the settings at start-up, and a changed settings file takes effect after a restart.
    Each search still passes the settings it was started with to ``run``."""
    pipeline = build_pipeline(_settings)
    # Load the image model once, here, so the first photo search does not pay for it. False means
    # image similarity is unavailable here: not an error, the pipeline then ranks by text and
    # price and says so in the warnings of a photo search. Never called again: this function
    # runs once per process.
    ready = asyncio.run(_warm_up(pipeline))
    log.info("search pipeline ready", extra={"image_model_ready": ready})
    return pipeline


async def _warm_up(pipeline: SearchPipeline) -> bool:
    try:
        return await pipeline.warm_up()
    finally:
        # Warming up reads the stores' robots.txt files, and this loop ends with it: close the
        # HTTP client here, as `_run` does after a search.
        await pipeline.aclose()


def get_pipeline(settings: Settings) -> Pipeline:
    """The pipeline that answers a search. Tests replace this function with their own fake."""
    if settings.ui_fixture:
        return _fixture_pipeline()
    return _live_pipeline(settings)


def get_ready(settings: Settings) -> None:
    """Build the pipeline and load the image model now, when the page first opens in live mode, so
    the shopper's first photo search does not pay for the load (about 10 s cold, against a 30 s
    limit for the whole search). Streamlit shows its "Getting ready" message while this runs.
    Every later page run finds the finished pipeline in the cache and returns at once. Nothing to
    do in fixture mode, or while ``setup_problem`` says live mode cannot work yet."""
    if settings.ui_fixture or setup_problem(settings) is not None:
        return
    get_pipeline(settings)


async def _run(
    pipeline: Pipeline,
    request: SearchRequest,
    settings: Settings,
    overrides: RunOverrides | None,
    on_step: StepCallback | None,
) -> SearchResponse:
    try:
        return await pipeline.run(request, settings, overrides, on_step)
    finally:
        # The HTTP client belongs to this loop and the loop ends with this search. Closing it here
        # is safe: the rate limits, cooldowns and caches live outside it and are kept, and the
        # next search makes a new client.
        close = getattr(pipeline, "aclose", None)
        if close is not None:
            await close()


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
    return asyncio.run(_run(pipeline, request, settings, overrides, on_step))
