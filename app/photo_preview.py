"""The small preview of the shopper's photo that stays on the page next to the results.

Product rule 4 keeps the uploaded photo for one request only. The owner made one exception on
2026-10-08 (ADR 0005, update): after a search that used a photo, a small copy of it stays in the
page's session memory so the shopper can see what the results are for, until the page is refreshed
or a new search starts. This module makes that copy and nothing else; ``app.state`` keeps it.

The copy is drawn again from the photo's pixels (``vga.understand.image.prepare_image``, the same
step that prepares the photo for OpenAI): turned upright, shrunk, flattened onto white where it was
transparent, and saved as a new JPEG that carries no EXIF block, GPS position, colour profile or
comment. It is never logged, written to disk, put in the response or cache, or sent anywhere.
"""

from vga.log import get_logger
from vga.understand.image import prepare_image

log = get_logger(__name__)

PREVIEW_MAX_EDGE_PX = 512
"""The longest side of the preview. The page shows it much smaller; this is only the stored size."""


def make_photo_preview(photo: bytes, *, request_id: str | None = None) -> bytes | None:
    """A small, metadata-free JPEG of ``photo``, or ``None`` when one cannot be made.

    The search has already succeeded when this is called, so it never raises: an undecodable photo
    just means the page shows no preview. The warning names the kind of error and the request, and
    never any part of the image (a decoder's own message can quote bytes of the file).
    """
    try:
        return prepare_image(photo, max_edge=PREVIEW_MAX_EDGE_PX)
    except Exception as exc:
        log.warning(
            "photo preview not made",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        return None
