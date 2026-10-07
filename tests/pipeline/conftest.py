"""Fixtures shared by the Phase 13 tests. Nothing here touches the network: store HTTP is answered
by ``respx`` and time by the shared ``FakeClock``."""

from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from pathlib import Path

import pytest
import respx

from tests.factories import make_image_bytes, make_settings
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.world import StoreWorld, store_for
from vga.interfaces import ImageRanker, Understander
from vga.models import StoreConfig
from vga.pipeline import SearchPipeline
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine

PipelineMaker = Callable[..., SearchPipeline]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def photo() -> bytes:
    """A small but real JPEG, the shopper's photo."""
    return make_image_bytes("JPEG", (64, 64), (10, 120, 200))


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    """Answers every httpx request in the test. A request nobody mocked raises, so a test cannot
    reach the network by accident."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


@pytest.fixture
def world(router: respx.MockRouter, clock: FakeClock) -> StoreWorld:
    return StoreWorld(router, clock)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Code defaults, with the log directory inside the test's own folder."""
    return make_settings(log_dir=str(tmp_path / "logs"))


@pytest.fixture
def two_stores(world: StoreWorld) -> list[StoreConfig]:
    """Two stores that sell everything for everyone."""
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    return stores


@pytest.fixture
async def make_pipeline(
    world: StoreWorld, clock: FakeClock, settings: Settings
) -> AsyncIterator[PipelineMaker]:
    """Builds a pipeline around the REAL store engine, and closes the engines afterwards.

    The understander and the image ranker are the fakes unless a test passes its own; the stores
    default to every store the world serves.
    """
    engines: list[StoreSearchEngine] = []

    def make(
        *,
        understander: Understander | None = None,
        image_ranker: ImageRanker | None = None,
        stores: Sequence[StoreConfig] | None = None,
        engine_settings: Settings | None = None,
    ) -> SearchPipeline:
        chosen = list(stores) if stores is not None else world.stores()
        engine = StoreSearchEngine(engine_settings or settings, StoreRegistry(chosen), clock=clock)
        engines.append(engine)
        return SearchPipeline(
            understander or FakeUnderstander(),
            engine,
            image_ranker or FakeImageRanker(),
            chosen,
            clock=clock,
        )

    yield make
    for engine in engines:
        await engine.aclose()
