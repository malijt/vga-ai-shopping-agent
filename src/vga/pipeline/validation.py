"""Request validation: the first step of every run, on the server side (plan 13.1.1).

The UI checks input too, but a check in the browser is only a convenience: this is the one that
counts. It looks at the request and nothing else, so it makes no network call and no model call.

- The photo is judged by its first bytes (JPEG, PNG or WebP), never by a file name, so a PNG saved
  as ``.jpg`` is accepted and a text file saved as ``.jpg`` is not.
- The photo must fit ``Settings.max_image_bytes`` and have sane dimensions. Only the image header
  is read to find them: the picture is not decoded here.
- A request needs text or a photo. A re-run (``rerun_of`` set) carries neither, so it must come
  with the earlier understanding in ``overrides.understood``.

Everything raises ``InvalidInputError`` with a plain message. The bytes of the photo never go into
a message or a detail.
"""

import io
from typing import Literal

from PIL import Image

from vga.errors import InvalidInputError
from vga.models import MAX_TEXT_CHARS, RunOverrides, SearchRequest
from vga.pipeline import messages
from vga.settings import Settings

ImageKind = Literal["jpeg", "png", "webp"]

MIN_EDGE_PX = 8
"""Shorter than this on either side and the picture shows nothing (1x1 tracking pixels, icons)."""
MAX_EDGE_PX = 16_000
MAX_PIXELS = 50_000_000
"""Larger pictures are refused before anything decodes them (the same limit the Understand step
and the image ranker use as their own second line of defence)."""

_PIL_FORMATS = ("JPEG", "PNG", "WEBP")


def sniff_image_kind(data: bytes) -> ImageKind | None:
    """The real type of ``data`` from its magic bytes, or ``None`` if not JPEG, PNG or WebP."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def validate_request(
    req: SearchRequest, overrides: RunOverrides | None, settings: Settings
) -> None:
    """Raise ``InvalidInputError`` unless ``req`` can be searched. Returns nothing otherwise."""
    # ``SearchRequest`` validates its text when it is built, but a model can be built without
    # validation (``model_construct``), so the rules are checked again here.
    text = req.text.strip() if req.text is not None else ""
    if len(text) > MAX_TEXT_CHARS:
        raise InvalidInputError(
            messages.text_too_long(MAX_TEXT_CHARS),
            detail=f"text has {len(text)} characters, the limit is {MAX_TEXT_CHARS}",
        )

    if req.image is not None:
        _validate_photo(req.image, settings)

    if req.rerun_of is not None:
        if overrides is None or overrides.understood is None:
            raise InvalidInputError(
                messages.RERUN_WITHOUT_EARLIER_RESULTS,
                detail="rerun_of is set but overrides.understood is missing",
            )
        return
    if not text and req.image is None:
        raise InvalidInputError(detail="the request has neither text nor a photo")


def _validate_photo(data: bytes, settings: Settings) -> None:
    if not data:
        raise InvalidInputError(messages.EMPTY_PHOTO, detail="the photo has no bytes")
    if len(data) > settings.max_image_bytes:
        raise InvalidInputError(
            messages.photo_too_large(settings.max_image_bytes),
            detail=f"photo is {len(data)} bytes, the limit is {settings.max_image_bytes}",
        )
    kind = sniff_image_kind(data)
    if kind is None:
        raise InvalidInputError(
            messages.NOT_AN_IMAGE, detail="the photo does not start like a JPEG, PNG or WebP"
        )
    width, height = _read_dimensions(data)
    if min(width, height) < MIN_EDGE_PX:
        raise InvalidInputError(
            messages.PHOTO_TOO_SMALL, detail=f"photo is {width}x{height} pixels"
        )
    if max(width, height) > MAX_EDGE_PX or width * height > MAX_PIXELS:
        raise InvalidInputError(
            messages.PHOTO_TOO_LARGE_DIMENSIONS, detail=f"photo is {width}x{height} pixels"
        )


def _read_dimensions(data: bytes) -> tuple[int, int]:
    """Width and height from the image header. Raises ``InvalidInputError`` if it cannot be read."""
    try:
        with Image.open(io.BytesIO(data), formats=_PIL_FORMATS) as image:
            return image.size
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        # Only the type goes into the detail: a decoder's message can quote bytes of the file.
        raise InvalidInputError(
            messages.UNREADABLE_PHOTO, detail=f"cannot read the photo header: {type(exc).__name__}"
        ) from exc
