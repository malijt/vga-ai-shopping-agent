"""The real FashionSigLIP model at the pinned revision (marked `slow`).

Skipped automatically when `torch` / `open_clip` are not installed (`uv sync --group ml`) or when
the weights are not in the local Hugging Face cache (`uv run --group ml python -m
vga.rank.image.download`). Run them with `uv run pytest -m slow`. Nothing here touches the network:
the weights come from the local cache and every picture is drawn with Pillow.
"""

import asyncio
import importlib.util
import logging
import math
import socket
import sys
import time
from itertools import pairwise
from typing import Any, NoReturn

import pytest

from tests.factories import make_product
from tests.rank_image import pictures
from tests.rank_image.support import FakeThumbnails
from vga.models import QueryImage
from vga.rank.image.imaging import decode_rgb
from vga.rank.image.model import (
    DOWNLOAD_COMMAND,
    ImageModelUnavailableError,
    SiglipEmbedder,
    build_embedder,
    clear_embedder_cache,
    get_embedder,
    resolve_snapshot,
)
from vga.rank.image.scoring import cosine
from vga.rank.image.siglip import SiglipImageRanker
from vga.settings import Settings, load_settings

pytestmark = pytest.mark.slow

DARK_BLUE = (20, 20, 60)
RED = (200, 30, 30)
BLUE = (30, 30, 200)


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings(env={})  # config/settings.yaml pins the revision the spike measured


@pytest.fixture(scope="module")
def revision(settings: Settings) -> str:
    for package in ("torch", "open_clip"):
        if importlib.util.find_spec(package) is None:
            pytest.skip(f"{package} is not installed; run `uv sync --group ml`")
    assert settings.siglip_revision, "config/settings.yaml must pin siglip_revision"
    try:
        resolve_snapshot(settings.siglip_revision, download=False)
    except ImageModelUnavailableError:
        pytest.skip(f"the model weights are not downloaded; run `{DOWNLOAD_COMMAND}`")
    return str(settings.siglip_revision)


@pytest.fixture
def embedder(revision: str) -> SiglipEmbedder:
    return get_embedder(revision)


def make_ranker(embedder: SiglipEmbedder, settings: Settings, fetch: Any, **options: Any) -> Any:
    return SiglipImageRanker(
        embedder_provider=lambda: embedder,
        fetch_image=fetch,
        cos_lo=options.pop("cos_lo", settings.siglip_cos_lo),
        cos_hi=options.pop("cos_hi", settings.siglip_cos_hi),
        **options,
    )


def embed_one(embedder: SiglipEmbedder, data: bytes) -> list[float]:
    return embedder.embed([decode_rgb(data)])[0]


def block_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> NoReturn:
        msg = "the model loader tried to use the network"
        raise AssertionError(msg)

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


async def test_the_pinned_model_loads_offline_without_transformers(
    revision: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clear_embedder_cache()
    block_the_network(monkeypatch)
    for blocked in ("transformers", "tokenizers"):
        monkeypatch.setitem(sys.modules, blocked, None)  # `import transformers` now raises

    with caplog.at_level(logging.INFO, logger="vga"):
        first = get_embedder(revision)
        second = get_embedder(revision)

    assert first is second  # the second call does not reload
    assert first.revision == revision
    assert first.device in {"cuda", "mps", "cpu"}
    vector = embed_one(first, pictures.to_jpeg(pictures.tee(RED)))
    assert len(vector) == 768
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-4)
    (loaded,) = [r for r in caplog.records if r.getMessage() == "image model loaded"]
    assert loaded.revision == revision  # type: ignore[attr-defined]
    assert loaded.device == first.device  # type: ignore[attr-defined]


async def test_an_image_scores_near_one_against_itself(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    picture = pictures.to_jpeg(pictures.tee(RED))
    product = make_product(1)
    ranker = make_ranker(embedder, settings, FakeThumbnails({product.key: picture}))

    scores = await ranker.score(QueryImage(image=picture), [product])

    assert scores[product.key] == pytest.approx(1.0, abs=1e-3)


async def test_an_unrelated_image_scores_clearly_lower(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    same, unrelated = make_product(1), make_product(2)
    thumbnails = FakeThumbnails(
        {
            same.key: pictures.to_jpeg(pictures.tee(RED)),
            unrelated.key: pictures.to_jpeg(pictures.checkerboard()),
        }
    )
    ranker = make_ranker(embedder, settings, thumbnails)

    scores = await ranker.score(
        QueryImage(image=pictures.to_jpeg(pictures.tee(RED))), [same, unrelated]
    )

    same_score, unrelated_score = scores[same.key], scores[unrelated.key]
    assert same_score is not None
    assert unrelated_score is not None
    assert same_score > 0.99
    assert unrelated_score < 0.6
    assert same_score - unrelated_score > 0.4


async def test_the_most_similar_products_rank_first(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    other_tee, rings, checkerboard = make_product(1), make_product(2), make_product(3)
    thumbnails = FakeThumbnails(
        {
            other_tee.key: pictures.to_jpeg(pictures.tee(BLUE)),
            rings.key: pictures.to_jpeg(pictures.rings()),
            checkerboard.key: pictures.to_jpeg(pictures.checkerboard()),
        }
    )
    ranker = make_ranker(embedder, settings, thumbnails)

    scores = await ranker.score(
        QueryImage(image=pictures.to_jpeg(pictures.tee(RED))), [checkerboard, rings, other_tee]
    )

    ranked = sorted(scores, key=lambda key: scores[key] or 0.0, reverse=True)
    assert ranked[0] == other_tee.key


async def test_a_transparent_png_is_not_turned_black(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    cut_out = pictures.tee(DARK_BLUE, transparent=True)
    on_white = pictures.to_png(pictures.flatten(cut_out, (255, 255, 255)))
    on_black = pictures.to_png(pictures.flatten(cut_out, (0, 0, 0)))
    transparent = pictures.to_png(cut_out)

    from_transparent = embed_one(embedder, transparent)

    # The dark garment is invisible on black, so a PNG turned black would not match the white
    # version. Decoded as intended, the transparent PNG is the white version, pixel for pixel.
    assert cosine(from_transparent, embed_one(embedder, on_white)) == pytest.approx(1.0, abs=1e-4)
    assert cosine(from_transparent, embed_one(embedder, on_black)) < 0.98

    # The same through the ranker, with bounds tight enough not to saturate.
    kept, blackened = make_product(1), make_product(2)
    thumbnails = FakeThumbnails({kept.key: transparent, blackened.key: on_black})
    ranker = make_ranker(embedder, settings, thumbnails, cos_lo=0.98, cos_hi=1.0)
    scores = await ranker.score(QueryImage(image=on_white), [kept, blackened])
    assert scores[kept.key] == pytest.approx(1.0, abs=1e-2)
    assert scores[blackened.key] == pytest.approx(0.0, abs=1e-6)


async def test_a_stored_embedding_gives_the_same_scores_as_the_photo(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    drawn = {
        "tee": pictures.tee(RED),
        "checkerboard": pictures.checkerboard(),
        "rings": pictures.rings(),
    }
    products = {name: make_product(i) for i, name in enumerate(drawn, start=1)}
    thumbnails = FakeThumbnails(
        {products[name].key: pictures.to_jpeg(image) for name, image in drawn.items()}
    )
    ranker = make_ranker(embedder, settings, thumbnails)
    query = QueryImage(image=pictures.to_jpeg(pictures.rings()))
    candidates = list(products.values())

    with_photo = await ranker.score(query, candidates)
    from_embedding = await ranker.score(
        QueryImage(image=None, embedding=query.embedding), candidates
    )

    assert query.embedding is not None
    assert len(query.embedding) == 768
    assert from_embedding == pytest.approx(with_photo, abs=1e-6)
    assert max(with_photo, key=lambda key: with_photo[key] or 0.0) == products["rings"].key


async def test_forty_thumbnails_are_scored_in_under_three_seconds(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    products = [make_product(i, store=f"Store {i % 4}") for i in range(1, 41)]
    pictures_by_key = {
        p.key: pictures.to_jpeg(pictures.thumbnail(i)) for i, p in enumerate(products)
    }
    ranker = make_ranker(embedder, settings, FakeThumbnails(pictures_by_key))
    query_photo = pictures.to_jpeg(pictures.thumbnail(999))

    durations: list[float] = []
    for _ in range(3):
        started = time.perf_counter()
        scores = await ranker.score(QueryImage(image=query_photo), products)
        durations.append(time.perf_counter() - started)

    print(
        f"\n40 thumbnails scored in {', '.join(f'{d:.2f}' for d in durations)} s "
        f"(three runs, first is cold) on {embedder.device}"
    )
    assert sum(score is not None for score in scores.values()) == 40
    assert max(durations) < 3.0


async def test_scoring_does_not_block_the_event_loop(
    embedder: SiglipEmbedder, settings: Settings
) -> None:
    products = [make_product(i, store=f"Store {i % 4}") for i in range(1, 41)]
    pictures_by_key = {
        p.key: pictures.to_jpeg(pictures.thumbnail(i)) for i, p in enumerate(products)
    }
    ranker = make_ranker(embedder, settings, FakeThumbnails(pictures_by_key))
    ticks: list[float] = []

    async def heartbeat() -> None:
        while True:
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.02)

    beat = asyncio.create_task(heartbeat())
    await ranker.score(QueryImage(image=pictures.to_jpeg(pictures.thumbnail(999))), products)
    beat.cancel()

    gaps = [later - earlier for earlier, later in pairwise(ticks)]
    assert gaps, "the event loop never ran while the model was working"
    assert max(gaps) < 0.25


async def test_the_cpu_fallback_gives_the_same_embeddings_and_is_fast_enough(
    embedder: SiglipEmbedder, settings: Settings, revision: str
) -> None:
    cpu = build_embedder(revision, device="cpu")
    picture = pictures.to_jpeg(pictures.tee(RED))
    products = [make_product(i, store=f"Store {i % 4}") for i in range(1, 41)]
    pictures_by_key = {
        p.key: pictures.to_jpeg(pictures.thumbnail(i)) for i, p in enumerate(products)
    }
    ranker = make_ranker(cpu, settings, FakeThumbnails(pictures_by_key))

    started = time.perf_counter()
    scores = await ranker.score(QueryImage(image=picture), products)
    elapsed = time.perf_counter() - started

    print(f"\n40 thumbnails scored in {elapsed:.2f} s on cpu (default device is {embedder.device})")
    assert cpu.device == "cpu"
    assert cosine(embed_one(cpu, picture), embed_one(embedder, picture)) == pytest.approx(
        1.0, abs=1e-4
    )  # one set of cos_lo / cos_hi serves every device
    assert sum(score is not None for score in scores.values()) == 40
    assert elapsed < 3.0
