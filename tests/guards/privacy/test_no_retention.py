"""Product rule 4: the photo is not kept after the request, not on disk, in a log or in memory.

Each test runs whole requests through the real pipeline (``rig.py``) while ``watch.py`` records what
the machine does, then checks one place the photo could have been left. The scenarios cover a photo
of one garment, of an outfit, a photo with text, a chip edit afterwards, and requests that go wrong
(a photo that is not a photo, the model down, the deadline). See ``docs/privacy.md`` for what this
proves and what it cannot see.
"""

import pytest

from tests.guards.privacy.audit import (
    Audited,
    caller_problems,
    file_problems,
    log_problems,
    memory_problems,
    outbound_problems,
)
from tests.guards.privacy.scenarios import every_case, every_scenario_once


@pytest.mark.parametrize("audited", every_case(), indirect=True)
async def test_no_file_holds_the_photo(audited: Audited) -> None:
    assert file_problems(audited) == []


@pytest.mark.parametrize("audited", every_case(), indirect=True)
async def test_no_log_line_holds_the_photo(audited: Audited) -> None:
    assert log_problems(audited) == []


@pytest.mark.parametrize("audited", every_scenario_once(), indirect=True)
async def test_nothing_in_memory_holds_the_photo_after_the_request(audited: Audited) -> None:
    assert memory_problems(audited) == []


@pytest.mark.parametrize("audited", every_scenario_once(), indirect=True)
async def test_the_photo_is_in_no_request_but_the_one_to_openai(audited: Audited) -> None:
    assert outbound_problems(audited) == []


@pytest.mark.parametrize("audited", every_scenario_once(), indirect=True)
async def test_the_caller_is_handed_no_photo(audited: Audited) -> None:
    assert caller_problems(audited) == []
