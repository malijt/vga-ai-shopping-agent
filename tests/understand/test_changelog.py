"""The prompt and the model change together with a changelog entry (plan 5.3.6)."""

import re

from vga.settings import DEFAULT_SETTINGS_PATH, load_settings
from vga.understand import PROMPT_VERSION
from vga.understand.prompt import PROMPTS_DIR

CHANGELOG = PROMPTS_DIR / "CHANGELOG.md"


def test_the_current_prompt_version_has_an_entry_with_a_date_and_an_eval_result() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")

    heading = re.search(rf"^## {re.escape(PROMPT_VERSION)}: (\d{{4}}-\d{{2}}-\d{{2}})", text, re.M)
    assert heading, f"no '## {PROMPT_VERSION}: <date>' entry in {CHANGELOG.name}"
    entry = text[heading.start() :].split("\n## ")[0]
    assert "**Prompt:**" in entry
    assert "**Model:**" in entry
    assert "**Eval score:" in entry
    assert "**Reason:**" in entry


def test_the_current_entry_names_the_model_pinned_in_the_settings() -> None:
    # The prompt and the model are a matched pair (genai best practice 8): changing the pinned
    # model without a new changelog entry leaves the newest entry naming the old one.
    pinned = load_settings(DEFAULT_SETTINGS_PATH, env={}).openai_model
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = re.search(rf"^## {re.escape(PROMPT_VERSION)}: ", text, re.M)
    assert heading
    entry = text[heading.start() :].split("\n## ")[0]
    model_line = re.search(r"\*\*Model:\*\*[^\n]*", entry)

    assert pinned
    assert model_line
    assert f"`{pinned}`" in model_line.group(0)


def test_the_newest_entry_is_first_and_belongs_to_the_current_prompt_version() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")

    first = re.search(r"^## (\S+): ", text, re.M)

    assert first
    assert first.group(1) == PROMPT_VERSION


def test_a_prompt_version_that_has_not_been_run_live_says_pending_and_claims_no_result() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = re.search(rf"^## {re.escape(PROMPT_VERSION)}: ", text, re.M)
    assert heading
    entry = text[heading.start() :].split("\n## ")[0]
    score = re.search(r"\*\*Eval score[^\n]*", entry)
    assert score

    if "NOT RUN" in score.group(0):
        assert "pending" in score.group(0), "say who runs it and when"
        assert not re.search(r"\b\d+ ?/ ?\d+\b", score.group(0)), "no result may be claimed"


def test_the_current_entry_records_a_real_score_or_says_plainly_that_there_is_none() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = re.search(rf"^## {re.escape(PROMPT_VERSION)}: ", text, re.M)
    assert heading
    entry = text[heading.start() :].split("\n## ")[0]
    score = re.search(r"\*\*Eval score[^\n]*", entry)

    assert score, "the entry has no eval score line"
    assert "NOT RUN" in score.group(0) or re.search(r"\b\d+ ?/ ?\d+\b", score.group(0))
