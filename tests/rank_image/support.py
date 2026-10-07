"""Small fakes and builders for the image-ranker tests.

The shared fakes in ``tests/fakes.py`` stand in for the whole ranker; these stand in for the two
boundaries *inside* it: the model (an ``ImageEmbedder``) and the thumbnail download
(``fetch_image``). Both are deterministic and need no network, no weights and no ``torch``.
"""

import asyncio
import io
import math
from collections.abc import Mapping, Sequence

from PIL import Image

from tests.factories import make_image_bytes, make_product
from vga.models import Product

RED = (255, 0, 0)
BLUE = (0, 0, 255)
PINK = (255, 150, 150)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# Chosen so the scores are easy to read with cos_lo=0.45 and cos_hi=0.90:
# red/red = cos 1.0 -> 1.0; red/pink = cos 0.675 -> 0.5; red/blue = cos 0.0 -> 0.0.
DEFAULT_VECTORS: dict[tuple[int, int, int], list[float]] = {
    RED: [1.0, 0.0, 0.0],
    PINK: [0.675, math.sqrt(1 - 0.675**2), 0.0],
    BLUE: [0.0, 0.0, 1.0],
    WHITE: [0.0, 1.0, 0.0],
    BLACK: [0.0, 0.0, 1.0],
}
UNKNOWN_COLOUR_VECTOR = [0.0, 1.0, 1.0]


class ColourEmbedder:
    """Stands in for the model: an image's embedding is looked up by its top-left pixel colour.

    Records every call so tests can check batch sizes and what the model was actually shown.
    """

    def __init__(
        self, vectors: Mapping[tuple[int, int, int], Sequence[float]] | None = None
    ) -> None:
        self._vectors = {colour: list(v) for colour, v in (vectors or DEFAULT_VECTORS).items()}
        self.batch_sizes: list[int] = []
        self.seen_pixels: list[tuple[int, int, int]] = []
        self.seen_modes: list[str] = []

    def embed(self, images: Sequence[Image.Image]) -> list[list[float]]:
        self.batch_sizes.append(len(images))
        rows: list[list[float]] = []
        for image in images:
            self.seen_modes.append(image.mode)
            pixel = image.getpixel((0, 0))
            if not isinstance(pixel, tuple):
                msg = f"expected an RGB pixel, got {pixel!r}"
                raise TypeError(msg)
            colour = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
            self.seen_pixels.append(colour)
            rows.append(list(self._vectors.get(colour, UNKNOWN_COLOUR_VECTOR)))
        return rows


def png(colour: tuple[int, int, int] = RED, size: tuple[int, int] = (8, 8)) -> bytes:
    """A lossless solid-colour PNG, so the colour the fake model sees is exactly ``colour``."""
    return make_image_bytes("PNG", size, colour)


def transparent_png(size: tuple[int, int] = (8, 8)) -> bytes:
    """A fully transparent PNG with black hidden under the transparency (what a plain
    ``convert("RGB")`` would show)."""
    buffer = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def products_for(stores: Mapping[str, int]) -> list[Product]:
    """``{store name: count}`` to products, store by store, with unique URLs."""
    products: list[Product] = []
    index = 0
    for store, count in stores.items():
        for _ in range(count):
            index += 1
            products.append(make_product(index, store=store))
    return products


class FakeThumbnails:
    """Stands in for Phase 6's ``fetch_image``.

    Returns ``images[product.key]`` when given, else ``default`` (a red PNG). A value of ``None``
    means "could not fetch"; an ``Exception`` instance is raised. Records the keys it was asked for
    and the most requests that were in flight at once.
    """

    def __init__(
        self,
        images: Mapping[str, bytes | Exception | None] | None = None,
        *,
        default: bytes | None = None,
    ) -> None:
        self._images = dict(images or {})
        self._default = png() if default is None else default
        self.calls: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def __call__(self, product: Product) -> bytes | None:
        self.calls.append(product.key)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)  # let every other request start before this one finishes
            outcome = self._images.get(product.key, self._default)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        finally:
            self.in_flight -= 1
