"""Fixtures for the scraping guards: the pipeline tests' own, with a ``GuardWorld`` for the stores.

The clock, router, settings, photo and the worker-thread patch come from ``tests/pipeline`` (they
are what makes a whole pipeline run deterministic on the ``FakeClock``); the world is the guards'.
"""

from collections.abc import AsyncIterator

import pytest
import respx

from tests.fakes import FakeClock
from tests.guards.scraping.support import GuardPipelines, GuardWorld
from tests.pipeline.conftest import (  # noqa: F401  (re-exported fixtures)
    PipelineMaker,
    _no_worker_threads,
    clock,
    photo,
    router,
    settings,
)
from tests.pipeline.world import store_for
from vga.models import StoreConfig
from vga.settings import Settings


@pytest.fixture
def world(router: respx.MockRouter, clock: FakeClock) -> GuardWorld:  # noqa: F811
    return GuardWorld(router, clock)


@pytest.fixture
async def build(
    world: GuardWorld,
    clock: FakeClock,  # noqa: F811
    settings: Settings,  # noqa: F811
) -> AsyncIterator[GuardPipelines]:
    """Builds the real pipeline over the stores added to ``world`` so far, after sealing the world
    so that any request nobody expected is recorded in ``world.stray``.

    Call it after every ``world.add``. It takes the same options as ``PipelineMaker.__call__``
    (``understander``, ``stores``, ``thumbnails``, ...).
    """
    pipelines = GuardPipelines(world, PipelineMaker(world, clock, settings))
    yield pipelines
    await pipelines.aclose()


@pytest.fixture
def two_stores(world: GuardWorld) -> list[StoreConfig]:
    """Alpha and Beta: two ordinary stores that sell everything for everyone, robots.txt open."""
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    return stores
