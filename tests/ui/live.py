"""The real search pipeline behind the page, with only the boundaries faked.

``tests/pipeline/world.py`` serves fake stores over ``respx`` (the real store engine, real
extraction, real ranking and price-range shaping run). OpenAI is ``FakeUnderstander`` and the image
model is ``FakeImageRanker``. Every boundary is wrapped so a test can count what crossed it:
store requests on the fake network, OpenAI calls on the fake understander, image-model calls on the
spy. That is how the page tests prove "a mix change asks no store and no AI".

The page runs each search with ``asyncio.run``, so the pipeline sees a new event loop on every
search. ``PerLoopFakeClock`` makes the shared fake clock safe for that: the ``FakeClock`` keeps a
"tick scheduled" flag, and a loop that ends while a tick is pending would otherwise leave it set
for ever, so the next loop's sleepers would never wake.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from tests.factories import make_settings
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.spies import RankerCall, SearchCall, SpyImageRanker, SpySearcher
from tests.pipeline.world import StoreWorld
from vga.interfaces import ImageRanker
from vga.models import StoreConfig
from vga.pipeline import SearchPipeline
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine


class PerLoopFakeClock(FakeClock):
    """A ``FakeClock`` that can be used from one ``asyncio.run`` after another."""

    SETTLE_HOPS = 500  # as in tests/pipeline: a whole run has long stretches of zero-time work

    def __init__(self) -> None:
        super().__init__()
        self._tick_loop: asyncio.AbstractEventLoop | None = None

    def _schedule_tick(self, loop: asyncio.AbstractEventLoop) -> None:
        if loop is not self._tick_loop:
            self._tick_loop = loop
            self._tick_scheduled = False  # a tick of an earlier, closed loop will never run
        super()._schedule_tick(loop)


@dataclass
class LiveSearch:
    """The real pipeline and everything that counts what reached its boundaries."""

    pipeline: SearchPipeline
    world: StoreWorld
    understander: FakeUnderstander
    searcher: SpySearcher
    ranker: SpyImageRanker
    engine: StoreSearchEngine
    stores: list[StoreConfig]

    @property
    def store_requests(self) -> int:
        """Search-page requests that reached any store (not robots.txt, not thumbnails)."""
        return self.world.search_requests()

    @property
    def openai_calls(self) -> int:
        return len(self.understander.calls)

    @property
    def store_searches(self) -> list[SearchCall]:
        """Every search the pipeline asked the store engine for, in order."""
        return self.searcher.calls

    @property
    def image_model_calls(self) -> list[RankerCall]:
        return self.ranker.calls


def build_live_search(
    world: StoreWorld,
    clock: FakeClock,
    understander: FakeUnderstander,
    *,
    log_dir: Path,
    stores: list[StoreConfig] | None = None,
    image_ranker: ImageRanker | None = None,
) -> LiveSearch:
    """The real ``SearchPipeline`` over the real store engine, serving ``stores`` (default: every
    store the world serves). ``image_ranker`` is the image-model boundary (default: a fake that
    scores every product 0.5)."""
    chosen = list(stores) if stores is not None else world.stores()
    settings: Settings = make_settings(log_dir=str(log_dir))
    engine = StoreSearchEngine(settings, StoreRegistry(chosen), clock=clock)
    searcher = SpySearcher(engine)
    ranker = SpyImageRanker(image_ranker or FakeImageRanker())
    pipeline = SearchPipeline(
        understander, searcher, ranker, chosen, clock=clock, on_close=engine.aclose
    )
    return LiveSearch(pipeline, world, understander, searcher, ranker, engine, chosen)
