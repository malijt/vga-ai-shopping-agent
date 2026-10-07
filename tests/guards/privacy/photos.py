"""Synthetic private photos for the privacy audit.

Nothing here is a real photo and nobody is in it: each picture is seeded random noise, so it is
deterministic, it compresses badly (the file is full of bytes that appear nowhere else) and no slice
of it can be mistaken for another file. What makes a photo *recognisable* is its marker, a text that
is hidden in the file the way real private data is hidden in a real photo: in the metadata and after
the picture data. Finding the marker anywhere it should not be means the file itself was kept.

A photo can carry its marker in any of these places (``carriers``):

``exif``     the camera make, the picture description and the orientation tag
``gps``      a GPS position (latitude and longitude)
``icc``      an embedded colour profile
``xmp``      an XMP packet
``comment``  a JPEG comment segment, or a PNG text chunk named ``comment``
``text``     PNG text chunks with other names (``Description``, ``Author``)
``tail``     bytes written after the end of the picture data (JPEG and PNG)
"""

import io
import random
from collections.abc import Iterable
from dataclasses import dataclass

from PIL import Image, ImageCms
from PIL.PngImagePlugin import PngInfo

DEFAULT_CARRIERS = frozenset({"exif", "gps", "icc", "xmp", "tail"})
"""Everything except ``comment``: the audits that follow the photo around the machine use this.
``comment`` has its own tests, because it is the one carrier the app does not strip (see
``test_sent_photo.py``)."""

_EXIF_MAKE = 0x010F
_EXIF_DESCRIPTION = 0x010E
_EXIF_GPS_IFD = 0x8825


@dataclass(frozen=True)
class PrivatePhoto:
    data: bytes
    marker: bytes
    """ASCII text that is in ``data`` (in each place named in ``carriers``) and nowhere else."""
    fmt: str
    carriers: frozenset[str]


def marker_for(seed: int) -> bytes:
    return f"VGA-PRIVATE-PHOTO-{seed:04d}-7c1e5a93".encode("ascii")


def make_private_photo(
    fmt: str = "JPEG",
    *,
    seed: int = 1,
    size: tuple[int, int] = (160, 120),
    carriers: Iterable[str] = DEFAULT_CARRIERS,
) -> PrivatePhoto:
    """A noise picture in ``fmt`` (``JPEG``, ``PNG`` or ``WEBP``) that carries a marker."""
    chosen = frozenset(carriers)
    marker = marker_for(seed)
    text = marker.decode("ascii")
    width, height = size
    noise = random.Random(seed).randbytes(width * height * 3)
    picture = Image.frombytes("RGB", size, noise)

    options: dict[str, object] = {}
    if chosen & {"exif", "gps"}:
        exif = Image.Exif()
        if "exif" in chosen:
            exif[_EXIF_MAKE] = "PrivatePhoneCo"
            exif[_EXIF_DESCRIPTION] = text
        if "gps" in chosen:
            gps = exif.get_ifd(_EXIF_GPS_IFD)
            gps[1], gps[2] = "N", (25.0, 12.0, 30.0)  # latitude
            gps[3], gps[4] = "E", (55.0, 16.0, 10.0)  # longitude
        options["exif"] = exif
    if "icc" in chosen:
        options["icc_profile"] = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    if "xmp" in chosen:
        options["xmp"] = f"<x:xmpmeta>{text}</x:xmpmeta>".encode("ascii")
    if fmt == "JPEG" and "comment" in chosen:
        options["comment"] = marker
    if fmt == "PNG" and chosen & {"comment", "text"}:
        info = PngInfo()
        if "comment" in chosen:
            info.add_text("comment", text)
        if "text" in chosen:
            info.add_text("Description", text)
            info.add_itxt("Author", text, zip=True)
        options["pnginfo"] = info

    buffer = io.BytesIO()
    picture.save(buffer, format=fmt, **options)
    data = buffer.getvalue()
    if "tail" in chosen and fmt in {"JPEG", "PNG"}:
        data += b"\x00" + marker * 3  # after the last byte of picture data; decoders ignore it
    return PrivatePhoto(data=data, marker=marker, fmt=fmt, carriers=chosen)


def truncated(photo: PrivatePhoto) -> bytes:
    """The first half of ``photo``: a valid header and size, then the file just stops."""
    return photo.data[: len(photo.data) // 2]


def disguised_as_a_jpeg(photo: PrivatePhoto) -> bytes:
    """Starts like a JPEG, is not one: it gets past the first check and fails to open."""
    return b"\xff\xd8\xff\xe0" + photo.marker * 40
