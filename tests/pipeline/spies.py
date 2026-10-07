"""A spy around the REAL store engine: it forwards every call and remembers how it began.

Not a mock: the engine does all the work. The spy only records which item and which stores each
``search`` call was started with, in the order the calls began, which is the order a recording
of the run keeps them in.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from vga.interfaces import StoreSearcher
from vga.models import Category, ItemIntent, StoreConfig, StoreResult


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
