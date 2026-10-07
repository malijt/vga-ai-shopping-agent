"""Plan 13.1.4 (assumption A7): a photo gives the look, the text edits it, and "cheaper" with no
budget switches that one request to the value-first price mix."""

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
    InputType,
    MixPreset,
    RunOverrides,
    SearchResponse,
    SettingsOverride,
)
from vga.pipeline.messages import CHEAPER_WITHOUT_BUDGET
from vga.settings import Settings

BROWN_AND_CHEAPER = make_understand_result(
    input_type=InputType.PHOTO_TEXT,
    items=[
        make_item_intent(
            colour="dark brown",
            style="oversized blazer",
            search_keywords=["dark brown oversized blazer", "oversized blazer"],
        )
    ],
    edits=["dark brown", "cheaper"],
)


def targets(response: SearchResponse) -> list[list[int]]:
    return [[tier.target_count for tier in group.tiers] for group in response.groups]


async def test_similar_but_dark_brown_and_cheaper_sets_the_colour_and_the_mix(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    world.add(store_for("alpha"), colour="Dark Brown")
    world.add(store_for("beta"), colour="Black")
    pipeline = make_pipeline(understander=FakeUnderstander(BROWN_AND_CHEAPER))
    request = make_search_request(image=photo, text="similar but dark brown and cheaper")

    response = await pipeline.run(request, settings)

    assert response.understood.items[0].colour == "dark brown"
    assert targets(response) == [[12, 9, 6, 3]]  # the value-first mix, 40/30/20/10 of 30
    assert CHEAPER_WITHOUT_BUDGET in response.warnings
    best = max(response.products, key=lambda scored: scored.scores.total)
    assert best.product.store == "Alpha"  # the dark brown blazers outrank the black ones


async def test_the_photo_is_still_compared_with_the_products(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    ranker = FakeImageRanker()
    pipeline = make_pipeline(understander=FakeUnderstander(BROWN_AND_CHEAPER), image_ranker=ranker)

    response = await pipeline.run(make_search_request(image=photo, text="cheaper"), settings)

    assert len(ranker.calls) == 1
    assert response.query_embedding is not None
    assert any(scored.scores.image is not None for scored in response.products)


async def test_a_budget_is_a_price_to_aim_at_so_the_mix_stays_even(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    with_budget = BROWN_AND_CHEAPER.model_copy(update={"budget": make_budget(max_price=300)})
    pipeline = make_pipeline(understander=FakeUnderstander(with_budget))

    response = await pipeline.run(make_search_request(image=photo, text="under 300"), settings)

    assert targets(response) == [[8, 8, 7, 7]]
    assert CHEAPER_WITHOUT_BUDGET not in response.warnings


async def test_a_budget_in_the_sidebar_also_counts_as_a_budget(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=FakeUnderstander(BROWN_AND_CHEAPER))
    overrides = RunOverrides(settings=SettingsOverride(budget=make_budget(max_price=300)))

    response = await pipeline.run(
        make_search_request(image=photo, text="cheaper"), settings, overrides
    )

    assert targets(response) == [[8, 8, 7, 7]]


async def test_a_mix_the_shopper_chose_is_kept(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=FakeUnderstander(BROWN_AND_CHEAPER))
    chosen = RunOverrides(settings=SettingsOverride(tier_mix=MixPreset.LUXURY_FIRST.mix))

    response = await pipeline.run(
        make_search_request(image=photo, text="cheaper"), settings, chosen
    )

    assert targets(response) == [[3, 6, 9, 12]]
    assert CHEAPER_WITHOUT_BUDGET not in response.warnings


async def test_the_sidebar_resting_on_its_default_mix_does_not_count_as_a_choice(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    # The sidebar always sends its current radio value, and it starts on the configured default.
    pipeline = make_pipeline(understander=FakeUnderstander(BROWN_AND_CHEAPER))
    resting = RunOverrides(settings=SettingsOverride(tier_mix=settings.tier_mix))

    response = await pipeline.run(
        make_search_request(image=photo, text="cheaper"), settings, resting
    )

    assert targets(response) == [[12, 9, 6, 3]]


async def test_text_that_does_not_ask_for_cheaper_keeps_the_even_mix(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    only_colour = BROWN_AND_CHEAPER.model_copy(update={"edits": ["dark brown"]})
    pipeline = make_pipeline(understander=FakeUnderstander(only_colour))

    response = await pipeline.run(make_search_request(image=photo, text="dark brown"), settings)

    assert targets(response) == [[8, 8, 7, 7]]


async def test_the_mix_change_applies_to_that_request_only(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=FakeUnderstander(BROWN_AND_CHEAPER))

    await pipeline.run(make_search_request(image=photo, text="cheaper"), settings)

    assert settings.tier_mix == MixPreset.EVEN.mix  # the shared settings object is untouched
    plain = await make_pipeline().run(make_search_request(text="black oversized blazer"), settings)
    assert targets(plain) == [[8, 8, 7, 7]]
