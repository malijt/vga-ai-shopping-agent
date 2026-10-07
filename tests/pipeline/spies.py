"""A spy around the REAL store engine: it forwards every call and remembers how it began.

Not a mock: the engine does all the work. The spy only records which item and which stores each
``search`` call was started with, in the order the calls began, which is the order a recording
of the run keeps them in.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from vga.interfaces import ImageRanker, StoreSearcher
from vga.models import Category, ItemIntent, Product, QueryImage, StoreConfig, StoreResult


@dataclass(frozen=True)
class SearchCall:
    category: Category
    keywords: tuple[str, ...]
    store_ids: tuple[str, ...]


class SpySearcher:
    def __init__(self, inner: StoreSearcher) -> None:
        self._inner = inner
        self.calls: list[SearchCall] = []

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        self.calls.append(
            SearchCall(item.category, tuple(item.search_keywords), tuple(s.id for s in stores))
        )
        return await self._inner.search(item, stores)


@dataclass(frozen=True)
class RankerCall:
    had_photo: bool
    had_embedding: bool
    products: int


class SpyImageRanker:
    """Forwards to a real ranker and records what each ``score`` call was given: a photo, an
    embedding, or neither, at the moment of the call (the ranker later stores the embedding on the
    query and the pipeline clears the photo)."""

    def __init__(self, inner: ImageRanker) -> None:
        self._inner = inner
        self.calls: list[RankerCall] = []

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        self.calls.append(
            RankerCall(
                had_photo=query is not None and query.image is not None,
                had_embedding=query is not None and query.embedding is not None,
                products=len(products),
            )
        )
        return await self._inner.score(query, products)
