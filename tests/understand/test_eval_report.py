"""The live eval's own machinery, run offline: rows, strictness and the report it writes.

The live test (``test_live_eval``) cannot run without an API key. Everything in it except the
network call is exercised here, with the scripted fake model standing in.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.factories import make_image_bytes
from tests.understand.conftest import RigFactory
from tests.understand.eval_cases import load_edge_cases, load_golden_cases
from tests.understand.eval_report import FAIL, PASS, SKIPPED, Report, Row, edge_row, golden_row
from tests.understand.fake_openai import answer, http_error
from tests.understand.readings import make_reading
from tests.understand.test_edge_cases import WELL_BEHAVED
from vga.understand.schema import UnderstandReading

EDGE = {case.id: case for case in load_edge_cases()}
GOLDEN = {case.id: case for case in load_golden_cases()}


@pytest.mark.parametrize("case", GOLDEN.values(), ids=lambda c: c.id)
async def test_a_golden_row_passes_when_the_model_answers_as_the_fixture_expects(
    rig: RigFactory, case
) -> None:
    r = rig(answer(UnderstandReading.model_validate(case.model_output)))
    image = make_image_bytes() if case.image else None

    row = await golden_row(r.understander, case, image)

    assert (row.status, row.problems) == (PASS, [])


async def test_a_golden_row_fails_when_the_model_answers_something_else(rig: RigFactory) -> None:
    r = rig(answer(make_reading()))  # a black blazer, for a request about loafers

    row = await golden_row(r.understander, GOLDEN["g6_budget_in_text"], None)

    assert row.status == FAIL
    assert any("category" in problem for problem in row.problems)


async def test_a_golden_row_fails_when_the_model_path_fell_back(rig: RigFactory) -> None:
    r = rig(http_error(500), http_error(500))

    row = await golden_row(r.understander, GOLDEN["g3_text_english"], None)

    assert (row.status, row.got) == (FAIL, "fallback")


async def test_an_edge_row_passes_for_a_well_behaved_model(rig: RigFactory) -> None:
    case = EDGE["e12_out_of_scope_handbag"]
    step = WELL_BEHAVED[case.id]
    assert step is not None
    r = rig(step)

    row = await edge_row(r.understander, case)

    assert (row.status, row.expected, row.got) == (PASS, "friendly_error", "friendly_error")


async def test_the_live_run_is_strict_a_fallback_where_valid_schema_is_expected_fails(
    rig: RigFactory,
) -> None:
    r = rig(http_error(500), http_error(500))

    row = await edge_row(r.understander, EDGE["e01_injection_with_real_request"])

    assert row.status == FAIL
    assert row.problems == ["expected valid_schema, got fallback"]


async def test_a_request_that_cannot_be_built_counts_as_the_friendly_error_it_will_become(
    rig: RigFactory,
) -> None:
    r = rig()

    row = await edge_row(r.understander, EDGE["e08_empty_text"])

    assert (row.status, row.got) == (PASS, "friendly_error")
    assert r.fake.requests == []


def test_the_report_counts_and_lists_every_row(tmp_path: Path) -> None:
    report = Report(model="gpt-5-mini-2025-08-07", calls_made=7)
    report.add(Row("edge", "e01", "valid_schema", "valid_schema", PASS))
    report.add(Row("edge", "e02", "friendly_error", "valid_schema", FAIL, ["a | pipe", "second"]))
    report.add(Row("golden", "g1", "parsed", "-", SKIPPED, ["photo missing"]))

    target = report.write(tmp_path / "out", generated_at=datetime(2026, 10, 7, 12, 0, tzinfo=UTC))

    text = target.read_text(encoding="utf-8")
    assert target.name == "understand-live.md"
    assert "- passed: 1" in text
    assert "- failed: 1" in text
    assert "- skipped: 1" in text
    assert "- model: gpt-5-mini-2025-08-07" in text
    assert "- generated_at: 2026-10-07T12:00:00+00:00" in text
    assert "a / pipe; second" in text  # a pipe would break the table
    data = json.loads((tmp_path / "out" / "understand-live.json").read_text(encoding="utf-8"))
    assert [row["case_id"] for row in data["rows"]] == ["e01", "e02", "g1"]
    assert data["calls_made"] == 7
