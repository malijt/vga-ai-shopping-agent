"""Fixtures shared by the Phase 13 tests. Nothing here touches the network: store HTTP is answered
by ``respx`` and time by the shared ``FakeClock``."""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
import respx

from tests.factories import make_image_bytes, make_settings
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.spies import SpyImageRanker, SpySearcher
from tests.pipeline.world import StoreWorld, store_for
from tests.rank_image.support import ColourEmbedder
from vga.interfaces import ImageRanker, StoreSearcher, Understander
from vga.models import StoreConfig
from vga.pipeline import SearchPipeline
from vga.rank.image import SiglipImageRanker
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine


@pytest.fixture
def clock() -> FakeClock:
    """The shared fake clock, told to wait longer for the event loop to go quiet.

    The ``FakeClock`` moves time on once the loop has run ``SETTLE_HOPS`` iterations without
    anyone scheduling a new sleep. The pipeline's own deadline is a 30 s sleeper that is always
    pending, so a stretch of zero-time work longer than that (a chain of mocked HTTP calls whose
    rate-limit slot is already free) would fire the deadline early. A whole pipeline run has longer
    such stretches than any single fetch, so the tests allow far more iterations.
    """
    fake = FakeClock()
    fake.SETTLE_HOPS = 500
    return fake


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


async def run_inline[T](function: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """``asyncio.to_thread`` without the thread."""
    return function(*args, **kwargs)


@pytest.fixture(autouse=True)
def _no_worker_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run work that would be handed to a worker thread in place, in every test here.

    The ``FakeClock`` moves virtual time on once the event loop has run a few hundred iterations
    with nothing to do, and a loop that is waiting for a worker thread looks exactly like that:
    the pipeline's 30 s deadline would then be reached while the thread is still starting up (the
    main thread holds the interpreter for up to 5 ms before the worker gets a turn). It happens
    whether a fake model embeds an image (the FashionSigLIP ranker uses ``asyncio.to_thread``) or
    the OpenAI SDK reads the platform name before its first request. Nothing here does real
    blocking work, so there is nothing to offload.
    """
    monkeypatch.setattr(asyncio, "to_thread", run_inline)


class PipelineMaker:
    """Builds pipelines around the REAL store engine and remembers the parts of the last one.

    The understander and the image ranker are the shared fakes unless a test passes its own; the
    stores default to every store the world serves. ``thumbnails=True`` uses the real FashionSigLIP
    ranker with a fake embedder and the engine's own thumbnail fetcher, so thumbnail requests are
    real requests to the fake CDN and can be counted.
    """

    def __init__(self, world: StoreWorld, clock: FakeClock, settings: Settings) -> None:
        self._world = world
        self._clock = clock
        self._settings = settings
        self.engines: list[StoreSearchEngine] = []
        self.spy: SpySearcher | None = None
        self.ranker_spy: SpyImageRanker | None = None
        self.embedder: ColourEmbedder | None = None

    def __call__(
        self,
        *,
        understander: Understander | None = None,
        image_ranker: ImageRanker | None = None,
        stores: Sequence[StoreConfig] | None = None,
        engine_settings: Settings | None = None,
        thumbnails: bool = False,
        wrap_searcher: Callable[[StoreSearcher], StoreSearcher] | None = None,
    ) -> SearchPipeline:
        chosen = list(stores) if stores is not None else self._world.stores()
        used = engine_settings or self._settings
        engine = StoreSearchEngine(used, StoreRegistry(chosen), clock=self._clock)
        self.engines.append(engine)
        self.spy = SpySearcher(engine)
        searcher: StoreSearcher = self.spy
        if wrap_searcher is not None:
            searcher = wrap_searcher(searcher)
        ranker = image_ranker or FakeImageRanker()
        if thumbnails:
            self.embedder = ColourEmbedder()
            embedder = self.embedder
            ranker = SiglipImageRanker(
                embedder_provider=lambda: embedder,
                fetch_image=engine.fetch_image,
                cos_lo=used.siglip_cos_lo,
                cos_hi=used.siglip_cos_hi,
            )
        self.ranker_spy = SpyImageRanker(ranker)
        return SearchPipeline(
            understander or FakeUnderstander(),
            searcher,
            self.ranker_spy,
            chosen,
            clock=self._clock,
        )

    async def aclose(self) -> None:
        for engine in self.engines:
            await engine.aclose()


@pytest.fixture
async def make_pipeline(
    world: StoreWorld, clock: FakeClock, settings: Settings
) -> AsyncIterator[PipelineMaker]:
    maker = PipelineMaker(world, clock, settings)
    yield maker
    await maker.aclose()
