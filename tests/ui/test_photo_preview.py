"""The small preview of the photo that stays on the page (owner's decision 2026-10-08, ADR 0005
update): what it is, what it must not carry, and that failing to make one never breaks anything.
"""

import io
import logging

import pytest
from PIL import Image

from app.photo_preview import PREVIEW_MAX_EDGE_PX, make_photo_preview
from tests.factories import make_image_bytes
from tests.guards.privacy.jpeg import PICTURE_ONLY, names_of, segments_of
from tests.guards.privacy.photos import PrivatePhoto, make_private_photo
from tests.guards.privacy.traces import forms_of

EXIF_ORIENTATION = 0x0112


def opened(jpeg: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(jpeg))
    image.load()
    return image


def make_jpeg(size: tuple[int, int], orientation: int | None = None) -> bytes:
    exif = Image.Exif()
    if orientation is not None:
        exif[EXIF_ORIENTATION] = orientation
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


class TestSize:
    @pytest.mark.parametrize("size", [(3000, 1500), (1500, 3000), (2048, 2048), (700, 513)])
    def test_the_longest_side_is_at_most_512_pixels_and_the_shape_is_kept(
        self, size: tuple[int, int]
    ) -> None:
        preview = make_photo_preview(make_image_bytes("PNG", size))

        assert preview is not None
        width, height = opened(preview).size
        assert max(width, height) <= PREVIEW_MAX_EDGE_PX == 512
        assert width / height == pytest.approx(size[0] / size[1], abs=0.02)

    def test_a_small_photo_is_not_enlarged(self) -> None:
        preview = make_photo_preview(make_image_bytes("PNG", (300, 200)))

        assert preview is not None
        assert opened(preview).size == (300, 200)

    def test_a_photo_turned_by_its_camera_tag_comes_out_upright(self) -> None:
        # Orientation 6: a 200x100 file shows as 100x200. The preview shows what the shopper saw.
        preview = make_photo_preview(make_jpeg((200, 100), orientation=6))

        assert preview is not None
        assert opened(preview).size == (100, 200)


class TestWhatItCarries:
    @pytest.mark.parametrize(
        "photo",
        [
            pytest.param(
                make_private_photo(
                    "JPEG",
                    size=(800, 600),
                    carriers={"exif", "gps", "icc", "xmp", "comment", "tail"},
                ),
                id="JPEG with EXIF, GPS, colour profile, XMP, comment and trailing bytes",
            ),
            pytest.param(
                make_private_photo("PNG", size=(800, 600), carriers={"exif", "gps", "icc", "text"}),
                id="PNG with EXIF, GPS, colour profile and text chunks",
            ),
            pytest.param(
                make_private_photo("PNG", size=(800, 600), carriers={"comment"}),
                id="PNG text chunk named comment",
            ),
            pytest.param(
                make_private_photo("WEBP", size=(800, 600), carriers={"exif", "icc", "xmp"}),
                id="WebP with EXIF, colour profile and XMP",
            ),
        ],
    )
    def test_no_exif_gps_profile_or_comment_travels_with_it(self, photo: PrivatePhoto) -> None:
        assert photo.marker in photo.data, "the test photo must carry its marker"

        preview = make_photo_preview(photo.data)

        assert preview is not None
        picture = opened(preview)
        assert dict(picture.getexif()) == {}
        assert not picture.getexif().get_ifd(0x8825)  # the GPS block
        assert not {"icc_profile", "exif", "xmp", "comment"} & set(picture.info)
        assert photo.marker not in preview

    def test_it_is_a_jpeg_made_of_the_picture_segments_only(self) -> None:
        photo = make_private_photo("JPEG", size=(800, 600), carriers={"exif", "gps", "icc", "xmp"})

        preview = make_photo_preview(photo.data)

        assert preview is not None
        assert opened(preview).format == "JPEG"
        extra = [
            n for n in names_of(segments_of(preview)) if n not in names_of(sorted(PICTURE_ONLY))
        ]
        assert extra == []

    def test_it_is_not_the_upload_in_any_shape(self) -> None:
        photo = make_private_photo("JPEG", size=(800, 600))

        preview = make_photo_preview(photo.data)

        assert preview is not None
        assert preview != photo.data
        assert photo.data not in preview
        assert not any(trace.needle in preview for trace in forms_of(photo.marker, "marker"))

    def test_transparency_is_flattened_onto_white(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGBA", (20, 20), (255, 0, 0, 0)).save(buffer, format="PNG")

        preview = make_photo_preview(buffer.getvalue())

        assert preview is not None
        pixel = opened(preview).getpixel((10, 10))
        assert isinstance(pixel, tuple)
        assert all(channel >= 250 for channel in pixel)


class TestWhenItCannotBeMade:
    @pytest.mark.parametrize(
        "garbage",
        [
            b"",
            b"plain text",
            b"\x89PNG\r\n\x1a\n" + b"not really a picture",
            b"\xff\xd8\xff\xe0" + b"VGA-PRIVATE-PHOTO" * 40,
        ],
        ids=["empty", "text", "png header, no picture", "jpeg header, no picture"],
    )
    def test_it_returns_none_and_does_not_raise(self, garbage: bytes) -> None:
        assert make_photo_preview(garbage) is None

    def test_the_warning_names_the_request_and_the_kind_of_error_and_holds_no_image_data(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        garbage = b"\xff\xd8\xff\xe0" + b"VGA-PRIVATE-PHOTO" * 40

        with caplog.at_level(logging.WARNING):
            make_photo_preview(garbage, request_id="req-123")

        [record] = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert record.__dict__["request_id"] == "req-123"
        assert record.__dict__["error_type"]
        shown = f"{record.getMessage()} {record.__dict__}"
        assert "VGA-PRIVATE-PHOTO" not in shown
        assert "\\xff\\xd8" not in shown
