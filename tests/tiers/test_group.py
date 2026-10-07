"""9.3.2 Per-garment groups: one GarmentGroup per category, with the right total."""

import pytest

from tests.factories import make_search_response, make_settings, make_understand_result
from tests.tiers.helpers import LUXURY_STORE, make_pool, make_prd_pool
from vga.models import (
    TIER_ORDER,
    Budget,
    Category,
    Flag,
    GarmentGroup,
    InputType,
    ScoredProduct,
    SearchResponse,
    Tier,
)
from vga.tiers import build_group, results_total

GARMENTS = (Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES)
STORES_12 = tuple(f"Store {n:02d}" for n in range(1, 13))


def garment_pool(index: int) -> list[ScoredProduct]:
    """48 candidates for one garment, spread over 12 stores so the cap never bites. Each garment
    has its own price level, so its borders differ from the others'."""
    scale = 25.0 * (index + 1)
    return make_pool([scale * n for n in range(1, 49)], stores=STORES_12, start=1 + 100 * index)


# --- results_total ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_type", "expected"),
    [
        pytest.param(InputType.OUTFIT_PHOTO, 12, id="outfit_photo_uses_outfit_results_per_garment"),
        pytest.param(InputType.PRODUCT_PHOTO, 30, id="product_photo_uses_results"),
        pytest.param(InputType.TEXT, 30, id="text_uses_results"),
        pytest.param(InputType.PHOTO_TEXT, 30, id="photo_text_uses_results"),
    ],
)
def test_total_for_each_input_type(input_type: InputType, expected: int) -> None:
    assert results_total(make_settings(), input_type) == expected


def test_total_follows_the_settings() -> None:
    settings = make_settings(results=24, outfit_results_per_garment=8)
    assert results_total(settings, InputType.OUTFIT_PHOTO) == 8
    assert results_total(settings, InputType.TEXT) == 24


# --- build_group --------------------------------------------------------------------------------


def test_four_garments_produce_four_groups_of_twelve() -> None:
    settings = make_settings()
    total = results_total(settings, InputType.OUTFIT_PHOTO)

    built = [
        build_group(
            garment_pool(index),
            settings,
            None,
            (LUXURY_STORE,),
            item_index=index,
            category=category,
            total=total,
        )
        for index, category in enumerate(GARMENTS)
    ]

    groups = [item.group for item in built]
    assert [g.item_index for g in groups] == [0, 1, 2, 3]
    assert [g.category for g in groups] == list(GARMENTS)
    assert [g.result_count for g in groups] == [12, 12, 12, 12]
    for group in groups:
        assert [tier.name for tier in group.tiers] == list(TIER_ORDER)
        assert [tier.target_count for tier in group.tiers] == [3, 3, 3, 3]
        assert [tier.count for tier in group.tiers] == [3, 3, 3, 3]


def test_each_garment_gets_its_own_price_borders() -> None:
    settings = make_settings()
    spans = []
    for index, category in enumerate((Category.TOPS, Category.OUTERWEAR)):
        group = build_group(
            garment_pool(index),
            settings,
            None,
            (LUXURY_STORE,),
            item_index=index,
            category=category,
            total=12,
        ).group
        spans.append([(tier.price_min, tier.price_max) for tier in group.tiers])
    assert spans[0] != spans[1]


def test_the_store_cap_applies_inside_each_garments_own_list() -> None:
    # The same single store supplies both garments: 6 products may be shown in each list.
    settings = make_settings()
    groups = [
        build_group(
            make_pool([10.0 * n for n in range(1, 31)], stores=("Solo",), start=1 + 100 * index),
            settings,
            None,
            (LUXURY_STORE,),
            item_index=index,
            category=category,
            total=12,
        ).group
        for index, category in enumerate((Category.TOPS, Category.SHOES))
    ]
    assert [g.result_count for g in groups] == [6, 6]


def test_a_garment_with_no_products_gets_four_empty_ranges() -> None:
    built = build_group(
        [],
        make_settings(),
        None,
        (LUXURY_STORE,),
        item_index=2,
        category=Category.BOTTOMS,
        total=12,
    )
    assert built.group.result_count == 0
    assert all(tier.flags == [Flag.FEW_OPTIONS] for tier in built.group.tiers)
    assert built.warnings == []


def test_warnings_from_shaping_reach_the_caller() -> None:
    built = build_group(
        make_prd_pool(),
        make_settings(),
        Budget(max_price=300, currency="USD"),
        (LUXURY_STORE,),
        item_index=0,
        category=Category.OUTERWEAR,
        total=30,
    )
    assert len(built.warnings) == 1
    assert "USD" in built.warnings[0]


def test_a_budget_applies_to_every_group_it_is_given_to() -> None:
    built = build_group(
        make_prd_pool(),
        make_settings(),
        Budget(max_price=300, currency="AED"),
        (LUXURY_STORE,),
        item_index=0,
        category=Category.OUTERWEAR,
        total=30,
    )
    group = built.group
    assert [t.count for t in group.tiers] == [8, 8, 7, 7]
    assert all(p.tier is t.name for t in group.tiers for p in t.results)
    over = [p for t in group.tiers for p in t.results if Flag.OVER_BUDGET in p.flags]
    assert len(over) == 13
    assert {p.tier for p in over} == {Tier.PREMIUM, Tier.LUXURY}


def test_groups_fit_into_a_search_response_and_survive_a_json_round_trip() -> None:
    settings = make_settings()
    groups = [
        build_group(
            garment_pool(index),
            settings,
            None,
            (LUXURY_STORE,),
            item_index=index,
            category=category,
            total=12,
        ).group
        for index, category in enumerate(GARMENTS)
    ]
    understood = make_understand_result(
        input_type=InputType.OUTFIT_PHOTO,
        items=[
            {"category": c, "search_keywords": ["a thing"], "colour": None, "style": None}
            for c in GARMENTS
        ],
    )
    response = make_search_response(understood=understood, groups=groups)

    again = SearchResponse.model_validate_json(response.model_dump_json())

    assert again == response
    assert again.result_count == 48
    assert isinstance(again.groups[0], GarmentGroup)
