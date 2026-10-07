"""Live eval of the Understand step against the real OpenAI API (plan 5.3.5).

Run it with::

    OPENAI_API_KEY=... OPENAI_MODEL=gpt-5-mini-2025-08-07 uv run pytest -m live tests/understand

It runs the 6 golden inputs and every case in ``eval/data/edge_cases.yaml`` (about 25 calls), and
writes a small report to ``eval/results/understand-live.md`` (and ``.json``); set
``VGA_EVAL_REPORT_DIR`` to put it somewhere else. ``eval/results/`` is git-ignored.

It is skipped, not failed, when ``OPENAI_API_KEY`` is missing, and never runs in CI or in a plain
``pytest``. Run it again, and record the score in ``src/vga/understand/prompts/CHANGELOG.md``,
before any change to the prompt or the model (CLAUDE.md, Non-Negotiables).

Golden cases that need a real photo are skipped, and listed as skipped in the report, until the
photos in ``eval/data/ASSETS.md`` are in ``eval/data/assets/private/``.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from tests.understand.eval_cases import (
    REPO_ROOT,
    EdgeCase,
    GoldenCase,
    load_edge_cases,
    load_golden_cases,
)
from tests.understand.eval_report import SKIPPED, Report, Row, edge_row, golden_row
from vga.errors import ConfigError
from vga.settings import Settings, load_dotenv, load_settings
from vga.understand import CallBudget, OpenAIUnderstander, create_openai_client

pytestmark = pytest.mark.live

REPORT_DIR_ENV = "VGA_EVAL_REPORT_DIR"
DEFAULT_REPORT_DIR = REPO_ROOT / "eval" / "results"


@pytest.fixture(scope="module")
def settings() -> Settings:
    """The key and the model are checked here, once, so a missing key skips every test cleanly."""
    load_dotenv()  # reads .env into the environment when the shell has not set the key
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY is not set: the live eval needs a real key")
    try:
        loaded = load_settings()
    except ConfigError as error:
        pytest.fail(f"settings are invalid: {error.detail}")
    if not loaded.openai_model:
        pytest.fail(
            "openai_model is not set: set OPENAI_MODEL (or openai_model in config/settings.yaml) "
            "to a dated snapshot such as gpt-5-mini-2025-08-07"
        )
    return loaded


@pytest.fixture(scope="module")
def budget() -> CallBudget:
    return CallBudget()


@pytest.fixture(scope="module")
def report(settings: Settings, budget: CallBudget) -> Iterator[Report]:
    live = Report(model=settings.openai_model)
    yield live
    live.calls_made = budget.used_today
    target = live.write(Path(os.environ.get(REPORT_DIR_ENV) or DEFAULT_REPORT_DIR))
    print(f"\nUnderstand live eval report: {target}")


@pytest.fixture
async def understander(settings: Settings, budget: CallBudget) -> AsyncIterator[OpenAIUnderstander]:
    """A fresh client per test: an async client belongs to the event loop it is first used in."""
    client = create_openai_client()
    yield OpenAIUnderstander(settings, client, budget=budget)
    await client.close()


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda case: case.id)
async def test_golden_case(
    case: GoldenCase, understander: OpenAIUnderstander, report: Report
) -> None:
    image = None
    if case.image_path is not None:
        if not case.image_path.is_file():
            report.add(Row("golden", case.id, "parsed", "-", SKIPPED, ["photo missing"]))
            pytest.skip(f"{case.image} is missing; see eval/data/ASSETS.md")
        image = case.image_path.read_bytes()

    row = await golden_row(understander, case, image)

    report.add(row)
    assert not row.problems, "\n".join(row.problems)


@pytest.mark.parametrize("case", load_edge_cases(), ids=lambda case: case.id)
async def test_edge_case(case: EdgeCase, understander: OpenAIUnderstander, report: Report) -> None:
    row = await edge_row(understander, case)

    report.add(row)
    assert not row.problems, "\n".join([case.why, *row.problems])
