"""BRD Rule 4: the photo is not kept after the request. Not on disk, not in a log, not in the cache.

After the image step the pipeline drops the photo and keeps only its embedding (a list of numbers),
which the next search of the same photo (a chip edit) needs instead of the photo (assumption A8).
"""

import base64
import dataclasses
import io
import logging
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from tests.factories import make_image_bytes, make_search_request, make_settings
from tests.fakes import FakeClock, FakeImageRanker
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.disk import files_under, read_bytes
from tests.pipeline.test_outfit import OUTFIT, outfit_understander
from tests.pipeline.test_rerun import photo_search, rerun
from tests.pipeline.world import StoreWorld, store_for
from vga.errors import InvalidInputError
from vga.log import LOG_FILE_NAME, configure_logging
from vga.models import MixPreset, Product, QueryImage
from vga.settings import Settings


@pytest.fixture
def distinctive_photo() -> bytes:
    """A real JPEG with a long, unusual tail, so finding any part of it means a leak."""
    return make_image_bytes("JPEG", (64, 64), (33, 77, 191)) + b"\x00PRIVATE-PHOTO-TAIL-4f2a9c" * 40


@pytest.fixture
def file_logging(tmp_path: Path) -> Iterator[Path]:
    """The real JSON log, written to a file in the test's folder, at the most detailed level."""
    configure_logging(level="DEBUG", log_dir=tmp_path / "logs", stream=io.StringIO())
    yield tmp_path / "logs" / LOG_FILE_NAME
    root = logging.getLogger("vga")
    for handler in [h for h in root.handlers if getattr(h, "_vga_handler", False)]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.NOTSET)


def traces_of(photo: bytes) -> list[bytes]:
    """Every way a photo could show up in text: raw, a long slice, base64, hex, a repr."""
    middle = photo[len(photo) // 2 : len(photo) // 2 + 48]
    return [
        photo,
        middle,
        b"PRIVATE-PHOTO-TAIL-4f2a9c",
        base64.b64encode(photo)[:64],
        base64.b64encode(middle),
        photo[:48].hex().encode(),
        repr(middle).encode(),
    ]


def assert_no_trace(blob: bytes, photo: bytes) -> None:
    for trace in traces_of(photo):
        assert trace not in blob, f"a trace of the photo was found: {trace[:30]!r}"


def walk(value: Any, seen: set[int] | None = None) -> Iterator[Any]:
    """Every object reachable from ``value`` through containers, dataclasses and models."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return
    seen.add(id(value))
    yield value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from walk(getattr(value, field.name), seen)
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from walk(getattr(value, name), seen)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk(key, seen)
            yield from walk(item, seen)
    elif isinstance(value, list | tuple | set | frozenset):
        for item in value:
            yield from walk(item, seen)
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        yield from walk(vars(value), seen)


def bytes_in(value: Any) -> list[Any]:
    return [x for x in walk(value) if isinstance(x, bytes | bytearray | memoryview)]


class KeepsTheQuery(FakeImageRanker):
    """A fake ranker that keeps the ``QueryImage`` it was handed, to look at it afterwards."""

    def __init__(self) -> None:
        super().__init__(default=0.7, embedding=[0.1, 0.2, 0.3])
        self.queries: list[QueryImage] = []

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        assert query is not None
        self.queries.append(query)
        assert query.image is not None  # the photo is there while the ranker works
        return await super().score(query, products)


# --------------------------------------------------------------------------------------------
# The photo is dropped once it has been compared
# --------------------------------------------------------------------------------------------


async def test_the_query_image_is_cleared_after_the_comparison_and_the_embedding_is_kept(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, distinctive_photo: bytes
) -> None:
    ranker = KeepsTheQuery()
    pipeline = make_pipeline(image_ranker=ranker)

    response = await pipeline.run(
        make_search_request(image=distinctive_photo, text="black blazer"), settings
    )

    [query] = ranker.queries
    assert query.image is None
    assert query.embedding == [0.1, 0.2, 0.3]
    assert response.query_embedding == [0.1, 0.2, 0.3]


async def test_the_response_holds_no_photo_in_any_form(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, distinctive_photo: bytes
) -> None:
    pipeline = make_pipeline(image_ranker=KeepsTheQuery())

    response = await pipeline.run(
        make_search_request(image=distinctive_photo, text="black blazer"), settings
    )

    assert bytes_in(response) == []
    assert_no_trace(response.model_dump_json().encode(), distinctive_photo)
    assert_no_trace(repr(response).encode(), distinctive_photo)


# --------------------------------------------------------------------------------------------
# The re-run cache
# --------------------------------------------------------------------------------------------


async def test_the_rerun_cache_holds_no_photo_bytes(
    make_pipeline: PipelineMaker,
    two_stores: list,
    settings: Settings,
    distinctive_photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=photo_search(), image_ranker=KeepsTheQuery())
    first = await pipeline.run(
        make_search_request(image=distinctive_photo, text="black blazer"), settings
    )
    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    await pipeline.run(request, settings, overrides)

    cache = pipeline._cache  # the only state the pipeline keeps between requests

    assert len(cache) == 2  # the first request and the re-run are both remembered
    assert bytes_in(cache) == []
    assert_no_trace(repr(cache._runs).encode(), distinctive_photo)
    floats = [x for x in walk(cache._runs) if isinstance(x, float)]
    assert 0.1 in floats  # the embedding is kept: numbers, not the photo


async def test_nothing_the_pipeline_owns_holds_a_photo(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, distinctive_photo: bytes
) -> None:
    pipeline = make_pipeline(image_ranker=KeepsTheQuery())

    await pipeline.run(make_search_request(image=distinctive_photo, text="black blazer"), settings)

    injected = {"_understander", "_searcher", "_image_ranker"}  # the fakes keep what they were sent
    own = {name: value for name, value in vars(pipeline).items() if name not in injected}
    assert bytes_in(own) == []


# --------------------------------------------------------------------------------------------
# Disk and logs
# --------------------------------------------------------------------------------------------


async def test_the_photo_is_never_written_to_disk(
    make_pipeline: PipelineMaker,
    two_stores: list,
    tmp_path: Path,
    distinctive_photo: bytes,
    file_logging: Path,
) -> None:
    # Every switch that writes something is on: the dump and a log file at DEBUG level.
    settings = make_settings(debug_dump=True, log_dir=str(tmp_path / "logs"))
    pipeline = make_pipeline(understander=photo_search(), image_ranker=KeepsTheQuery())

    first = await pipeline.run(
        make_search_request(image=distinctive_photo, text="black blazer"), settings
    )
    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    await pipeline.run(request, settings, overrides)

    files = files_under(tmp_path)
    assert file_logging in files  # the log really was written
    assert any(path.name.startswith("candidates-") for path in files)  # and so was the dump
    for path in files:
        assert_no_trace(path.read_bytes(), distinctive_photo)


async def test_the_photo_is_in_no_log_line_and_nothing_had_to_be_redacted(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    distinctive_photo: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="vga")
    world.add(store_for("alpha"))
    world.add(store_for("beta"), status=403)  # a failure path logs too
    pipeline = make_pipeline(image_ranker=FakeImageRanker(error=RuntimeError("model crashed")))

    await pipeline.run(
        make_search_request(image=distinctive_photo, text="black oversized blazer"), settings
    )

    everything = "\n".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records
    )
    assert everything
    assert_no_trace(everything.encode(), distinctive_photo)
    # The logger would hide a photo in a field called "image" behind a marker. Seeing a marker
    # means the pipeline tried to log one, even if the logger caught it.
    assert "REDACTED" not in everything


async def test_a_rejected_photo_is_not_logged_either(
    make_pipeline: PipelineMaker,
    two_stores: list,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
    file_logging: Path,
) -> None:
    caplog.set_level(logging.DEBUG, logger="vga")
    not_a_photo = b"PRIVATE-PHOTO-TAIL-4f2a9c is a text file pretending to be a picture"
    pipeline = make_pipeline()

    with pytest.raises(InvalidInputError) as caught:
        await pipeline.run(make_search_request(image=not_a_photo, text=None), settings)

    everything = "\n".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records
    )
    assert b"PRIVATE-PHOTO-TAIL-4f2a9c" not in everything.encode()
    assert b"PRIVATE-PHOTO-TAIL-4f2a9c" not in read_bytes(file_logging)
    assert "PRIVATE-PHOTO-TAIL" not in caught.value.user_message
    assert "PRIVATE-PHOTO-TAIL" not in (caught.value.detail or "")


async def test_the_photo_is_dropped_even_when_the_deadline_cuts_the_comparison_short(
    make_pipeline: PipelineMaker,
    two_stores: list,
    settings: Settings,
    clock: FakeClock,
    distinctive_photo: bytes,
) -> None:
    queries: list[QueryImage] = []

    class NeverFinishes:
        async def score(
            self, query: QueryImage | None, products: Sequence[Product]
        ) -> dict[str, float | None]:
            assert query is not None
            queries.append(query)
            await clock.sleep(1000)
            return {}

    pipeline = make_pipeline(image_ranker=NeverFinishes())

    response = await pipeline.run(
        make_search_request(image=distinctive_photo, text="black blazer"), settings
    )

    assert response.warnings
    assert [query.image for query in queries] == [None]


async def test_an_outfit_photo_is_dropped_after_the_last_garment(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, distinctive_photo: bytes
) -> None:
    ranker = KeepsTheQuery()
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT), image_ranker=ranker)

    await pipeline.run(make_search_request(image=distinctive_photo, text=None), settings)

    assert len(ranker.queries) == 4
    assert len({id(query) for query in ranker.queries}) == 1  # one shared query for the outfit
    assert ranker.queries[0].image is None
