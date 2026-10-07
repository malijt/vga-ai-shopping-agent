"""The two debug switches, and what each one writes.

``VGA_LOG_PROMPTS`` and ``VGA_DEBUG_DUMP`` exist to help a developer see what the app did, and both
write more to disk. Neither may ever write the photo (the audit in ``test_no_retention.py`` runs
under every combination). These tests pin down what they *do* write, because
``docs/privacy.md`` tells the owner exactly that, and the owner decides whether to turn them on.
"""

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.guards.privacy.audit import Audited, Workspace, log_problems
from tests.guards.privacy.scenarios import (
    BOTH,
    DUMP,
    MODEL_DOWN_WITH_TEXT,
    OFF,
    PHOTO_AND_TEXT,
    PRODUCT_PHOTO,
    PROMPTS,
    SHOPPER_WORDS,
    cases,
)
from vga.log import ROOT_LOGGER_NAME, configure_logging
from vga.settings import DEFAULT_SETTINGS_PATH, Settings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[3]

DUMP_KEYS = {
    "request_id",
    "item_index",
    "category",
    "rank",
    "url",
    "store",
    "strategy",
    "title",
    "price",
    "currency",
    "scores",
    "flags",
    "shown",
    "price_range",
    "price_range_min",
    "price_range_max",
}
"""What one line of the candidate dump holds (``vga.pipeline.dump``). Nothing about the shopper."""

LIBRARIES = ("openai", "httpx", "httpx2", "httpcore")
"""The libraries the photo passes through on its way to OpenAI."""


def log_text(audited: Audited) -> str:
    return audited.log_file.read_text(encoding="utf-8")


def records(audited: Audited) -> list[dict]:
    return [json.loads(line) for line in log_text(audited).splitlines()]


# --------------------------------------------------------------------------------------------
# Off unless someone turns them on
# --------------------------------------------------------------------------------------------


def test_both_switches_are_off_in_the_code_the_shipped_settings_and_the_example_file() -> None:
    shipped = load_settings(DEFAULT_SETTINGS_PATH, env={})
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert (Settings().log_prompts, Settings().debug_dump) == (False, False)
    assert (shipped.log_prompts, shipped.debug_dump) == (False, False)
    assert "\nVGA_LOG_PROMPTS=0\n" in example
    assert "\nVGA_DEBUG_DUMP=0\n" in example


@pytest.mark.parametrize("name", ["VGA_LOG_PROMPTS", "VGA_DEBUG_DUMP"])
def test_an_environment_variable_turns_a_switch_on(name: str) -> None:
    field = {"VGA_LOG_PROMPTS": "log_prompts", "VGA_DEBUG_DUMP": "debug_dump"}[name]

    settings = load_settings(DEFAULT_SETTINGS_PATH, env={name: "1"})

    assert getattr(settings, field) is True


# --------------------------------------------------------------------------------------------
# VGA_LOG_PROMPTS
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("audited", cases([PHOTO_AND_TEXT], [OFF, DUMP]), indirect=True)
async def test_with_prompt_logging_off_what_the_shopper_typed_is_not_logged(
    audited: Audited,
) -> None:
    assert SHOPPER_WORDS not in log_text(audited)
    assert not any(SHOPPER_WORDS in line for line in audited.watch.raw_logs.lines)
    messages = {record["message"] for record in records(audited)}
    assert not {"understand input", "understand parsed answer"} & messages


@pytest.mark.parametrize("audited", cases([PHOTO_AND_TEXT], [PROMPTS, BOTH]), indirect=True)
async def test_with_prompt_logging_on_the_typed_words_and_the_models_reading_are_logged(
    audited: Audited,
) -> None:
    by_message = {record["message"]: record for record in records(audited)}

    assert by_message["understand input"]["user_text"].endswith(SHOPPER_WORDS)
    reading = by_message["understand parsed answer"]["parsed_result"]
    assert reading["items"][0]["style"] == "oversized blazer"


@pytest.mark.parametrize("audited", cases([PRODUCT_PHOTO], [PROMPTS]), indirect=True)
async def test_with_prompt_logging_on_what_the_model_saw_in_the_photo_is_logged_but_not_the_photo(
    audited: Audited,
) -> None:
    reading = {r["message"]: r for r in records(audited)}["understand parsed answer"]

    assert reading["parsed_result"]["items"][0]["colour"] == "black"
    assert log_problems(audited) == []


# --------------------------------------------------------------------------------------------
# VGA_DEBUG_DUMP
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("audited", cases([PRODUCT_PHOTO], [OFF, PROMPTS]), indirect=True)
async def test_with_the_dump_off_no_candidate_file_is_written(audited: Audited) -> None:
    assert list(audited.workspace.logs.glob("candidates-*")) == []


@pytest.mark.parametrize("audited", cases([PHOTO_AND_TEXT], [DUMP]), indirect=True)
async def test_with_the_dump_on_each_request_writes_one_file_about_products_and_nothing_else(
    audited: Audited,
) -> None:
    [dump] = audited.workspace.logs.glob("candidates-*.jsonl")

    lines = [json.loads(line) for line in dump.read_text(encoding="utf-8").splitlines()]
    assert dump.name == f"candidates-{audited.responses[0].request_id}.jsonl"
    assert lines
    assert all(set(line) == DUMP_KEYS for line in lines)
    assert SHOPPER_WORDS not in dump.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------
# VGA_LOG_LEVEL=DEBUG
# --------------------------------------------------------------------------------------------


def test_the_debug_level_of_our_log_does_not_switch_on_debug_logging_of_the_libraries(
    tmp_path: Path, workspace: Workspace
) -> None:
    configure_logging(level="DEBUG", log_dir=tmp_path / "logs", stream=io.StringIO())

    assert logging.getLogger(ROOT_LOGGER_NAME).isEnabledFor(logging.DEBUG)
    for name in ("PIL", *LIBRARIES):
        assert not logging.getLogger(name).isEnabledFor(logging.DEBUG), (
            f"debug logging is on for {name!r} in this process; Pillow logs the EXIF values "
            "of a photo it reads at that level"
        )


@pytest.fixture
def libraries_at_debug() -> Iterator[None]:
    """What a developer does by setting ``OPENAI_LOG=debug`` or ``logging.basicConfig(DEBUG)``."""
    loggers = [logging.getLogger(name) for name in LIBRARIES]
    before = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
    yield
    for logger, level in zip(loggers, before, strict=True):
        logger.setLevel(level)


async def test_the_libraries_that_carry_the_photo_do_not_log_it_even_at_debug_level(
    libraries_at_debug: None, run
) -> None:
    """A guard on upgrades: a new version of the OpenAI SDK or of httpx that starts to log request
    bodies at debug level would put the photo in the log of anyone who turns that level on."""
    audited = await run(PRODUCT_PHOTO)

    from_libraries = [
        line for line in audited.watch.raw_logs.lines if line.split(" ", 1)[0].startswith(LIBRARIES)
    ]
    assert from_libraries, "the libraries logged nothing at debug level: the test saw no calls"
    assert log_problems(audited) == []


# --------------------------------------------------------------------------------------------
# When the model is down
# --------------------------------------------------------------------------------------------


async def test_when_the_model_is_down_the_typed_words_go_to_the_stores_and_the_photo_does_not(
    run,
) -> None:
    """The shopper is told so ("we searched with your words as typed"). The photo is not used."""
    audited = await run(MODEL_DOWN_WITH_TEXT)

    queries = audited.rig.world.queries("alpha")
    assert any(SHOPPER_WORDS in query for query in queries)
    assert audited.responses[0].warnings
    assert audited.rig.world.all_requests() > 0
    from tests.guards.privacy.audit import outbound_problems

    assert outbound_problems(audited) == []
