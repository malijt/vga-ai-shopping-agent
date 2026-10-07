"""Pictures drawn with Pillow for the real-model tests. Nothing is downloaded from anywhere."""

import io
import random

from PIL import Image, ImageDraw

_TEE_OUTLINE = [
    (100, 120), (160, 90), (240, 90), (300, 120), (360, 200), (310, 230),
    (290, 200), (290, 340), (110, 340), (110, 200), (90, 230), (40, 200),
]  # fmt: skip


def tee(colour: tuple[int, int, int], *, transparent: bool = False) -> Image.Image:
    """A flat t-shirt silhouette, 400x400. With ``transparent`` the background is fully
    transparent (black underneath), like a cut-out product PNG; otherwise it is white."""
    background = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
    image = Image.new("RGBA", (400, 400), background)
    ImageDraw.Draw(image).polygon(_TEE_OUTLINE, fill=(*colour, 255))
    return image


def flatten(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """``image`` composited onto a solid background (what a viewer shows for a transparent PNG)."""
    canvas = Image.new("RGBA", image.size, (*background, 255))
    return Image.alpha_composite(canvas, image.convert("RGBA")).convert("RGB")


def checkerboard(size: int = 400, squares: int = 8) -> Image.Image:
    """Yellow and black squares: nothing like a garment."""
    image = Image.new("RGB", (size, size), "black")
    draw = ImageDraw.Draw(image)
    step = size // squares
    for row in range(squares):
        for col in range(squares):
            if (row + col) % 2 == 0:
                draw.rectangle(
                    [col * step, row * step, (col + 1) * step, (row + 1) * step],
                    fill=(240, 200, 20),
                )
    return image


def rings(size: int = 400) -> Image.Image:
    """Concentric blue rings on white."""
    image = Image.new("RGB", (size, size), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    for radius in range(size // 2 - 10, 0, -30):
        centre = size // 2
        draw.ellipse(
            [centre - radius, centre - radius, centre + radius, centre + radius],
            outline=(20, 120, 220),
            width=10,
        )
    return image


def thumbnail(seed: int, size: tuple[int, int] = (400, 300)) -> Image.Image:
    """A distinct, busy picture of the size a store thumbnail has (long edge about 400 px)."""
    rnd = random.Random(seed)
    image = Image.new("RGB", size, tuple(rnd.randrange(150, 256) for _ in range(3)))
    draw = ImageDraw.Draw(image)
    for _ in range(6):
        x, y = rnd.randrange(0, size[0] - 100), rnd.randrange(0, size[1] - 100)
        draw.rectangle(
            [x, y, x + rnd.randrange(30, 100), y + rnd.randrange(30, 100)],
            fill=tuple(rnd.randrange(256) for _ in range(3)),
        )
    return image


def to_jpeg(image: Image.Image, quality: int = 85) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
