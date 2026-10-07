"""Photo preparation (plan 5.2.2): upright, metadata-free, small JPEG, no image in any error."""

import base64
import io

import pytest
from PIL import Image

from tests.factories import make_image_bytes
from vga.errors import InvalidInputError
from vga.understand.image import (
    MAX_EDGE_PX,
    UNREADABLE_PHOTO_MESSAGE,
    prepare_image,
    prepare_image_data_url,
)

EXIF_ORIENTATION = 0x0112
EXIF_GPS_IFD = 0x8825
EXIF_MAKE = 0x010F


def _jpeg_with_exif(size: tuple[int, int], orientation: int | None = None) -> bytes:
    exif = Image.Exif()
    exif[EXIF_MAKE] = "SecretPhone Inc"
    if orientation is not None:
        exif[EXIF_ORIENTATION] = orientation
    gps = exif.get_ifd(EXIF_GPS_IFD)
    gps[1] = "N"  # GPSLatitudeRef
    gps[2] = (25.0, 12.0, 30.0)  # GPSLatitude
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _open(jpeg: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(jpeg))
    image.load()
    return image


def test_output_is_a_jpeg() -> None:
    out = prepare_image(make_image_bytes("PNG", (64, 48)))

    assert _open(out).format == "JPEG"


def test_exif_and_gps_are_removed() -> None:
    source = _jpeg_with_exif((200, 100))
    assert Image.open(io.BytesIO(source)).getexif().get_ifd(EXIF_GPS_IFD), "test setup"

    out = prepare_image(source)

    image = _open(out)
    assert dict(image.getexif()) == {}
    assert not image.getexif().get_ifd(EXIF_GPS_IFD)
    assert b"SecretPhone" not in out
    assert b"Exif" not in out
    assert "icc_profile" not in image.info
    assert "comment" not in image.info


def test_exif_rotation_is_applied_before_the_metadata_is_dropped() -> None:
    # Orientation 6 means "rotate 90 degrees to display": a 200x100 file shows as 100x200.
    out = prepare_image(_jpeg_with_exif((200, 100), orientation=6))

    assert _open(out).size == (100, 200)


@pytest.mark.parametrize("size", [(3000, 1500), (1500, 3000), (2048, 2048)])
def test_long_edge_is_at_most_the_cap_and_the_shape_is_kept(size: tuple[int, int]) -> None:
    out = prepare_image(make_image_bytes("PNG", size))

    width, height = _open(out).size
    assert max(width, height) == MAX_EDGE_PX
    assert width / height == pytest.approx(size[0] / size[1], abs=0.01)


def test_a_small_photo_is_not_enlarged() -> None:
    out = prepare_image(make_image_bytes("PNG", (300, 200)))

    assert _open(out).size == (300, 200)


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_every_accepted_format_comes_out_as_jpeg(fmt: str) -> None:
    assert _open(prepare_image(make_image_bytes(fmt, (40, 40)))).format == "JPEG"


def test_transparency_is_flattened_onto_white() -> None:
    buffer = io.BytesIO()
    Image.new("RGBA", (20, 20), (255, 0, 0, 0)).save(buffer, format="PNG")  # fully transparent

    pixel = _open(prepare_image(buffer.getvalue())).getpixel((10, 10))

    assert isinstance(pixel, tuple)
    assert all(channel >= 250 for channel in pixel)


def test_an_animated_image_uses_its_first_frame() -> None:
    first = Image.new("RGB", (30, 30), (0, 0, 255))
    second = Image.new("RGB", (30, 30), (255, 0, 0))
    buffer = io.BytesIO()
    first.save(buffer, format="GIF", save_all=True, append_images=[second])

    pixel = _open(prepare_image(buffer.getvalue())).getpixel((5, 5))

    assert isinstance(pixel, tuple)
    assert pixel[2] > pixel[0]  # blue, not red


def test_data_url_decodes_back_to_the_prepared_jpeg() -> None:
    url = prepare_image_data_url(make_image_bytes("PNG", (50, 50)))

    prefix, _, payload = url.partition(",")
    assert prefix == "data:image/jpeg;base64"
    assert _open(base64.b64decode(payload)).size == (50, 50)


@pytest.mark.parametrize(
    "garbage", [b"", b"not an image at all", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20]
)
def test_unreadable_bytes_raise_a_plain_invalid_input_error(garbage: bytes) -> None:
    with pytest.raises(InvalidInputError) as caught:
        prepare_image(garbage)

    assert caught.value.user_message == UNREADABLE_PHOTO_MESSAGE
    assert "PNG, JPG or WebP" in str(caught.value)


def test_an_absurdly_large_image_is_refused_before_it_is_decoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vga.understand.image.MAX_SOURCE_PIXELS", 100)

    with pytest.raises(InvalidInputError) as caught:
        prepare_image(make_image_bytes("PNG", (20, 20)))

    assert caught.value.detail is not None
    assert "pixels" in caught.value.detail


def test_error_detail_never_contains_image_bytes() -> None:
    secret = b"PRIVATE-PHOTO-BYTES"

    with pytest.raises(InvalidInputError) as caught:
        prepare_image(secret + b"\x00" * 40)

    assert secret.decode() not in (caught.value.detail or "")
    assert secret.decode() not in repr(caught.value)
