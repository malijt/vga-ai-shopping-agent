"""Photo preparation for the Understand call (plan 5.2.2, BRD Rule 4).

The shopper's photo is decoded, rotated upright, stripped of everything except pixels (EXIF, GPS,
colour profile, comments), shrunk so its long edge is at most ``MAX_EDGE_PX`` and re-encoded as
JPEG. The result goes to OpenAI as a base64 data URL.

The bytes stay in memory. Nothing here writes to disk or to a log, and an error never carries image
data, so a failure cannot leak the photo.
"""

import base64
import io

from PIL import Image, ImageOps

from vga.errors import InvalidInputError

MAX_EDGE_PX = 1024
"""Longest side sent to OpenAI. Enough to tell a garment's cut and colour, and it bounds the
number of image tokens we pay for."""

JPEG_QUALITY = 85

MAX_SOURCE_PIXELS = 50_000_000
"""Refuse to decode anything larger (a decompression bomb, or a photo no phone takes). The
pipeline entry also checks size and dimensions (plan 13.1.1); this is the second line of defence."""

ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")
"""The formats the app accepts. Pillow can open many more (EPS may even start Ghostscript); only
these are decoded."""

UNREADABLE_PHOTO_MESSAGE = (
    "We couldn't read that photo. Please upload a PNG, JPG or WebP image, "
    "or describe the item in words instead."
)


def prepare_image(data: bytes, max_edge: int = MAX_EDGE_PX) -> bytes:
    """Return the photo as a metadata-free JPEG whose long edge is at most ``max_edge`` pixels
    (``MAX_EDGE_PX`` unless a smaller picture is wanted, such as the page's preview).

    Raises ``InvalidInputError`` (plain message, no image data) when the bytes are not a readable
    image.
    """
    try:
        with Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS) as source:
            width, height = source.size
            if width * height > MAX_SOURCE_PIXELS:
                raise InvalidInputError(
                    UNREADABLE_PHOTO_MESSAGE,
                    detail=f"photo has {width * height} pixels, the limit is {MAX_SOURCE_PIXELS}",
                )
            # JPEGs can be decoded at a fraction of their size: much less memory for a big photo.
            source.draft("RGB", (max_edge, max_edge))
            upright = ImageOps.exif_transpose(source)  # apply the rotation BEFORE dropping EXIF
            flat = _flatten_to_rgb(upright)
    except InvalidInputError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        # Pillow raises SyntaxError for some corrupt PNGs. Only the type goes in the detail: the
        # message of a decoder error can quote bytes of the file.
        raise InvalidInputError(
            UNREADABLE_PHOTO_MESSAGE, detail=f"cannot decode photo: {type(exc).__name__}"
        ) from exc

    flat.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    # Draw the pixels into a new image, which carries none of the source's ``info``. Saving ``flat``
    # itself is not enough: Pillow's JPEG writer falls back on ``image.info`` for a comment when
    # none is passed, so a JPEG comment (or a PNG text chunk named "comment") went to OpenAI with
    # the picture. A fresh image also keeps any field a future Pillow starts to reuse from leaking.
    pixels = Image.frombytes("RGB", flat.size, flat.tobytes())
    buffer = io.BytesIO()
    # No exif=, icc_profile= or comment= arguments: the encoder writes pixels only.
    pixels.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def to_data_url(jpeg: bytes) -> str:
    """The ``data:image/jpeg;base64,...`` form OpenAI accepts for an image input."""
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def prepare_image_data_url(data: bytes) -> str:
    """``prepare_image`` and ``to_data_url`` in one step."""
    return to_data_url(prepare_image(data))


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """RGB pixels with transparency composited onto white (JPEG has no alpha channel)."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")
