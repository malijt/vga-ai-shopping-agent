"""Structured JSON-lines logging with a request id and secret / image redaction (PRD R12).

Usage::

    from vga.log import configure_logging, get_logger, request_context, timed

    configure_logging(level=settings.log_level, log_dir=settings.log_dir)   # once, at start-up
    log = get_logger(__name__)

    with request_context(req.request_id):
        with timed("fetch", store="demo") as step:
            ...
            step.status = "ok"
        log.warning("store skipped", extra={"store": "demo", "status": "blocked"})

Rules this module enforces for everyone:
- every line carries ``request_id`` (``null`` outside a request);
- API keys, tokens, passwords, image bytes and base64 / data-URL photos are replaced by a
  ``[REDACTED...]`` marker before anything is written (BRD Rule 4, backend doc);
- ``get_logger`` has no side effects; only ``configure_logging`` installs handlers, so importing a
  module never creates files.
"""

import contextvars
import json
import logging
import os
import re
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from vga.interfaces import Clock, SystemClock
from vga.models import StepTiming

ROOT_LOGGER_NAME = "vga"
LOG_FILE_NAME = "vga.jsonl"
REDACTED = "[REDACTED]"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "vga_request_id", default=None
)


def current_request_id() -> str | None:
    """The request id bound to the current task, or ``None`` outside a request."""
    return _request_id.get()


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    """Bind ``request_id`` to every log line written inside the block (also in tasks it starts)."""
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


# --------------------------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------------------------

_SENSITIVE_KEYS = frozenset(
    {
        "api_key", "apikey", "openai_api_key", "authorization", "auth", "token", "access_token",
        "secret", "password", "passwd", "cookie", "set-cookie", "image", "image_bytes",
        "image_data", "photo", "photo_bytes", "b64", "base64", "data_url", "embedding",
        "query_embedding",
    }
)  # fmt: skip
_SENSITIVE_KEY_SUFFIXES = ("api_key", "_secret", "_password", "_token")

_DATA_URL = re.compile(r"data:[A-Za-z0-9.+/-]+;base64,[A-Za-z0-9+/=_-]+")
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_KEY_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or lowered.endswith(_SENSITIVE_KEY_SUFFIXES)


def redact_text(text: str) -> str:
    """Remove secrets and encoded images from a string."""
    secret = os.environ.get("OPENAI_API_KEY", "")
    if len(secret) >= 8:
        text = text.replace(secret, REDACTED)
    text = _DATA_URL.sub("[REDACTED data-url]", text)
    text = _OPENAI_KEY.sub(REDACTED, text)
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return _BASE64_BLOB.sub("[REDACTED blob]", text)


def redact(value: Any, key: str | None = None) -> Any:
    """Return a copy of ``value`` that is safe to log.

    ``key`` is the dictionary key or log field the value came from: sensitive keys hide the whole
    value, whatever it is. Bytes are never logged, only their length.
    """
    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, bytes | bytearray | memoryview):
        return f"[REDACTED bytes len={len(value)}]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(v) for v in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return redact_text(repr(value))


_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class RedactionFilter(logging.Filter):
    """Redacts a record's message and every ``extra`` field in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = None
        for name in [n for n in record.__dict__ if n not in _STANDARD_ATTRS]:
            setattr(record, name, redact(record.__dict__[name], key=name))
        return True


class RequestIdFilter(logging.Filter):
    """Stamps ``record.request_id`` from the current request context."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, request_id, message, then extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or current_request_id(),
            "message": record.getMessage(),
        }
        for name, value in record.__dict__.items():
            if name not in _STANDARD_ATTRS and name not in payload:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Redact again at the point of output: the guarantee holds even for a logger that was not
        # created through get_logger() and so never had the filters attached.
        return json.dumps(redact(payload), ensure_ascii=False, default=repr)


# --------------------------------------------------------------------------------------------
# Configuration and loggers
# --------------------------------------------------------------------------------------------

_HANDLER_MARK = "_vga_handler"


def configure_logging(
    level: str = "INFO",
    log_dir: str | Path | None = None,
    stream: IO[str] | None = None,
) -> None:
    """Install JSON handlers on the ``vga`` logger: stderr (or ``stream``) and, when ``log_dir``
    is given, ``<log_dir>/vga.jsonl``. Safe to call again: it replaces its earlier handlers."""
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(level.upper())
    for handler in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(handler)
        handler.close()

    handlers: list[logging.Handler] = [logging.StreamHandler(stream or sys.stderr)]
    if log_dir is not None:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(directory / LOG_FILE_NAME, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(JsonFormatter())
        setattr(handler, _HANDLER_MARK, True)
        root.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """A logger under the ``vga`` namespace with request-id stamping and redaction attached.

    Pass ``__name__``. Extra fields go in ``extra={...}`` and appear as JSON keys.
    """
    if not name or name == ROOT_LOGGER_NAME:
        full_name = ROOT_LOGGER_NAME
    elif name.startswith(f"{ROOT_LOGGER_NAME}."):
        full_name = name
    else:
        full_name = f"{ROOT_LOGGER_NAME}.{name}"
    logger = logging.getLogger(full_name)
    if not any(isinstance(f, RedactionFilter) for f in logger.filters):
        logger.addFilter(RequestIdFilter())
        logger.addFilter(RedactionFilter())
    return logger


# --------------------------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------------------------


@dataclass
class TimedStep:
    """Handle yielded by ``timed()``. Set ``status`` inside the block to report an outcome other
    than ``ok``; ``duration_ms`` is filled in when the block ends."""

    step: str
    store: str | None = None
    status: str = "ok"
    duration_ms: float = 0.0

    def to_timing(self) -> StepTiming:
        return StepTiming(
            step=self.step, store=self.store, duration_ms=self.duration_ms, status=self.status
        )


@contextmanager
def timed(
    step: str,
    store: str | None = None,
    *,
    clock: Clock | None = None,
) -> Iterator[TimedStep]:
    """Time a block and write ``{request_id, step, store, duration_ms, status}`` when it ends.

    ``status`` is ``ok`` unless the block sets it or raises (then ``error``; the exception still
    propagates). Blocks may be nested: each reports its own duration. Pass ``clock`` in tests.
    """
    time_source = clock or SystemClock()
    handle = TimedStep(step=step, store=store)
    started = time_source.monotonic()
    try:
        yield handle
    except BaseException:
        if handle.status == "ok":
            handle.status = "error"
        raise
    finally:
        handle.duration_ms = round((time_source.monotonic() - started) * 1000, 3)
        get_logger("timing").info(
            "timing",
            extra={
                "step": handle.step,
                "store": handle.store,
                "duration_ms": handle.duration_ms,
                "status": handle.status,
            },
        )
