"""Pieces for the tests of a live run's manners: the pause, the link spacing, the stop and the
resume. Nothing here touches the network or really waits.
"""

from collections.abc import Callable

from eval.harness.wiring import Wiring, WiringFactory
from tests.fakes import FakeClock
from tests.harness.helpers import ToyPipeline
from tests.harness.live_parts import LiveParts, make_stores, ok_link_fetch
from vga.interfaces import ImageRanker, StoreSearcher, Understander
from vga.models import RunOverrides, SearchRequest, SearchResponse, Step
from vga.settings import Settings


class WatchingClock(FakeClock):
    """A fake clock that tells a test what happened when someone started to wait."""

    def __init__(self, on_sleep: Callable[[float], None] | None = None) -> None:
        super().__init__()
        self._on_sleep = on_sleep

    async def sleep(self, seconds: float) -> None:
        if self._on_sleep is not None:
            self._on_sleep(seconds)
        await super().sleep(seconds)


class SteppedPipeline:
    """Wraps a pipeline and lets a test decide, query by query, what it answers.

    A query is a run with no overrides; the search after the shopper's answer to "Who is this
    for?" carries overrides and belongs to the query before it. ``answer`` is given the number of
    the query (0 for the first) and the real answer; it returns a response to use instead, or
    ``None`` to let the wrapped pipeline answer. ``seconds`` is how long each run takes on the
    fake clock."""

    def __init__(
        self,
        inner: ToyPipeline,
        clock: FakeClock | None = None,
        *,
        seconds: float = 0.0,
        answer: Callable[[int], SearchResponse | None] | None = None,
    ) -> None:
        self._inner = inner
        self._clock = clock
        self._seconds = seconds
        self._answer = answer
        self.queries_started = 0
        """How many queries (first searches) reached the pipeline."""
        self.runs = 0
        """How many times ``run`` was called, searches after an answer included."""

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: Callable[[Step], None] | None = None,
    ) -> SearchResponse:
        self.runs += 1
        if overrides is None:
            self.queries_started += 1
        if self._clock is not None:
            self._clock.advance(self._seconds)
        position = self.queries_started - 1
        replacement = self._answer(position) if self._answer is not None else None
        if replacement is not None:
            return replacement
        return await self._inner.run(req, settings, overrides, on_step)


def stepped_wiring(
    live: LiveParts,
    *,
    clock: FakeClock | None = None,
    seconds: float = 0.0,
    answer: Callable[[int], SearchResponse | None] | None = None,
    fetch: object = ok_link_fetch,
    pipelines: list[SteppedPipeline] | None = None,
) -> WiringFactory:
    """A wiring over the toy pipeline whose answers a test controls (see ``SteppedPipeline``)."""
    stores = make_stores()

    def factory(settings: Settings) -> Wiring:
        def build(
            understander: Understander, searcher: StoreSearcher, ranker: ImageRanker
        ) -> SteppedPipeline:
            pipeline = SteppedPipeline(
                ToyPipeline(understander, searcher, ranker, stores),
                clock,
                seconds=seconds,
                answer=answer,
            )
            if pipelines is not None:
                pipelines.append(pipeline)
            return pipeline

        return Wiring(
            pipeline_factory=build,
            stores=stores,
            link_fetch=fetch,  # type: ignore[arg-type]
            build_boundaries=live.boundaries,
        )

    return factory
