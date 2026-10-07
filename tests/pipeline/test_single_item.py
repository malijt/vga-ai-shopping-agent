"""Plan 13.1.2: a single item, from request to response, through the REAL engine, ranker and
price-range shaper. Only the stores' HTTP, OpenAI and the image model are faked."""

import logging
from collections import Counter

import pytest

from tests.factories import make_item_intent, make_search_request, make_understand_result
from tests.fakes import FakeImageRanker, FakeUnderstander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld
from vga.models import (
    Category,
    GenderSource,
    InputType,
    Step,
    StoreConfig,
    StoreStatus,
    Tier,
)
from vga.settings import Settings

STEP_NAMES = [step.value for step in Step]


async def test_a_text_request_gives_a_full_response_with_a_timing_for_each_step(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list[StoreConfig],
    settings: Settings,
) -> None:
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, settings)

    steps = [timing.step for timing in response.timings if timing.store is None]
    # No photo, so no image step; every other step is timed, once, in order.
    assert steps == [name for name in STEP_NAMES if name != Step.IMAGE_RANK.value]
    assert response.request_id == request.request_id
    assert response.duration_ms > 0
    assert response.result_count > 0
    assert [group.category for group in response.groups] == [Category.OUTERWEAR]


async def test_each_store_has_its_own_fetch_timing_before_the_search_step(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    names = [(timing.step, timing.store) for timing in response.timings]
    fetches = [store for step, store in names if step == "fetch"]
    assert fetches == ["alpha", "beta"]
    assert names.index(("fetch", "beta")) < names.index(("search", None))
    assert all(timing.status == "ok" for timing in response.timings)


async def test_the_steps_are_reported_to_on_step_in_order(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    pipeline = make_pipeline()
    seen: list[Step] = []

    await pipeline.run(
        make_search_request(text="black oversized blazer"), settings, on_step=seen.append
    )

    assert seen == [
        Step.VALIDATE,
        Step.UNDERSTAND,
        Step.SEARCH,
        Step.FILTER,
        Step.RANK,
        Step.SHAPE,
        Step.ASSEMBLE,
    ]


async def test_a_photo_adds_the_image_step_between_ranking_and_shaping(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(
        understander=FakeUnderstander(make_understand_result(input_type=InputType.PRODUCT_PHOTO))
    )
    seen: list[Step] = []

    response = await pipeline.run(
        make_search_request(image=photo, text=None), settings, on_step=seen.append
    )

    assert seen[3:6] == [Step.FILTER, Step.RANK, Step.IMAGE_RANK]
    assert Step.IMAGE_RANK.value in [timing.step for timing in response.timings]


async def test_the_four_price_ranges_are_filled_from_both_stores(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    [group] = response.groups
    assert [tier.name for tier in group.tiers] == list(Tier)
    assert {s.product.store for s in response.products} == {"Alpha", "Beta"}
    assert [report.store_id for report in response.stores_used] == ["alpha", "beta"]
    assert response.stores_skipped == []
    # 16 blazers were offered (8 per store), but no store may supply more than 6 (PRD R9).
    assert response.result_count == 12
    assert Counter(scored.product.store for scored in response.products) == {"Alpha": 6, "Beta": 6}


async def test_the_search_uses_the_keywords_the_understander_chose_and_nothing_else(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list[StoreConfig],
    settings: Settings,
) -> None:
    item = make_item_intent(search_keywords=["black oversized blazer", "oversized blazer"])
    pipeline = make_pipeline(understander=FakeUnderstander(make_understand_result(items=[item])))

    await pipeline.run(make_search_request(text="black oversized blazer under 400 AED"), settings)

    assert world.queries("alpha") == ["black oversized blazer", "oversized blazer"]
    assert world.queries("beta") == ["black oversized blazer", "oversized blazer"]


async def test_the_usage_of_the_understanding_is_reported(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert response.usage.llm_calls == 1
    assert response.usage == response.understood.usage


async def test_an_inferred_gender_is_shown_as_a_note_and_keeps_every_store(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    item = make_item_intent(gender="men", gender_source=GenderSource.INFERRED)
    pipeline = make_pipeline(understander=FakeUnderstander(make_understand_result(items=[item])))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert any("guessed" in warning and "men" in warning for warning in response.warnings)
    assert {report.store_id for report in response.stores_used} == {"alpha", "beta"}
    assert response.understood.items[0].gender_source is GenderSource.INFERRED


async def test_the_image_ranker_is_not_asked_when_there_is_no_photo(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    ranker = FakeImageRanker()
    pipeline = make_pipeline(image_ranker=ranker)

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert ranker.calls == []
    assert all(scored.scores.image is None for scored in response.products)
    assert response.query_embedding is None


async def test_stores_that_gave_products_are_reported_as_used_with_their_strategy(
    make_pipeline: PipelineMaker, two_stores: list[StoreConfig], settings: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert {report.status for report in response.stores_used} == {StoreStatus.OK}
    assert {report.strategy for report in response.stores_used} == {"shopify"}
    assert all(report.product_count == 8 for report in response.stores_used)


async def test_every_log_line_of_a_run_carries_its_request_id(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="vga")
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    await pipeline.run(request, settings)

    ours = [r for r in caplog.records if r.name.startswith("vga")]
    assert {r.name.split(".")[1] for r in ours} >= {"pipeline", "stores", "timing"}
    assert {getattr(r, "request_id", None) for r in ours} == {request.request_id}
    # a second request does not borrow the first one's id
    other = make_search_request(text="black oversized blazer")
    caplog.clear()
    await pipeline.run(other, settings)
    assert {getattr(r, "request_id", None) for r in caplog.records if r.name.startswith("vga")} == {
        other.request_id
    }
