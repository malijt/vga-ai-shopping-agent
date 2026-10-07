"""Building the real pipeline from the settings (plan 13: ``build_pipeline`` and ``warm_up``).

Nothing here touches the network. OpenAI is faked where a test needs a model call; a test that must
not need one proves it by running without any key.
"""

import asyncio
import importlib.util

import pytest
import respx

from tests.factories import (
    make_item_intent,
    make_search_request,
    make_settings,
    make_understand_result,
)
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.world import StoreWorld, store_for
from vga.errors import ConfigError
from vga.interfaces import Pipeline
from vga.models import RunOverrides, SearchRequest
from vga.pipeline import LazyUnderstander, SearchPipeline, build_pipeline, pipeline_factory
from vga.settings import Settings
from vga.stores import StoreRegistry

PINNED = "c56244cc94f92419e8369fa71efdaf403b124ce8"
DATED_MODEL = "gpt-5-mini-2025-08-07"


@pytest.fixture(autouse=True)
def _no_key_and_no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """No OpenAI key in the environment, and no ``.env`` file to find one in."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("vga.understand.understander.load_dotenv", lambda *a, **k: [])


@pytest.fixture
def stores(world: StoreWorld) -> list:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    return stores


async def test_building_the_pipeline_touches_neither_the_network_nor_the_model(
    router: respx.MockRouter, stores: list, clock: FakeClock, settings: Settings
) -> None:
    pipeline = build_pipeline(settings, registry=StoreRegistry(stores), clock=clock)

    assert isinstance(pipeline, SearchPipeline)
    assert isinstance(pipeline, Pipeline)
    assert router.calls.call_count == 0
    await pipeline.aclose()


async def test_the_real_parts_search_the_stores_and_a_rerun_needs_no_openai_key(
    world: StoreWorld, stores: list, clock: FakeClock, settings: Settings
) -> None:
    pipeline = build_pipeline(settings, registry=StoreRegistry(stores), clock=clock)
    overrides = RunOverrides(
        understood=make_understand_result(
            items=[make_item_intent(search_keywords=["black oversized blazer"])]
        )
    )

    # The earlier understanding comes with the request, so no model call, so no key is needed.
    response = await pipeline.run(SearchRequest(rerun_of="earlier"), settings, overrides)
    await pipeline.aclose()

    assert response.result_count > 0
    assert world.queries("alpha") == ["black oversized blazer"]
    assert {r.strategy for r in response.stores_used} == {"shopify"}


async def test_a_text_search_without_an_api_key_is_a_plain_error_raised_only_then(
    world: StoreWorld, stores: list, clock: FakeClock
) -> None:
    configured = make_settings(openai_model=DATED_MODEL)
    pipeline = build_pipeline(
        configured, registry=StoreRegistry(stores), clock=clock
    )  # no error yet

    with pytest.raises(ConfigError) as caught:
        await pipeline.run(make_search_request(text="black blazer"), configured)
    await pipeline.aclose()

    assert "OpenAI API key is missing" in caught.value.user_message
    assert "sk-" not in caught.value.user_message
    assert world.all_requests() == 0  # no store was contacted for a request that cannot be read


async def test_a_text_search_without_a_model_is_a_plain_error(
    world: StoreWorld, stores: list, clock: FakeClock, settings: Settings
) -> None:
    assert settings.openai_model is None
    pipeline = build_pipeline(settings, registry=StoreRegistry(stores), clock=clock)

    with pytest.raises(ConfigError) as caught:
        await pipeline.run(make_search_request(text="black blazer"), settings)
    await pipeline.aclose()

    assert "model is not set up" in caught.value.user_message


async def test_closing_twice_is_harmless(
    stores: list, clock: FakeClock, settings: Settings
) -> None:
    pipeline = build_pipeline(settings, registry=StoreRegistry(stores), clock=clock)

    await pipeline.aclose()
    await pipeline.aclose()


# --------------------------------------------------------------------------------------------
# warm_up
# --------------------------------------------------------------------------------------------


async def test_warming_up_with_the_image_ranker_off_has_nothing_to_load(
    stores: list, clock: FakeClock, settings: Settings
) -> None:
    assert settings.image_ranker == "off"
    pipeline = build_pipeline(settings, registry=StoreRegistry(stores), clock=clock)

    assert await pipeline.warm_up() is True
    await pipeline.aclose()


async def test_warming_up_reports_false_instead_of_raising_when_the_model_is_missing(
    stores: list, clock: FakeClock
) -> None:
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("the ml packages are installed here, so the model may really load")
    siglip = make_settings(image_ranker="siglip", siglip_revision=PINNED)
    pipeline = build_pipeline(siglip, registry=StoreRegistry(stores), clock=FakeClock())

    assert await pipeline.warm_up() is False  # text and price ranking will carry the search
    await pipeline.aclose()


async def test_warm_up_asks_the_image_ranker_that_has_one(stores: list) -> None:
    class Ready(FakeImageRanker):
        async def warm_up(self) -> bool:
            return True

    class Missing(FakeImageRanker):
        async def warm_up(self) -> bool:
            return False

    ready = SearchPipeline(FakeUnderstander(), _NoSearch(), Ready(), stores)
    missing = SearchPipeline(FakeUnderstander(), _NoSearch(), Missing(), stores)
    plain = SearchPipeline(FakeUnderstander(), _NoSearch(), FakeImageRanker(), stores)

    assert await ready.warm_up() is True
    assert await missing.warm_up() is False
    assert await plain.warm_up() is True  # a ranker with nothing to load is always ready


class _NoSearch:
    async def search(self, item, stores):  # type: ignore[no-untyped-def]
        return []


# --------------------------------------------------------------------------------------------
# The lazy understander
# --------------------------------------------------------------------------------------------


class _CountingModel:
    """Stands in for ``OpenAIUnderstander`` and counts how many were built."""

    built = 0

    def __init__(self, settings: Settings, clock: object = None) -> None:
        type(self).built += 1

    async def understand(self, req: SearchRequest):  # type: ignore[no-untyped-def]
        return make_understand_result()


def test_the_model_understander_is_built_on_first_use_and_again_for_a_new_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CountingModel.built = 0
    monkeypatch.setattr("vga.pipeline.build.OpenAIUnderstander", _CountingModel)
    lazy = LazyUnderstander(make_settings())
    assert _CountingModel.built == 0  # nothing is built just by creating it

    async def twice() -> None:
        await lazy.understand(make_search_request(text="a"))
        await lazy.understand(make_search_request(text="b"))

    asyncio.run(twice())
    assert _CountingModel.built == 1  # once for a loop, however many requests
    asyncio.run(twice())  # a UI that runs asyncio.run for every search starts a new loop
    assert _CountingModel.built == 2


# --------------------------------------------------------------------------------------------
# Binding for the acceptance harness
# --------------------------------------------------------------------------------------------


async def test_the_factory_builds_a_pipeline_from_the_three_boundaries(
    world: StoreWorld, stores: list, clock: FakeClock, settings: Settings
) -> None:
    from vga.stores import StoreSearchEngine

    engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
    factory = pipeline_factory(stores, clock=clock)

    pipeline = factory(FakeUnderstander(), engine, FakeImageRanker())
    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    await engine.aclose()

    assert isinstance(pipeline, Pipeline)
    assert response.result_count > 0
    assert {r.store_id for r in response.stores_used} == {"alpha", "beta"}
