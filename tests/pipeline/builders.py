"""Requests, understandings and re-runs shared by several pipeline test files."""

from tests.factories import make_item_intent, make_understand_result
from tests.fakes import FakeUnderstander
from vga.models import (
    Category,
    InputType,
    ItemIntent,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    SettingsOverride,
    TierMix,
)

BLAZER = make_item_intent(
    colour="black",
    search_keywords=["black oversized blazer", "oversized blazer"],
)
SHIRT = make_item_intent(
    category=Category.TOPS,
    colour="white",
    style="shirt",
    search_keywords=["white shirt", "cotton shirt"],
)

OUTFIT = [
    make_item_intent(
        category=Category.OUTERWEAR,
        search_keywords=["black blazer", "oversized blazer", "tailored jacket"],
    ),
    make_item_intent(
        category=Category.TOPS,
        colour="white",
        style="shirt",
        search_keywords=["white shirt", "cotton shirt", "oxford shirt"],
    ),
    make_item_intent(
        category=Category.BOTTOMS,
        colour="blue",
        style="jeans",
        search_keywords=["blue jeans", "wide-leg jeans", "straight jeans"],
    ),
    make_item_intent(
        category=Category.SHOES,
        colour="white",
        style="sneakers",
        search_keywords=["white sneakers", "leather sneakers", "court shoes"],
    ),
]
"""Four garments with three keyword variants each: the pipeline keeps two."""


def outfit_understander(items: list[ItemIntent] | None = None) -> FakeUnderstander:
    return FakeUnderstander(
        make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=items or OUTFIT)
    )


def photo_search(
    items: list[ItemIntent] | None = None, input_type: InputType = InputType.PHOTO_TEXT
) -> FakeUnderstander:
    """An understander that reads a photo (and text) as ``items`` (default: the black blazer)."""
    return FakeUnderstander(make_understand_result(input_type=input_type, items=items or [BLAZER]))


def rerun(
    first: SearchResponse,
    *,
    mix: TierMix | None = None,
    budget=None,
    chips=None,
) -> tuple[SearchRequest, RunOverrides]:
    """What the app sends after a first search: no text, no photo, the earlier understanding and
    the photo's embedding."""
    sidebar = SettingsOverride(tier_mix=mix, budget=budget) if mix or budget else None
    return (
        SearchRequest(rerun_of=first.request_id),
        RunOverrides(
            settings=sidebar,
            chips=chips,
            understood=first.understood,
            query_embedding=first.query_embedding,
        ),
    )
