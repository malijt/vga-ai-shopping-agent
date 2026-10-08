"""The live eval's own machinery, run offline: rows, strictness and the report it writes.

The live test (``test_live_eval``) cannot run without an API key. Everything in it except the
network call is exercised here, with the scripted fake model standing in.
"""

import json
import logging
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


async def test_a_row_records_the_calls_tokens_and_latency_of_its_case(rig: RigFactory) -> None:
    case = EDGE["e01_injection_with_real_request"]
    step = WELL_BEHAVED[case.id]
    assert step is not None
    r = rig(step)

    row = await edge_row(r.understander, case)

    assert (row.calls, row.input_tokens, row.output_tokens) == (1, 100, 40)
    assert row.latency_ms is not None
    assert row.latency_ms >= 0
    assert row.with_image is False
    assert "outerwear | black | leather jacket" in row.answer


async def test_tokens_are_counted_even_when_the_case_ends_in_a_plain_error(
    rig: RigFactory,
) -> None:
    case = EDGE["e12_out_of_scope_handbag"]
    step = WELL_BEHAVED[case.id]
    assert step is not None
    r = rig(step)

    row = await edge_row(r.understander, case)

    assert (row.got, row.calls, row.input_tokens, row.output_tokens) == (
        "friendly_error",
        1,
        100,
        40,
    )
    assert row.answer == "error: nothing to shop for: out_of_scope"


async def test_a_case_that_never_reaches_the_model_costs_no_calls(rig: RigFactory) -> None:
    r = rig()

    row = await edge_row(r.understander, EDGE["e08_empty_text"])

    assert (row.calls, row.input_tokens, row.output_tokens) == (0, 0, 0)


async def test_a_failed_call_is_explained_in_the_notes(rig: RigFactory) -> None:
    r = rig(http_error(400))

    row = await edge_row(r.understander, EDGE["e01_injection_with_real_request"])

    assert row.status == FAIL
    assert any("call error" in note and "400" in note for note in row.notes)
    assert any(note.startswith("fallback:") for note in row.notes)


async def test_measuring_does_not_leave_the_logger_changed(rig: RigFactory) -> None:
    logger = logging.getLogger("vga.understand")
    handlers, level = list(logger.handlers), logger.level
    r = rig(answer(make_reading()))

    await edge_row(r.understander, EDGE["e01_injection_with_real_request"])

    assert (list(logger.handlers), logger.level) == (handlers, level)


def test_the_report_counts_and_lists_every_row(tmp_path: Path) -> None:
    report = Report(model="gpt-6-luna", calls_made=7, reasoning_effort="low")
    report.add(Row("edge", "e01", "valid_schema", "valid_schema", PASS))
    report.add(Row("edge", "e02", "friendly_error", "valid_schema", FAIL, ["a | pipe", "second"]))
    report.add(Row("golden", "g1", "parsed", "-", SKIPPED, ["photo missing"]))

    target = report.write(tmp_path / "out", generated_at=datetime(2026, 10, 7, 12, 0, tzinfo=UTC))

    text = target.read_text(encoding="utf-8")
    assert target.name == "understand-live.md"
    assert "- passed: 1" in text
    assert "- failed: 1" in text
    assert "- skipped: 1" in text
    assert "- model: gpt-6-luna" in text
    assert "- reasoning_effort: low" in text
    assert "- generated_at: 2026-10-07T12:00:00+00:00" in text
    assert "a / pipe; second" in text  # a pipe would break the table
    data = json.loads((tmp_path / "out" / "understand-live.json").read_text(encoding="utf-8"))
    assert [row["case_id"] for row in data["rows"]] == ["e01", "e02", "g1"]
    assert data["calls_made"] == 7


def test_the_summary_gives_median_and_worst_latency_and_average_tokens(tmp_path: Path) -> None:
    report = Report(model="gpt-6-luna")
    for case_id, ms, calls, tokens_in, tokens_out, image in [
        ("a", 1000.0, 1, 400, 100, False),
        ("b", 3000.0, 1, 600, 200, False),
        ("c", 2000.0, 2, 900, 300, False),
        ("d", 9000.0, 1, 1500, 100, True),  # a photo request: left out of the text median
        ("e", 0.0, 0, 0, 0, False),  # rejected before any call: left out of everything
    ]:
        report.add(
            Row(
                "edge",
                case_id,
                "valid_schema",
                "valid_schema",
                PASS,
                with_image=image,
                latency_ms=ms,
                calls=calls,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
            )
        )

    summary = report.summary()

    assert summary["median_latency_ms_text_requests"] == 2000.0
    assert summary["median_latency_ms_all"] == 2500.0
    assert summary["worst_latency_ms"] == 9000.0
    assert summary["openai_calls_in_rows"] == 5
    assert summary["avg_input_tokens_per_call"] == 680.0
    assert summary["avg_output_tokens_per_call"] == 140.0


def test_an_empty_report_has_no_figures_rather_than_an_error(tmp_path: Path) -> None:
    summary = Report(model=None).summary()

    assert summary["median_latency_ms_text_requests"] is None
    assert summary["worst_latency_ms"] is None
    assert summary["avg_input_tokens_per_call"] is None
