"""Turning untrusted image bytes into RGB images the model can read (plan 8.1.2).

Both the shopper's photo and every store thumbnail are untrusted input: anything that is not a
decodable, reasonably sized image is rejected with ``UndecodableImageError`` and the caller treats
the product as "no score". Everything stays in memory; nothing here touches the disk.
"""

import io

from PIL import Image, ImageOps

MAX_DECODE_PIXELS = 50_000_000
"""Images with more pixels than this are refused before they are decoded (a decompression-bomb
guard; a 48 MP phone photo still fits)."""

_ALPHA_MODES = frozenset({"RGBA", "LA", "PA", "La", "RGBa"})


class UndecodableImageError(ValueError):
    """The bytes are not an image we are willing to decode."""


def to_rgb(image: Image.Image) -> Image.Image:
    """An RGB copy of ``image`` in which transparent pixels are white.

    A plain ``convert("RGB")`` turns transparent pixels black, and product cut-outs are often
    transparent PNGs, so the picture is composited onto white first (spike finding 4).
    """
    if image.mode in _ALPHA_MODES or "transparency" in image.info:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def decode_rgb(data: bytes) -> Image.Image:
    """Decode image bytes into an upright RGB image, or raise ``UndecodableImageError``.

    The picture is decoded completely, so a truncated file fails here and not later inside the
    model. The EXIF orientation is applied because phone photos are often stored sideways.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_DECODE_PIXELS:
                msg = f"image is {image.width}x{image.height} pixels, more than the allowed maximum"
                raise UndecodableImageError(msg)
            image.load()
            return to_rgb(ImageOps.exif_transpose(image))
    except UndecodableImageError:
        raise
    except Exception as exc:  # Pillow raises many kinds of error for bad input
        msg = f"the bytes are not a readable image ({type(exc).__name__})"
        raise UndecodableImageError(msg) from exc
