"""Shared setup for the UI tests: the page under Streamlit's ``AppTest``, no network, no real
pipeline. The only boundary faked is the pipeline, through the one seam ``app.runner.get_pipeline``
(QA doc: fake only the boundaries, from ``tests/fakes.py``).
"""

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import runner
from tests.fakes import FakePipeline, PipelineCall
from tests.ui.helpers import search
from vga.errors import VgaError
from vga.log import ROOT_LOGGER_NAME
from vga.models import RunOverrides, SearchRequest, SearchResponse, Step
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
