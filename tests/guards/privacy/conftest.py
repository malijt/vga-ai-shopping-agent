"""Fixtures for the privacy audit.

The fake clock, the fake store network and the "no worker threads" rule are the pipeline tests' own
(``tests/pipeline/conftest.py``): they are imported, not copied, so the two suites cannot drift
apart. Everything else is specific to watching a request.
"""

import logging
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import pytest

from tests.fakes import FakeClock
from tests.guards.privacy.audit import Audited, Workspace, run_case
from tests.guards.privacy.scenarios import BOTH, Case, Scenario
from tests.pipeline import conftest as pipeline_conftest
from tests.pipeline.world import StoreWorld
from vga.log import ROOT_LOGGER_NAME

# Bound by name so that pytest finds them here; they are the pipeline tests' own fixtures.
clock = pipeline_conftest.clock
router = pipeline_conftest.router
world = pipeline_conftest.world
_no_worker_threads = pipeline_conftest._no_worker_threads


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    cwd, temp = tmp_path / "cwd", tmp_path / "tmp"
    cwd.mkdir()
    temp.mkdir()
    monkeypatch.chdir(cwd)  # a relative path now lands in a folder we watch
    monkeypatch.setattr(tempfile, "tempdir", str(temp))  # Python caches the temp folder
    monkeypatch.setenv("TMPDIR", str(temp))
    return Workspace(root=tmp_path, cwd=cwd, temp=temp, logs=tmp_path / "logs")


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Put the ``vga`` logger back as it was: ``configure_logging`` installs file handlers."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    level = logger.level
    yield
    for handler in [h for h in logger.handlers if getattr(h, "_vga_handler", False)]:
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)


@pytest.fixture
async def run(
    world: StoreWorld, clock: FakeClock, workspace: Workspace
) -> AsyncIterator[Callable[[Scenario], Awaitable[Audited]]]:
    """``await run(scenario)``: one scenario of the test's own, with both debug switches on."""
    results: list[Audited] = []

    async def go(scenario: Scenario) -> Audited:
        result = await run_case(Case(scenario, BOTH), world, clock, workspace)
        results.append(result)
        return result

    yield go
    for result in results:
        await result.rig.aclose()


@pytest.fixture
async def audited(
    request: pytest.FixtureRequest, world: StoreWorld, clock: FakeClock, workspace: Workspace
) -> AsyncIterator[Audited]:
    """One scenario, run through the real pipeline while everything is watched.

    Used with ``@pytest.mark.parametrize("audited", cases, indirect=True)``; ``cases`` come from
    ``scenarios.py``.
    """
    case: Case = request.param
    result = await run_case(case, world, clock, workspace)
    yield result
    await result.rig.aclose()
    assert not result.rig.fake_openai.unexpected, "OpenAI got a request nothing scripted"
