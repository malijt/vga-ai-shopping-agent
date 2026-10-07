"""The re-run cache (plan 13.1.5): what a finished request keeps so a change can be cheap.

When a shopper changes only the price-range mix or the budget, the products found earlier are still
right: they only need re-scoring and re-shaping. This cache holds, for each recent request and each
of its items, the products the stores returned, the image scores and the per-store reports.

Rules
- In memory, per process, keyed by the request id (a re-run names it in ``rerun_of``). Nothing is
  written to disk.
- An entry is good for ``Settings.store_cache_ttl_s`` seconds on the injected ``Clock``, counted
  from when its stores were really asked. A re-run that reuses an entry does not renew it, so old
  products never live longer than the stores' own cache would let them.
- It holds no photo (BRD Rule 4): products, numbers, store reports, and the image *embedding*
  (a vector of numbers, which plan assumption A8 allows to be kept for chip edits).
- Small and bounded: the oldest request goes first.
"""

from collections import OrderedDict
from dataclasses import dataclass, field

from vga.interfaces import Clock
from vga.models import ItemIntent, Product, StoreReport

MAX_REQUESTS = 32
"""A long-running process must not grow without bound."""


@dataclass(frozen=True)
class CachedItem:
    """What searching for one item produced, and what it was searched with."""

    item: ItemIntent
    """The item exactly as it was searched (keywords included): the key of a reuse."""
    store_ids: tuple[str, ...]
    """The stores that were searched for it."""
    products: tuple[Product, ...]
    """Every product the stores returned, before any filter, in store order."""
    image_scores: dict[str, float | None]
    """Image score per ``Product.key`` (empty when there was no photo or no scoring)."""
    reports: tuple[StoreReport, ...]
    """One report per active store for this item."""
    searched_ids: frozenset[str]
    """Which of those stores were really searched (the others were skipped for their gender)."""
    expires_at: float
    """Clock time after which the products are too old to reuse."""


@dataclass(frozen=True)
class CachedRun:
    items: dict[int, CachedItem] = field(default_factory=dict)
    """By item index. An item whose search did not finish is not here."""
    query_embedding: tuple[float, ...] | None = None


class RerunCache:
    def __init__(self, clock: Clock, max_requests: int = MAX_REQUESTS) -> None:
        self._clock = clock
        self._max = max_requests
        self._runs: OrderedDict[str, CachedRun] = OrderedDict()

    def put(self, request_id: str, run: CachedRun) -> None:
        self._runs.pop(request_id, None)
        self._runs[request_id] = run
        while len(self._runs) > self._max:
            self._runs.popitem(last=False)

    def get(self, request_id: str | None) -> CachedRun | None:
        """The cached request, or ``None`` when it is unknown. Expired items are not removed here:
        ``reusable`` checks each one, and the whole entry ages out with the cap."""
        if request_id is None:
            return None
        return self._runs.get(request_id)

    def reusable(
        self,
        run: CachedRun | None,
        index: int,
        item: ItemIntent,
        store_ids: tuple[str, ...],
    ) -> CachedItem | None:
        """The cached search of item ``index`` when it was made for this very item and these very
        stores and has not expired; else ``None`` (the caller searches again)."""
        if run is None:
            return None
        cached = run.items.get(index)
        if cached is None or cached.expires_at <= self._clock.monotonic():
            return None
        if cached.item != item or cached.store_ids != store_ids:
            return None
        return cached

    def __len__(self) -> int:
        return len(self._runs)
