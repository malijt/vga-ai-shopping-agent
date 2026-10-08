"""8.3.1 / 8.3.2 The `off` ranker, the factory, and the fallback: failures become `None` scores."""

import asyncio
import logging
from pathlib import Path

import pytest

from tests.factories import make_settings
from tests.rank_image.ml_fakes import REVISION, FakeMlPackages
from tests.rank_image.support import (
    PINK,
    RED,
    ColourEmbedder,
    FakeThumbnails,
    png,
    products_for,
)
from vga.errors import VgaError
from vga.log import request_context
from vga.models import QueryImage
from vga.rank.image import (
    OffImageRanker,
    SiglipImageRanker,
    create_image_ranker,
)
from vga.rank.image.model import ImageModelUnavailableError, clear_embedder_cache
from vga.rank.image.siglip import ImageEmbedder

PRODUCTS = products_for({"Store A": 3, "Store B": 2})
ALL_NONE = dict.fromkeys(p.key for p in PRODUCTS)


@pytest.fixture(autouse=True)
def fresh_singleton():
    clear_embedder_cache()
    yield
    clear_embedder_cache()


def degraded_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "image scoring unavailable" in record.getMessage()
    ]


class TestOffRanker:
    async def test_every_product_gets_none(self) -> None:
        scores = await OffImageRanker().score(QueryImage(image=png(RED)), PRODUCTS)

        assert scores == ALL_NONE

    async def test_it_does_not_store_a_query_embedding(self) -> None:
        query = QueryImage(image=png(RED))

        await OffImageRanker().score(query, PRODUCTS)

        assert query.embedding is None

    async def test_no_products_gives_an_empty_mapping(self) -> None:
        assert await OffImageRanker().score(QueryImage(image=png(RED)), []) == {}


class TestFactory:
    def test_off_selects_the_off_ranker(self) -> None:
        settings = make_settings(image_ranker="off")

        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails())

        assert isinstance(ranker, OffImageRanker)

    def test_siglip_selects_the_siglip_ranker(self) -> None:
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)

        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails())

        assert isinstance(ranker, SiglipImageRanker)

    def test_the_default_settings_select_off(self) -> None:
        assert isinstance(
            create_image_ranker(make_settings(), fetch_image=FakeThumbnails()), OffImageRanker
        )

    def test_creating_a_siglip_ranker_loads_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packages = FakeMlPackages(tmp_path).install(monkeypatch)
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)

        create_image_ranker(settings, fetch_image=FakeThumbnails())

        assert packages.hub.calls == []
        assert packages.open_clip.model_names == []

    async def test_off_never_fetches_a_thumbnail(self) -> None:
        thumbnails = FakeThumbnails()
        ranker = create_image_ranker(make_settings(image_ranker="off"), fetch_image=thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        assert scores == ALL_NONE
        assert thumbnails.calls == []

    async def test_siglip_is_built_from_the_pinned_revision_and_the_settings_bounds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked_for: list[str | None] = []

        def fake_get_embedder(revision: str | None) -> ImageEmbedder:
            asked_for.append(revision)
            return ColourEmbedder()

        monkeypatch.setattr("vga.rank.image.factory.get_embedder", fake_get_embedder)
        settings = make_settings(
            image_ranker="siglip", siglip_revision=REVISION, siglip_cos_lo=0.0, siglip_cos_hi=0.675
        )
        product = PRODUCTS[0]
        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails({product.key: png(PINK)}))

        scores = await ranker.score(QueryImage(image=png(RED)), [product])

        assert asked_for == [REVISION]
        assert scores[product.key] == pytest.approx(1.0)  # cos 0.675 is the top of this range


class TestSiglipFallback:
    """Anything that goes wrong becomes all-None and one warning, never an exception."""

    async def test_an_unpinned_revision_gives_all_none_and_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        packages = FakeMlPackages(tmp_path).install(monkeypatch)
        thumbnails = FakeThumbnails()
        settings = make_settings(image_ranker="siglip", siglip_revision=None)
        ranker = create_image_ranker(settings, fetch_image=thumbnails)

        with caplog.at_level(logging.WARNING, logger="vga"):
            scores = await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        assert scores == ALL_NONE
        assert len(degraded_warnings(caplog)) == 1
        assert packages.hub.calls == []
        assert thumbnails.calls == []

    async def test_missing_ml_packages_give_all_none_and_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        FakeMlPackages(tmp_path, missing=["torch", "open_clip"]).install(monkeypatch)
        thumbnails = FakeThumbnails()
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
        ranker = create_image_ranker(settings, fetch_image=thumbnails)

        with caplog.at_level(logging.WARNING, logger="vga"):
            scores = await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        (record,) = degraded_warnings(caplog)
        assert scores == ALL_NONE
        assert record.reason == "image_model_unavailable"  # type: ignore[attr-defined]
        assert "uv sync --group ml" in record.detail  # type: ignore[attr-defined]
        assert thumbnails.calls == []  # no thumbnail is downloaded for a model that is not there

    async def test_missing_weights_give_all_none_and_never_a_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails())

        with caplog.at_level(logging.WARNING, logger="vga"):
            scores = await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        (record,) = degraded_warnings(caplog)
        assert scores == ALL_NONE
        assert "python -m vga.rank.image.download" in record.detail  # type: ignore[attr-defined]
        assert packages.hub.downloads == []

    async def test_the_warning_carries_the_request_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails())

        with caplog.at_level(logging.WARNING, logger="vga"), request_context("req-8f3a"):
            await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        (record,) = degraded_warnings(caplog)
        assert record.request_id == "req-8f3a"  # type: ignore[attr-defined]

    async def test_a_forced_exception_does_not_propagate_and_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class Exploding:
            def embed(self, images: object) -> list[list[float]]:
                raise RuntimeError("the GPU fell over")

        ranker = SiglipImageRanker(
            embedder_provider=Exploding,
            fetch_image=FakeThumbnails(),
            cos_lo=0.45,
            cos_hi=0.9,
        )

        with caplog.at_level(logging.WARNING, logger="vga"), request_context("req-1"):
            scores = await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        (record,) = degraded_warnings(caplog)
        assert scores == ALL_NONE
        assert record.request_id == "req-1"  # type: ignore[attr-defined]
        assert record.reason == "RuntimeError"  # type: ignore[attr-defined]
        assert record.exc_info is not None  # an unexpected error keeps its traceback in the log

    async def test_a_model_that_fails_while_scoring_gives_all_none(self) -> None:
        class FailsOnThumbnails(ColourEmbedder):
            def embed(self, images):  # type: ignore[no-untyped-def]
                if len(images) > 1:
                    raise RuntimeError("out of memory")
                return super().embed(images)

        ranker = SiglipImageRanker(
            embedder_provider=FailsOnThumbnails,
            fetch_image=FakeThumbnails(),
            cos_lo=0.45,
            cos_hi=0.9,
        )

        assert await ranker.score(QueryImage(image=png(RED)), PRODUCTS) == ALL_NONE

    async def test_a_query_photo_that_is_not_an_image_gives_all_none_and_no_fetch(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        thumbnails = FakeThumbnails()
        ranker = SiglipImageRanker(
            embedder_provider=ColourEmbedder,
            fetch_image=thumbnails,
            cos_lo=0.45,
            cos_hi=0.9,
        )

        with caplog.at_level(logging.WARNING, logger="vga"):
            scores = await ranker.score(QueryImage(image=b"not a photo"), PRODUCTS)

        assert scores == ALL_NONE
        assert len(degraded_warnings(caplog)) == 1
        assert thumbnails.calls == []

    async def test_a_degraded_result_is_a_complete_mapping_of_none(self) -> None:
        def unavailable() -> ImageEmbedder:
            raise ImageModelUnavailableError(detail="not installed")

        ranker = SiglipImageRanker(
            embedder_provider=unavailable,
            fetch_image=FakeThumbnails(),
            cos_lo=0.45,
            cos_hi=0.9,
        )

        scores = await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        assert list(scores) == [p.key for p in PRODUCTS]
        assert set(scores.values()) == {None}

    async def test_the_query_embedding_is_not_stored_when_scoring_is_unavailable(self) -> None:
        def unavailable() -> ImageEmbedder:
            raise ImageModelUnavailableError(detail="not installed")

        ranker = SiglipImageRanker(
            embedder_provider=unavailable,
            fetch_image=FakeThumbnails(),
            cos_lo=0.45,
            cos_hi=0.9,
        )
        query = QueryImage(image=png(RED))

        await ranker.score(query, PRODUCTS)

        assert query.embedding is None

    async def test_a_successful_run_logs_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        ranker = SiglipImageRanker(
            embedder_provider=ColourEmbedder,
            fetch_image=FakeThumbnails(),
            cos_lo=0.45,
            cos_hi=0.9,
        )

        with caplog.at_level(logging.WARNING, logger="vga"):
            await ranker.score(QueryImage(image=png(RED)), PRODUCTS)

        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

    async def test_cancelling_the_request_is_not_swallowed(self) -> None:
        release = asyncio.Event()

        async def never_finishes(product: object) -> bytes | None:
            await release.wait()
            return None

        ranker = SiglipImageRanker(
            embedder_provider=ColourEmbedder,
            fetch_image=never_finishes,  # type: ignore[arg-type]
            cos_lo=0.45,
            cos_hi=0.9,
        )
        task = asyncio.create_task(ranker.score(QueryImage(image=png(RED)), PRODUCTS))
        await asyncio.sleep(0.05)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestWarmUp:
    async def test_warm_up_loads_the_model_and_reports_ready(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packages = FakeMlPackages(tmp_path).install(monkeypatch)
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails())
        assert isinstance(ranker, SiglipImageRanker)

        assert await ranker.warm_up() is True
        assert len(packages.open_clip.models) == 1

    async def test_warm_up_reports_unavailable_without_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
        ranker = create_image_ranker(settings, fetch_image=FakeThumbnails())
        assert isinstance(ranker, SiglipImageRanker)

        with caplog.at_level(logging.WARNING, logger="vga"):
            assert await ranker.warm_up() is False

        assert len(degraded_warnings(caplog)) == 1


def test_unavailable_is_an_ordinary_vga_error() -> None:
    error = ImageModelUnavailableError(detail="x")

    assert isinstance(error, VgaError)
    assert error.code == "image_model_unavailable"
    assert "x" not in str(error)  # the detail is for the log, never for the shopper
