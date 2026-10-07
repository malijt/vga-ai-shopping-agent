"""Shared setup for the UI tests: the page under Streamlit's ``AppTest``, no network, no real
pipeline. The only boundary faked is the pipeline, through the one seam ``app.runner.get_pipeline``
(QA doc: fake only the boundaries, from ``tests/fakes.py``).
"""

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import respx
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import runner
from tests.fakes import FakePipeline, FakeUnderstander, PipelineCall
from tests.pipeline.world import StoreWorld, store_for
from tests.ui.helpers import search
from tests.ui.live import LiveSearch, PerLoopFakeClock, build_live_search
from vga.errors import VgaError
from vga.interfaces import ImageRanker
from vga.log import ROOT_LOGGER_NAME
from vga.models import RunOverrides, SearchRequest, SearchResponse, Step, StoreConfig
from vga.settings import Settings

APP_PATH = Path(__file__).resolve().parents[2] / "app" / "main.py"


class RaisingPipeline:
    """A pipeline that fails with any exception (``FakePipeline`` only raises a ``VgaError``).
    Used for the "something unexpected broke" path of the error boundary."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls: list[PipelineCall] = []

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: Callable[[Step], None] | None = None,
    ) -> SearchResponse:
        self.calls.append(PipelineCall(req, settings, overrides))
        raise self._error


InstallPipeline = Callable[..., FakePipeline | RaisingPipeline]


@pytest.fixture(autouse=True)
def ui_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Fixture mode on, logs in a temporary folder, and no log handler left behind."""
    monkeypatch.setenv("VGA_UI_FIXTURE", "1")
    monkeypatch.setenv("VGA_LOG_DIR", str(tmp_path / "logs"))
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in [h for h in logger.handlers if getattr(h, "_vga_handler", False)]:
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def install_pipeline(monkeypatch: pytest.MonkeyPatch) -> InstallPipeline:
    """Put a fake pipeline behind the page: it returns ``response`` (default: the bundled sample),
    or raises ``error``. The fake records every call it receives in ``calls``."""

    def install(
        response: SearchResponse | None = None, *, error: Exception | None = None
    ) -> FakePipeline | RaisingPipeline:
        fake: FakePipeline | RaisingPipeline
        if error is None:
            fake = FakePipeline(response)
        elif isinstance(error, VgaError):
            fake = FakePipeline(response, error=error)
        else:
            fake = RaisingPipeline(error)
        monkeypatch.setattr(runner, "get_pipeline", lambda settings: fake)
        return fake

    return install


@pytest.fixture
def pipeline(install_pipeline: InstallPipeline) -> FakePipeline:
    """The default fake: answers every search with the bundled sample response."""
    fake = install_pipeline()
    assert isinstance(fake, FakePipeline)
    return fake


@pytest.fixture
def at() -> AppTest:
    """The page, not yet run."""
    return AppTest.from_file(str(APP_PATH), default_timeout=60)


@pytest.fixture
def results_at(at: AppTest, pipeline: FakePipeline) -> AppTest:
    """The page after one search that returned the bundled sample (two garments)."""
    at.run()
    return search(at)


@pytest.fixture(autouse=True)
def _no_cached_pipeline() -> Iterator[None]:
    """``runner`` keeps the real pipeline in Streamlit's resource cache for the whole process. A
    test that builds one must not leave it for the next."""
    yield
    st.cache_resource.clear()


# --- The real pipeline behind the page (tests/ui/live.py) -------------------------------------

InstallLive = Callable[..., LiveSearch]


@pytest.fixture
def live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live mode: fixture mode off and an API key present, as a configured machine has. The key is
    a placeholder: the OpenAI call itself is faked. The image model is switched off so that no test
    can load real weights when the page gets the pipeline ready."""
    monkeypatch.setenv("VGA_UI_FIXTURE", "0")
    monkeypatch.setenv("VGA_IMAGE_RANKER", "off")
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder-not-a-real-key")


@pytest.fixture
def clock() -> PerLoopFakeClock:
    return PerLoopFakeClock()


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    """Answers every httpx request of the test; one nobody mocked raises, so no test can reach a
    real store by accident."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


@pytest.fixture
def world(router: respx.MockRouter, clock: PerLoopFakeClock) -> StoreWorld:
    return StoreWorld(router, clock)


@pytest.fixture
def install_live(
    monkeypatch: pytest.MonkeyPatch,
    live_mode: None,
    world: StoreWorld,
    clock: PerLoopFakeClock,
    tmp_path: Path,
) -> InstallLive:
    """Put the REAL ``SearchPipeline`` behind the page, in live mode. Only the boundaries are
    faked: store HTTP (two fake stores that sell everything unless ``stores`` is given), OpenAI
    (``understander``) and the image model."""

    def install(
        understander: FakeUnderstander | None = None,
        *,
        stores: list[StoreConfig] | None = None,
        image_ranker: ImageRanker | None = None,
    ) -> LiveSearch:
        if stores is None:
            stores = [store_for("alpha"), store_for("beta")]
        for store in stores:
            world.add(store)
        live = build_live_search(
            world,
            clock,
            understander or FakeUnderstander(),
            log_dir=tmp_path / "pipeline-logs",
            stores=stores,
            image_ranker=image_ranker,
        )
        monkeypatch.setattr(runner, "get_pipeline", lambda settings: live.pipeline)
        return live

    return install
