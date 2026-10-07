"""Rows and the small report of the Understand eval, shared by the live run and its offline test."""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tests.factories import make_search_request
from tests.understand.eval_cases import (
    VALID_SCHEMA,
    EdgeCase,
    GoldenCase,
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


@dataclass
class Row:
    kind: str
    case_id: str
    expected: str
    got: str
    status: str
    problems: list[str] = field(default_factory=list)


@dataclass
class Report:
    model: str | None
    calls_made: int = 0
    rows: list[Row] = field(default_factory=list)

    def add(self, row: Row) -> None:
        self.rows.append(row)

    def count(self, status: str) -> int:
        return sum(row.status == status for row in self.rows)

    def write(self, directory: Path, *, generated_at: datetime | None = None) -> Path:
        """Write ``understand-live.md`` and ``understand-live.json``; returns the Markdown path."""
        directory.mkdir(parents=True, exist_ok=True)
        moment = generated_at or datetime.now(UTC)
        header = {
            "generated_at": moment.isoformat(timespec="seconds"),
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
            "calls_made": self.calls_made,
            "passed": self.count(PASS),
            "failed": self.count(FAIL),
            "skipped": self.count(SKIPPED),
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
            "| kind | case | expected | got | result | problems |",
            "|---|---|---|---|---|---|",
            *[
                f"| {row.kind} | {row.case_id} | {row.expected} | {row.got} | {row.status} | "
                f"{'; '.join(row.problems).replace('|', '/')} |"
                for row in self.rows
            ],
            "",
        ]
        target = directory / "understand-live.md"
        target.write_text("\n".join(lines), encoding="utf-8")
        return target


async def golden_row(understander: Understander, case: GoldenCase, image: bytes | None) -> Row:
    """Run one golden input and compare it with the fixture's ``expect``."""
    outcome = await run_request(understander, make_search_request(text=case.text, image=image))
    if outcome.result is None or outcome.kind != VALID_SCHEMA:
        problems = [f"the request ended as {outcome.kind}: {outcome.message or 'a fallback'}"]
    else:
        problems = golden_problems(outcome.result, case.expect)
    return Row("golden", case.id, "parsed", outcome.kind, FAIL if problems else PASS, problems)


async def edge_row(understander: Understander, case: EdgeCase) -> Row:
    """Run one edge case. Strict: a fallback where ``valid_schema`` is expected is a failure."""
    outcome = await run_edge_case(understander, case)
    problems = judge_edge_case(case, outcome)
    return Row("edge", case.id, case.expected, outcome.kind, FAIL if problems else PASS, problems)
