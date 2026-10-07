"""The real application, wired for the acceptance harness (plan 16.1.1).

::

    uv run --group ml python -m eval.harness --record eval/results/run-1/recording \\
        --wiring eval.harness.real:real_wiring
    uv run python -m eval.harness --replay eval/results/run-1/recording \\
        --wiring eval.harness.real:real_wiring

``real_wiring(settings)`` is the function ``--wiring`` names. It returns a ``Wiring`` over:

- the stores enabled in ``config/stores/`` (in the configured country),
- the model and image ranker of ``config/settings.yaml`` (and the environment),
- ONE ``StoreSearchEngine`` that the search, the thumbnails and the link check all share, so the
  link check is as polite as the search: same honest User-Agent, robots.txt, per-host rate limit,
  allowed hosts and cooldowns (``engine_links.EngineLinkFetch``).

Building it touches nothing: no network, no OpenAI client, no model weights. ``--replay`` therefore
needs no key and no ``ml`` group. Only ``--record`` calls ``build_boundaries``, which is when a
missing OpenAI key or model name is found, before the first query and before any folder is made.

``build_real_wiring`` is the same function with the seams a test needs (the stores, the clock, a
fake understander or image ranker); ``real_wiring`` is the production call.
"""

import io

from eval.harness.engine_links import EngineLinkFetch
from eval.harness.errors import WiringError
from eval.harness.links import LinkResult
from eval.harness.wiring import Boundaries, Wiring
from vga.interfaces import Clock, ImageRanker, Understander
from vga.log import configure_logging
from vga.models import StoreConfig
from vga.pipeline import LazyUnderstander, pipeline_factory
from vga.rank.image import create_image_ranker
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine
from vga.understand import OpenAIUnderstander


class _Discard(io.StringIO):
    """A stream that throws everything away, so the JSON log lines do not bury the harness's own
    progress on screen. They still go to the log file."""

    def write(self, text: str) -> int:
        return len(text)


class _LiveParts:
    """The parts a live run shares, built the first time they are needed."""

    def __init__(
        self,
        settings: Settings,
        registry: StoreRegistry,
        stores: list[StoreConfig],
        clock: Clock | None,
        understander: Understander | None,
        image_ranker: ImageRanker | None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._stores = stores
        self._clock = clock
        self._understander = understander
        self._image_ranker = image_ranker
        self._engine: StoreSearchEngine | None = None
        self._links: EngineLinkFetch | None = None

    @property
    def engine(self) -> StoreSearchEngine:
        if self._engine is None:
            self._engine = StoreSearchEngine(self._settings, self._registry, clock=self._clock)
        return self._engine

    def boundaries(self) -> Boundaries:
        understander = self._understander
        if understander is None:
            # Finds a missing key or model now, in plain words, instead of failing all 10 queries.
            OpenAIUnderstander(self._settings, clock=self._clock)
            understander = LazyUnderstander(self._settings, clock=self._clock)
        engine = self.engine
        ranker = self._image_ranker or create_image_ranker(
            self._settings, fetch_image=engine.fetch_image
        )
        return Boundaries(understander, engine, ranker)

    async def fetch_link(self, url: str) -> LinkResult:
        if self._links is None:
            self._links = EngineLinkFetch(self.engine, self._stores)
        return await self._links(url)

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.aclose()


def build_real_wiring(
    settings: Settings,
    *,
    registry: StoreRegistry | None = None,
    clock: Clock | None = None,
    understander: Understander | None = None,
    image_ranker: ImageRanker | None = None,
) -> Wiring:
    """The real pipeline, stores, link fetch and boundaries for ``settings``.

    ``registry`` defaults to ``config/stores/``; ``clock`` times the engine and the pipeline;
    ``understander`` and ``image_ranker`` replace the OpenAI call and the image model (tests only).
    Raises ``WiringError`` when no store is enabled, because there would be nothing to search.
    """
    stores_registry = registry if registry is not None else StoreRegistry.from_directory()
    stores = stores_registry.active(settings)
    if not stores:
        msg = (
            f"No store is enabled for country {settings.country}, so there is nothing to search. "
            "Enable a store in config/stores/ (enabled: true), or check `country` and `stores` "
            "in config/settings.yaml."
        )
        raise WiringError(msg)
    parts = _LiveParts(settings, stores_registry, stores, clock, understander, image_ranker)
    return Wiring(
        pipeline_factory=pipeline_factory(stores, clock=clock),
        stores=stores,
        link_fetch=parts.fetch_link,
        build_boundaries=parts.boundaries,
        aclose=parts.aclose,
    )


def real_wiring(settings: Settings) -> Wiring:
    """What ``--wiring eval.harness.real:real_wiring`` calls."""
    # The log of a live run is how a failure is explained afterwards: one JSON line per event in
    # <log_dir>/vga.jsonl, never the photo. Nothing is printed.
    configure_logging(level=settings.log_level, log_dir=settings.log_dir, stream=_Discard())
    return build_real_wiring(settings)
