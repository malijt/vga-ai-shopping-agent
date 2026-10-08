"""Fetching product thumbnails for scoring (plan 8.2.1): orchestration only.

This module makes no HTTP request. It is handed a ``fetch_image`` function (Phase 6 supplies it)
that already enforces https, the store's allowed hosts, the per-host rate limit, the 4 s timeout
and the size cap, and returns ``None`` when it cannot or will not fetch. Here the products are
fetched concurrently and every failure becomes "no thumbnail". Bytes live in memory only.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from vga.log import get_logger
from vga.models import Product

log = get_logger(__name__)

ImageFetcher = Callable[[Product], Awaitable[bytes | None]]
"""Downloads one product's thumbnail: the image bytes, or ``None`` when it could not be fetched
(off-list host, timeout, too large, HTTP error). It must enforce its own timeout."""


async def fetch_thumbnails(
    products: Sequence[Product], fetch_image: ImageFetcher
) -> dict[str, bytes | None]:
    """Fetch every product's thumbnail at the same time; ``{Product.key: bytes or None}``.

    All requests start together and are paced by the fetcher's own per-host rate limit, so slow
    stores overlap instead of queueing behind each other (a global concurrency limit here would
    let one store's rate-limit waits starve the others). An exception from the fetcher counts as
    a failed thumbnail and is logged once; it never reaches the caller.
    """
    failures: list[str] = []

    async def fetch_one(product: Product) -> bytes | None:
        try:
            data = await fetch_image(product)
        except Exception as exc:  # the fetcher is a boundary: its failure is one missing score
            failures.append(type(exc).__name__)
            return None
        return data or None

    results = await asyncio.gather(*(fetch_one(product) for product in products))
    if failures:
        log.warning(
            "some thumbnail fetches raised instead of returning None",
            extra={
                "failed": len(failures),
                "total": len(products),
                "error_types": sorted(set(failures)),
            },
        )
    return {product.key: data for product, data in zip(products, results, strict=True)}
