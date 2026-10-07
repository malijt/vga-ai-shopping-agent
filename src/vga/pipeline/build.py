"""Building the real pipeline from the settings, and binding one for the acceptance harness.

``build_pipeline(settings)`` creates the real parts once and returns a ready ``SearchPipeline``:

- the store registry, read from ``config/stores/`` (empty is fine),
- one long-lived ``StoreSearchEngine``: it owns the HTTP client, the per-host rate limiter, the
  cooldowns and the result cache, so every search and every garment of an outfit shares them,
- the image ranker the settings select, handed the engine's thumbnail fetcher,
- an understander that creates the OpenAI client only when a model call is first needed, so a
  missing API key or model is a plain ``ConfigError`` at that moment and never at start-up. A
  re-run that reuses the earlier understanding needs no key at all.

Nothing here touches the network when it is built.
"""

import asyncio
import weakref
from collections.abc import Callable, Sequence

from vga.interfaces import Clock, ImageRanker, StoreSearcher, SystemClock, Understander
from vga.models import SearchRequest, StoreConfig, UnderstandResult
from vga.pipeline.pipeline import SearchPipeline
from vga.rank.image import create_image_ranker
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine
from vga.understand import OpenAIUnderstander

PipelineFactory = Callable[[Understander, StoreSearcher, ImageRanker], SearchPipeline]
"""The shape the acceptance harness builds a pipeline with (``eval.harness.wiring``)."""


class LazyUnderstander:
    """An ``Understander`` that builds the real ``OpenAIUnderstander`` on first use.

    The OpenAI client is tied to the event loop it is first used in, so there is one real
    understander per event loop: a UI that runs ``asyncio.run`` for every search gets a fresh one
    each time, and the old one is dropped with its loop instead of piling up. Building one is cheap
    and shares the process-wide daily call counter, so nothing is lost by it. The table is keyed by
    the loop and read and written in single steps, so searches on different threads, each with its
    own loop, never use one another's client.
    """

    def __init__(self, settings: Settings, *, clock: Clock | None = None) -> None:
        self._settings = settings
        self._clock = clock
        self._by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, OpenAIUnderstander] = (
            weakref.WeakKeyDictionary()
        )

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        loop = asyncio.get_running_loop()
        understander = self._by_loop.get(loop)
        if understander is None:
            # Raises ConfigError (a plain message) when the model or the API key is not set.
            understander = OpenAIUnderstander(self._settings, clock=self._clock)
            self._by_loop[loop] = understander
        return await understander.understand(req)


def build_pipeline(
    settings: Settings,
    *,
    registry: StoreRegistry | None = None,
    clock: Clock | None = None,
) -> SearchPipeline:
    """The real pipeline for ``settings``.

    ``registry`` defaults to the stores in ``config/stores/``; tests pass their own. Call
    ``await pipeline.warm_up()`` once at start-up to load the image model, and
    ``await pipeline.aclose()`` when finished.
    """
    time_source = clock or SystemClock()
    stores = registry if registry is not None else StoreRegistry.from_directory()
    engine = StoreSearchEngine(settings, stores, clock=time_source)
    return SearchPipeline(
        LazyUnderstander(settings, clock=time_source),
        engine,
        create_image_ranker(settings, fetch_image=engine.fetch_image),
        stores,
        clock=time_source,
        on_close=engine.aclose,
    )


def pipeline_factory(
    stores: Sequence[StoreConfig] | StoreRegistry, *, clock: Clock | None = None
) -> PipelineFactory:
    """A ``(understander, searcher, image_ranker) -> pipeline`` function with the stores bound.

    For the acceptance harness, whose wiring module returns
    ``Wiring(pipeline_factory=pipeline_factory(stores), stores=stores, ...)``.
    """

    def factory(
        understander: Understander, searcher: StoreSearcher, image_ranker: ImageRanker
    ) -> SearchPipeline:
        return SearchPipeline(understander, searcher, image_ranker, stores, clock=clock)

    return factory
