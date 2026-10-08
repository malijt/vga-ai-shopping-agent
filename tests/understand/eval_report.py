"""Rows and the small report of the Understand eval, shared by the live run and its offline test.

Each row also records what the case cost: how long ``understand()`` took (the wait a shopper would
feel), how many OpenAI calls it made and how many tokens they used. The call and token counts come
from the one log line the gateway writes per call, so they are counted even for a case that ends in
a plain error message (a result object would not carry them).
"""

import json
import logging
import statistics
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tests.factories import make_search_request
from tests.understand.eval_cases import (
    VALID_SCHEMA,
    EdgeCase,
    GoldenCase,
    Outcome,
    golden_problems,
    judge_edge_case,
    run_edge_case,
    run_request,
)
from vga.interfaces import Understander
from vga.understand import PROMPT_VERSION

PASS = "pass"
FAIL = "FAIL"
SKIPPED = "skipped"

UNDERSTAND_LOGGER = "vga.understand"
"""The gateway and the understander log under this name; one handler on it sees both."""
CALL_LINE = "openai call"


@dataclass
class Measured:
    """What one case cost. Filled in when the ``measure()`` block ends."""

    latency_ms: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    notes: list[str] = field(default_factory=list)
    """Short, value-free facts about calls that did not go well (outcome, HTTP status, fallback
    reason), to explain a failing row."""


class _CallCollector(logging.Handler):
    def __init__(self, measured: Measured) -> None:
        super().__init__(logging.INFO)
        self._measured = measured

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message == CALL_LINE:
            self._measured.calls += 1
            self._measured.input_tokens += int(getattr(record, "input_tokens", 0) or 0)
            self._measured.output_tokens += int(getattr(record, "output_tokens", 0) or 0)
            outcome = getattr(record, "outcome", "ok")
            if outcome != "ok":
                status = getattr(record, "status_code", None)
                error_type = getattr(record, "error_type", None)
                detail = " ".join(str(part) for part in (error_type, status) if part)
                self._measured.notes.append(f"call {outcome} {detail}".strip())
        elif message == "understand fallback":
            self._measured.notes.append(f"fallback: {getattr(record, 'reason', '?')}")
        elif message == "model answer rejected":
            self._measured.notes.append(f"answer rejected: {getattr(record, 'problems', '?')}")


@contextmanager
def measure() -> Iterator[Measured]:
    """Time the block and count the OpenAI calls and tokens logged inside it."""
    measured = Measured()
    logger = logging.getLogger(UNDERSTAND_LOGGER)
    handler = _CallCollector(measured)
    previous_level = logger.level
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)  # the "ok" call line is INFO; a quiet logger would drop it
    logger.addHandler(handler)
    started = time.perf_counter()
    try:
        yield measured
    finally:
        measured.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


@dataclass
class Row:
    kind: str
    case_id: str
    expected: str
    got: str
    status: str
    problems: list[str] = field(default_factory=list)
    answer: str = ""
    """One line saying what came back (the items, or the reason for a plain error)."""
    with_image: bool = False
    latency_ms: float | None = None
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    notes: list[str] = field(default_factory=list)


def _p50(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


@dataclass
class Report:
    model: str | None
    calls_made: int = 0
    reasoning_effort: str | None = None
    rows: list[Row] = field(default_factory=list)

    def add(self, row: Row) -> None:
        self.rows.append(row)

    def count(self, status: str) -> int:
        return sum(row.status == status for row in self.rows)

    def summary(self) -> dict[str, object]:
        """Latency and token figures over the rows that made at least one OpenAI call."""
        called = [row for row in self.rows if row.calls and row.latency_ms is not None]
        text_only = [row.latency_ms for row in called if not row.with_image and row.latency_ms]
        total_calls = sum(row.calls for row in called)
        return {
            "rows_with_model_calls": len(called),
            "openai_calls_in_rows": total_calls,
            "median_latency_ms_text_requests": _p50([float(v) for v in text_only]),
            "median_latency_ms_all": _p50([row.latency_ms or 0.0 for row in called]),
            "worst_latency_ms": max((row.latency_ms or 0.0 for row in called), default=None),
            "avg_input_tokens_per_call": (
                round(sum(row.input_tokens for row in called) / total_calls, 1)
                if total_calls
                else None
            ),
            "avg_output_tokens_per_call": (
                round(sum(row.output_tokens for row in called) / total_calls, 1)
                if total_calls
                else None
            ),
        }

    def write(self, directory: Path, *, generated_at: datetime | None = None) -> Path:
        """Write ``understand-live.md`` and ``understand-live.json``; returns the Markdown path."""
        directory.mkdir(parents=True, exist_ok=True)
        moment = generated_at or datetime.now(UTC)
        header = {
            "generated_at": moment.isoformat(timespec="seconds"),
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "prompt_version": PROMPT_VERSION,
            "calls_made": self.calls_made,
            "passed": self.count(PASS),
            "failed": self.count(FAIL),
            "skipped": self.count(SKIPPED),
            **self.summary(),
        }
        (directory / "understand-live.json").write_text(
            json.dumps({**header, "rows": [asdict(row) for row in self.rows]}, indent=2),
            encoding="utf-8",
        )
        lines = [
            "# Understand live eval",
            "",
            *[f"- {key}: {value}" for key, value in header.items()],
            "",
            "| kind | case | expected | got | result | ms | calls | tokens in/out | answer "
            "| problems | notes |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
            *[
                f"| {row.kind} | {row.case_id} | {row.expected} | {row.got} | {row.status} | "
                f"{'-' if row.latency_ms is None else row.latency_ms} | {row.calls} | "
                f"{row.input_tokens}/{row.output_tokens} | {_cell(row.answer)} | "
                f"{_cell('; '.join(row.problems))} | {_cell('; '.join(row.notes))} |"
                for row in self.rows
            ],
            "",
        ]
        target = directory / "understand-live.md"
        target.write_text("\n".join(lines), encoding="utf-8")
        return target


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def describe(outcome: Outcome) -> str:
    """One line saying what a case produced, for the report (no photo, nothing secret)."""
    result = outcome.result
    if result is None:
        reason = outcome.detail or ""
        return f"error: {reason}" if reason else "error"
    items = "; ".join(
        f"{item.category.value} | {item.colour} | {item.style} | "
        f"{item.gender.value if item.gender else None}/{item.gender_source.value} | "
        f"{item.search_keywords}"
        for item in result.items
    )
    budget = (
        None if result.budget is None else f"{result.budget.max_price} {result.budget.currency}"
    )
    return (
        f"{result.input_type.value}/{result.language}: {items}; budget {budget}; "
        f"edits {result.edits}"
    )


async def golden_row(understander: Understander, case: GoldenCase, image: bytes | None) -> Row:
    """Run one golden input and compare it with the fixture's ``expect``."""
    with measure() as cost:
        outcome = await run_request(understander, make_search_request(text=case.text, image=image))
    if outcome.result is None or outcome.kind != VALID_SCHEMA:
        problems = [f"the request ended as {outcome.kind}: {outcome.message or 'a fallback'}"]
    else:
        problems = golden_problems(outcome.result, case.expect)
    return _row("golden", case.id, "parsed", outcome, problems, cost, image is not None)


async def edge_row(understander: Understander, case: EdgeCase) -> Row:
    """Run one edge case. Strict: a fallback where ``valid_schema`` is expected is a failure."""
    with measure() as cost:
        outcome = await run_edge_case(understander, case)
    problems = judge_edge_case(case, outcome)
    return _row("edge", case.id, case.expected, outcome, problems, cost, case.image is not None)


def _row(
    kind: str,
    case_id: str,
    expected: str,
    outcome: Outcome,
    problems: list[str],
    cost: Measured,
    with_image: bool,
) -> Row:
    return Row(
        kind,
        case_id,
        expected,
        outcome.kind,
        FAIL if problems else PASS,
        problems,
        answer=describe(outcome),
        with_image=with_image,
        latency_ms=cost.latency_ms,
        calls=cost.calls,
        input_tokens=cost.input_tokens,
        output_tokens=cost.output_tokens,
        notes=cost.notes,
    )
