"""The real pipeline, with only the boundaries faked.

The audit exists to catch what the real code does with a photo, so almost nothing is replaced:

=========================  ============================================================
real                       faked (a boundary)
=========================  ============================================================
``SearchPipeline``         the stores' HTTP (``respx``, through ``StoreWorld``)
``OpenAIUnderstander``     OpenAI's HTTP (``FakeOpenAI``; the real OpenAI SDK talks to it)
``OpenAIGateway``          the model weights (``ColourEmbedder`` stands in for FashionSigLIP)
``StoreSearchEngine``      the clock (``FakeClock``)
``SiglipImageRanker``
the real JSON logging
=========================  ============================================================

Both the SDK and the stores' HTTP stay real code: the photo travels through the same request
building, JSON encoding and response parsing it would use in production.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from tests.factories import make_settings
from tests.fakes import FakeClock
from tests.pipeline.world import StoreWorld, store_for
from tests.rank_image.support import ColourEmbedder
from tests.understand.fake_openai import FakeOpenAI, Step
from tests.understand.readings import make_reading, make_reading_item
from vga.interfaces import Understander
from vga.models import Category, InputType, Product, SearchRequest, UnderstandResult
from vga.pipeline import SearchPipeline
from vga.rank.image import SiglipImageRanker
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine
from vga.understand import OpenAIUnderstander
from vga.understand.budget import CallBudget
from vga.understand.schema import UnderstandReading

MODEL = "gpt-6-luna"
"""The project's pinned model (``config/settings.yaml``)."""

LOG_LEVEL = "DEBUG"
"""The most detailed level: the audit wants every line the app can write."""

ImageFetcher = Callable[[Product], Awaitable[bytes | None]]


def blazer_reading(input_type: InputType = InputType.PRODUCT_PHOTO) -> UnderstandReading:
    """What the model says about a photo of one black blazer."""
    return make_reading(input_type=input_type, items=[make_reading_item()])


def outfit_reading() -> UnderstandReading:
    """What the model says about a photo of a whole outfit: four garments."""
    return make_reading(
        input_type=InputType.OUTFIT_PHOTO,
        items=[
            make_reading_item(search_keywords=["black blazer", "oversized blazer"]),
            make_reading_item(
                category=Category.TOPS,
                colour="white",
                style="shirt",
                search_keywords=["white shirt", "cotton shirt"],
            ),
            make_reading_item(
                category=Category.BOTTOMS,
                colour="blue",
                style="jeans",
                search_keywords=["blue jeans", "wide-leg jeans"],
            ),
            make_reading_item(
                category=Category.SHOES,
                colour="white",
                style="sneakers",
                search_keywords=["white sneakers", "leather sneakers"],
            ),
        ],
    )


class SlowModel:
    """An ``Understander`` that is the real one followed by a long wait: OpenAI answered, but the
    network took longer than the request is allowed to."""

    def __init__(self, inner: Understander, clock: FakeClock) -> None:
        self._inner = inner
        self._clock = clock

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        result = await self._inner.understand(req)
        await self._clock.sleep(1000)
        return result


Leak = Callable[[SearchRequest, "Rig"], Awaitable[None] | None]
"""A deliberate bug for the canary tests: what a careless change to the app could do with the
photo. It is called with the request, and the rig so that it can hide the photo in the app's own
objects."""


class LeakingUnderstander:
    """The real understander, preceded by a ``Leak``: the app with a privacy bug in it. The audit
    must fail for every one (``test_canaries.py``), or it proves nothing."""

    def __init__(self, inner: Understander, leak: Leak) -> None:
        self._inner = inner
        self._leak = leak
        self.rig: Rig | None = None

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        assert self.rig is not None
        outcome = self._leak(req, self.rig)
        if outcome is not None:
            await outcome
        return await self._inner.understand(req)


class BrokenWeights(ColourEmbedder):
    """Model weights that fail to run, as a corrupt checkpoint or a full GPU would."""

    def embed(self, images):
        msg = "the image model crashed"
        raise RuntimeError(msg)


@dataclass
class Rig:
    pipeline: SearchPipeline
    understander: OpenAIUnderstander
    """The real one, also when the pipeline holds it inside ``SlowModel``."""
    engine: StoreSearchEngine
    fake_openai: FakeOpenAI
    world: StoreWorld
    clock: FakeClock
    settings: Settings
    embedder: ColourEmbedder

    async def aclose(self) -> None:
        await self.engine.aclose()
        await self.fake_openai.aclose()


def settings_for(
    log_dir: str, *, log_prompts: bool, debug_dump: bool, **overrides: object
) -> Settings:
    return make_settings(
        openai_model=MODEL,
        daily_llm_call_cap=100,
        image_ranker="siglip",
        log_dir=log_dir,
        log_level=LOG_LEVEL,
        log_prompts=log_prompts,
        debug_dump=debug_dump,
        **overrides,
    )


def build_rig(
    world: StoreWorld,
    clock: FakeClock,
    settings: Settings,
    steps: Sequence[Step],
    *,
    stores: Sequence[str] = ("alpha", "beta"),
    store_status: Mapping[str, int] | None = None,
    embedder: ColourEmbedder | None = None,
    slow_model: bool = False,
    slow_thumbnails: bool = False,
    leak: Leak | None = None,
) -> Rig:
    """The real pipeline over the fake world. ``steps`` are OpenAI's scripted answers in order;
    ``store_status`` makes a store answer with an HTTP error (by store id); ``leak`` puts a
    deliberate privacy bug in front of the understander (canary tests only)."""
    configs = [store_for(key) for key in stores]
    for config in configs:
        world.add(config, status=(store_status or {}).get(config.id, 200))
    fake = FakeOpenAI(*steps)
    real = OpenAIUnderstander(
        settings,
        fake.client(),
        clock=clock,
        budget=CallBudget(today=lambda: date(2026, 10, 8)),
        jitter=lambda: 0.5,
    )
    understander: Understander = SlowModel(real, clock) if slow_model else real
    leaking = LeakingUnderstander(understander, leak) if leak is not None else None
    if leaking is not None:
        understander = leaking
    engine = StoreSearchEngine(settings, StoreRegistry(configs), clock=clock)
    model = embedder or ColourEmbedder()
    fetch: ImageFetcher = engine.fetch_image
    if slow_thumbnails:
        fetch = _slow(engine.fetch_image, clock)
    ranker = SiglipImageRanker(
        embedder_provider=lambda: model,
        fetch_image=fetch,
        cos_lo=settings.siglip_cos_lo,
        cos_hi=settings.siglip_cos_hi,
    )
    pipeline = SearchPipeline(understander, engine, ranker, configs, clock=clock)
    rig = Rig(pipeline, real, engine, fake, world, clock, settings, model)
    if leaking is not None:
        leaking.rig = rig
    return rig


def _slow(fetch: ImageFetcher, clock: FakeClock) -> ImageFetcher:
    """A thumbnail CDN that never answers in time."""

    async def slow(product: Product) -> bytes | None:
        await clock.sleep(1000)
        return await fetch(product)

    return slow
