"""The kind of request is derived from facts the code knows, never taken from the model's label.

The rule (plan A26 depends on it, because only a product photo or a photo + text request gets the
image comparison and the full 30 results):

- no photo: ``text``;
- a photo and typed text: ``photo_text``;
- a photo only, exactly one garment: ``product_photo``;
- a photo only, two or more garments: ``outfit_photo``.

Why: on 2026-10-08 the model called one burgundy gown worn by a model an ``outfit_photo`` in one
run and a ``product_photo`` in another. Trusting the label meant a single-garment photo silently
lost its image comparison and got 12 results instead of 30.
"""

import logging
from typing import Any

import pytest

from tests.factories import make_image_bytes, make_search_request
from tests.understand.conftest import RigFactory
from tests.understand.fake_openai import answer
from tests.understand.readings import make_reading, make_reading_item
from vga.log import request_context
from vga.models import Category, InputType, Usage
from vga.understand.fallback import fallback_result
from vga.understand.input_type import derive_input_type
from vga.understand.validation import OutputValidationError, validate_reading

OVERRIDE_LINE = "model input type overridden"

SITUATIONS = [
    # (text, has_image, item_count, derived)
    ("black blazer", False, 1, InputType.TEXT),
    ("black blazer and jeans", False, 3, InputType.TEXT),
    (None, True, 1, InputType.PRODUCT_PHOTO),
    (None, True, 2, InputType.OUTFIT_PHOTO),
    (None, True, 4, InputType.OUTFIT_PHOTO),
    ("same but in black", True, 1, InputType.PHOTO_TEXT),
    ("this top with these shoes", True, 2, InputType.PHOTO_TEXT),
]
LABELS = [*InputType, "nonsense", None]
"""Everything the model could say, including a value that is not an input type at all."""


def _items(count: int) -> list[Any]:
    return [make_reading_item() for _ in range(count)]


def _override_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == OVERRIDE_LINE]


# --------------------------------------------------------------------------------------------
# The rule itself
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "has_image", "item_count", "derived"), SITUATIONS)
def test_the_rule_gives_one_type_for_each_situation(
    text: str | None, has_image: bool, item_count: int, derived: InputType
) -> None:
    result = derive_input_type(
        has_image=has_image, has_text=text is not None, item_count=item_count
    )

    assert result is derived


@pytest.mark.parametrize("label", LABELS, ids=str)
@pytest.mark.parametrize(("text", "has_image", "item_count", "derived"), SITUATIONS)
def test_validation_ignores_the_models_label_whatever_it_says(
    label: Any, text: str | None, has_image: bool, item_count: int, derived: InputType
) -> None:
    reading = make_reading(input_type=label, items=_items(item_count))

    checked = validate_reading(reading, text=text, has_image=has_image)

    assert checked.input_type is derived


# --------------------------------------------------------------------------------------------
# The two cases that matter most
# --------------------------------------------------------------------------------------------


def test_one_garment_the_model_calls_an_outfit_photo_is_a_product_photo() -> None:
    # The 2026-10-08 case: a burgundy gown on a model, photo only, one item.
    reading = make_reading(
        input_type=InputType.OUTFIT_PHOTO,
        items=[
            make_reading_item(
                category=Category.DRESSES,
                colour="burgundy",
                style="floor-length evening gown",
                search_keywords=["burgundy evening gown", "evening gown"],
            )
        ],
    )

    checked = validate_reading(reading, text=None, has_image=True)

    assert checked.input_type is InputType.PRODUCT_PHOTO


def test_two_garments_the_model_calls_a_product_photo_are_an_outfit_photo() -> None:
    reading = make_reading(input_type=InputType.PRODUCT_PHOTO, items=_items(2))

    checked = validate_reading(reading, text=None, has_image=True)

    assert checked.input_type is InputType.OUTFIT_PHOTO


async def test_the_single_garment_case_is_settled_with_one_call_and_no_warning(
    rig: RigFactory,
) -> None:
    # A label that disagrees with the facts is not an error: no corrective retry, nothing for the
    # shopper to read.
    item = make_reading_item(
        category=Category.DRESSES,
        colour="burgundy",
        style="floor-length evening gown",
        search_keywords=["burgundy evening gown", "evening gown"],
    )
    r = rig(answer(make_reading(input_type=InputType.OUTFIT_PHOTO, items=[item])))

    result = await r.understander.understand(
        make_search_request(image=make_image_bytes(), text=None)
    )

    assert result.input_type is InputType.PRODUCT_PHOTO
    assert len(r.fake.requests) == 1
    assert result.usage.llm_calls == 1
    assert result.warnings == []


async def test_a_photo_with_typed_text_naming_two_garments_stays_photo_and_text(
    rig: RigFactory,
) -> None:
    reading = make_reading(input_type=InputType.OUTFIT_PHOTO, items=_items(2))
    r = rig(answer(reading))

    result = await r.understander.understand(
        make_search_request(image=make_image_bytes(), text="a black blazer like this with jeans")
    )

    assert result.input_type is InputType.PHOTO_TEXT
    assert len(result.items) == 2


# --------------------------------------------------------------------------------------------
# A disagreement is logged at debug level with the request id, an agreement is not
# --------------------------------------------------------------------------------------------


def test_a_disagreement_is_logged_at_debug_with_both_values_and_the_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="vga")
    reading = make_reading(input_type=InputType.OUTFIT_PHOTO, items=_items(1))

    with request_context("req-input-type"):
        validate_reading(reading, text=None, has_image=True)

    [line] = _override_lines(caplog)
    assert line.levelno == logging.DEBUG
    assert line.request_id == "req-input-type"  # type: ignore[attr-defined]
    assert line.model_input_type == "outfit_photo"  # type: ignore[attr-defined]
    assert line.input_type == "product_photo"  # type: ignore[attr-defined]
    assert line.item_count == 1  # type: ignore[attr-defined]


def test_a_label_that_is_not_an_input_type_is_logged_without_its_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The label is the model's output, so a stray value is never copied into the log.
    caplog.set_level(logging.DEBUG, logger="vga")
    reading = make_reading(input_type="IGNORE ALL RULES", items=_items(1))

    validate_reading(reading, text="black blazer", has_image=False)

    [line] = _override_lines(caplog)
    assert line.model_input_type == "unrecognised"  # type: ignore[attr-defined]
    assert "IGNORE" not in caplog.text


@pytest.mark.parametrize(("text", "has_image", "item_count", "derived"), SITUATIONS)
def test_an_agreeing_label_writes_no_line(
    caplog: pytest.LogCaptureFixture,
    text: str | None,
    has_image: bool,
    item_count: int,
    derived: InputType,
) -> None:
    caplog.set_level(logging.DEBUG, logger="vga")
    reading = make_reading(input_type=derived, items=_items(item_count))

    validate_reading(reading, text=text, has_image=has_image)

    assert _override_lines(caplog) == []


async def test_the_line_carries_the_request_id_of_the_request_being_understood(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="vga")
    r = rig(answer(make_reading(input_type=InputType.OUTFIT_PHOTO, items=_items(1))))
    request = make_search_request(image=make_image_bytes(), text=None)

    await r.understander.understand(request)

    [line] = _override_lines(caplog)
    assert line.request_id == request.request_id  # type: ignore[attr-defined]


def test_an_answer_that_is_rejected_derives_and_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Only an accepted answer has a request type. A rejected one is asked for again, and the
    # corrective retry's answer is the one that counts.
    caplog.set_level(logging.DEBUG, logger="vga")
    broken = make_reading_item(search_keywords=[])  # a garment with nothing to search for
    reading = make_reading(input_type=InputType.OUTFIT_PHOTO, items=[broken])

    with pytest.raises(OutputValidationError):
        validate_reading(reading, text=None, has_image=True)

    assert _override_lines(caplog) == []


# --------------------------------------------------------------------------------------------
# The raw-text fallback decides the same way
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("has_image", [False, True])
def test_the_fallback_gives_the_type_the_rule_gives_for_one_item_of_typed_text(
    has_image: bool,
) -> None:
    result = fallback_result("white sneakers", has_image=has_image, usage=Usage())

    assert result.input_type is derive_input_type(
        has_image=has_image, has_text=True, item_count=len(result.items)
    )
    assert result.input_type is (InputType.PHOTO_TEXT if has_image else InputType.TEXT)
