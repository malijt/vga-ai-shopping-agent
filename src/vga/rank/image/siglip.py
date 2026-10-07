"""The FashionSigLIP image ranker (plan 8.1.2, 8.1.3 and the scoring half of 8.3.2).

The image score is a low-weight nudge, never a filter, so this ranker never raises: if the model is
missing, a thumbnail cannot be read, or anything else goes wrong, the products it could not score
get ``None`` and the request carries on with text and price only. Every degradation is logged at
warn level; the request id is added by the logging context the pipeline sets up.

All model work sits behind the small ``ImageEmbedder`` protocol, so the orchestration here is
tested with a fake embedder and the real model is only needed for the ``slow`` tests.
"""

import asyncio
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from PIL import Image

from vga.errors import VgaError
from vga.log import get_logger, timed
from vga.models import Product, QueryImage
from vga.rank.image.imaging import UndecodableImageError, decode_rgb
from vga.rank.image.scoring import similarity_score
from vga.rank.image.selection import MAX_CANDIDATE_LIMIT, MAX_PER_STORE, select_candidates
from vga.rank.image.thumbnails import ImageFetcher, fetch_thumbnails

log = get_logger(__name__)

DEFAULT_BATCH_SIZE = 16
"""Images per forward pass: 16 was the fastest on the Apple GPU, 8 and 16 tie on the CPU."""


class ImageEmbedder(Protocol):
    """The model boundary: turns RGB images into one embedding each."""

    def embed(self, images: Sequence[Image.Image]) -> list[list[float]]:
        """One vector per image, in order. Called from a worker thread, not the event loop."""
        ...


EmbedderProvider = Callable[[], ImageEmbedder]
"""Returns the ready model, loading it on first use. Raises when the model is unavailable."""


class SiglipImageRanker:
    """Scores products by how visually similar their thumbnail is to the shopper's photo.

    ``embedder_provider`` yields the model (see ``model.get_embedder``); ``fetch_image`` downloads a
    product's thumbnail (Phase 6's guarded client). ``cos_lo`` and ``cos_hi`` map a cosine to 0-1
    (``Settings.siglip_cos_lo`` and ``siglip_cos_hi``). Products beyond ``max_candidates`` in total
    or ``max_per_store`` per store are not fetched and score ``None``; callers pass the best
    candidates first (see ``selection.select_candidates``).
    """

    def __init__(
        self,
        *,
        embedder_provider: EmbedderProvider,
        fetch_image: ImageFetcher,
        cos_lo: float,
        cos_hi: float,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_candidates: int = MAX_CANDIDATE_LIMIT,
        max_per_store: int = MAX_PER_STORE,
    ) -> None:
        if not cos_lo < cos_hi:
            msg = f"cos_lo ({cos_lo}) must be below cos_hi ({cos_hi})"
            raise ValueError(msg)
        if batch_size < 1:
            msg = f"batch_size must be at least 1, got {batch_size}"
            raise ValueError(msg)
        self._embedder_provider = embedder_provider
        self._fetch_image = fetch_image
        self._cos_lo = cos_lo
        self._cos_hi = cos_hi
        self._batch_size = batch_size
        self._max_candidates = max_candidates
        self._max_per_store = max_per_store

    async def warm_up(self) -> bool:
        """Load the model now, so the first request does not wait for it. ``True`` when it is
        ready, ``False`` (and a warn log) when image scoring is unavailable."""
        try:
            await asyncio.to_thread(self._embedder_provider)
        except Exception as exc:  # unavailable is a normal, degraded state
            _log_degraded(exc)
            return False
        return True

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        """Map ``Product.key`` to a 0-1 score, or ``None`` when a product cannot be scored.

        With no photo and no stored embedding, every score is ``None`` and nothing is loaded or
        fetched. When given the photo, its embedding is stored in ``query.embedding`` so a later
        call can pass ``QueryImage(image=None, embedding=...)`` and get the same ranking; a stored
        embedding is used in preference to the photo. The photo bytes are not kept.
        """
        scores = _no_scores(products)
        if not products or query is None or (not query.image and query.embedding is None):
            return scores
        with timed("image_rank") as step:
            try:
                scores.update(await self._score(query, products))
            except Exception as exc:  # image scoring must never fail the request (plan 8.3.2)
                step.status = "degraded"
                _log_degraded(exc)
                return _no_scores(products)
        return scores

    async def _score(
        self, query: QueryImage, products: Sequence[Product]
    ) -> dict[str, float | None]:
        # Loading the model comes first: when it is unavailable we find out before any download.
        embedder = await asyncio.to_thread(self._embedder_provider)
        query_vector = await self._query_vector(embedder, query)
        candidates = select_candidates(
            products, limit=self._max_candidates, per_store=self._max_per_store
        )
        thumbnails = await fetch_thumbnails(candidates, self._fetch_image)
        fetched = {key: data for key, data in thumbnails.items() if data is not None}
        vectors, undecodable = await asyncio.to_thread(self._embed_thumbnails, embedder, fetched)
        scores: dict[str, float | None] = {
            key: similarity_score(query_vector, vector, lo=self._cos_lo, hi=self._cos_hi)
            for key, vector in vectors.items()
        }
        log.info(
            "image scores computed",
            extra={
                "products": len(products),
                "candidates": len(candidates),
                "fetched": len(fetched),
                "undecodable": undecodable,
                "scored": sum(score is not None for score in scores.values()),
            },
        )
        return scores

    async def _query_vector(self, embedder: ImageEmbedder, query: QueryImage) -> list[float]:
        """The query embedding: the stored one, or computed from the photo and stored."""
        if query.embedding is not None:
            return _usable_vector(list(query.embedding))
        if not query.image:  # score() has checked this; kept for the type checker and for safety
            msg = "no photo and no embedding"
            raise ValueError(msg)
        vector = _usable_vector(await asyncio.to_thread(_embed_photo, embedder, query.image))
        query.embedding = list(vector)
        return vector

    def _embed_thumbnails(
        self, embedder: ImageEmbedder, thumbnails: Mapping[str, bytes]
    ) -> tuple[dict[str, list[float]], int]:
        """Decode and embed thumbnails in batches. Returns ``({key: vector}, undecodable count)``.
        Runs in a worker thread. Decoding one batch at a time bounds the memory in use."""
        keys = list(thumbnails)
        vectors: dict[str, list[float]] = {}
        undecodable = 0
        for start in range(0, len(keys), self._batch_size):
            batch_keys: list[str] = []
            batch_images: list[Image.Image] = []
            for key in keys[start : start + self._batch_size]:
                try:
                    batch_images.append(decode_rgb(thumbnails[key]))
                except UndecodableImageError:
                    undecodable += 1
                else:
                    batch_keys.append(key)
            if not batch_images:
                continue
            rows = embedder.embed(batch_images)
            if len(rows) != len(batch_images):
                msg = f"the model returned {len(rows)} embeddings for {len(batch_images)} images"
                raise RuntimeError(msg)
            vectors.update(zip(batch_keys, rows, strict=True))
        return vectors, undecodable


def _embed_photo(embedder: ImageEmbedder, photo: bytes) -> list[float]:
    """Embedding of the shopper's photo. Runs in a worker thread."""
    return embedder.embed([decode_rgb(photo)])[0]


def _usable_vector(vector: list[float]) -> list[float]:
    """The vector, if it can be compared; a ``ValueError`` when it is empty or not finite."""
    if not vector or not all(math.isfinite(value) for value in vector):
        msg = "the query embedding is empty or not finite"
        raise ValueError(msg)
    return vector


def _no_scores(products: Sequence[Product]) -> dict[str, float | None]:
    return {product.key: None for product in products}


def _log_degraded(exc: Exception) -> None:
    """Warn that image scoring is off for this request. The request id is stamped by the logger."""
    if isinstance(exc, VgaError):
        reason, detail = exc.code, exc.detail
    else:
        reason, detail = type(exc).__name__, str(exc)
    log.warning(
        "image scoring unavailable; ranking without image scores",
        extra={"reason": reason, "detail": detail},
        exc_info=None if isinstance(exc, VgaError | UndecodableImageError) else exc,
    )
