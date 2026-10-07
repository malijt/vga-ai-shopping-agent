"""Live eval of the Understand step against the real OpenAI API (plan 5.3.5).

Run it with::

    OPENAI_API_KEY=... uv run pytest -m live tests/understand

The model comes from ``config/settings.yaml`` (``OPENAI_MODEL`` overrides it). It runs the 6 golden
inputs and every case in ``eval/data/edge_cases.yaml`` (about 16 OpenAI calls: the cases that are
rejected before any call, such as empty text, cost none), and writes a small report to
``eval/results/understand-live.md`` (and ``.json``) with, for every case, what was expected, what
came back, and the latency, calls and tokens it took. Set ``VGA_EVAL_REPORT_DIR`` to put the report
somewhere else. ``eval/results/`` is git-ignored.

``VGA_EVAL_REASONING_EFFORT`` (one of ``none``, ``low``, ``medium``, ``high``, ``xhigh``, ``max``)
runs the eval with another reasoning effort than the one in ``vga.understand.gateway``, to compare
two settings without editing the code. The report records the effort used.

It is skipped, not failed, when ``OPENAI_API_KEY`` is missing, and never runs in CI or in a plain
``pytest``. Run it again, and record the score in ``src/vga/understand/prompts/CHANGELOG.md``,
before any change to the prompt or the model (CLAUDE.md, Non-Negotiables).

Golden cases that need a real photo are skipped, and listed as skipped in the report, until the
photos in ``eval/data/ASSETS.md`` are in ``eval/data/assets/private/``.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import get_args

import pytest
from openai.types.shared import ReasoningEffort

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
from vga.understand.gateway import REASONING_EFFORT

pytestmark = pytest.mark.live

REPORT_DIR_ENV = "VGA_EVAL_REPORT_DIR"
EFFORT_ENV = "VGA_EVAL_REASONING_EFFORT"
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
            "to a pinned snapshot id such as gpt-6-luna"
        )
    return loaded


@pytest.fixture(scope="module", autouse=True)
def reasoning_effort(settings: Settings, request: pytest.FixtureRequest) -> Iterator[str]:
    """The effort this run uses: the constant in the gateway, or ``VGA_EVAL_REASONING_EFFORT``."""
    chosen = os.environ.get(EFFORT_ENV, "").strip() or REASONING_EFFORT
    if chosen not in get_args(ReasoningEffort):
        pytest.fail(f"{EFFORT_ENV} must be one of {get_args(ReasoningEffort)}, got {chosen!r}")
    patcher = pytest.MonkeyPatch()
    patcher.setattr("vga.understand.understander.REASONING_EFFORT", chosen)
    yield chosen
    patcher.undo()


@pytest.fixture(scope="module")
def budget() -> CallBudget:
    return CallBudget()


@pytest.fixture(scope="module")
def report(settings: Settings, budget: CallBudget, reasoning_effort: str) -> Iterator[Report]:
    live = Report(model=settings.openai_model, reasoning_effort=reasoning_effort)
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
