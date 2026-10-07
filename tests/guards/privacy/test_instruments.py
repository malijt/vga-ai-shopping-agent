"""The instruments, tested on their own: what each can see, and what it cannot.

These are the limits that ``docs/privacy.md`` states, written as tests so that the note cannot
claim more than the audit does.
"""

import asyncio
import base64
import io
import json
import logging
import os
import shutil
import socket
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from tests.guards.privacy.photos import make_private_photo
from tests.guards.privacy.reachable import photos_held, reachable
from tests.guards.privacy.traces import (
    find,
    forms_of,
    is_an_image,
    signs_of_an_image,
    traces_of_photo,
)
from tests.guards.privacy.watch import NetworkBlockedError, RawLogs, Watch
from vga.understand.image import prepare_image

# --------------------------------------------------------------------------------------------
# The audit hook
# --------------------------------------------------------------------------------------------


def write_with_open(path: Path) -> None:
    with path.open("wb") as stream:
        stream.write(b"x")


def write_text(path: Path) -> None:
    path.write_text("x")


def write_with_os_open(path: Path) -> None:
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT))


def append(path: Path) -> None:
    with path.open("a") as stream:
        stream.write("x")


def read_and_write(path: Path) -> None:
    path.write_text("x")
    with path.open("r+") as stream:
        stream.write("y")


def copy_over(path: Path) -> None:
    source = path.with_suffix(".src")
    source.write_text("x")
    shutil.copyfile(source, path)


WAYS_TO_WRITE: list[Callable[[Path], None]] = [
    write_with_open,
    write_text,
    write_with_os_open,
    append,
    read_and_write,
    copy_over,
]


@pytest.mark.parametrize("write", WAYS_TO_WRITE, ids=lambda f: f.__name__)
def test_the_hook_sees_every_way_python_can_write_a_file(write, tmp_path: Path) -> None:
    target = tmp_path / "out.bin"

    with Watch([tmp_path]) as watch:
        write(target)

    assert target in {opened.path for opened in watch.activity.file_writes}


def test_the_hook_sees_a_file_that_is_gone_before_the_request_ends(tmp_path: Path) -> None:
    target = tmp_path / "scratch.bin"

    with Watch([tmp_path]) as watch:
        target.write_bytes(b"photo")
        target.unlink()

    assert target in {opened.path for opened in watch.activity.file_writes}
    assert watch.changed == []  # a look at the folder afterwards finds nothing


def test_the_hook_does_not_report_a_file_that_is_only_read(tmp_path: Path) -> None:
    target = tmp_path / "in.bin"
    target.write_bytes(b"photo")

    with Watch([tmp_path]) as watch:
        target.read_bytes()

    assert watch.activity.file_writes == []


def test_the_hook_reports_who_asked_for_the_file(tmp_path: Path) -> None:
    with Watch([tmp_path]) as watch:
        write_text(tmp_path / "out.txt")

    [opened] = watch.activity.file_writes
    assert "write_text" in opened.caller


def test_the_hook_does_not_see_a_write_through_a_file_opened_before_the_request(
    tmp_path: Path,
) -> None:
    """The limit of the hook, and the reason for the snapshot: a handle that was open already."""
    target = tmp_path / "held-open.bin"
    with target.open("wb") as stream, Watch([tmp_path]) as watch:
        stream.write(b"photo")
        stream.flush()

    assert watch.activity.file_writes == []
    assert target in watch.changed  # the snapshot of the folder does see it


def test_the_snapshot_does_not_see_a_file_that_was_already_there_and_untouched(
    tmp_path: Path,
) -> None:
    (tmp_path / "old.bin").write_bytes(b"old")

    with Watch([tmp_path]) as watch:
        pass

    assert watch.changed == []


def test_python_compiling_its_own_code_is_not_reported(tmp_path: Path) -> None:
    cache = tmp_path / "__pycache__"
    cache.mkdir()

    with Watch([tmp_path]) as watch:
        (cache / "module.cpython-312.pyc").write_bytes(b"code")

    assert watch.activity.file_writes == []


def test_the_network_is_blocked_and_reported_while_a_watch_is_open() -> None:
    with Watch([]) as watch, pytest.raises(NetworkBlockedError):
        socket.create_connection(("203.0.113.5", 443), timeout=0.1)

    assert any(attempt.startswith("socket.") for attempt in watch.activity.network)


def test_the_hook_does_nothing_once_the_watch_is_closed() -> None:
    with Watch([]):
        pass

    with pytest.raises(OSError, match=r"refused|unreachable|Connection") as caught:
        socket.create_connection(("127.0.0.1", 1), timeout=0.1)
    assert not isinstance(caught.value, NetworkBlockedError)


# --------------------------------------------------------------------------------------------
# The record of log calls
# --------------------------------------------------------------------------------------------


def test_every_log_call_is_recorded_from_whatever_logger_makes_it() -> None:
    with RawLogs() as logs:
        logging.getLogger("some.library").warning("photo %s", "abc")
        logging.getLogger("vga.something").warning("hello", extra={"image": "def"})

    text = "\n".join(logs.lines)
    assert "photo %s" in text
    assert "abc" in text
    assert "def" in text  # the logger would hide this one in the file; the call still shows it


def test_a_log_call_made_with_an_exception_records_the_traceback_text() -> None:
    with RawLogs() as logs:
        try:
            msg = "boom with a detail"
            raise ValueError(msg)
        except ValueError:
            logging.getLogger("vga.x").exception("failed")

    assert "boom with a detail" in "\n".join(logs.lines)


def test_the_record_is_removed_when_the_watch_ends() -> None:
    original = logging.Logger.makeRecord

    with RawLogs():
        pass

    assert logging.Logger.makeRecord is original


# --------------------------------------------------------------------------------------------
# Traces of a photo
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def photo():
    return make_private_photo(seed=7)


@pytest.mark.parametrize("before", [0, 1, 2, 3, 4, 5])
def test_base64_of_the_photo_is_found_wherever_it_starts_in_the_text(photo, before: int) -> None:
    traces = traces_of_photo(photo.data, photo.marker)
    text = base64.b64encode(b"?" * before + photo.data + b"!!")
    url_safe = base64.urlsafe_b64encode(b"?" * before + photo.data + b"!!")

    found = find(text, traces)
    assert any("marker as base64" in label for label in found)
    assert any("original photo, piece 2 as base64" in label for label in found)
    assert any("urlsafe-base64" in label for label in find(url_safe, traces))


def test_the_jpeg_that_is_sent_is_a_trace_too(photo) -> None:
    sent = prepare_image(photo.data)
    text = "data:image/jpeg;base64," + base64.b64encode(sent).decode()

    found = find(text, traces_of_photo(photo.data, photo.marker, sent))

    assert any("JPEG sent to OpenAI" in label for label in found)


@pytest.mark.parametrize(
    "shape",
    [
        lambda blob: blob,
        lambda blob: blob.hex().encode(),
        lambda blob: blob.hex().upper().encode(),
        lambda blob: repr(blob).encode(),
        lambda blob: json.dumps(repr(blob)).encode(),
    ],
    ids=["bytes", "hex", "HEX", "repr", "repr in JSON"],
)
def test_a_piece_is_found_in_every_shape_python_can_print_it(photo, shape) -> None:
    piece = photo.data[len(photo.data) // 2 : len(photo.data) // 2 + 48]

    assert find(b"log: " + shape(piece) + b" end", forms_of(piece, "piece"))


def test_another_photo_leaves_no_trace_of_this_one(photo) -> None:
    other = make_private_photo(seed=8)
    traces = traces_of_photo(photo.data, photo.marker)

    assert find(other.data, traces) == []
    assert find(base64.b64encode(other.data), traces) == []
    assert find(other.data.hex(), traces) == []


def test_ordinary_log_lines_are_not_mistaken_for_a_photo() -> None:
    line = json.dumps(
        {
            "message": "store search finished",
            "url": "https://alpha.example/search/suggest.json?q=black%20oversized%20blazer",
            "request_id": "0123456789abcdef0123456789abcdef",
            "scores": [0.51, 0.2, 0.7],
        }
    )

    assert signs_of_an_image(line) == []


@pytest.mark.parametrize(
    "text",
    [
        "data:image/jpeg;base64,/9j/4AAQSkZJRg",
        "x " + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 60).decode(),
        "x " + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 60).decode(),
        "piece b'\\xff\\xd8\\xff\\xe0'",
        "A" * 500,
    ],
    ids=["data URL", "JPEG as base64", "PNG as base64", "JPEG header repr", "long base64"],
)
def test_any_image_is_recognised_without_knowing_the_photo(text: str) -> None:
    assert signs_of_an_image(text)


def test_a_shrunk_copy_is_a_picture_even_though_it_shares_no_bytes_with_the_original(
    photo, tmp_path: Path
) -> None:
    thumbnail = tmp_path / "thumb.jpg"
    Image.open(io.BytesIO(photo.data)).resize((16, 12)).save(thumbnail)

    assert find(thumbnail.read_bytes(), traces_of_photo(photo.data, photo.marker)) == []
    assert is_an_image(thumbnail.read_bytes())


# --------------------------------------------------------------------------------------------
# The memory walk
# --------------------------------------------------------------------------------------------


class Plain:
    def __init__(self, value: object) -> None:
        self.value = value


class Slotted:
    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value


def closure_over(value: object):
    return lambda: value


def hidden_in(value: object) -> list[tuple[str, object]]:
    return [
        ("an attribute", Plain(value)),
        ("a slot", Slotted(value)),
        ("a closure", closure_over(value)),
        ("a dict", {"k": [value]}),
        ("a tuple in a set", {(1, value)}),
        ("a bound method", Plain(value).__init__),
    ]


@pytest.mark.parametrize("name", [name for name, _ in hidden_in(b"")])
def test_the_walk_finds_the_photo_wherever_it_is_hidden(photo, name: str) -> None:
    holder = dict(hidden_in(photo.data))[name]

    held = photos_held([holder], traces_of_photo(photo.data, photo.marker))

    assert held, f"the photo is in {name} and the walk did not find it"


async def test_the_walk_finds_the_photo_in_a_coroutine_that_is_still_waiting(photo) -> None:
    async def wait(data: bytes) -> None:
        await asyncio.Event().wait()

    task = asyncio.ensure_future(wait(photo.data))
    await asyncio.sleep(0)
    try:
        held = photos_held([task], traces_of_photo(photo.data, photo.marker))
    finally:
        task.cancel()

    assert held


def test_the_walk_does_not_leave_the_objects_it_was_given(photo) -> None:
    """Modules and classes are code: following them would walk the whole interpreter."""
    holder = Plain({"module": asyncio, "class": Plain, "function": closure_over})

    seen = list(reachable([holder]))

    assert len(seen) < 50


def test_the_walk_reports_nothing_for_an_object_that_holds_only_numbers(photo) -> None:
    holder = Plain({"embedding": (0.1, 0.2, 0.3), "title": "Black blazer", "price": 120.0})

    assert photos_held([holder], traces_of_photo(photo.data, photo.marker)) == []


def test_a_decoded_picture_is_a_photo_held_in_memory(photo) -> None:
    holder = Plain(Image.new("RGB", (4, 4)))

    assert photos_held([holder], traces_of_photo(photo.data, photo.marker))
