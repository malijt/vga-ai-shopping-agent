"""BRD Rule 2, the cheapest request is the one not made: answering "Who is this for?" (or choosing
the gender chip) re-runs the search with a garment's gender changed and nothing else. The products
the first search found already hold both audiences, so the re-run applies the gender to them and
makes NO request of any kind: not a search page, not a robots.txt, not a thumbnail, and no OpenAI
call. On 2026-10-08 the second search of a run, triggered by that very answer, was the one the
stores' platform refused.

The real pipeline and the real store engine, counting what reaches the fake stores (``world.stray``
catches a request nobody expected, which ``respx`` would otherwise swallow).
"""

import pytest

from tests.factories import make_chip_edits, make_item_intent, make_search_request
from tests.fakes import FakeClock
from tests.guards.scraping.support import GuardPipelines, GuardWorld
from tests.pipeline.builders import OUTFIT, outfit_understander, photo_search, rerun
from tests.pipeline.world import store_for
from vga.models import Gender, GenderSource, InputType, ItemEdit
from vga.settings import Settings

GUESSED = make_item_intent(
    search_keywords=["black oversized blazer", "oversized blazer"],
    gender=Gender.MEN,
    gender_source=GenderSource.INFERRED,
)


@pytest.fixture
def stores(world: GuardWorld) -> None:
    for key in ("alpha", "beta"):
        world.add(store_for(key))
    world.add(store_for("mens", genders=[Gender.MEN]))


@pytest.mark.parametrize("gender", [Gender.WOMEN, Gender.MEN])
async def test_a_gender_only_rerun_makes_no_request_of_any_kind(
    gender: Gender,
    world: GuardWorld,
    stores: None,
    build: GuardPipelines,
    settings: Settings,
    photo: bytes,
    clock: FakeClock,
) -> None:
    understander = photo_search([GUESSED], InputType.PRODUCT_PHOTO)
    pipeline = build(understander=understander, thumbnails=True)
    first = await pipeline.run(make_search_request(image=photo, text=None), settings)
    sent, fetched, started = world.all_requests(), len(world.thumbnails), clock.monotonic()
    assert sent > 0  # the first search was not free
    assert fetched > 0

    chips = make_chip_edits(items=[ItemEdit(index=0, gender=gender)])
    request, overrides = rerun(first, chips=chips)
    second = await pipeline.run(request, settings, overrides)

    assert world.all_requests() == sent  # nothing of any kind
    assert len(world.thumbnails) == fetched
    assert world.stray == []
    assert len(understander.calls) == 1  # and no OpenAI call
    assert clock.monotonic() == started  # nothing waited for, either
    assert second.result_count > 0
    assert second.understood.items[0].gender is gender


async def test_a_gender_only_rerun_of_an_outfit_makes_no_request_of_any_kind(
    world: GuardWorld, stores: None, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    guessed = [
        item.model_copy(update={"gender": Gender.MEN, "gender_source": GenderSource.INFERRED})
        for item in OUTFIT
    ]
    pipeline = build(understander=outfit_understander(guessed))
    first = await pipeline.run(make_search_request(image=photo, text=None), settings)
    sent = world.all_requests()

    chips = make_chip_edits(
        items=[ItemEdit(index=index, gender=Gender.WOMEN) for index in range(len(OUTFIT))]
    )
    request, overrides = rerun(first, chips=chips)
    second = await pipeline.run(request, settings, overrides)

    assert world.all_requests() == sent
    assert world.stray == []
    assert all(group.result_count > 0 for group in second.groups)


async def test_a_gender_only_rerun_is_not_paid_for_by_the_stores_platform_cooldown(
    world: GuardWorld, stores: None, build: GuardPipelines, settings: Settings, photo: bytes
) -> None:
    pipeline = build(understander=photo_search([GUESSED], InputType.PRODUCT_PHOTO))
    first = await pipeline.run(make_search_request(image=photo, text=None), settings)
    build.engine.client.cooldowns.start("platform:shopify")  # the platform has just said "stop"

    chips = make_chip_edits(items=[ItemEdit(index=0, gender=Gender.WOMEN)])
    request, overrides = rerun(first, chips=chips)
    second = await pipeline.run(request, settings, overrides)

    # Nothing was asked, so nothing was refused: the shopper still gets the answered results.
    assert second.result_count > 0
    assert [report.store_id for report in second.stores_skipped] == ["mens"]  # not for women
