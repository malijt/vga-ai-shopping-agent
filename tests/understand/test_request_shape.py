"""What one Understand request looks like on the wire, and what comes back (plan 5.1.2, 5.2.1)."""

import base64
import io
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tests.factories import make_image_bytes, make_search_request, make_settings
from tests.understand.conftest import TEST_MODEL, RigFactory
from tests.understand.fake_openai import answer
from tests.understand.readings import make_reading, make_reading_budget, make_reading_item
from vga.models import Category, Gender, GenderSource, InputType, UnderstandResult
from vga.understand import PROMPT_VERSION
from vga.understand.gateway import MAX_OUTPUT_TOKENS, OPENAI_TIMEOUT_S
from vga.understand.prompt import system_prompt


def _assert_strict_schema(node: Any, path: str = "schema") -> None:
    """Every object in a strict structured-output schema lists all its properties as required and
    forbids extra ones. OpenAI rejects the call otherwise."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, path
            assert sorted(node.get("required", [])) == sorted(node.get("properties", {})), path
        for key, value in node.items():
            _assert_strict_schema(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_strict_schema(value, f"{path}[{index}]")


async def test_the_call_is_pinned_bounded_stored_nowhere_and_asks_for_a_strict_schema(
    rig: RigFactory,
) -> None:
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request(text="black blazer"))

    [request] = r.fake.requests
    assert request.body["model"] == TEST_MODEL
    assert request.body["store"] is False
    assert request.body["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert request.body["reasoning"] == {"effort": "low"}
    assert request.timeout["read"] == OPENAI_TIMEOUT_S
    assert request.body["text"]["format"]["type"] == "json_schema"
    assert request.body["text"]["format"]["strict"] is True
    _assert_strict_schema(request.schema)


async def test_the_schema_the_model_sees_has_no_field_the_model_must_not_write(
    rig: RigFactory,
) -> None:
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request())

    properties = set(r.fake.requests[0].schema["properties"])
    assert properties == {"verdict", "input_type", "language", "items", "budget", "edits"}
    assert not properties & {"prompt_version", "model", "usage", "warnings"}


async def test_instructions_are_the_system_message_and_the_shopper_a_separate_user_message(
    rig: RigFactory,
) -> None:
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request(text="black blazer for men"))

    [request] = r.fake.requests
    assert request.system_messages == [system_prompt()]
    assert "<user_text>\nblack blazer for men\n</user_text>" in request.user_text
    assert "black blazer for men" not in request.system_messages[0]


async def test_a_photo_is_sent_as_a_small_metadata_free_jpeg_data_url(rig: RigFactory) -> None:
    exif = Image.Exif()
    exif[0x010F] = "SecretPhone Inc"
    buffer = io.BytesIO()
    Image.new("RGB", (3000, 1500), (90, 60, 30)).save(buffer, format="JPEG", exif=exif)
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request(image=buffer.getvalue(), text=None))

    url = r.fake.requests[0].image_url
    assert url is not None
    prefix, _, payload = url.partition(",")
    assert prefix == "data:image/jpeg;base64"
    sent = Image.open(io.BytesIO(base64.b64decode(payload)))
    assert sent.size == (1024, 512)
    assert dict(sent.getexif()) == {}
    assert b"SecretPhone" not in base64.b64decode(payload)


async def test_the_photo_is_never_written_to_disk(
    rig: RigFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))  # Python caches the temp dir
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request(image=make_image_bytes(), text=None))

    assert os.listdir(tmp_path) == []


async def test_a_text_request_sends_no_image(rig: RigFactory) -> None:
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request(text="black blazer"))

    assert r.fake.requests[0].image_url is None


async def test_text_with_no_letter_or_digit_is_not_sent_along_with_a_photo(
    rig: RigFactory,
) -> None:
    r = rig(answer(make_reading()))

    result = await r.understander.understand(
        make_search_request(image=make_image_bytes(), text="!!! ### ;;;")
    )

    request = r.fake.requests[0]
    assert "<user_text>" not in request.user_text
    assert request.image_url is not None
    assert result.input_type is InputType.PRODUCT_PHOTO


async def test_the_result_carries_the_checked_answer_and_the_matched_pair_of_versions(
    rig: RigFactory,
) -> None:
    item = make_reading_item(
        category=Category.TOPS,
        colour="white",
        style="cotton shirt",
        material="cotton",
        gender=Gender.MEN,
        gender_source=GenderSource.EXPLICIT,
        search_keywords=["white cotton shirt", "cotton shirt"],
    )
    reading = make_reading(
        items=[item],
        budget=make_reading_budget(max_price=200, currency="AED"),
        language="ar",
    )
    r = rig(answer(reading, input_tokens=321, output_tokens=45))

    result = await r.understander.understand(
        make_search_request(text="أريد قميصاً أبيض من القطن للرجال بأقل من 200 درهم")
    )

    assert isinstance(result, UnderstandResult)
    assert result.model == TEST_MODEL
    assert result.prompt_version == PROMPT_VERSION
    assert result.language == "ar"
    assert result.input_type is InputType.TEXT
    assert result.budget is not None
    assert (result.budget.max_price, result.budget.currency) == (200.0, "AED")
    [out] = result.items
    assert out.category is Category.TOPS
    assert out.gender_source is GenderSource.EXPLICIT
    assert out.search_keywords == ["white cotton shirt men", "cotton shirt"]
    assert result.usage.input_tokens == 321
    assert result.usage.output_tokens == 45
    assert result.usage.llm_calls == 1
    assert result.warnings == []


async def test_an_outfit_photo_gives_one_item_per_garment(rig: RigFactory) -> None:
    items = [
        make_reading_item(
            category=Category.TOPS, style="t-shirt", search_keywords=["white t-shirt"]
        ),
        make_reading_item(category=Category.BOTTOMS, style="jeans", search_keywords=["blue jeans"]),
        make_reading_item(
            category=Category.SHOES, style="sneakers", search_keywords=["white sneakers"]
        ),
    ]
    r = rig(answer(make_reading(items=items, input_type=InputType.OUTFIT_PHOTO)))

    result = await r.understander.understand(
        make_search_request(image=make_image_bytes(), text=None)
    )

    assert result.input_type is InputType.OUTFIT_PHOTO
    assert [i.category for i in result.items] == [Category.TOPS, Category.BOTTOMS, Category.SHOES]


async def test_the_request_object_is_left_untouched(rig: RigFactory) -> None:
    r = rig(answer(make_reading()))
    request = make_search_request(text="black blazer")
    before = request.model_copy()

    await r.understander.understand(request)

    assert request == before


@pytest.mark.parametrize(
    ("model", "sends_reasoning"),
    [
        ("gpt-5-mini-2025-08-07", True),
        ("gpt-5.4-mini-2026-03-17", True),
        ("o4-mini-2025-04-16", True),
        ("gpt-4.1-mini-2025-04-14", False),
        ("gpt-4o-mini-2024-07-18", False),
    ],
)
async def test_reasoning_effort_is_sent_only_to_models_that_accept_it(
    rig: RigFactory, model: str, sends_reasoning: bool
) -> None:
    r = rig(answer(make_reading()), settings_override=make_settings(openai_model=model))

    await r.understander.understand(make_search_request(text="black blazer"))

    body = r.fake.requests[0].body
    assert body["model"] == model
    assert ("reasoning" in body) is sends_reasoning
