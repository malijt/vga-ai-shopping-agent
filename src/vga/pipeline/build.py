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

    The OpenAI client is tied to the event loop it is first used in, so the real understander is
    rebuilt when a different loop calls (a UI that runs ``asyncio.run`` for every search). Building
    one is cheap and shares the process-wide daily call counter, so nothing is lost by it.
    """

    def __init__(self, settings: Settings, *, clock: Clock | None = None) -> None:
        self._settings = settings
        self._clock = clock
        self._loop: asyncio.AbstractEventLoop | None = None
        self._understander: OpenAIUnderstander | None = None

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        loop = asyncio.get_running_loop()
        if self._understander is None or self._loop is not loop:
            # Raises ConfigError (a plain message) when the model or the API key is not set.
            self._understander = OpenAIUnderstander(self._settings, clock=self._clock)
            self._loop = loop
        return await self._understander.understand(req)


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
