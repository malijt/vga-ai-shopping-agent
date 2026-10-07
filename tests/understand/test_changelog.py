"""The prompt and the model change together with a changelog entry (plan 5.3.6)."""

import re

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


def test_an_entry_that_did_not_run_the_live_eval_says_so_plainly() -> None:
    entry = CHANGELOG.read_text(encoding="utf-8")

    # Honesty guard: either a real score is recorded, or the entry says it is not run.
    assert "NOT RUN" in entry or re.search(r"\b\d+ ?/ ?\d+\b", entry)
