"""An outfit photo is not compared with product thumbnails (PRD R8 asks for that only when the
request has a product photo; an outfit photo gets one search per garment, grouped).

Why: thumbnails come from one shared image host at about five a second, so two garments mean up to
eighty of them and four garments cannot fit in the 30 s request deadline. A whole-outfit photo is
also a poor likeness for a single garment's thumbnail. The skip is by design, so it is not
reported as a failure: no "image similarity was not available" warning.

Everything is counted at the boundary: thumbnail requests on the fake image host, model calls on the
fake embedder, and the calls the image ranker received.
"""

import pytest

from tests.factories import make_search_request, make_settings, make_understand_result
from tests.fakes import FakeUnderstander
from tests.pipeline.builders import BLAZER, OUTFIT, outfit_understander, photo_search, rerun
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld
from vga.models import InputType, MixPreset, RunOverrides, SearchRequest, Step
from vga.pipeline import messages
from vga.settings import Settings


@pytest.fixture
def siglip(tmp_path) -> Settings:
    """Settings that expect image scores, so a missing comparison would be warned about."""
    return make_settings(image_ranker="siglip", log_dir=str(tmp_path / "logs"))


async def test_an_outfit_photo_fetches_no_thumbnail_and_runs_no_model(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    siglip: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]), thumbnails=True)

    await pipeline.run(make_search_request(image=photo, text=None), siglip)

    assert world.thumbnails == []
    assert make_pipeline.embedder is not None
    assert make_pipeline.embedder.batch_sizes == []  # the photo was not embedded either
    assert make_pipeline.ranker_spy is not None
    assert make_pipeline.ranker_spy.calls == []


async def test_an_outfit_photo_gives_no_image_scores_no_embedding_and_no_warning(
    make_pipeline: PipelineMaker, two_stores: list, siglip: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]), thumbnails=True)

    response = await pipeline.run(make_search_request(image=photo, text=None), siglip)

    assert response.result_count > 0
    assert all(scored.scores.image is None for scored in response.products)
    assert response.query_embedding is None
    # "Not available" would mean something broke. Nothing broke: the comparison is not made.
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in response.warnings
    assert response.warnings == []


async def test_a_four_garment_outfit_still_ranks_every_garment_on_text_and_price(
    make_pipeline: PipelineMaker, two_stores: list, siglip: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(), thumbnails=True)

    response = await pipeline.run(make_search_request(image=photo, text=None), siglip)

    assert len(response.groups) == 4
    assert all(group.result_count > 0 for group in response.groups)
    scores = [scored.scores for scored in response.products]
    assert all(score.total > 0 for score in scores)


async def test_the_skipped_step_is_in_the_timings_and_is_not_announced_as_a_step_that_runs(
    make_pipeline: PipelineMaker, two_stores: list, siglip: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]))
    seen: list[Step] = []

    response = await pipeline.run(
        make_search_request(image=photo, text=None), siglip, on_step=seen.append
    )

    # The progress display never says "Comparing products with your photo" for it ...
    assert Step.IMAGE_RANK not in seen
    # ... but the timings keep the step, in its place, marked as skipped (as the understand step
    # of a re-run is marked "reused").
    steps = [timing.step for timing in response.timings if timing.store is None]
    assert steps.index("image_rank") == steps.index("rank") + 1
    assert steps.index("shape") == steps.index("image_rank") + 1
    [skipped] = [timing for timing in response.timings if timing.step == "image_rank"]
    assert skipped.status == "skipped"
    assert skipped.duration_ms == 0


@pytest.mark.parametrize("input_type", [InputType.PRODUCT_PHOTO, InputType.PHOTO_TEXT])
async def test_a_product_photo_and_a_photo_with_text_are_still_compared(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    siglip: Settings,
    photo: bytes,
    input_type: InputType,
) -> None:
    pipeline = make_pipeline(understander=photo_search(input_type=input_type), thumbnails=True)
    text = "black blazer" if input_type is InputType.PHOTO_TEXT else None

    response = await pipeline.run(make_search_request(image=photo, text=text), siglip)

    assert len(world.thumbnails) > 0
    assert any(scored.scores.image is not None for scored in response.products)
    assert response.query_embedding is not None
    [step] = [timing for timing in response.timings if timing.step == "image_rank"]
    assert step.status == "ok"


async def test_a_photo_with_text_that_names_two_garments_is_still_compared(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    siglip: Settings,
    photo: bytes,
) -> None:
    # The skip follows the understood input type, not the number of garments: here the shopper
    # typed what they want next to the photo, so it is a photo-with-text request.
    understander = FakeUnderstander(
        make_understand_result(input_type=InputType.PHOTO_TEXT, items=OUTFIT[:2])
    )
    pipeline = make_pipeline(understander=understander, thumbnails=True)

    response = await pipeline.run(
        make_search_request(image=photo, text="a black blazer and a white shirt"), siglip
    )

    assert len(world.thumbnails) > 0
    assert any(scored.scores.image is not None for scored in response.products)


async def test_a_rerun_of_an_outfit_does_not_try_to_compare_either(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    siglip: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]), thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text=None), siglip)

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, siglip, overrides)

    assert world.thumbnails == []
    assert make_pipeline.ranker_spy is not None
    assert make_pipeline.ranker_spy.calls == []
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in second.warnings
    assert all(scored.scores.image is None for scored in second.products)
    [skipped] = [timing for timing in second.timings if timing.step == "image_rank"]
    assert skipped.status == "skipped"


async def test_a_rerun_of_an_outfit_ignores_an_embedding_it_is_handed(
    make_pipeline: PipelineMaker, two_stores: list, siglip: Settings, photo: bytes
) -> None:
    # An embedding could still arrive (from a response kept from before this rule): the garments
    # of an outfit are not compared with it either.
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]), thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text=None), siglip)

    stale = RunOverrides(understood=first.understood, query_embedding=[0.1, 0.2, 0.3])
    second = await pipeline.run(SearchRequest(rerun_of=first.request_id), siglip, stale)

    assert make_pipeline.ranker_spy is not None
    assert make_pipeline.ranker_spy.calls == []
    assert second.query_embedding is None
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in second.warnings


async def test_a_new_photo_sent_with_an_outfit_rerun_is_not_compared_either(
    make_pipeline: PipelineMaker, two_stores: list, siglip: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]), thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text=None), siglip)

    _, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    await pipeline.run(SearchRequest(image=photo, rerun_of=first.request_id), siglip, overrides)

    assert make_pipeline.ranker_spy is not None
    assert make_pipeline.ranker_spy.calls == []


async def test_an_outfit_understanding_of_one_garment_is_skipped_the_same_way(
    make_pipeline: PipelineMaker, two_stores: list, siglip: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander([BLAZER]), thumbnails=True)

    response = await pipeline.run(make_search_request(image=photo, text=None), siglip)

    assert make_pipeline.ranker_spy is not None
    assert make_pipeline.ranker_spy.calls == []
    assert [timing.status for timing in response.timings if timing.step == "image_rank"] == [
        "skipped"
    ]
