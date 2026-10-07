"""The instruments of the audit: what watches the machine while one request runs.

``Watch`` is a context manager. Wrap one request in it and, afterwards, it can say what the request
did to the machine. It uses three independent instruments, because each sees what another cannot:

1. **Python's audit hook** (``sys.addaudithook``). The interpreter reports every file it opens, with
   the mode. The hook keeps every open that could write (write, append, create, truncate, read and
   write) and every attempt to reach the network, start another program or open a database. It sees
   a file that was written and deleted again before the request ended, and a write to any folder,
   not only the ones we thought of. It does not see code that bypasses Python's file handling: a C
   library that opens a file by itself, or a write through a file that was opened before the request
   began (nothing the request owns is open before it begins). Network attempts are *blocked*, not
   only recorded, so a test can never reach a real host.
2. **A snapshot of the folders the request could write to**, taken before and after: the temporary
   folder, the working directory and the log folder. It sees a file however it was written, even by
   a C library, and the content that is left. It does not see a file that was created and deleted
   inside the request, which is why the first instrument is there.
3. **A record of every log call at the moment it is made**, before the logger's own redaction runs.
   The logger replaces a photo it is handed with ``[REDACTED]``, so the log *file* can look clean
   although the code tried to write a photo. This instrument sees the call itself, from every logger
   in the process (ours, the OpenAI library's, httpx, Pillow), at every level that is switched on.

What none of them see: memory (``reachable.py`` looks at that), anything the operating system does
by itself (swap, a crash dump, a terminal's scrollback), and anything outside this process.
"""

import logging
import os
import sys
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Self

# --------------------------------------------------------------------------------------------
# 1. The audit hook
# --------------------------------------------------------------------------------------------

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_PROGRAM_EVENTS = frozenset(
    {
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.spawn",
        "os.fork",
        "os.forkpty",
    }
)
_NETWORK_EVENTS = frozenset({"socket.connect", "socket.getaddrinfo"})


class NetworkBlockedError(PermissionError):
    """Raised inside the code under test when it tries to reach a network."""


@dataclass(frozen=True)
class FileOpen:
    path: Path
    mode: str | None
    caller: str
    """The code that asked for the file: the innermost frames outside this module."""


@dataclass
class Activity:
    """What the interpreter reported while the watch was open."""

    file_writes: list[FileOpen] = field(default_factory=list)
    """Every file opened in a way that can write, including files that no longer exist."""
    network: list[str] = field(default_factory=list)
    programs: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)


_open_watches: list[Activity] = []
_hook_installed = False


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if not _open_watches:
        return
    if event == "open":
        _record_open(*args)
    elif event in _NETWORK_EVENTS:
        what = f"{event} {args[1:]!r}"
        for activity in _open_watches:
            activity.network.append(what)
        msg = f"the privacy audit blocks all network access ({what})"
        raise NetworkBlockedError(msg)
    elif event in _PROGRAM_EVENTS:
        for activity in _open_watches:
            activity.programs.append(f"{event} {args[:1]!r}")
    elif event == "sqlite3.connect":
        for activity in _open_watches:
            activity.databases.append(repr(args[:1]))


def _record_open(path: object, mode: object, flags: object) -> None:
    if isinstance(path, int):  # an already-open file descriptor, not a new file
        return
    writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
        isinstance(flags, int) and bool(flags & _WRITE_FLAGS)
    )
    if not writes:
        return
    where = Path(os.fsdecode(path)) if isinstance(path, str | bytes | os.PathLike) else None
    if where is None or (where.suffix == ".pyc" and where.parent.name == "__pycache__"):
        return  # Python caching its own compiled code is not data
    frames = traceback.extract_stack(limit=8)[:-2]  # without this function and the hook
    caller = " <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames))
    opened = FileOpen(where, mode if isinstance(mode, str) else None, caller)
    for activity in _open_watches:
        activity.file_writes.append(opened)


def _install_hook() -> None:
    global _hook_installed
    if not _hook_installed:
        sys.addaudithook(_hook)
        _hook_installed = True


# --------------------------------------------------------------------------------------------
# 3. Every log call, before redaction
# --------------------------------------------------------------------------------------------


class RawLogs:
    """The text of every log call made while it is open, in whatever logger and at whatever level.

    It wraps ``logging.Logger.makeRecord``, which runs before any filter. A call to a logger whose
    level is off makes no record, so this sees exactly what the process would have written if every
    handler were attached.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._original: Any = None

    def __enter__(self) -> Self:
        self._original = original = logging.Logger.makeRecord
        lines = self.lines

        def make_record(
            logger: logging.Logger,
            name: str,
            level: int,
            fn: str,
            lno: int,
            msg: object,
            args: Any,
            exc_info: Any,
            func: str | None = None,
            extra: Any = None,
            sinfo: str | None = None,
        ) -> logging.LogRecord:
            lines.append(_describe(name, level, msg, args, exc_info, extra))
            return original(logger, name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)

        logging.Logger.makeRecord = make_record
        return self

    def __exit__(self, *_: object) -> None:
        logging.Logger.makeRecord = self._original


def _describe(name: str, level: int, msg: object, args: Any, exc_info: Any, extra: Any) -> str:
    parts = [f"{name} {logging.getLevelName(level)} {msg!s} | args={args!r} | extra={extra!r}"]
    if exc_info:
        error = exc_info if isinstance(exc_info, BaseException) else None
        if isinstance(exc_info, tuple):
            parts.append("".join(traceback.format_exception(*exc_info)))
        elif error is not None:
            parts.append("".join(traceback.format_exception(error)))
    return "\n".join(parts)


@contextmanager
def without_pytest_log_capture() -> Iterator[None]:
    """Take pytest's own log handlers off the root logger for a while.

    pytest keeps every log record of a test in memory so it can print them if the test fails. A
    record made with ``exc_info`` keeps the whole traceback, and a traceback keeps the local
    variables of every frame it passed through, the photo among them. That is pytest holding on to
    the photo, not the app: a real handler formats a record and lets it go. The audit reads the log
    through its own instruments (``RawLogs``, the stream and the file), so it does not need
    pytest's copy.
    """
    root = logging.getLogger()
    taken = [h for h in root.handlers if type(h).__module__.startswith("_pytest")]
    for handler in taken:
        root.removeHandler(handler)
    try:
        yield
    finally:
        for handler in taken:
            root.addHandler(handler)


# --------------------------------------------------------------------------------------------
# 2. Snapshots of folders
# --------------------------------------------------------------------------------------------

Snapshot = dict[Path, tuple[int, int]]


def snapshot(root: Path) -> Snapshot:
    """Every file under ``root`` with its size and modification time (nanoseconds)."""
    found: Snapshot = {}
    for path in _files_under(root):
        stat = path.stat()
        found[path] = (stat.st_size, stat.st_mtime_ns)
    return found


def _files_under(root: Path) -> Iterator[Path]:
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                yield path


def changed_files(before: Snapshot, after: Snapshot) -> list[Path]:
    """Files that are new, or whose size or modification time changed."""
    return [path for path, state in after.items() if before.get(path) != state]


# --------------------------------------------------------------------------------------------
# All three together
# --------------------------------------------------------------------------------------------


class Watch:
    """Watches one request. Use as ``with Watch(folders) as watch:`` around the request.

    ``folders`` are the folders the request could write to. After the block: ``activity`` (the
    audit hook), ``raw_logs`` (every log call) and ``changed`` (files that appeared or changed in
    ``folders``).
    """

    def __init__(self, folders: list[Path]) -> None:
        self._folders = folders
        self.activity = Activity()
        self.raw_logs = RawLogs()
        self.changed: list[Path] = []
        self._before: list[Snapshot] = []

    def __enter__(self) -> Self:
        _install_hook()
        self._before = [snapshot(folder) for folder in self._folders]
        self.raw_logs.__enter__()
        _open_watches.append(self.activity)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _open_watches.remove(self.activity)
        self.raw_logs.__exit__()
        for folder, before in zip(self._folders, self._before, strict=True):
            self.changed += changed_files(before, snapshot(folder))
