"""Which stores a request reaches also depends on the garment's category.

Four of the stores sell only dress-category garments. A store that does not sell the item's
category is not searched at all for it: no robots.txt, no search page, and none of its products can
turn up in that garment's group. A real run showed why it matters: an abaya titled only
"ELAN EMBROIDERED VELVET BLACK" has no garment word, so the category filter keeps it for every
request, and it landed in the shoes group of an outfit. It is listed among the skipped stores with
a plain reason, like a store left out for its gender.

Everything is counted at the boundary: requests on the fake network, searches on the spy around
the store engine.
"""

import pytest

from tests.factories import (
    make_chip_edits,
    make_item_intent,
    make_search_request,
    make_understand_result,
)
from tests.fakes import FakeUnderstander
from tests.fetch.conftest import shopify_product, suggest_body
from tests.pipeline.builders import outfit_understander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import CDN_PREFIX, StoreWorld, store_for
from vga.models import (
    Category,
    Gender,
    GenderSource,
    InputType,
    ItemEdit,
    MixPreset,
    RunOverrides,
    SettingsOverride,
    StoreStatus,
)
from vga.pipeline import messages
from vga.settings import Settings

PADDING_TITLE = "ELAN EMBROIDERED VELVET BLACK"
"""An abaya whose title names no garment: nothing in it tells the ranker it is not a shoe."""


def padding_body() -> str:
    """What a dress-only store answers to ANY query: its own abayas, whatever was asked for."""
    return suggest_body(
        shopify_product(
            1,
            title=PADDING_TITLE,
            price="1200.00",
            price_min="1200.00",
            price_max="1200.00",
            handle="elan-black",
            id=3001,
            image=f"{CDN_PREFIX}s/files/1/0001/elan-black.jpg?v=1",
            url="/products/elan-black?_pos=1",
            type="Kaftans and Abayas",
        )
    )


@pytest.fixture
def stores(world: StoreWorld) -> None:
    """A dresses-only boutique that pads every answer, a dresses-only one that answers properly,
    and a store that sells every category."""
    world.add(
        store_for("atelier", categories=[Category.DRESSES]),
        bodies={kind: padding_body() for kind in ("blazer", "shoes", "shirt", "jeans", "dress")},
    )
    world.add(store_for("boutique", categories=[Category.DRESSES]))
    world.add(store_for("everything"))


GARMENTS: dict[Category, dict[str, object]] = {
    Category.SHOES: {
        "colour": "white",
        "style": "sneakers",
        "search_keywords": ["white sneakers", "leather sneakers"],
    },
    Category.DRESSES: {
        "colour": "black",
        "style": "evening dress",
        "search_keywords": ["black evening dress", "evening dress"],
    },
}


def wanting(category: Category, **fields: object) -> FakeUnderstander:
    item = make_item_intent(category=category, **{**GARMENTS[category], **fields})
    return FakeUnderstander(make_understand_result(items=[item]))


def reached(world: StoreWorld) -> set[str]:
    return {key for key, site in world.sites.items() if world.requests_to(site.host) > 0}


async def test_a_shoes_request_never_reaches_a_dresses_only_store(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Category.SHOES))

    await pipeline.run(make_search_request(text="white sneakers"), settings)

    assert reached(world) == {"everything"}
    assert world.requests_to("atelier.example") == 0  # not even its robots.txt
    assert world.requests_to("boutique.example") == 0
    assert make_pipeline.spy is not None
    assert {store for call in make_pipeline.spy.calls for store in call.store_ids} == {"everything"}


async def test_the_skipped_dresses_only_stores_are_listed_with_a_plain_reason(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Category.SHOES))

    response = await pipeline.run(make_search_request(text="white sneakers"), settings)

    assert [r.store_id for r in response.stores_used] == ["everything"]
    assert [(r.store_id, r.status, r.reason) for r in response.stores_skipped] == [
        ("atelier", StoreStatus.EMPTY, "Not searched: Atelier does not sell shoes."),
        ("boutique", StoreStatus.EMPTY, "Not searched: Boutique does not sell shoes."),
    ]
    # a store left out for what it sells is not a failure, so no warning names it
    assert not any("Atelier" in w or "Boutique" in w for w in response.warnings)
    assert [t.store for t in response.timings if t.step == "fetch"] == ["everything"]


async def test_an_abaya_with_no_garment_word_cannot_turn_up_among_the_shoes(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Category.SHOES))

    response = await pipeline.run(make_search_request(text="white sneakers"), settings)

    assert response.result_count > 0
    assert PADDING_TITLE not in {scored.product.title for scored in response.products}
    assert {scored.product.store for scored in response.products} == {"Everything"}


async def test_a_dresses_request_does_reach_the_dresses_only_stores(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Category.DRESSES))

    response = await pipeline.run(make_search_request(text="black evening dress"), settings)

    assert reached(world) == {"atelier", "boutique", "everything"}
    assert response.stores_skipped == []
    assert {r.store_id for r in response.stores_used} == {"atelier", "boutique", "everything"}


async def test_in_an_outfit_a_dresses_only_store_is_searched_for_the_dress_only(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    stores: None,
    settings: Settings,
    photo: bytes,
) -> None:
    items = [
        make_item_intent(
            category=Category.DRESSES, colour="black", search_keywords=["black evening dress"]
        ),
        make_item_intent(
            category=Category.SHOES, colour="white", search_keywords=["white sneakers"]
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
        (Category.DRESSES, "atelier"),
        (Category.DRESSES, "boutique"),
        (Category.DRESSES, "everything"),
        (Category.SHOES, "everything"),
    }
    # the store was asked for the dress and for nothing else
    assert world.queries("atelier") == ["black evening dress"]
    assert world.queries("boutique") == ["black evening dress"]
    # it gave products for one garment, so it is used, not listed as skipped
    assert {r.store_id for r in response.stores_used} == {"atelier", "boutique", "everything"}
    assert response.stores_skipped == []
    dresses, shoes = response.groups
    assert {s.product.store for s in dresses.tiers[0].results + dresses.tiers[1].results} <= {
        "Atelier",
        "Boutique",
        "Everything",
    }
    assert {s.product.store for tier in shoes.tiers for s in tier.results} == {"Everything"}
    assert not any("Atelier" in warning for warning in response.warnings)


async def test_a_four_garment_outfit_asks_a_dresses_only_store_for_nothing_it_does_not_sell(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    assert world.requests_to("atelier.example") == 0
    assert world.requests_to("boutique.example") == 0
    assert {r.store_id for r in response.stores_skipped} == {"atelier", "boutique"}
    assert {r.store_id for r in response.stores_used} == {"everything"}


async def test_when_no_store_sells_the_category_the_garment_is_empty_with_a_warning(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("atelier", categories=[Category.DRESSES]))
    world.add(store_for("boutique", categories=[Category.DRESSES]))
    pipeline = make_pipeline(understander=wanting(Category.SHOES))

    response = await pipeline.run(make_search_request(text="white sneakers"), settings)

    assert world.all_requests() == 0
    assert response.result_count == 0
    [group] = response.groups
    assert all(tier.count == 0 for tier in group.tiers)
    assert messages.no_store_for_category(Category.SHOES) in response.warnings
    assert "None of the stores we search sell shoes" in " ".join(response.warnings)
    assert {r.store_id for r in response.stores_skipped} == {"atelier", "boutique"}
    assert all("does not sell shoes" in (r.reason or "") for r in response.stores_skipped)
    assert response.stores_used == []
    # the other empty-result warnings would only repeat it
    assert messages.NO_RESULTS_ANYWHERE not in response.warnings


async def test_one_garment_with_no_store_does_not_stop_the_other_garments(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    world.add(store_for("atelier", categories=[Category.DRESSES]))
    items = [
        make_item_intent(
            category=Category.DRESSES, colour="black", search_keywords=["black evening dress"]
        ),
        make_item_intent(
            category=Category.SHOES, colour="white", search_keywords=["white sneakers"]
        ),
    ]
    understander = FakeUnderstander(
        make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=items)
    )
    pipeline = make_pipeline(understander=understander)

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    dresses, shoes = response.groups
    assert dresses.result_count > 0
    assert shoes.result_count == 0
    assert messages.no_store_for_category(Category.SHOES) in response.warnings
    assert world.queries("atelier") == ["black evening dress"]
    assert [r.store_id for r in response.stores_used] == ["atelier"]
    assert response.stores_skipped == []


async def test_a_store_failing_both_checks_is_reported_for_its_category(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("womens-dresses", genders=[Gender.WOMEN], categories=[Category.DRESSES]))
    world.add(store_for("everyone"))
    pipeline = make_pipeline(
        understander=wanting(Category.SHOES, gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)
    )

    response = await pipeline.run(make_search_request(text="sneakers for men"), settings)

    [skipped] = response.stores_skipped
    assert skipped.reason == "Not searched: Womens Dresses does not sell shoes."
    assert world.requests_to("womens-dresses.example") == 0


async def test_the_gender_rule_still_applies_to_a_store_that_does_sell_the_category(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("womens-dresses", genders=[Gender.WOMEN], categories=[Category.DRESSES]))
    world.add(store_for("everyone"))
    pipeline = make_pipeline(
        understander=wanting(
            Category.DRESSES, gender=Gender.MEN, gender_source=GenderSource.EXPLICIT
        )
    )

    response = await pipeline.run(make_search_request(text="kurta for men"), settings)

    [skipped] = response.stores_skipped
    assert skipped.reason == "Not searched: Womens Dresses does not sell clothing for men."
    assert world.requests_to("womens-dresses.example") == 0


async def test_a_category_skip_is_not_asked_again_on_a_mix_change_and_is_listed_as_before(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    pipeline = make_pipeline(understander=wanting(Category.SHOES))
    first = await pipeline.run(make_search_request(text="white sneakers"), settings)
    requests_before = world.all_requests()

    second = await pipeline.run(
        make_search_request(text="white sneakers", rerun_of=first.request_id),
        settings,
        RunOverrides(
            understood=first.understood,
            settings=SettingsOverride(tier_mix=MixPreset.VALUE_FIRST.mix),
        ),
    )

    assert world.all_requests() == requests_before
    assert [r.store_id for r in second.stores_used] == [r.store_id for r in first.stores_used]
    assert [(r.store_id, r.reason) for r in second.stores_skipped] == [
        (r.store_id, r.reason) for r in first.stores_skipped
    ]
    assert len(second.stores_skipped) == 2


async def test_changing_the_garment_in_the_chips_changes_which_stores_are_searched(
    make_pipeline: PipelineMaker, world: StoreWorld, stores: None, settings: Settings
) -> None:
    understander = wanting(Category.SHOES)
    pipeline = make_pipeline(understander=understander)
    first = await pipeline.run(make_search_request(text="something white"), settings)
    assert world.requests_to("atelier.example") == 0

    edit = make_chip_edits(items=[ItemEdit(index=0, category=Category.DRESSES)])
    second = await pipeline.run(
        make_search_request(text="something white", rerun_of=first.request_id),
        settings,
        RunOverrides(chips=edit, understood=first.understood),
    )

    # a different garment is a different search, and this time the dresses-only stores are asked
    assert world.requests_to("atelier.example") > 0
    assert {r.store_id for r in second.stores_used} >= {"atelier", "boutique"}
    assert len(understander.calls) == 1
