"""Plan 13.2.3: the response carries everything the page and the acceptance run need: the stores
used and skipped (with reasons), the warnings, the usage, the timings and the request id."""

from tests.factories import (
    make_budget,
    make_item_intent,
    make_search_request,
    make_understand_result,
)
from tests.fakes import FakeImageRanker, FakeUnderstander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from vga.models import (
    RunOverrides,
    SearchResponse,
    SettingsOverride,
    StoreStatus,
    Usage,
)
from vga.settings import Settings


async def run_two_store_search(
    make_pipeline: PipelineMaker, settings: Settings, **kwargs: object
) -> SearchResponse:
    pipeline = make_pipeline(**kwargs)  # type: ignore[arg-type]
    return await pipeline.run(make_search_request(text="black oversized blazer"), settings)


async def test_the_response_validates_as_a_search_response_and_survives_a_json_round_trip(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    response = await run_two_store_search(make_pipeline, settings)

    again = SearchResponse.model_validate_json(response.model_dump_json())

    assert again == response


async def test_the_request_id_is_the_one_the_request_carried(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    request = make_search_request(text="black oversized blazer")

    response = await make_pipeline().run(request, settings)

    assert response.request_id == request.request_id


async def test_stores_used_hold_only_stores_that_gave_products_and_skipped_ones_have_reasons(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta"), status=403)
    world.add(store_for("gamma"), bodies={})

    response = await run_two_store_search(make_pipeline, settings)

    assert [(r.store_id, r.status) for r in response.stores_used] == [("alpha", StoreStatus.OK)]
    assert {r.store_id: r.status for r in response.stores_skipped} == {
        "beta": StoreStatus.BLOCKED,
        "gamma": StoreStatus.EMPTY,
    }
    assert all(r.reason for r in response.stores_skipped)
    [used] = response.stores_used
    assert used.product_count == 8
    assert used.strategy == "shopify"
    assert used.reason is None


async def test_every_store_appears_once_in_the_order_it_was_configured(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    for key in ("zulu", "alpha", "mike"):
        world.add(store_for(key))

    response = await run_two_store_search(make_pipeline, settings)

    assert [r.store_id for r in response.stores_used] == ["zulu", "alpha", "mike"]


async def test_the_understanding_usage_is_the_responses_usage(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    usage = Usage(input_tokens=321, output_tokens=45, llm_calls=2)
    understander = FakeUnderstander(make_understand_result(usage=usage))

    response = await run_two_store_search(make_pipeline, settings, understander=understander)

    assert response.usage == usage
    assert response.understood.usage == usage


async def test_the_duration_covers_the_whole_run_on_the_pipelines_clock(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    response = await run_two_store_search(make_pipeline, settings)

    # two stores, two keyword variants each, one second apart (BRD Rule 2)
    assert response.duration_ms >= 1000
    step_total = sum(t.duration_ms for t in response.timings if t.store is None)
    assert response.duration_ms >= step_total


async def test_the_understanding_warnings_come_first_and_nothing_repeats(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    understood = make_understand_result(
        warnings=["Please check the colour.", "Please check the colour."]
    )
    understander = FakeUnderstander(understood)

    response = await run_two_store_search(make_pipeline, settings, understander=understander)

    assert response.warnings[0] == "Please check the colour."
    assert len(response.warnings) == len(set(response.warnings))


async def test_the_shapers_currency_warning_is_merged_into_the_response(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta"))
    world.add(store_for("dollars", currency="USD"))  # prices in another currency

    response = await run_two_store_search(make_pipeline, settings)

    [note] = [w for w in response.warnings if "more than one currency" in w]
    assert "USD" in note
    assert {s.product.currency for s in response.products} == {"AED"}  # never converted


async def test_a_budget_in_another_currency_is_reported_not_applied(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    pipeline = make_pipeline()
    overrides = RunOverrides(
        settings=SettingsOverride(budget=make_budget(max_price=100, currency="USD"))
    )

    response = await pipeline.run(
        make_search_request(text="black oversized blazer"), settings, overrides
    )

    assert any("Your budget is in USD" in w for w in response.warnings)


async def test_the_response_excludes_the_query_embedding_from_its_json(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(image_ranker=FakeImageRanker(embedding=[0.25, 0.5, 0.75]))

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    assert response.query_embedding == [0.25, 0.5, 0.75]
    assert "0.25" not in response.model_dump_json()
    assert "query_embedding" not in response.model_dump_json()


async def test_a_product_keeps_its_reason_and_both_scores(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    understander = FakeUnderstander(
        make_understand_result(items=[make_item_intent(colour="black")])
    )
    pipeline = make_pipeline(understander=understander, image_ranker=FakeImageRanker(default=0.8))

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    for scored in response.products:
        assert scored.reason
        assert scored.tier is not None
        assert scored.scores.image == 0.8
        assert 0 < scored.scores.total <= 1
