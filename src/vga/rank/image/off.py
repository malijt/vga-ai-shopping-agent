"""The ``off`` image ranker (plan 8.3.1): no image scores at all."""

from collections.abc import Sequence

from vga.models import Product, QueryImage


class OffImageRanker:
    """Returns ``None`` for every product and does no work: no model, no thumbnail fetch.

    It is what ``Settings.image_ranker == "off"`` selects, so the pipeline ranks by text and price
    only. It does not store a query embedding.
    """

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        return {product.key: None for product in products}
