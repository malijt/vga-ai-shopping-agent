"""Answering "Who is this for?" (or choosing the gender chip) costs nothing: the products already
found are kept and the gender is applied to them (BRD Rule 8, Rule 2).

A search made before the shopper answered asks for no gender, because a guessed one is never
applied. What its stores returned therefore holds both audiences. When a re-run changes only a
garment's gender, the pipeline reuses those products instead of rebuilding keywords and searching
again: the ranker's gender rule drops the other gender's products, and a store that does not sell
for the gender is left out, as for any confirmed gender. No store is asked, OpenAI is not called,
no thumbnail is fetched and the image scores already worked out stand. Anything else that changes
(colour, category) is a new search.
"""

import pytest

from tests.factories import (
    make_chip_edits,
    make_item_intent,
    make_search_request,
    make_settings,
    make_understand_result,
)
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.fetch.conftest import shopify_product, suggest_body
from tests.pipeline.builders import OUTFIT, outfit_understander, photo_search, rerun
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import CDN_PREFIX, StoreWorld, store_for
from vga.models import (
    Category,
    Gender,
    GenderSource,
    InputType,
    ItemEdit,
    ItemIntent,
    MixPreset,
    SearchResponse,
    StoreStatus,
)
from vga.pipeline import messages
from vga.settings import Settings

GUESSED = make_item_intent(
    search_keywords=["black oversized blazer", "oversized blazer"],
    gender=Gender.MEN,
    gender_source=GenderSource.INFERRED,
)
"""A blazer the model guessed is for men. A guess excludes nothing."""

NO_GENDER = make_item_intent(search_keywords=["black oversized blazer", "oversized blazer"])


def mixed_blazers(tag: str) -> str:
    """Women's, men's and unstated blazers, as a store that sells for both would list them."""
    titled = [
        "Women's Black Oversized Blazer",
        "Men's Black Oversized Blazer",
        "Women's Black Tailored Blazer",
        "Men's Black Tailored Blazer",
        "Black Boxy Blazer",
    ]
    products = []
    for number, title in enumerate(titled, start=1):
        slug = f"blazer-{tag}-{number}"
        price = f"{100 + 30 * number}.00"
        products.append(
            shopify_product(
                number,
                title=f"{title} {tag.upper()}",
                price=price,
                price_min=price,
                price_max=price,
                handle=slug,
                id=5000 + number,
                image=f"{CDN_PREFIX}s/files/1/0001/{slug}.jpg?v=1",
                url=f"/products/{slug}?_pos={number}",
                type="Coats & Jackets",
            )
        )
    return suggest_body(*products)


@pytest.fixture
def stores(world: StoreWorld) -> None:
    """Two stores for everyone, a women-only store and a men-only store, all with both audiences'
    blazers except the single-gender ones, which sell only theirs."""
    for key in ("alpha", "beta"):
        world.add(store_for(key), bodies={"blazer": mixed_blazers(key)})
    world.add(store_for("womens", genders=[Gender.WOMEN]), bodies={"blazer": mixed_blazers("w")})
    world.add(store_for("mens", genders=[Gender.MEN]), bodies={"blazer": mixed_blazers("m")})


def answer(first: SearchResponse, gender: Gender, **kwargs: object):
    chips = make_chip_edits(items=[ItemEdit(index=0, gender=gender)])
    return rerun(first, chips=chips, **kwargs)  # type: ignore[arg-type]


def titles(response: SearchResponse) -> set[str]:
    return {scored.product.title for scored in response.products}


def total_requests(world: StoreWorld) -> int:
    return world.all_requests()


async def first_search(
    make_pipeline: PipelineMaker,
    settings: Settings,
    photo: bytes,
    item: ItemIntent = GUESSED,
    **options: object,
):
    understander = photo_search([item], InputType.PRODUCT_PHOTO)
    pipeline = make_pipeline(understander=understander, thumbnails=True, **options)  # type: ignore[arg-type]
    first = await pipeline.run(make_search_request(image=photo, text=None), settings)
    return pipeline, understander, first


# --------------------------------------------------------------------------------------------
# It costs nothing
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("gender", [Gender.WOMEN, Gender.MEN])
async def test_the_answer_makes_no_store_request_no_model_call_and_no_thumbnail_fetch(
    gender: Gender,
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    stores: None,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline, understander, first = await first_search(make_pipeline, settings, photo)
    assert make_pipeline.embedder is not None
    assert make_pipeline.ranker_spy is not None
    requests, thumbnails = total_requests(world), len(world.thumbnails)
    batches, ranked = len(make_pipeline.embedder.batch_sizes), len(make_pipeline.ranker_spy.calls)
    assert thumbnails > 0  # the first search really did fetch thumbnails

    request, overrides = answer(first, gender)
    second = await pipeline.run(request, settings, overrides)

    assert total_requests(world) == requests  # not robots.txt, not a search page, not an image
    assert len(world.thumbnails) == thumbnails
    assert len(understander.calls) == 1
    assert len(make_pipeline.embedder.batch_sizes) == batches  # the model did not run again
    assert len(make_pipeline.ranker_spy.calls) == ranked
    assert make_pipeline.spy is not None
    assert len(make_pipeline.spy.calls) == 4  # the first search's four stores; none since
    assert second.result_count > 0


async def test_the_answer_makes_no_search_step_and_no_image_step(
    make_pipeline: PipelineMaker, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    steps_before = [t.step for t in first.timings if t.store is None]
    assert "search" in steps_before
    assert "image_rank" in steps_before
    announced: list[str] = []

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, settings, overrides, lambda step: announced.append(step))

    assert "search" not in announced
    assert "image_rank" not in announced
    assert [t.step for t in second.timings if t.store is None and t.step == "search"] == []
    assert next(t for t in second.timings if t.step == "understand").status == "reused"


async def test_the_answer_takes_no_time_at_all_on_the_fake_clock(
    make_pipeline: PipelineMaker,
    stores: None,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    before = clock.monotonic()

    request, overrides = answer(first, Gender.WOMEN)
    await pipeline.run(request, settings, overrides)

    assert clock.monotonic() == before  # no queue to wait in, no thumbnail to wait for


# --------------------------------------------------------------------------------------------
# The gender is applied to what was found
# --------------------------------------------------------------------------------------------


async def test_before_the_answer_both_audiences_are_shown_and_after_it_only_the_answered_one(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    assert any("Men's" in title for title in titles(first))
    assert any("Women's" in title for title in titles(first))

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, settings, overrides)

    assert second.result_count > 0
    assert not any("Men's" in title for title in titles(second))
    assert any("Women's" in title for title in titles(second))
    assert any("Boxy" in title for title in titles(second))  # a product that states no gender stays


async def test_the_answer_leaves_out_the_stores_that_do_not_sell_for_it_with_a_plain_reason(
    make_pipeline: PipelineMaker, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    assert {r.store_id for r in first.stores_used} == {"alpha", "beta", "womens", "mens"}

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, settings, overrides)

    assert {r.store_id for r in second.stores_used} == {"alpha", "beta", "womens"}
    [skipped] = second.stores_skipped
    assert skipped.store_id == "mens"
    assert skipped.status is StoreStatus.EMPTY
    assert skipped.reason == "Not searched: Mens does not sell clothing for women."
    assert {scored.product.store for scored in second.products} == {"Alpha", "Beta", "Womens"}
    assert not any("Mens" in warning for warning in second.warnings)  # not a failure


async def test_the_answer_is_recorded_as_stated_and_the_keywords_carry_it(
    make_pipeline: PipelineMaker, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, settings, overrides)

    [item] = second.understood.items
    assert (item.gender, item.gender_source) == (Gender.WOMEN, GenderSource.EXPLICIT)
    assert item.search_keywords[0].endswith("women")  # what a fresh search would have sent
    assert messages.inferred_gender_note(Gender.MEN) not in second.warnings


async def test_a_store_that_failed_the_first_time_is_not_asked_again_by_the_answer(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    world.add(store_for("alpha"), bodies={"blazer": mixed_blazers("alpha")})
    world.add(store_for("beta"), bodies={"blazer": mixed_blazers("beta")}, status=500)
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    requests = total_requests(world)

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, settings, overrides)

    assert total_requests(world) == requests
    assert {r.store_id: r.status for r in second.stores_skipped} == {"beta": StoreStatus.ERROR}
    assert [r.store_id for r in second.stores_used] == ["alpha"]


async def test_a_second_answer_still_costs_nothing_and_is_applied_to_the_original_products(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    requests = total_requests(world)
    request, overrides = answer(first, Gender.WOMEN)
    women = await pipeline.run(request, settings, overrides)

    request, overrides = answer(women, Gender.MEN)  # the shopper changes their mind
    men = await pipeline.run(request, settings, overrides)

    assert total_requests(world) == requests
    assert not any("Women's" in title for title in titles(men))
    assert any("Men's" in title for title in titles(men))  # the men's products were kept
    assert {r.store_id for r in men.stores_used} == {"alpha", "beta", "mens"}


async def test_a_mix_change_after_an_answer_costs_nothing_and_keeps_the_answer(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    request, overrides = answer(first, Gender.WOMEN)
    women = await pipeline.run(request, settings, overrides)
    requests, thumbnails = total_requests(world), len(world.thumbnails)

    request, overrides = rerun(women, mix=MixPreset.VALUE_FIRST.mix)
    reshaped = await pipeline.run(request, settings, overrides)

    assert (total_requests(world), len(world.thumbnails)) == (requests, thumbnails)
    assert not any("Men's" in title for title in titles(reshaped))
    assert [r.store_id for r in reshaped.stores_skipped] == ["mens"]


async def test_every_garment_of_an_outfit_is_answered_without_a_request(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    for key in ("alpha", "beta"):
        world.add(store_for(key))
    world.add(store_for("mens", genders=[Gender.MEN]))
    guessed = [
        item.model_copy(update={"gender": Gender.MEN, "gender_source": GenderSource.INFERRED})
        for item in OUTFIT
    ]
    pipeline = make_pipeline(understander=outfit_understander(guessed))
    first = await pipeline.run(make_search_request(image=photo, text=None), settings)
    requests = total_requests(world)
    chips = make_chip_edits(
        items=[ItemEdit(index=index, gender=Gender.WOMEN) for index in range(len(guessed))]
    )

    request, overrides = rerun(first, chips=chips)
    second = await pipeline.run(request, settings, overrides)

    assert total_requests(world) == requests
    assert [g.item_index for g in second.groups] == [0, 1, 2, 3]
    assert all(g.result_count > 0 for g in second.groups)
    assert [r.store_id for r in second.stores_skipped] == ["mens"]
    assert [i.gender for i in second.understood.items] == [Gender.WOMEN] * 4


async def test_only_the_garment_that_was_answered_is_reused_when_another_one_changes_too(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    shirt = make_item_intent(
        category=Category.TOPS,
        colour="white",
        style="shirt",
        search_keywords=["white shirt", "cotton shirt"],
    )
    understander = FakeUnderstander(
        make_understand_result(input_type=InputType.TEXT, items=[NO_GENDER, shirt])
    )
    pipeline = make_pipeline(understander=understander)
    first = await pipeline.run(make_search_request(text="a blazer and a shirt"), settings)
    blazer_searches = [q for k in ("alpha", "beta") for q in world.queries(k) if "blazer" in q]
    chips = make_chip_edits(
        items=[ItemEdit(index=0, gender=Gender.WOMEN), ItemEdit(index=1, colour="red")]
    )

    request, overrides = rerun(first, chips=chips)
    await pipeline.run(request, settings, overrides)

    # The blazer was answered from what was found; the shirt, whose colour changed, was searched.
    assert [q for k in ("alpha", "beta") for q in world.queries(k) if "blazer" in q] == (
        blazer_searches
    )
    assert any("red" in q for q in world.queries("alpha"))


# --------------------------------------------------------------------------------------------
# What is NOT a gender-only change
# --------------------------------------------------------------------------------------------


def count_searches(world: StoreWorld) -> int:
    return world.search_requests()


async def test_a_new_colour_is_a_new_search(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    before = count_searches(world)
    chips = make_chip_edits(items=[ItemEdit(index=0, colour="red")])

    request, overrides = rerun(first, chips=chips)
    await pipeline.run(request, settings, overrides)

    assert count_searches(world) > before


async def test_a_new_colour_together_with_the_answer_is_a_new_search(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    before = count_searches(world)
    chips = make_chip_edits(items=[ItemEdit(index=0, colour="red", gender=Gender.WOMEN)])

    request, overrides = rerun(first, chips=chips)
    second = await pipeline.run(request, settings, overrides)

    assert count_searches(world) > before
    assert any("women" in q for q in world.queries("alpha"))
    assert second.understood.items[0].colour == "red"


async def test_a_new_category_is_a_new_search(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    before = count_searches(world)
    chips = make_chip_edits(items=[ItemEdit(index=0, category=Category.TOPS, gender=Gender.WOMEN)])

    request, overrides = rerun(first, chips=chips)
    await pipeline.run(request, settings, overrides)

    assert count_searches(world) > before


async def test_changing_a_gender_that_the_search_applied_is_a_new_search(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    for key in ("alpha", "beta"):
        world.add(store_for(key), bodies={"blazer": mixed_blazers(key)})
    stated = NO_GENDER.model_copy(
        update={"gender": Gender.MEN, "gender_source": GenderSource.EXPLICIT}
    )
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo, stated)
    before = count_searches(world)

    request, overrides = answer(first, Gender.WOMEN)  # the first search asked for men's blazers
    second = await pipeline.run(request, settings, overrides)

    # What the stores returned for "... men" is no basis for a women's search: ask again.
    assert count_searches(world) > before
    assert any("women" in q for q in world.queries("alpha"))
    assert second.understood.items[0].gender is Gender.WOMEN


async def test_an_answer_after_the_products_have_expired_is_a_new_search(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    stores: None,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    before = count_searches(world)
    clock.advance(settings.store_cache_ttl_s + 1)

    request, overrides = answer(first, Gender.WOMEN)
    await pipeline.run(request, settings, overrides)

    assert count_searches(world) > before


async def test_an_answer_that_needs_a_store_the_first_search_never_asked_is_a_new_search(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    stores: None,
    settings: Settings,
    photo: bytes,
    tmp_path,
) -> None:
    # The first search used only Alpha. A store that was not asked has no products to reuse.
    just_alpha = make_settings(stores=["alpha"], log_dir=str(tmp_path / "logs"))
    pipeline, _understander, first = await first_search(make_pipeline, just_alpha, photo)
    before = count_searches(world)

    request, overrides = answer(first, Gender.WOMEN)
    await pipeline.run(request, settings, overrides)  # all four stores are in use now

    assert count_searches(world) > before
    assert world.queries("beta")  # Beta, never asked before, is asked now


# --------------------------------------------------------------------------------------------
# Images: the scores already worked out stand, and nothing is fetched to work out more
# --------------------------------------------------------------------------------------------


async def test_the_image_scores_of_the_first_search_decide_the_order_after_the_answer(
    make_pipeline: PipelineMaker, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline, _understander, first = await first_search(make_pipeline, settings, photo)
    assert make_pipeline.ranker_spy is not None
    ranked = len(make_pipeline.ranker_spy.calls)

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, settings, overrides)

    assert len(make_pipeline.ranker_spy.calls) == ranked
    first_scores = {s.product.key: s.scores.image for s in first.products}
    kept = {s.product.key: s.scores.image for s in second.products}
    assert kept
    assert all(first_scores[key] == score for key, score in kept.items())
    assert any(score is not None for score in kept.values())


async def test_an_earlier_comparison_that_did_not_happen_is_not_tried_again_by_an_answer(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, photo: bytes, tmp_path
) -> None:
    siglip = make_settings(
        image_ranker="siglip", siglip_revision="0" * 40, log_dir=str(tmp_path / "logs")
    )
    ranker = FakeImageRanker(default=None)  # the model gives no score: the comparison "failed"
    pipeline = make_pipeline(
        understander=photo_search([GUESSED], InputType.PRODUCT_PHOTO),
        image_ranker=ranker,
        engine_settings=siglip,
    )
    first = await pipeline.run(make_search_request(image=photo, text=None), siglip)
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE in first.warnings
    requests, ranked = total_requests(world), len(ranker.calls)

    request, overrides = answer(first, Gender.WOMEN)
    second = await pipeline.run(request, siglip, overrides)

    assert (total_requests(world), len(ranker.calls)) == (requests, ranked)  # no thumbnail either
    assert world.thumbnails == []
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE in second.warnings  # and it still says so
    assert second.result_count > 0
