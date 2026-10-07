"""8.1.2 Cosine, its 0-1 mapping, and decoding images (transparent PNGs go on white)."""

import io
import math

import pytest
from PIL import Image

from tests.factories import make_image_bytes
from tests.rank_image.support import transparent_png
from vga.rank.image.imaging import (
    MAX_DECODE_PIXELS,
    UndecodableImageError,
    decode_rgb,
    to_rgb,
)
from vga.rank.image.scoring import cosine, cosine_to_score, similarity_score


class TestCosine:
    def test_identical_vectors_have_cosine_one(self) -> None:
        assert cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_scale_does_not_matter(self) -> None:
        assert cosine([1.0, 2.0], [10.0, 20.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_have_cosine_zero(self) -> None:
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_have_cosine_minus_one(self) -> None:
        assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_a_zero_vector_has_no_cosine(self) -> None:
        assert cosine([0.0, 0.0], [1.0, 0.0]) is None

    def test_a_non_finite_value_has_no_cosine(self) -> None:
        assert cosine([math.nan, 1.0], [1.0, 1.0]) is None
        assert cosine([math.inf, 1.0], [1.0, 1.0]) is None

    def test_vectors_of_different_sizes_are_an_error(self) -> None:
        with pytest.raises(ValueError, match="sizes differ"):
            cosine([1.0, 0.0], [1.0, 0.0, 0.0])


class TestCosineToScore:
    LO = 0.45
    HI = 0.90

    @pytest.mark.parametrize(
        ("cos", "expected"),
        [
            (1.0, 1.0),
            (0.90, 1.0),
            (0.675, 0.5),
            (0.45, 0.0),
            (0.2, 0.0),
            (-1.0, 0.0),
        ],
    )
    def test_the_range_is_mapped_and_clipped(self, cos: float, expected: float) -> None:
        assert cosine_to_score(cos, self.LO, self.HI) == pytest.approx(expected)

    def test_the_bounds_come_from_the_caller(self) -> None:
        assert cosine_to_score(0.5, lo=0.0, hi=1.0) == pytest.approx(0.5)

    def test_bounds_in_the_wrong_order_are_refused(self) -> None:
        with pytest.raises(ValueError, match="below"):
            cosine_to_score(0.5, lo=0.9, hi=0.45)

    def test_similarity_score_combines_cosine_and_mapping(self) -> None:
        assert similarity_score([1.0, 0.0], [1.0, 0.0], lo=self.LO, hi=self.HI) == 1.0
        assert similarity_score([1.0, 0.0], [0.0, 1.0], lo=self.LO, hi=self.HI) == 0.0

    def test_similarity_score_is_none_when_the_cosine_is_undefined(self) -> None:
        assert similarity_score([0.0, 0.0], [1.0, 0.0], lo=self.LO, hi=self.HI) is None


class TestToRgb:
    def test_transparent_pixels_become_white_not_black(self) -> None:
        transparent = Image.new("RGBA", (4, 4), (0, 0, 0, 0))

        flat = to_rgb(transparent)

        assert flat.mode == "RGB"
        assert flat.getpixel((0, 0)) == (255, 255, 255)

    def test_opaque_pixels_keep_their_colour(self) -> None:
        image = Image.new("RGBA", (4, 4), (10, 20, 30, 255))

        assert to_rgb(image).getpixel((0, 0)) == (10, 20, 30)

    def test_half_transparent_pixels_blend_with_white(self) -> None:
        image = Image.new("RGBA", (4, 4), (0, 0, 0, 128))

        red, green, blue = to_rgb(image).getpixel((0, 0))  # type: ignore[misc]

        assert 120 <= red == green == blue <= 135

    def test_a_palette_image_with_transparency_goes_on_white(self) -> None:
        palette = Image.new("P", (4, 4), 0)
        palette.putpalette([0, 0, 0] * 256)
        palette.info["transparency"] = 0

        assert to_rgb(palette).getpixel((0, 0)) == (255, 255, 255)

    def test_a_plain_rgb_image_is_just_copied(self) -> None:
        image = Image.new("RGB", (4, 4), (1, 2, 3))

        flat = to_rgb(image)

        assert flat.getpixel((0, 0)) == (1, 2, 3)
        assert flat is not image

    def test_a_greyscale_image_becomes_rgb(self) -> None:
        assert to_rgb(Image.new("L", (4, 4), 99)).getpixel((0, 0)) == (99, 99, 99)


class TestDecodeRgb:
    @pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
    def test_the_common_formats_decode_to_rgb(self, fmt: str) -> None:
        image = decode_rgb(make_image_bytes(fmt, (12, 9)))

        assert image.mode == "RGB"
        assert image.size == (12, 9)

    def test_a_transparent_png_is_not_turned_black(self) -> None:
        image = decode_rgb(transparent_png())

        assert image.getpixel((0, 0)) == (255, 255, 255)

    def test_bytes_that_are_not_an_image_are_refused(self) -> None:
        with pytest.raises(UndecodableImageError):
            decode_rgb(b"<html>not a picture</html>")

    def test_empty_bytes_are_refused(self) -> None:
        with pytest.raises(UndecodableImageError):
            decode_rgb(b"")

    def test_a_truncated_image_is_refused(self) -> None:
        buffer = io.BytesIO()
        Image.effect_noise((200, 200), 80).convert("RGB").save(buffer, format="PNG")
        truncated = buffer.getvalue()[:300]

        with pytest.raises(UndecodableImageError):
            decode_rgb(truncated)

    def test_an_image_with_too_many_pixels_is_refused_before_decoding(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("vga.rank.image.imaging.MAX_DECODE_PIXELS", 100)

        with pytest.raises(UndecodableImageError, match="pixels"):
            decode_rgb(make_image_bytes("PNG", (11, 11)))

    def test_the_pixel_limit_leaves_room_for_a_large_phone_photo(self) -> None:
        assert MAX_DECODE_PIXELS >= 48_000_000

    def test_the_exif_orientation_is_applied(self) -> None:
        sideways = Image.new("RGB", (20, 10), (200, 0, 0))
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 270 degrees to display upright
        buffer = io.BytesIO()
        sideways.save(buffer, format="JPEG", exif=exif)

        upright = decode_rgb(buffer.getvalue())

        assert upright.size == (10, 20)
