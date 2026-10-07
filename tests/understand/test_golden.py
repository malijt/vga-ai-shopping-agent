"""The six golden examples (plan 5.1.3): hand-written expected outputs, labelled as such.

They are NOT recordings of the OpenAI API: no key was available when they were written. Offline
they prove that an answer of this shape is accepted and read correctly by our code. The live eval
(``test_live_eval``) runs the same six inputs against the real model and compares with ``expect``.
"""

import json

import pytest

from tests.factories import make_image_bytes, make_search_request
from tests.understand.conftest import RigFactory
from tests.understand.eval_cases import GOLDEN_DIR, GoldenCase, golden_problems, load_golden_cases
from tests.understand.fake_openai import answer
from vga.models import GenderSource
from vga.understand import FALLBACK_MARKER
from vga.understand.schema import UnderstandReading

GOLDEN = {case.id: case for case in load_golden_cases()}


def test_the_six_cases_the_plan_asks_for_are_present() -> None:
    assert set(GOLDEN) == {
        "g1_product_photo",
        "g2_outfit_photo",
        "g3_text_english",
        "g4_text_arabic",
        "g5_photo_and_text",
        "g6_budget_in_text",
    }


@pytest.mark.parametrize("path", sorted(GOLDEN_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_every_fixture_says_in_its_own_text_that_it_is_hand_written_not_recorded(path) -> None:
    provenance = json.loads(path.read_text(encoding="utf-8"))["provenance"]

    assert "HAND-WRITTEN" in provenance
    assert "NOT recorded" in provenance


@pytest.mark.parametrize("case", GOLDEN.values(), ids=lambda c: c.id)
def test_every_fixture_loads_into_the_models_answer_schema(case: GoldenCase) -> None:
    reading = UnderstandReading.model_validate(case.model_output)

    assert reading.verdict.value == "ok"


@pytest.mark.parametrize("case", GOLDEN.values(), ids=lambda c: c.id)
async def test_the_parsed_result_satisfies_the_fields_the_fixture_expects(
    rig: RigFactory, case: GoldenCase
) -> None:
    reading = UnderstandReading.model_validate(case.model_output)
    r = rig(answer(reading))
    image = make_image_bytes() if case.image else None  # stand-in: the fake model sees no pixels

    result = await r.understander.understand(make_search_request(text=case.text, image=image))

    assert result.model != FALLBACK_MARKER
    assert golden_problems(result, case.expect) == []
    assert len(r.fake.requests) == 1


async def test_an_inferred_gender_in_the_outfit_photo_stays_out_of_every_keyword(
    rig: RigFactory,
) -> None:
    case = GOLDEN["g2_outfit_photo"]
    r = rig(answer(UnderstandReading.model_validate(case.model_output)))

    result = await r.understander.understand(
        make_search_request(image=make_image_bytes(), text=None)
    )

    assert [item.gender_source for item in result.items] == [GenderSource.INFERRED] * 3
    words = {word for item in result.items for kw in item.search_keywords for word in kw.split()}
    assert not words & {"men", "man", "women", "male", "female"}


async def test_a_stated_gender_goes_into_the_first_keyword_only(rig: RigFactory) -> None:
    case = GOLDEN["g3_text_english"]
    r = rig(answer(UnderstandReading.model_validate(case.model_output)))

    result = await r.understander.understand(make_search_request(text=case.text))

    assert result.items[0].search_keywords == ["navy slim fit chinos men", "slim fit chinos"]


async def test_an_arabic_request_comes_back_with_english_keywords(rig: RigFactory) -> None:
    case = GOLDEN["g4_text_arabic"]
    r = rig(answer(UnderstandReading.model_validate(case.model_output)))

    result = await r.understander.understand(make_search_request(text=case.text))

    assert result.language == "ar"
    assert all(kw.isascii() for kw in result.items[0].search_keywords)


async def test_the_budget_stays_out_of_the_keywords(rig: RigFactory) -> None:
    case = GOLDEN["g6_budget_in_text"]
    r = rig(answer(UnderstandReading.model_validate(case.model_output)))

    result = await r.understander.understand(make_search_request(text=case.text))

    assert result.budget is not None
    assert result.budget.max_price == 600.0
    assert not any(ch.isdigit() for kw in result.items[0].search_keywords for ch in kw)


def test_the_comparison_really_fails_when_a_result_is_wrong() -> None:
    # A guard on the guard: if golden_problems accepted everything these tests would prove nothing.
    from tests.factories import make_understand_result

    wrong = make_understand_result()  # a black oversized blazer for a text request

    problems = golden_problems(wrong, GOLDEN["g6_budget_in_text"].expect)

    assert any("category" in p for p in problems)
    assert any("budget" in p for p in problems)
