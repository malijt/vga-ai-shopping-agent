"""What "the photo shows up somewhere" means.

A photo can end up in a file, a log line or a request body in more than one shape: as it is, cut
into a piece, as base64 (which looks different depending on where in the file the piece starts), as
hex, or as the escaped text Python prints for a ``bytes`` value. ``Trace`` is one such shape, and
``find`` says which ones a blob or a text contains.

Two kinds of check work together, because each misses what the other sees:

- *Traces of this photo.* Exact: a piece of the file in any of the shapes above. They cannot be
  fooled by a long unrelated base64 string. They do not see a copy that was changed (shrunk,
  re-encoded).
- *Signs of any image.* Structural: a data URL, an image header, base64 that starts like a JPEG,
  PNG or WebP. They see a changed copy, and they do not need to know which photo it is.

The photo is judged in two forms, because the app does not send the file it was given: it sends a
re-encoded JPEG (``vga.understand.image``). Both the original and the JPEG that actually leaves the
machine count as "the photo".
"""

import base64
import io
import json
import re
import warnings
from collections.abc import Iterable
from dataclasses import dataclass

from PIL import Image

from vga.understand.image import prepare_image

PIECE_BYTES = 48
"""Length of the pieces cut out of a photo. Long enough that two files never share one by chance."""

_B64_GROUP = 4
"""Base64 turns 3 bytes into 4 characters, so the same bytes encode differently depending on their
position modulo 3. ``_base64_forms`` covers the three positions."""


@dataclass(frozen=True)
class Trace:
    label: str
    needle: bytes


def _base64_forms(blob: bytes, label: str) -> list[Trace]:
    """``blob`` as base64 (standard and URL-safe alphabets) at each of the three alignments.

    The first and last four characters are dropped: they encode the group that is shared with the
    bytes next to the blob, which are not known. What remains is in any base64 text of a file that
    contains ``blob``, wherever in the file it starts.
    """
    forms: list[Trace] = []
    for shift in range(3):
        padded = b"\x00" * shift + blob
        for name, encode in (
            ("base64", base64.b64encode),
            ("urlsafe-base64", base64.urlsafe_b64encode),
        ):
            encoded = encode(padded)[_B64_GROUP:-_B64_GROUP]
            if len(encoded) >= 16:
                forms.append(Trace(f"{label} as {name} (alignment {shift})", encoded))
    return forms


def forms_of(blob: bytes, label: str) -> list[Trace]:
    """Every shape ``blob`` can take in text or in a file."""
    escaped = repr(blob)[2:-1]
    return [
        Trace(f"{label} as bytes", blob),
        Trace(f"{label} as hex", blob.hex().encode()),
        Trace(f"{label} as upper-case hex", blob.hex().upper().encode()),
        Trace(f"{label} as a bytes repr", escaped.encode()),
        Trace(f"{label} as a bytes repr inside JSON", json.dumps(escaped)[1:-1].encode()),
        *_base64_forms(blob, label),
    ]


def pieces_of(photo: bytes, label: str) -> list[Trace]:
    """Three pieces from the middle of ``photo`` (where the picture data is, not the header, which
    many files share), in every shape."""
    traces: list[Trace] = []
    for part, share in enumerate((0.35, 0.5, 0.65), start=1):
        start = int(len(photo) * share)
        traces += forms_of(photo[start : start + PIECE_BYTES], f"{label}, piece {part}")
    return traces


def traces_of_photo(original: bytes, marker: bytes, sent: bytes | None = None) -> list[Trace]:
    """All traces of a photo: its marker and pieces, and the JPEG that leaves the machine.

    ``sent`` is the JPEG found in the request to OpenAI. When the request never got that far, the
    JPEG the app would have sent is worked out from the original, so a failure path that logs the
    prepared photo is caught too.
    """
    prepared = sent if sent is not None else _prepare(original)
    traces = forms_of(marker, "the marker")
    traces += pieces_of(original, "the original photo")
    if prepared is not None:
        traces += pieces_of(prepared, "the JPEG sent to OpenAI")
    return traces


def _prepare(original: bytes) -> bytes | None:
    try:
        return prepare_image(original)
    except Exception:  # a photo the app rejects has no prepared form
        return None


def find(haystack: bytes | str, traces: Iterable[Trace]) -> list[str]:
    """The labels of the traces that ``haystack`` contains."""
    blob = haystack if isinstance(haystack, bytes) else haystack.encode("utf-8", "replace")
    return [trace.label for trace in traces if trace.needle in blob]


# --------------------------------------------------------------------------------------------
# Signs of any image, whichever photo it is
# --------------------------------------------------------------------------------------------

_DATA_URL = re.compile(rb"data:[A-Za-z0-9.+/-]+;base64,")
_BASE64_IMAGE = re.compile(rb"(?:/9j/|iVBORw0KGgo|UklGR)[A-Za-z0-9+/]{40,}")
"""Base64 that starts the way a JPEG, a PNG or a RIFF (WebP) file starts."""
_LONG_BASE64 = re.compile(rb"[A-Za-z0-9+/]{400,}")
_IMAGE_HEADERS = (
    b"\xff\xd8\xff",
    b"\x89PNG\r\n\x1a\n",
    b"GIF87a",
    b"GIF89a",
    b"JFIF",
    b"Exif\x00\x00",
    b"\\xff\\xd8\\xff",  # a JPEG header as Python prints it
    b"\\x89PNG",
)


def signs_of_an_image(haystack: bytes | str) -> list[str]:
    """What in ``haystack`` looks like image data, whichever picture it is."""
    blob = haystack if isinstance(haystack, bytes) else haystack.encode("utf-8", "replace")
    signs: list[str] = []
    if _DATA_URL.search(blob):
        signs.append("a data URL")
    if _BASE64_IMAGE.search(blob):
        signs.append("base64 that starts like a JPEG, PNG or WebP file")
    if _LONG_BASE64.search(blob):
        signs.append("a base64 string of 400 characters or more")
    signs += [f"an image header ({header!r})" for header in _IMAGE_HEADERS if header in blob]
    if b"RIFF" in blob and b"WEBP" in blob:
        signs.append("a WebP header")
    return signs


MIN_PICTURE_BYTES = 32


def is_an_image(blob: bytes) -> bool:
    """Whether Pillow can open ``blob`` as a picture (any format it knows)."""
    if len(blob) < MIN_PICTURE_BYTES:
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Pillow warns about half-readable metadata
            with Image.open(io.BytesIO(blob)):
                return True
    except Exception:
        return False
