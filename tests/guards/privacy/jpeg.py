"""Reading the structure of a JPEG file: which marker segments it has.

A JPEG is a list of segments, each starting ``FF`` and a marker byte. Everything a photographer or a
phone adds besides the picture lives in segments of its own: ``APP1`` holds EXIF (the camera, the
time, the GPS position) and XMP, ``APP2`` an ICC colour profile, ``APP13`` the Photoshop and IPTC
caption data, ``COM`` a free-text comment. Listing the segments of the JPEG that leaves the machine
shows what it carries without having to know what to search for.
"""

SOI, EOI, SOS = 0xD8, 0xD9, 0xDA
APP0 = 0xE0
COM = 0xFE

NAMES = {
    0xE0: "APP0 (JFIF)",
    0xE1: "APP1 (EXIF or XMP)",
    0xE2: "APP2 (colour profile)",
    0xED: "APP13 (Photoshop or IPTC)",
    0xEE: "APP14 (Adobe)",
    0xFE: "COM (comment)",
    0xDB: "DQT (quantisation table)",
    0xC0: "SOF0 (baseline picture)",
    0xC2: "SOF2 (progressive picture)",
    0xC4: "DHT (Huffman table)",
    0xDD: "DRI (restart interval)",
    0xDA: "SOS (picture data)",
}

PICTURE_ONLY = frozenset({APP0, 0xDB, 0xC0, 0xC2, 0xC4, 0xDD, SOS})
"""The segments a JPEG needs to be a picture: a JFIF header, the tables and the picture data."""


def segments_of(jpeg: bytes) -> list[int]:
    """The marker byte of each segment, in order, up to and including the start of the picture
    data. Raises ``ValueError`` if ``jpeg`` is not a JPEG."""
    if jpeg[:2] != bytes([0xFF, SOI]):
        msg = "not a JPEG: it does not start with the start-of-image marker"
        raise ValueError(msg)
    markers: list[int] = []
    position = 2
    while position + 4 <= len(jpeg):
        if jpeg[position] != 0xFF:
            msg = f"bad JPEG: expected a marker at byte {position}"
            raise ValueError(msg)
        marker = jpeg[position + 1]
        markers.append(marker)
        if marker == SOS:
            break
        position += 2 + int.from_bytes(jpeg[position + 2 : position + 4], "big")
    return markers


def names_of(markers: list[int]) -> list[str]:
    return [NAMES.get(marker, f"marker {marker:#x}") for marker in markers]
