"""The audit must fail when the app leaks. If it cannot, a green audit means nothing.

Each test here puts a deliberate privacy bug in front of the real understander
(``LeakingUnderstander``: the kind of careless change a developer could make) and runs a whole
request through the same instruments and the same checks as the real audit. The check that is
meant to catch the bug must report it. The bugs are named for what they do; none of them is in the
app.

They are grouped by the check that must catch them: files, logs, memory, the network and the
answer the caller gets.
"""

import asyncio
import base64
import contextlib
import io
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from PIL import Image

import vga.log
from tests.guards.privacy.audit import (
    Audited,
    caller_problems,
    content_problems,
    file_problems,
    log_problems,
    memory_problems,
    outbound_problems,
)
from tests.guards.privacy.photos import make_private_photo
from tests.guards.privacy.rig import Rig, blazer_reading
from tests.guards.privacy.scenarios import Scenario
from tests.guards.privacy.traces import traces_of_photo
from tests.understand.fake_openai import answer
from vga.errors import InvalidInputError
from vga.log import get_logger
from vga.models import SearchRequest

Check = Callable[[Audited], list[str]]

_pending: list[asyncio.Future[None]] = []


@pytest.fixture(autouse=True)
def _clean_up_after_a_leak() -> Iterator[None]:
    yield
    for task in _pending:
        task.cancel()
    _pending.clear()
    vars(vga.log).pop("_leaked_photo", None)


def photo_of(req: SearchRequest) -> bytes:
    assert req.image is not None
    return req.image


def middle_of(photo: bytes) -> bytes:
    start = int(len(photo) * 0.5)
    return photo[start : start + 48]


# --------------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------------


def write_to_the_working_directory(req: SearchRequest, rig: Rig) -> None:
    Path("photo-copy.jpg").write_bytes(photo_of(req))


def write_to_the_temp_folder(req: SearchRequest, rig: Rig) -> None:
    descriptor, _ = tempfile.mkstemp(suffix=".jpg")
    os.write(descriptor, photo_of(req))
    os.close(descriptor)


def write_a_shrunk_copy(req: SearchRequest, rig: Rig) -> None:
    """A thumbnail: no byte of it is in the original, so only the file itself gives it away."""
    with Image.open(io.BytesIO(photo_of(req))) as picture:
        picture.resize((24, 18)).save(Path(tempfile.gettempdir()) / "thumb.png", format="PNG")


def write_and_delete(req: SearchRequest, rig: Rig) -> None:
    """Gone before the request ends: a look at the folder afterwards finds nothing."""
    with tempfile.NamedTemporaryFile(delete=True) as scratch:
        scratch.write(photo_of(req))
        scratch.flush()


FILE_LEAKS = [
    pytest.param(
        write_to_the_working_directory, "photo-copy.jpg", id="a copy in the working directory"
    ),
    pytest.param(write_to_the_temp_folder, ".jpg", id="a copy in the temp folder"),
    pytest.param(write_a_shrunk_copy, "thumb.png", id="a shrunk copy"),
    pytest.param(write_and_delete, "opened for writing", id="a file written and deleted again"),
]


def scenario_with(leak, **options) -> Scenario:
    return Scenario("with a leak", lambda: [answer(blazer_reading())], leak=leak, **options)


@pytest.mark.parametrize(("leak", "expected"), FILE_LEAKS)
async def test_the_file_check_catches(leak, expected, run) -> None:
    audited = await run(scenario_with(leak))

    assert any(expected in problem for problem in file_problems(audited)), file_problems(audited)


def test_a_file_that_is_a_shrunk_copy_is_recognised_without_knowing_which_photo(
    tmp_path: Path,
) -> None:
    """The content check is independent of the allow-list: it sees a picture in a file that is
    allowed to exist (the log, the dump)."""
    thumbnail = tmp_path / "candidates-x.jsonl"
    Image.new("RGB", (24, 18), (1, 2, 3)).save(thumbnail, format="PNG")
    unrelated = make_private_photo(seed=99)

    problems = content_problems(thumbnail, traces_of_photo(unrelated.data, unrelated.marker))

    assert "candidates-x.jsonl can be opened as a picture" in problems


def test_base64_of_the_photo_in_a_text_file_is_found(tmp_path: Path) -> None:
    photo = make_private_photo()
    note = tmp_path / "notes.txt"
    note.write_text("saved: " + base64.b64encode(photo.data).decode())

    problems = content_problems(note, traces_of_photo(photo.data, photo.marker))

    assert problems


# --------------------------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------------------------


def log_a_piece_as_hex(req: SearchRequest, rig: Rig) -> None:
    """Short enough that the logger's own redaction (200 characters or more) does not touch it."""
    get_logger("leak").info("photo", extra={"piece": middle_of(photo_of(req)).hex()})


def log_the_photo_in_a_field_the_logger_hides(req: SearchRequest, rig: Rig) -> None:
    """The logger replaces a field called ``image`` with a marker, so the file looks clean."""
    encoded = base64.b64encode(photo_of(req)).decode()
    get_logger("leak").info("photo", extra={"image": encoded})


def log_the_photo_in_the_message(req: SearchRequest, rig: Rig) -> None:
    get_logger("leak").info("got " + base64.b64encode(photo_of(req)).decode())


def log_the_bytes_the_way_python_prints_them(req: SearchRequest, rig: Rig) -> None:
    get_logger("leak").info("piece %r", middle_of(photo_of(req)))


def log_from_a_logger_nobody_configured(req: SearchRequest, rig: Rig) -> None:
    """Not a ``vga`` logger, so neither the file nor the redaction sees it; only the record of the
    call does."""
    import logging

    logging.getLogger("some.library").warning("photo %s", base64.b64encode(photo_of(req)).decode())


def write_straight_into_the_log_file(req: SearchRequest, rig: Rig) -> None:
    """Around the logger, so nothing is redacted."""
    log_file = Path(rig.settings.log_dir) / vga.log.LOG_FILE_NAME
    with log_file.open("a") as stream:
        stream.write(base64.b64encode(photo_of(req)).decode() + "\n")


LOG_LEAKS = [
    pytest.param(log_a_piece_as_hex, "log stream", id="a piece as hex"),
    pytest.param(
        log_the_photo_in_a_field_the_logger_hides, "log call", id="a field the logger hides"
    ),
    pytest.param(log_the_photo_in_the_message, "log call", id="the whole photo in a message"),
    pytest.param(log_the_bytes_the_way_python_prints_them, "log stream", id="a bytes repr"),
    pytest.param(log_from_a_logger_nobody_configured, "log call", id="another library's logger"),
    pytest.param(write_straight_into_the_log_file, "log file", id="straight into the file"),
]


@pytest.mark.parametrize(("leak", "expected"), LOG_LEAKS)
async def test_the_log_check_catches(leak, expected, run) -> None:
    audited = await run(scenario_with(leak))

    assert any(expected in problem for problem in log_problems(audited)), log_problems(audited)


async def test_a_field_the_logger_hides_is_seen_by_the_log_call_but_not_by_the_file(run) -> None:
    """Why the audit looks at the call and not only at the file: the file here is clean."""
    audited = await run(scenario_with(log_the_photo_in_a_field_the_logger_hides))

    in_the_file = [p for p in log_problems(audited) if "the log file holds" in p]
    in_the_call = [p for p in log_problems(audited) if "the log call" in p]
    assert in_the_file == []
    assert in_the_call


# --------------------------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------------------------


def keep_in_the_rerun_cache(req: SearchRequest, rig: Rig) -> None:
    rig.pipeline._cache._runs["leak"] = photo_of(req)


def keep_in_the_store_result_cache(req: SearchRequest, rig: Rig) -> None:
    rig.engine.cache._entries[("alpha", "leak")] = (0.0, photo_of(req))


def keep_in_a_closure(req: SearchRequest, rig: Rig) -> None:
    photo = photo_of(req)
    rig.pipeline._on_close = lambda: photo


def keep_a_decoded_picture(req: SearchRequest, rig: Rig) -> None:
    picture = Image.open(io.BytesIO(photo_of(req)))
    picture.load()
    rig.engine._decoded = picture


def keep_in_a_task_that_never_ends(req: SearchRequest, rig: Rig) -> None:
    async def wait_forever(photo: bytes) -> None:
        await asyncio.Event().wait()

    task = asyncio.ensure_future(wait_forever(photo_of(req)))
    _pending.append(task)
    rig.pipeline._waiting = task


def keep_in_a_module_variable(req: SearchRequest, rig: Rig) -> None:
    vga.log._leaked_photo = photo_of(req)


def keep_in_a_slotted_object(req: SearchRequest, rig: Rig) -> None:
    class Holder:
        __slots__ = ("photo",)

        def __init__(self, photo: bytes) -> None:
            self.photo = photo

    rig.engine._holder = Holder(photo_of(req))


MEMORY_LEAKS = [
    pytest.param(keep_in_the_rerun_cache, id="the re-run cache"),
    pytest.param(keep_in_the_store_result_cache, id="the store result cache"),
    pytest.param(keep_in_a_closure, id="a closure"),
    pytest.param(keep_a_decoded_picture, id="a decoded picture"),
    pytest.param(keep_in_a_task_that_never_ends, id="a task that is still waiting"),
    pytest.param(keep_in_a_module_variable, id="a module variable"),
    pytest.param(keep_in_a_slotted_object, id="an object with slots"),
]


@pytest.mark.parametrize("leak", MEMORY_LEAKS)
async def test_the_memory_check_catches(leak, run) -> None:
    audited = await run(scenario_with(leak))

    assert memory_problems(audited), "the photo was kept and the check did not notice"


# --------------------------------------------------------------------------------------------
# The network and other programs
# --------------------------------------------------------------------------------------------


async def send_it_to_a_store(req: SearchRequest, rig: Rig) -> None:
    async with httpx.AsyncClient() as client:
        await client.get(
            "https://alpha.example/robots.txt",
            headers={"x-note": base64.b64encode(middle_of(photo_of(req))).decode()},
        )


async def attach_a_body_to_a_store_request(req: SearchRequest, rig: Rig) -> None:
    async with httpx.AsyncClient() as client:
        await client.request("GET", "https://alpha.example/robots.txt", content=b"hello")


def reach_a_server_of_its_own(req: SearchRequest, rig: Rig) -> None:
    with contextlib.suppress(OSError):  # blocked by the audit; the attempt is what is reported
        socket.create_connection(("203.0.113.5", 443), timeout=0.1)


def start_another_program(req: SearchRequest, rig: Rig) -> None:
    subprocess.run([sys.executable, "-c", "pass"], check=False)


def open_a_database(req: SearchRequest, rig: Rig) -> None:
    sqlite3.connect(":memory:").close()


NETWORK_LEAKS = [
    pytest.param(send_it_to_a_store, "headers", id="a header of a store request"),
    pytest.param(attach_a_body_to_a_store_request, "a body", id="a body on a store request"),
    pytest.param(reach_a_server_of_its_own, "network attempt", id="a connection of its own"),
    pytest.param(start_another_program, "another program", id="another program"),
    pytest.param(open_a_database, "a database was opened", id="a database"),
]


@pytest.mark.parametrize(("leak", "expected"), NETWORK_LEAKS)
async def test_the_outbound_check_catches(leak, expected, run) -> None:
    audited = await run(scenario_with(leak))

    assert any(expected in problem for problem in outbound_problems(audited)), outbound_problems(
        audited
    )


# --------------------------------------------------------------------------------------------
# What the caller is handed
# --------------------------------------------------------------------------------------------


def put_the_photo_in_an_error(req: SearchRequest, rig: Rig) -> None:
    raise InvalidInputError("We couldn't read that.", detail=repr(photo_of(req)[:300]))


async def test_the_caller_check_catches_a_photo_in_an_error(run) -> None:
    audited = await run(scenario_with(put_the_photo_in_an_error, expect=InvalidInputError))

    assert caller_problems(audited)
