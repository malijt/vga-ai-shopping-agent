"""Image-similarity ranker: ``siglip`` or ``off`` behind the ``ImageRanker`` protocol (Phase 8).

Typical use::

    from vga.rank.image import create_image_ranker, select_candidates

    ranker = create_image_ranker(settings, fetch_image=fetch_thumbnail)  # Phase 6's fetcher
    candidates = select_candidates(products_best_first)                  # top 40, 10 per store
    scores = await ranker.score(query_image, candidates)       # {product.key: 0-1 or None}

The image score is a low-weight nudge, never a filter. It degrades to ``None`` for every product
when the model is unavailable. The optional ``ml`` dependency group (torch, open_clip) is imported
lazily, so importing this package needs none of it. One-time setup, about 816 MB::

    uv sync --group ml
    uv run --group ml python -m vga.rank.image.download
"""

from vga.rank.image.factory import create_image_ranker
from vga.rank.image.model import ImageModelUnavailableError, get_embedder
from vga.rank.image.off import OffImageRanker
from vga.rank.image.selection import select_candidates
from vga.rank.image.siglip import SiglipImageRanker
from vga.rank.image.thumbnails import ImageFetcher

__all__ = [
    "ImageFetcher",
    "ImageModelUnavailableError",
    "OffImageRanker",
    "SiglipImageRanker",
    "create_image_ranker",
    "get_embedder",
    "select_candidates",
]
