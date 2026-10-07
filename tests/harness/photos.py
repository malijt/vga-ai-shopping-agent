"""Synthetic photos that carry a unique marker, and a scan for any trace of them (BRD Rule 4).

The real photos are private and not in the repository, so the privacy tests use pictures drawn from
random noise: every window of bytes is unique, so finding even a slice of one in a file is proof the
photo (or something made from it) leaked. Each photo also holds a plain-text marker in a PNG text
chunk, so the test can tell which photo a request carried.
"""

import base64
import io
import random
from collections.abc import Iterable, Sequence
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from eval.harness.queries import AcceptanceQuery

MARKER_PREFIX = "VGA-PHOTO-MARKER"
SIZE = (64, 64)
WINDOW = 48
"""Bytes per window. A multiple of 3, so the base64 of a window is a substring of the base64 of the
whole photo. A leak of at least twice this, in one piece, is always found."""


def make_marked_photo(name: str) -> bytes:
    """A valid PNG of random noise whose text chunk holds ``VGA-PHOTO-MARKER:<name>``."""
    noise = random.Random(name).randbytes(SIZE[0] * SIZE[1] * 3)
    info = PngInfo()
    info.add_text("marker", f"{MARKER_PREFIX}:{name}")
    buffer = io.BytesIO()
    Image.frombytes("RGB", SIZE, noise).save(buffer, format="PNG", pnginfo=info)
    return buffer.getvalue()


def marker_of(photo: bytes) -> str:
    """The name a photo was made with."""
    with Image.open(io.BytesIO(photo)) as image:
        text = image.text  # type: ignore[attr-defined]
    return str(text["marker"]).split(":", 1)[1]


def put_marked_photos(root: Path, queries: Iterable[AcceptanceQuery]) -> dict[str, bytes]:
    """Write one marked photo per image path the queries use, under ``root``. Returns them by
    path (queries that share a photo share its bytes)."""
    photos: dict[str, bytes] = {}
    for query in queries:
        if query.image and query.image not in photos:
            photos[query.image] = make_marked_photo(Path(query.image).name)
            target = root / query.image
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(photos[query.image])
    return photos


def _traces(photo: bytes) -> list[tuple[str, bytes]]:
    """Byte strings that would prove ``photo`` was written somewhere: slices of it as it is, and
    as the two kinds of base64."""
    found: list[tuple[str, bytes]] = []
    # Windows side by side, so any leak of 2 x WINDOW bytes in a row holds one whole window.
    for start in range(0, max(len(photo) - WINDOW, 1), WINDOW):
        window = photo[start : start + WINDOW]
        found.append((f"bytes at {start}", window))
        found.append((f"base64 at {start}", base64.b64encode(window)))
        found.append((f"url-safe base64 at {start}", base64.urlsafe_b64encode(window)))
    marker = f"{MARKER_PREFIX}:".encode()
    found.append(("marker", marker))
    return found


def traces_of_photos(
    folder: Path, photos: Iterable[bytes], numbers: Sequence[float] = ()
) -> list[str]:
    """Every file under ``folder`` that holds a trace of one of ``photos``, or of a number derived
    from them (an embedding), as ``"<file>: <what was found>"``. Empty means clean."""
    traces = [trace for photo in photos for trace in _traces(photo)]
    shown = [repr(number).encode() for number in numbers]
    problems: list[str] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        content = path.read_bytes()
        relative = path.relative_to(folder)
        problems.extend(f"{relative}: {what}" for what, needle in traces if needle in content)
        problems.extend(f"{relative}: the number {n.decode()}" for n in shown if n in content)
    return problems
