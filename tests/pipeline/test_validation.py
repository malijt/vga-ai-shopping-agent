"""Plan 13.1.1: the request is checked first, on the server side, before anything costs money."""

import struct
import zlib

import pytest

from tests.factories import (
    make_image_bytes,
    make_search_request,
    make_settings,
    make_understand_result,
)
from tests.fakes import FakeUnderstander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld
from vga.errors import InvalidInputError
from vga.models import MAX_TEXT_CHARS, RunOverrides, SearchRequest
from vga.pipeline import sniff_image_kind, validate_request
from vga.settings import Settings


def rebuilt(**fields: object) -> SearchRequest:
    """A request built WITHOUT its own validation, as a buggy or hostile caller could."""
    values: dict[str, object] = {"text": None, "image": None, "request_id": "r1", "rerun_of": None}
    return SearchRequest.model_construct(**{**values, **fields})


def png_header(width: int, height: int) -> bytes:
    """The smallest PNG a decoder will read the size of: a header, an empty data chunk, an end."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------------------------
# The real type comes from the first bytes, never from a file name
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("fmt", "kind"), [("JPEG", "jpeg"), ("PNG", "png"), ("WEBP", "webp")])
def test_the_three_accepted_types_are_recognised_by_their_first_bytes(fmt: str, kind: str) -> None:
    assert sniff_image_kind(make_image_bytes(fmt)) == kind


@pytest.mark.parametrize(
    "data",
    [b"hello, this is a text file", b"GIF89a....", b"%PDF-1.7", b"RIFF1234WAVE", b"\x00" * 40],
    ids=["text", "gif", "pdf", "riff-but-not-webp", "zeros"],
)
def test_anything_else_is_not_an_image(data: bytes) -> None:
    assert sniff_image_kind(data) is None


def test_a_png_that_was_saved_as_a_jpg_is_accepted(settings: Settings) -> None:
    # The file name never reaches the server: only the bytes do, and these are a real PNG.
    png = make_image_bytes("PNG", (40, 40))

    validate_request(make_search_request(image=png, text=None), None, settings)


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_each_accepted_type_passes(fmt: str, settings: Settings) -> None:
    validate_request(
        make_search_request(image=make_image_bytes(fmt, (32, 32)), text=None), None, settings
    )


# --------------------------------------------------------------------------------------------
# Every kind of bad input raises the invalid-input error with a plain message
# --------------------------------------------------------------------------------------------


def assert_plain_invalid_input(error: InvalidInputError) -> None:
    assert error.code == "invalid_input"
    assert error.user_message
    assert str(error) == error.user_message
    assert "Traceback" not in error.user_message


def test_a_text_file_saved_as_a_jpg_is_rejected(settings: Settings) -> None:
    request = make_search_request(image=b"just some words, not a picture", text=None)

    with pytest.raises(InvalidInputError) as caught:
        validate_request(request, None, settings)

    assert_plain_invalid_input(caught.value)
    assert "PNG, JPG or WebP" in caught.value.user_message


def test_a_photo_over_the_size_limit_is_rejected() -> None:
    photo = make_image_bytes("PNG", (128, 128))
    small_limit = make_settings(max_image_bytes=len(photo) - 1)

    with pytest.raises(InvalidInputError) as caught:
        validate_request(make_search_request(image=photo, text=None), None, small_limit)

    assert_plain_invalid_input(caught.value)
    assert "larger than" in caught.value.user_message


def test_a_photo_exactly_at_the_size_limit_is_accepted() -> None:
    photo = make_image_bytes("PNG", (32, 32))
    exact = make_settings(max_image_bytes=len(photo))

    validate_request(make_search_request(image=photo, text=None), None, exact)


def test_the_size_limit_comes_from_the_settings_not_from_a_constant() -> None:
    photo = make_image_bytes("PNG", (64, 64))
    limit = make_settings(max_image_bytes=len(photo) - 1)

    with pytest.raises(InvalidInputError):
        validate_request(make_search_request(image=photo, text=None), None, limit)
    validate_request(make_search_request(image=photo, text=None), None, make_settings())


def test_a_request_with_neither_text_nor_photo_is_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(), None, settings)

    assert_plain_invalid_input(caught.value)


def test_text_of_only_spaces_counts_as_no_text(settings: Settings) -> None:
    with pytest.raises(InvalidInputError):
        validate_request(rebuilt(text="    \n  "), None, settings)


def test_text_over_the_length_cap_is_rejected_even_when_the_model_was_not_validated(
    settings: Settings,
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(text="x" * (MAX_TEXT_CHARS + 1)), None, settings)

    assert str(MAX_TEXT_CHARS) in caught.value.user_message


def test_an_empty_photo_is_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(image=b""), None, settings)

    assert "empty" in caught.value.user_message


def test_a_photo_that_claims_to_be_a_jpeg_but_is_not_readable_is_rejected(
    settings: Settings,
) -> None:
    broken = b"\xff\xd8\xff\xe0" + b"this is not a jpeg body"

    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(image=broken), None, settings)

    assert_plain_invalid_input(caught.value)
    assert "couldn't read" in caught.value.user_message


@pytest.mark.parametrize("size", [(4, 400), (400, 4), (1, 1)])
def test_a_photo_too_small_to_show_anything_is_rejected(
    size: tuple[int, int], settings: Settings
) -> None:
    photo = make_image_bytes("PNG", size)

    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(image=photo), None, settings)

    assert "too small" in caught.value.user_message


def test_a_photo_with_an_absurd_edge_is_rejected_without_decoding_it(settings: Settings) -> None:
    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(image=png_header(20_000, 20)), None, settings)

    assert "far larger" in caught.value.user_message


def test_a_photo_with_too_many_pixels_is_rejected_without_decoding_it(settings: Settings) -> None:
    # 10,000 x 6,000 = 60 million pixels: each edge is allowed, the product is not.
    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(image=png_header(10_000, 6_000)), None, settings)

    assert "far larger" in caught.value.user_message


def test_the_photo_bytes_never_appear_in_the_error(settings: Settings) -> None:
    secret = b"SECRET-PHOTO-BYTES-" + b"\x00" * 30

    with pytest.raises(InvalidInputError) as caught:
        validate_request(rebuilt(image=secret), None, settings)

    assert "SECRET-PHOTO-BYTES" not in caught.value.user_message
    assert "SECRET-PHOTO-BYTES" not in (caught.value.detail or "")


# --------------------------------------------------------------------------------------------
# A re-run has neither text nor photo, so it must bring the earlier understanding
# --------------------------------------------------------------------------------------------


def test_a_rerun_without_the_earlier_understanding_is_rejected(settings: Settings) -> None:
    request = SearchRequest(rerun_of="earlier")

    with pytest.raises(InvalidInputError) as caught:
        validate_request(request, None, settings)
    with pytest.raises(InvalidInputError):
        validate_request(request, RunOverrides(), settings)

    assert "start a new search" in caught.value.user_message


def test_a_rerun_with_the_earlier_understanding_needs_no_text_and_no_photo(
    settings: Settings,
) -> None:
    overrides = RunOverrides(understood=make_understand_result())

    validate_request(SearchRequest(rerun_of="earlier"), overrides, settings)


def test_a_rerun_still_has_its_photo_checked_when_it_brings_one(settings: Settings) -> None:
    overrides = RunOverrides(understood=make_understand_result())
    request = rebuilt(rerun_of="earlier", image=b"not a picture")

    with pytest.raises(InvalidInputError):
        validate_request(request, overrides, settings)


# --------------------------------------------------------------------------------------------
# It is the first step of a run: nothing is spent on a request that cannot be searched
# --------------------------------------------------------------------------------------------


async def test_a_rejected_request_makes_no_model_call_and_no_store_request(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, settings: Settings
) -> None:
    understander = FakeUnderstander()
    pipeline = make_pipeline(understander=understander)
    request = make_search_request(image=b"a text file renamed .jpg", text="a blazer")

    with pytest.raises(InvalidInputError):
        await pipeline.run(request, settings)

    assert understander.calls == []
    assert world.all_requests() == 0


async def test_a_png_runs_end_to_end(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    pipeline = make_pipeline()
    request = make_search_request(image=make_image_bytes("PNG", (48, 48)), text="black blazer")

    response = await pipeline.run(request, settings)

    assert response.result_count > 0
