"""Fixtures for the injection tests.

The fake clock, the fake store network, the pipeline maker and the rest come from
``tests/pipeline/conftest.py`` and are reused as they are (so a change to how the clock is tuned
reaches these tests too). ``make_rig`` adds what is specific here: the real pipeline around the
real ``OpenAIUnderstander`` talking to a fake OpenAI, over fake stores with a tripwire.
"""

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

import pytest
import respx

from tests.factories import make_settings
from tests.fakes import FakeClock
from tests.guards.injection.support import MODEL, Rig, open_shop
from tests.pipeline import conftest as pipeline
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from tests.understand.fake_openai import FakeOpenAI, Step
from vga.models import StoreConfig
from vga.settings import Settings
from vga.understand import OpenAIUnderstander
from vga.understand.budget import CallBudget

RigFactory = Callable[..., Rig]

# The shared fixtures, under their own names. (Assigned rather than imported so that a test or
# fixture here can ask for them by name without redefining an import.)
clock = pipeline.clock
photo = pipeline.photo
router = pipeline.router
world = pipeline.world
settings = pipeline.settings
make_pipeline = pipeline.make_pipeline
_no_worker_threads = pipeline._no_worker_threads  # autouse: no worker threads under a fake clock


@pytest.fixture
async def make_rig(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    router: respx.MockRouter,
    clock: FakeClock,
    settings: Settings,
) -> AsyncIterator[RigFactory]:
    """``make_rig(*steps, default=None, stores=None, bodies=None, thumbnails=False)``.

    ``steps`` and ``default`` script the fake OpenAI (see ``FakeOpenAI``). ``stores`` are the fake
    stores (default: ``alpha`` and ``beta``, which sell everything), ``bodies`` the answers they
    give, by store id and then by kind of garment, ``settings_changes`` the pipeline settings to
    change. At teardown every fake is closed and the test
    fails if OpenAI received a request that no step was scripted for.
    """
    fakes: list[FakeOpenAI] = []

    def build(
        *steps: Step,
        default: Step | None = None,
        stores: Sequence[StoreConfig] | None = None,
        bodies: Mapping[str, Mapping[str, str]] | None = None,
        thumbnails: bool = False,
        settings_changes: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> Rig:
        shop = open_shop(
            world, router, stores or [store_for("alpha"), store_for("beta")], bodies=bodies
        )
        fake = FakeOpenAI(*steps, default=default)
        fakes.append(fake)
        options.setdefault("jitter", lambda: 0.5)
        understander = OpenAIUnderstander(
            make_settings(openai_model=MODEL),
            fake.client(),
            clock=clock,
            budget=CallBudget(),
            **options,
        )
        chosen = make_pipeline(understander=understander, stores=shop.stores, thumbnails=thumbnails)
        used = settings.model_copy(update=dict(settings_changes or {}))
        return Rig(chosen, fake, shop, used)

    yield build

    for fake in fakes:
        await fake.aclose()
        assert not fake.unexpected, "OpenAI received a request the test did not script"
