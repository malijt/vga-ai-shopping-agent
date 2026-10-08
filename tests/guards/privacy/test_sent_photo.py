"""What leaves the machine: the one JPEG that goes to OpenAI, and how.

The app does not send the file it was given. It decodes it, turns it upright, draws it again as a
new JPEG and sends that (``vga.understand.image``), so whatever the original carried besides the
picture should be gone. These tests give the whole pipeline a photo that hides a marker in one
place at a time (the EXIF block, a GPS position, a colour profile, an XMP packet, a comment, a PNG
text chunk) and read the bytes OpenAI receives.

The comment cases were expected failures until ``prepare_image`` started drawing the pixels into a
new image: Pillow's JPEG writer re-used a comment from the source image's metadata.
"""

import io
import json

import pytest
from PIL import Image

from tests.guards.privacy.audit import problems_in
from tests.guards.privacy.jpeg import PICTURE_ONLY, names_of, segments_of
from tests.guards.privacy.rig import blazer_reading
from tests.guards.privacy.scenarios import (
    RETRIED,
    Scenario,
)
from tests.guards.privacy.traces import signs_of_an_image
from tests.understand.fake_openai import answer

EXIF_GPS_IFD = 0x8825
EXIF_DESCRIPTION = 0x010E


def sending(fmt: str, *carriers: str) -> Scenario:
    return Scenario(
        f"{fmt} with {' and '.join(carriers)}",
        lambda: [answer(blazer_reading())],
        photo_format=fmt,
        photo_carriers=frozenset(carriers),
    )


STRIPPED = [
    pytest.param(sending("JPEG", "exif"), id="JPEG EXIF (camera make, description)"),
    pytest.param(sending("JPEG", "gps"), id="JPEG GPS position"),
    pytest.param(sending("JPEG", "icc"), id="JPEG colour profile"),
    pytest.param(sending("JPEG", "xmp"), id="JPEG XMP packet"),
    pytest.param(sending("JPEG", "tail"), id="JPEG bytes after the picture"),
    pytest.param(sending("PNG", "exif", "gps", "icc"), id="PNG EXIF, GPS and colour profile"),
    pytest.param(sending("PNG", "text"), id="PNG text chunks (Description, Author)"),
    pytest.param(sending("WEBP", "exif", "gps", "icc", "xmp"), id="WebP EXIF, GPS, profile, XMP"),
    pytest.param(sending("JPEG", "comment"), id="JPEG comment"),
    pytest.param(sending("PNG", "comment"), id="PNG text chunk named comment"),
]


def carried_by(upload: bytes, carrier: str, marker: bytes) -> bool:
    """Whether the uploaded file really has what the scenario put in it."""
    picture = Image.open(io.BytesIO(upload))
    match carrier:
        case "exif":
            return EXIF_DESCRIPTION in picture.getexif()
        case "gps":
            return bool(picture.getexif().get_ifd(EXIF_GPS_IFD))
        case "icc":
            return bool(picture.info.get("icc_profile"))
        case _:
            return marker in upload


@pytest.mark.parametrize("scenario", STRIPPED)
async def test_nothing_but_the_picture_goes_to_openai(scenario: Scenario, run) -> None:
    audited = await run(scenario)

    [sent] = audited.sent_images
    for carrier in scenario.photo_carriers:
        assert carried_by(audited.submitted, carrier, audited.photo.marker), f"no {carrier} to hide"
    sent_picture = Image.open(io.BytesIO(sent))
    leftovers = {
        "the marker": audited.photo.marker in sent,
        "a GPS position": bool(sent_picture.getexif().get_ifd(EXIF_GPS_IFD)),
        "EXIF": EXIF_DESCRIPTION in sent_picture.getexif(),
        "metadata of Pillow's kind": bool(
            {"icc_profile", "exif", "xmp", "comment"} & set(sent_picture.info)
        ),
        "a segment besides the picture": [
            name
            for name in names_of(segments_of(sent))
            if name not in names_of(sorted(PICTURE_ONLY))
        ],
    }
    assert {what: found for what, found in leftovers.items() if found} == {}


# --------------------------------------------------------------------------------------------
# The request itself
# --------------------------------------------------------------------------------------------


async def test_every_call_to_openai_asks_for_nothing_to_be_stored(run) -> None:
    audited = await run(RETRIED)  # two calls: the first answer is cut off

    bodies = [request.body for request in audited.rig.fake_openai.requests]
    assert len(bodies) == 2
    assert [body["store"] for body in bodies] == [False, False]


async def test_the_photo_is_in_the_request_once_as_one_jpeg_data_url_and_nowhere_else(run) -> None:
    audited = await run(sending("PNG", "text"))

    [request] = audited.rig.fake_openai.requests
    [user] = [message for message in request.messages if message["role"] == "user"]
    images = [part for part in user["content"] if part["type"] == "input_image"]
    assert len(images) == 1
    assert images[0]["image_url"].startswith("data:image/jpeg;base64,")
    without_the_photo = json.dumps(request.body).replace(images[0]["image_url"], "")
    assert problems_in(without_the_photo, audited.traces, "the rest of the request") == []
    assert signs_of_an_image(without_the_photo) == []


async def test_a_second_call_after_a_bad_answer_sends_the_same_clean_photo_again(run) -> None:
    audited = await run(RETRIED)

    first, second = audited.sent_images
    assert first == second
    assert set(segments_of(second)) <= PICTURE_ONLY
    assert audited.photo.marker not in second


async def test_a_photo_that_is_rejected_sends_nothing_to_anyone(run) -> None:
    from tests.guards.privacy.scenarios import NOT_AN_IMAGE, TRUNCATED

    for scenario in (NOT_AN_IMAGE, TRUNCATED):
        audited = await run(scenario)
        assert audited.rig.fake_openai.requests == [], scenario.name
        assert audited.rig.world.all_requests() == 0, scenario.name
