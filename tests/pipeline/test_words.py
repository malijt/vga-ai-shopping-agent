"""The shopper says "price range", never "tier" (the code's word for the same thing)."""

import inspect
from collections.abc import Iterator

import pytest

from tests.factories import make_budget, make_search_request
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from vga.models import (
    Category,
    Gender,
    RunOverrides,
    SearchResponse,
    SettingsOverride,
    StoreStatus,
)
from vga.pipeline import messages
from vga.settings import Settings


def message_texts() -> Iterator[str]:
    """Every fixed message, and what every message function says for sample input."""
    for name, value in vars(messages).items():
        if name.startswith("_"):
            continue
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            yield from (item for item in value.values() if isinstance(item, str))
    for status in StoreStatus:
        yield from filter(None, [messages.store_warning("Some Store", status)])
        if status is not StoreStatus.OK:
            yield messages.store_reason(status)
    yield messages.store_partial_warning("Some Store")
    yield messages.photo_too_large(8_000_000)
    yield messages.text_too_long(2000)
    yield messages.deadline_warning(30)
    for category in Category:
        yield messages.nothing_found_for(category)
        for gender in Gender:
            yield messages.no_store_for_gender(category, gender)
    for gender in Gender:
        yield messages.inferred_gender_note(gender)


def shopper_text(response: SearchResponse) -> list[str]:
    """Everything in a response a shopper can read."""
    texts = list(response.warnings)
    texts += [report.reason or "" for report in response.stores_skipped]
    texts += [scored.reason for scored in response.products]
    texts += [tier.display_label for group in response.groups for tier in group.tiers]
    return texts


def test_no_fixed_message_says_tier() -> None:
    texts = list(message_texts())

    assert len(texts) > 40
    assert [text for text in texts if "tier" in text.lower()] == []


def test_a_category_or_gender_without_a_word_reads_as_its_own_name_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(messages, "_CATEGORY_WORDS", {})
    monkeypatch.setattr(messages, "_GENDER_WORDS", {})

    assert messages.category_word(Category.SHOES) == "shoes"
    assert messages.gender_word(Gender.WOMEN) == "women"
    assert "shoes" in messages.no_store_for_gender(Category.SHOES, Gender.MEN)


def test_every_message_function_is_covered_by_the_scan_above() -> None:
    functions = {name for name, value in vars(messages).items() if inspect.isfunction(value)}

    assert functions == {
        "photo_too_large",
        "text_too_long",
        "deadline_warning",
        "store_reason",
        "store_warning",
        "store_partial_warning",
        "gender_word",
        "category_word",
        "store_not_for_gender",
        "no_store_for_gender",
        "nothing_found_for",
        "inferred_gender_note",
    }


async def test_nothing_in_a_real_response_says_tier(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"), prices={"blazer": (500, 900, 1500)})
    world.add(store_for("beta"), status=403)
    world.add(store_for("gamma", currency="USD"))
    sidebar = SettingsOverride(budget=make_budget(max_price=100, currency="EUR"))
    pipeline = make_pipeline()

    response = await pipeline.run(
        make_search_request(text="black oversized blazer"),
        settings,
        RunOverrides(settings=sidebar),
    )

    assert response.warnings
    assert response.stores_skipped
    assert [text for text in shopper_text(response) if "tier" in text.lower()] == []
