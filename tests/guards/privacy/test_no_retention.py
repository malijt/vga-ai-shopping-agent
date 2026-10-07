"""Product rule 4: the photo is not kept after the request, not on disk, in a log or in memory.

Each case runs a whole request through the real pipeline (``rig.py``) while ``watch.py`` records
what the machine does, then looks in every place the photo could have been left (``audit.py``):

files      anything written during the request, and what it holds
logs       every log call (before the logger redacts it), the screen stream and the log file
memory     everything still reachable once the request is over
outbound   every request to a store or an image host, and any other program, network or database
caller     the answer, the re-run settings and the error the caller is handed

The cases are a photo of one garment, a photo with text and an outfit, each under all four settings
of the two debug switches, and then every other kind of request once with both switches on (the
setting that writes the most): a chip edit afterwards, a PNG and a WebP photo, a store that blocks
us, the image model crashing, the deadline, the model down, and photos that are not photos.

A failure names the channel and what was found, so a leak found later in one place can be marked
``xfail`` for that channel alone. See ``docs/privacy.md`` for what this proves and what it cannot
see, and ``test_canaries.py`` for the proof that each check can fail.
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
from tests.guards.privacy.scenarios import every_case

CHANNELS = {
    "files": file_problems,
    "logs": log_problems,
    "memory": memory_problems,
    "outbound": outbound_problems,
    "caller": caller_problems,
}


def assert_the_audit_watched_the_request(audited: Audited) -> None:
    """A clean result means something only if the instruments were on and the request ran."""
    assert audited.watch.raw_logs.lines, "no log call was recorded"
    assert audited.log_file.stat().st_size > 0, "nothing reached the log file"
    assert audited.log_stream.getvalue(), "nothing reached the log stream"
    assert (audited.failure is None) == (audited.case.scenario.expect is None)
    if audited.case.switches.debug_dump and audited.responses:
        assert list(audited.workspace.logs.glob("candidates-*.jsonl")), "the dump was not written"


@pytest.mark.parametrize("audited", every_case(), indirect=True)
async def test_a_request_leaves_no_trace_of_the_photo(audited: Audited) -> None:
    assert_the_audit_watched_the_request(audited)

    found = {name: check(audited) for name, check in CHANNELS.items()}

    assert {name: problems for name, problems in found.items() if problems} == {}
