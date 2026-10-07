"""Plan 13.1.5 (assumption A8): changing only the mix or the budget re-shapes the products already
found; changing what is searched searches again, still without calling OpenAI and without the photo.

Every count is asserted at the boundary: store requests and thumbnail requests are counted on the
fake network, OpenAI calls on the fake understander, and model calls on the fake embedder.
"""

from dataclasses import dataclass

import pytest

from tests.factories import (
    make_budget,
    make_chip_edits,
    make_search_request,
    make_understand_result,
)
from tests.fakes import FakeClock, FakeUnderstander
from tests.pipeline.builders import BLAZER, SHIRT, photo_search, rerun
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from vga.errors import InvalidInputError
from vga.models import (
    Category,
    Flag,
    InputType,
    ItemEdit,
    MixPreset,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    Step,
)
from vga.pipeline.rerun import MAX_REQUESTS, CachedItem, CachedRun, RerunCache
from vga.settings import Settings


@dataclass(frozen=True)
class Counts:
    """Everything that costs something, read off the boundaries."""

    http: int
    searches: int
    thumbnails: int
    openai: int
    model_batches: int
    searcher_calls: int
    ranker_calls: int


def counts(world: StoreWorld, understander: FakeUnderstander, maker: PipelineMaker) -> Counts:
    assert maker.spy is not None
    assert maker.ranker_spy is not None
    assert maker.embedder is not None
    return Counts(
        http=world.all_requests(),
        searches=world.search_requests(),
        thumbnails=len(world.thumbnails),
        openai=len(understander.calls),
        model_batches=len(maker.embedder.batch_sizes),
        searcher_calls=len(maker.spy.calls),
        ranker_calls=len(maker.ranker_spy.calls),
    )


def urls(response: SearchResponse) -> set[str]:
    return {scored.product.product_url for scored in response.products}


# --------------------------------------------------------------------------------------------
# A mix or budget change re-shapes what is cached
# --------------------------------------------------------------------------------------------


async def test_changing_only_the_mix_makes_no_store_request_no_thumbnail_fetch_no_model_call(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)
    assert before.searches > 0
    assert before.thumbnails > 0
    assert before.openai == 1

    request, overrides = rerun(first, mix=MixPreset.LUXURY_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert counts(world, understander, make_pipeline) == before
    assert [[t.target_count for t in g.tiers] for g in second.groups] == [[3, 6, 9, 12]]
    assert [[t.target_count for t in g.tiers] for g in first.groups] == [[8, 8, 7, 7]]
    assert second.result_count > 0


async def test_a_reshaped_response_is_the_same_search_seen_through_a_different_mix(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert second.understood == first.understood
    assert second.query_embedding == first.query_embedding
    assert second.usage.llm_calls == 0  # this request cost no model call
    assert first.usage.llm_calls == 1
    assert [r.store_id for r in second.stores_used] == [r.store_id for r in first.stores_used]
    # a product shown both times keeps the image score it was given the first time
    earlier = {s.product.product_url: s.scores.image for s in first.products}
    shared = [s for s in second.products if s.product.product_url in earlier]
    assert shared
    assert all(s.scores.image == earlier[s.product.product_url] for s in shared)
    assert any(s.scores.image is not None for s in shared)


async def test_the_reused_stores_are_reported_as_cached_and_cost_no_time(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=photo_search(), thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert all(not report.from_cache for report in first.stores_used)
    assert all(report.from_cache for report in second.stores_used)
    assert all(report.duration_ms == 0 for report in second.stores_used)
    assert {report.product_count for report in second.stores_used} == {
        report.product_count for report in first.stores_used
    }


async def test_a_rerun_reports_only_the_steps_it_really_runs(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=photo_search(), thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    seen: list[Step] = []

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides, on_step=seen.append)

    assert seen == [
        Step.VALIDATE,
        Step.UNDERSTAND,
        Step.FILTER,
        Step.RANK,
        Step.SHAPE,
        Step.ASSEMBLE,
    ]
    understanding = next(t for t in second.timings if t.step == "understand")
    assert understanding.status == "reused"


async def test_changing_only_the_budget_makes_no_store_request_and_no_model_call(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)

    request, overrides = rerun(first, budget=make_budget(max_price=200))
    second = await pipeline.run(request, settings, overrides)

    assert counts(world, understander, make_pipeline) == before
    group = second.groups[0]
    for tier in group.tiers[:2]:  # Budget and Mid-range stay within the budget
        assert all(s.product.price <= 200 for s in tier.results)
    over = [s for s in second.products if s.product.price > 200]
    assert over  # premium and luxury may go over, and say so
    assert all(Flag.OVER_BUDGET in s.flags for s in over)
    assert not any(Flag.OVER_BUDGET in s.flags for s in first.products)


async def test_a_budget_typed_in_the_chips_also_re_shapes_without_searching(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)

    request, overrides = rerun(first, chips=make_chip_edits(budget=make_budget(max_price=150)))
    second = await pipeline.run(request, settings, overrides)

    assert counts(world, understander, make_pipeline) == before
    assert second.understood.budget == make_budget(max_price=150)
    assert all(s.product.price <= 150 for s in second.groups[0].tiers[0].results)


async def test_a_text_request_re_shapes_too(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, settings: Settings
) -> None:
    understander = FakeUnderstander()
    pipeline = make_pipeline(understander=understander)
    first = await pipeline.run(make_search_request(text="black oversized blazer"), settings)
    http_before, openai_before = world.all_requests(), len(understander.calls)

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert world.all_requests() == http_before
    assert len(understander.calls) == openai_before
    assert [t.target_count for t in second.groups[0].tiers] == [12, 9, 6, 3]


# --------------------------------------------------------------------------------------------
# A chip edit that changes what is searched searches again, with no model call
# --------------------------------------------------------------------------------------------


async def test_a_changed_colour_searches_again_without_openai_and_without_the_photo(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)
    edit = make_chip_edits(items=[ItemEdit(index=0, colour="brown")])

    request, overrides = rerun(first, chips=edit)
    second = await pipeline.run(request, settings, overrides)

    after = counts(world, understander, make_pipeline)
    assert after.openai == before.openai == 1  # no second OpenAI call
    assert after.searches > before.searches  # the stores were asked again
    assert after.searcher_calls == before.searcher_calls + 2  # one search per store
    assert any("brown" in query for query in world.queries("alpha"))
    assert second.understood.items[0].colour == "brown"
    assert second.usage.llm_calls == 0


async def test_the_second_search_scores_the_images_from_the_stored_embedding(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    assert first.query_embedding is not None
    edit = make_chip_edits(items=[ItemEdit(index=0, colour="brown")])

    request, overrides = rerun(first, chips=edit)
    second = await pipeline.run(request, settings, overrides)

    assert make_pipeline.ranker_spy is not None
    first_call, second_call = make_pipeline.ranker_spy.calls
    assert (first_call.had_photo, first_call.had_embedding) == (True, False)
    assert (second_call.had_photo, second_call.had_embedding) == (False, True)
    assert any(s.scores.image is not None for s in second.products)
    assert second.query_embedding == first.query_embedding


async def test_an_unchanged_garment_is_not_searched_again_when_another_one_is_edited(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search([BLAZER, SHIRT], InputType.OUTFIT_PHOTO)
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text=None), settings)
    assert make_pipeline.spy is not None
    assert len(make_pipeline.spy.calls) == 4  # two garments, two stores
    alpha_before = len(world.queries("alpha"))
    edit = make_chip_edits(items=[ItemEdit(index=1, colour="blue")])

    request, overrides = rerun(first, chips=edit)
    second = await pipeline.run(request, settings, overrides)

    assert [call.category for call in make_pipeline.spy.calls[4:]] == [Category.TOPS] * 2
    assert all("shirt" in q or "blue" in q for q in world.queries("alpha")[alpha_before:])
    assert [group.category for group in second.groups] == [Category.OUTERWEAR, Category.TOPS]
    blazers_before = {s.product.product_url for s in first.groups[0].tiers[0].results}
    blazers_after = {s.product.product_url for s in second.groups[0].tiers[0].results}
    assert blazers_after == blazers_before  # served from the cache, shaped the same way


async def test_a_chip_edit_that_changes_nothing_is_a_pure_reshape(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)

    request, overrides = rerun(
        first, chips=make_chip_edits(items=[ItemEdit(index=0, category=Category.OUTERWEAR)])
    )
    await pipeline.run(request, settings, overrides)

    assert counts(world, understander, make_pipeline) == before


# --------------------------------------------------------------------------------------------
# When the cache cannot answer, the pipeline simply searches
# --------------------------------------------------------------------------------------------


async def test_an_expired_entry_falls_back_to_a_normal_search(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)
    clock.advance(settings.store_cache_ttl_s + 1)

    request, overrides = rerun(first, mix=MixPreset.LUXURY_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    after = counts(world, understander, make_pipeline)
    assert after.searches > before.searches  # real requests again
    assert after.openai == before.openai  # the understanding is still reused
    assert [[t.target_count for t in g.tiers] for g in second.groups] == [[3, 6, 9, 12]]
    assert second.result_count > 0


async def test_an_entry_just_inside_the_lifetime_is_still_used(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    before = counts(world, understander, make_pipeline)
    # The lifetime counts from when the stores were asked (about 2 s into the first run, which
    # then took 3 s more on thumbnails), so 10 s short of it leaves a margin.
    clock.advance(settings.store_cache_ttl_s - 10)

    request, overrides = rerun(first, mix=MixPreset.LUXURY_FIRST.mix)
    await pipeline.run(request, settings, overrides)

    assert counts(world, understander, make_pipeline) == before


async def test_a_rerun_does_not_make_old_products_live_longer(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    clock.advance(400)
    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)
    before = counts(world, understander, make_pipeline)
    clock.advance(300)  # 700 s after the stores were asked, over the 600 s lifetime

    request, overrides = rerun(second, mix=MixPreset.LUXURY_FIRST.mix)
    await pipeline.run(request, settings, overrides)

    assert counts(world, understander, make_pipeline).searches > before.searches


async def test_products_age_from_when_their_store_answered_not_from_when_it_was_collected(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    # The first garment is slow (about ten seconds); the second comes back in about a second but
    # is only collected after the first, because garments are collected in order.
    world.add(store_for("alpha"), delay=lambda query: 5.0 if "blazer" in query else 0.0)
    pipeline = make_pipeline(understander=photo_search([BLAZER, SHIRT], InputType.OUTFIT_PHOTO))
    started = clock.monotonic()

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    cached = pipeline._cache.get(response.request_id)
    assert cached is not None
    blazers, shirts = cached.items[0], cached.items[1]
    ttl = settings.store_cache_ttl_s
    assert shirts.expires_at - ttl < started + 5  # stamped when the shirts came back
    assert blazers.expires_at - shirts.expires_at > 5  # the slow blazers are younger
    assert response.duration_ms > 10_000


async def test_a_rerun_of_a_request_the_process_never_saw_searches_normally(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, settings: Settings
) -> None:
    understander = FakeUnderstander()
    pipeline = make_pipeline(understander=understander)
    earlier = make_understand_result(items=[BLAZER])
    request = SearchRequest(rerun_of="from-a-process-that-restarted")
    overrides = RunOverrides(understood=earlier)

    response = await pipeline.run(request, settings, overrides)

    assert world.search_requests() > 0
    assert understander.calls == []  # the understanding still came with the request
    assert response.result_count > 0


async def test_a_rerun_that_brings_a_new_photo_is_a_new_search(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    understander = photo_search()
    pipeline = make_pipeline(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    assert make_pipeline.spy is not None
    assert make_pipeline.ranker_spy is not None
    searches_before = len(make_pipeline.spy.calls)

    _, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    another = SearchRequest(image=photo, rerun_of=first.request_id)
    await pipeline.run(another, settings, overrides)

    assert len(make_pipeline.spy.calls) == searches_before + 2
    new_call = make_pipeline.ranker_spy.calls[-1]
    assert (new_call.had_photo, new_call.had_embedding) == (True, False)  # the new photo wins


async def test_the_earlier_understanding_without_a_rerun_id_still_skips_openai(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, settings: Settings
) -> None:
    understander = FakeUnderstander()
    pipeline = make_pipeline(understander=understander)
    overrides = RunOverrides(understood=make_understand_result(items=[BLAZER]))

    response = await pipeline.run(make_search_request(text="black blazer"), settings, overrides)

    assert understander.calls == []
    assert response.usage.llm_calls == 0
    assert response.result_count > 0


# --------------------------------------------------------------------------------------------
# The cache itself
# --------------------------------------------------------------------------------------------


def test_the_cache_keeps_a_bounded_number_of_requests(clock: FakeClock) -> None:
    cache = RerunCache(clock)

    for number in range(MAX_REQUESTS + 8):
        cache.put(f"request-{number}", CachedRun())

    assert len(cache) == MAX_REQUESTS
    assert cache.get("request-0") is None  # the oldest went first
    assert cache.get(f"request-{MAX_REQUESTS + 7}") is not None


def test_a_missing_request_id_finds_nothing(clock: FakeClock) -> None:
    assert RerunCache(clock).get(None) is None
    assert RerunCache(clock).get("unknown") is None


def cached_blazer(
    expires_at: float = 2000.0, stores: tuple[str, ...] = ("alpha", "beta")
) -> CachedItem:
    return CachedItem(
        item=BLAZER,
        store_ids=stores,
        products=(),
        image_scores={},
        reports=(),
        searched_ids=frozenset(stores),
        expires_at=expires_at,
    )


def test_an_entry_is_reusable_only_for_the_same_item_the_same_stores_and_before_it_expires(
    clock: FakeClock,
) -> None:
    cache = RerunCache(clock)  # the fake clock starts at 1000 s
    run = CachedRun(items={0: cached_blazer()})
    both = ("alpha", "beta")

    assert cache.reusable(run, 0, BLAZER, both) is not None
    assert cache.reusable(run, 1, BLAZER, both) is None  # another position
    assert cache.reusable(run, 0, SHIRT, both) is None  # another item
    assert cache.reusable(run, 0, BLAZER.model_copy(update={"colour": "red"}), both) is None
    assert cache.reusable(run, 0, BLAZER, ("alpha",)) is None  # other stores
    assert cache.reusable(None, 0, BLAZER, both) is None
    clock.advance(1000)
    assert cache.reusable(run, 0, BLAZER, both) is None  # expired exactly now


async def test_chips_with_no_earlier_understanding_are_applied_to_a_fresh_one(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    understander = FakeUnderstander(make_understand_result(items=[BLAZER]))
    pipeline = make_pipeline(understander=understander)
    chips = make_chip_edits(items=[ItemEdit(index=0, colour="brown")])

    response = await pipeline.run(
        make_search_request(text="a blazer"), settings, RunOverrides(chips=chips)
    )

    assert len(understander.calls) == 1
    assert response.understood.items[0].colour == "brown"
    assert make_pipeline.spy is not None
    sent = [keyword for call in make_pipeline.spy.calls for keyword in call.keywords]
    assert any("brown" in keyword for keyword in sent)


async def test_a_chip_edit_for_a_garment_that_does_not_exist_is_a_plain_error(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, settings: Settings
) -> None:
    pipeline = make_pipeline()
    overrides = RunOverrides(
        chips=make_chip_edits(items=[ItemEdit(index=3, colour="red")]),
        understood=make_understand_result(items=[BLAZER]),
    )

    with pytest.raises(InvalidInputError) as caught:
        await pipeline.run(SearchRequest(rerun_of="earlier"), settings, overrides)

    assert caught.value.code == "invalid_input"
    assert world.all_requests() == 0
