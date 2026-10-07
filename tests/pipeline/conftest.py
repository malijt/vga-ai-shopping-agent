"""Fixtures shared by the Phase 13 tests. Nothing here touches the network: store HTTP is answered
by ``respx`` and time by the shared ``FakeClock``."""

from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path

import pytest
import respx

from tests.factories import make_image_bytes, make_settings
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.spies import SpySearcher
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
        self.embedder: ColourEmbedder | None = None

    def __call__(
        self,
        *,
        understander: Understander | None = None,
        image_ranker: ImageRanker | None = None,
        stores: Sequence[StoreConfig] | None = None,
        engine_settings: Settings | None = None,
        thumbnails: bool = False,
    ) -> SearchPipeline:
        chosen = list(stores) if stores is not None else self._world.stores()
        used = engine_settings or self._settings
        engine = StoreSearchEngine(used, StoreRegistry(chosen), clock=self._clock)
        self.engines.append(engine)
        self.spy = SpySearcher(engine)
        searcher: StoreSearcher = self.spy
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
        return SearchPipeline(
            understander or FakeUnderstander(), searcher, ranker, chosen, clock=self._clock
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
