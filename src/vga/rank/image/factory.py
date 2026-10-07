"""Choosing the image ranker from the settings (plan 8.3.2)."""

from functools import partial

from vga.interfaces import ImageRanker
from vga.rank.image.model import get_embedder
from vga.rank.image.off import OffImageRanker
from vga.rank.image.siglip import SiglipImageRanker
from vga.rank.image.thumbnails import ImageFetcher
from vga.settings import Settings


def create_image_ranker(settings: Settings, *, fetch_image: ImageFetcher) -> ImageRanker:
    """The ranker ``settings.image_ranker`` selects: ``siglip`` or ``off``.

    ``fetch_image`` downloads one product's thumbnail (Phase 6's client: allow-listed hosts, rate
    limit, timeout and size cap); the ``off`` ranker never calls it.

    A ``siglip`` ranker loads its model on first use, from the local cache only. If the ``ml``
    packages or the pinned weights are missing, the revision is not pinned, or anything else goes
    wrong, it returns ``None`` for every product, logs a warning (with the request id) and does not
    raise, so the request carries on with text and price only.
    """
    if settings.image_ranker == "off":
        return OffImageRanker()
    return SiglipImageRanker(
        embedder_provider=partial(get_embedder, settings.siglip_revision),
        fetch_image=fetch_image,
        cos_lo=settings.siglip_cos_lo,
        cos_hi=settings.siglip_cos_hi,
    )
