"""Which stores a request reaches depends on its gender, and only a STATED gender counts.

A store that does not sell for the stated gender is not searched at all: no robots.txt, no search
page. It is listed among the skipped stores with a plain reason. A gender the AI only guessed
(BRD Rule 8, assumption A3) is shown to the shopper but excludes nothing.
"""

import pytest

from tests.factories import (
    make_chip_edits,
    make_item_intent,
    make_search_request,
    make_understand_result,
)
from tests.fakes import FakeUnderstander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from vga.models import (
    Category,
    Gender,
    GenderSource,
    InputType,
    ItemEdit,
    RunOverrides,
    StoreStatus,
)
from vga.pipeline import messages
from vga.settings import Settings


@pytest.fixture
def three_stores(world: StoreWorld) -> None:
    """A women-only store, a men-only store and one that sells for everyone."""
    world.add(store_for("womens", genders=[Gender.WOMEN]))
    world.add(store_for("mens", genders=[Gender.MEN]))
    world.add(store_for("everyone"))


def wanting(gender: Gender | None, source: GenderSource) -> FakeUnderstander:
    item = make_item_intent(gender=gender, gender_source=source)
    return FakeUnderstander(make_understand_result(items=[item]))


def reached(world: StoreWorld) -> set[str]:
    return {key for key, site in world.sites.items() if world.requests_to(site.host) > 0}


async def test_a_stated_men_request_never_reaches_a_women_only_store(
    make_pipeline: PipelineMaker, world: StoreWorld, three_stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Gender.MEN, GenderSource.EXPLICIT))

    response = await pipeline.run(make_search_request(text="blazer for men"), settings)

    assert reached(world) == {"mens", "everyone"}
    assert world.requests_to("womens.example") == 0  # not even its robots.txt
    assert make_pipeline.spy is not None
    assert {store for call in make_pipeline.spy.calls for store in call.store_ids} == {
        "mens",
        "everyone",
    }
    assert {s.product.store for s in response.products} == {"Mens", "Everyone"}


async def test_the_skipped_women_only_store_is_listed_with_a_plain_reason(
    make_pipeline: PipelineMaker, world: StoreWorld, three_stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Gender.MEN, GenderSource.EXPLICIT))

    response = await pipeline.run(make_search_request(text="blazer for men"), settings)

    [skipped] = response.stores_skipped
    assert skipped.store_id == "womens"
    assert skipped.status is StoreStatus.EMPTY
    assert skipped.reason == "Not searched: Womens does not sell clothing for men."
    assert [r.store_id for r in response.stores_used] == ["mens", "everyone"]
    # a store left out for its audience is not a failure, so no warning names it
    assert not any("Womens" in warning for warning in response.warnings)


async def test_a_stated_women_request_never_reaches_a_men_only_store(
    make_pipeline: PipelineMaker, world: StoreWorld, three_stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Gender.WOMEN, GenderSource.EXPLICIT))

    response = await pipeline.run(make_search_request(text="blazer for women"), settings)

    assert reached(world) == {"womens", "everyone"}
    assert [r.store_id for r in response.stores_skipped] == ["mens"]


@pytest.mark.parametrize(
    ("gender", "source"),
    [
        (Gender.MEN, GenderSource.INFERRED),
        (Gender.WOMEN, GenderSource.INFERRED),
        (None, GenderSource.NONE),
        (Gender.UNISEX, GenderSource.EXPLICIT),
    ],
    ids=["guessed-men", "guessed-women", "no-gender", "stated-unisex"],
)
async def test_these_requests_exclude_no_store(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    three_stores: None,
    settings: Settings,
    gender: Gender | None,
    source: GenderSource,
) -> None:
    pipeline = make_pipeline(understander=wanting(gender, source))

    response = await pipeline.run(make_search_request(text="a blazer"), settings)

    assert reached(world) == {"womens", "mens", "everyone"}
    assert response.stores_skipped == []


async def test_a_guessed_gender_is_shown_but_not_applied(
    make_pipeline: PipelineMaker, world: StoreWorld, three_stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Gender.MEN, GenderSource.INFERRED))

    response = await pipeline.run(make_search_request(text="a blazer"), settings)

    [item] = response.understood.items
    assert (item.gender, item.gender_source) == (Gender.MEN, GenderSource.INFERRED)
    assert messages.inferred_gender_note(Gender.MEN) in response.warnings


async def test_when_no_store_sells_for_the_stated_gender_the_garment_is_empty_with_a_warning(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("womens-a", genders=[Gender.WOMEN]))
    world.add(store_for("womens-b", genders=[Gender.WOMEN]))
    pipeline = make_pipeline(understander=wanting(Gender.MEN, GenderSource.EXPLICIT))

    response = await pipeline.run(make_search_request(text="blazer for men"), settings)

    assert world.all_requests() == 0
    assert response.result_count == 0
    [group] = response.groups
    assert all(tier.count == 0 for tier in group.tiers)
    assert messages.no_store_for_gender(Category.OUTERWEAR, Gender.MEN) in response.warnings
    assert {r.store_id for r in response.stores_skipped} == {"womens-a", "womens-b"}
    assert all(
        "does not sell clothing for men" in (r.reason or "") for r in response.stores_skipped
    )
    assert response.stores_used == []


async def test_each_garment_of_an_outfit_follows_its_own_gender(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    three_stores: None,
    settings: Settings,
    photo: bytes,
) -> None:
    items = [
        make_item_intent(
            gender=Gender.MEN,
            gender_source=GenderSource.EXPLICIT,
            search_keywords=["black blazer"],
        ),
        make_item_intent(
            category=Category.TOPS,
            colour="white",
            style="shirt",
            gender=Gender.WOMEN,
            gender_source=GenderSource.EXPLICIT,
            search_keywords=["white shirt"],
        ),
    ]
    understander = FakeUnderstander(
        make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=items)
    )
    pipeline = make_pipeline(understander=understander)

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    assert make_pipeline.spy is not None
    asked = {(call.category, store) for call in make_pipeline.spy.calls for store in call.store_ids}
    assert asked == {
        (Category.OUTERWEAR, "mens"),
        (Category.OUTERWEAR, "everyone"),
        (Category.TOPS, "womens"),
        (Category.TOPS, "everyone"),
    }
    # every store gave products for one of the garments, so none is listed as skipped
    assert {r.store_id for r in response.stores_used} == {"womens", "mens", "everyone"}
    assert response.stores_skipped == []


async def test_confirming_a_guessed_gender_in_the_chips_narrows_the_stores_on_the_next_search(
    make_pipeline: PipelineMaker, world: StoreWorld, three_stores: None, settings: Settings
) -> None:
    understander = wanting(Gender.MEN, GenderSource.INFERRED)
    pipeline = make_pipeline(understander=understander)
    first = await pipeline.run(make_search_request(text="a blazer"), settings)
    assert {r.store_id for r in first.stores_used} == {"womens", "mens", "everyone"}
    womens_before = world.requests_to("womens.example")

    confirm = make_chip_edits(items=[ItemEdit(index=0, gender=Gender.MEN)])
    second = await pipeline.run(
        make_search_request(text="a blazer", rerun_of=first.request_id),
        settings,
        RunOverrides(chips=confirm, understood=first.understood),
    )

    assert second.understood.items[0].gender_source is GenderSource.EXPLICIT
    assert world.requests_to("womens.example") == womens_before  # not asked again
    assert [r.store_id for r in second.stores_skipped] == ["womens"]
    assert len(understander.calls) == 1
