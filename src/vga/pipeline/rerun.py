"""The re-run cache (plan 13.1.5): what a finished request keeps so a change can be cheap.

When a shopper changes only the price-range mix or the budget, the products found earlier are still
right: they only need re-scoring and re-shaping. This cache holds, for each recent request and each
of its items, the products the stores returned, the image scores and the per-store reports.

Rules
- In memory, per process, keyed by the request id (a re-run names it in ``rerun_of``). Nothing is
  written to disk.
- An entry is good for ``Settings.store_cache_ttl_s`` seconds on the injected ``Clock``, counted
  from when its oldest store answered. A re-run that reuses an entry does not renew it, so old
  products do not live longer by being re-shaped.
- It holds no photo (BRD Rule 4): products, numbers, store reports, and the image *embedding*
  (a vector of numbers, which plan assumption A8 allows to be kept for chip edits).
- Small and bounded: the oldest request goes first.

A shopper's answer to "Who is this for?" (or the gender chip) changes only a garment's gender. The
search made before it asked for no gender (a guessed one is never applied), so what the stores
returned already holds both audiences, and the answer can be applied to it here: the ranker drops
the other gender's products and the stores that do not sell for it are left out. That is
``reusable_after_gender`` and ``narrowed_to``. It costs no store request, no model call and no
thumbnail.
"""

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from vga.interfaces import Clock
from vga.models import ItemIntent, Product, StoreConfig, StoreReport, StoreStatus
from vga.pipeline import messages
from vga.understand import effective_gender

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
    """Clock time after which the products are too old to reuse. Counted from when the OLDEST
    store answered (not from when the pipeline finished waiting for the others). An answer that
    the store engine served from its own cache is counted from when it arrived here, so in that
    one case a product can be up to twice ``store_cache_ttl_s`` old."""
    image_done: bool = True
    """False when the photo could not be compared with these products (the model was missing, the
    comparison failed or was cut short by the deadline). A re-run that still has the photo's
    embedding then tries again instead of reusing "no image scores" as if it were the answer."""


@dataclass(frozen=True)
class CachedRun:
    items: dict[int, CachedItem] = field(default_factory=dict)
    """By item index. An item whose search did not finish is not here."""
    query_embedding: tuple[float, ...] | None = None


_GENDER_AND_WORDS = {"gender", "gender_source", "search_keywords"}
"""What a gender answer changes about an item: the gender, where it came from, and the keywords
rebuilt from the item's fields (they gain the gender word)."""


def same_garment(searched: ItemIntent, wanted: ItemIntent) -> bool:
    """Whether ``wanted`` is the very garment ``searched`` was, whatever the gender: the same
    category, colour, style and material. The keywords are not compared: they are made from those
    fields, and a gender answer rebuilds them."""
    return searched.model_dump(exclude=_GENDER_AND_WORDS) == wanted.model_dump(
        exclude=_GENDER_AND_WORDS
    )


def narrowed_to(
    cached: CachedItem,
    item: ItemIntent,
    searched: Sequence[StoreConfig],
    skipped: Sequence[StoreConfig],
) -> CachedItem:
    """``cached`` as it is for ``item``: the products of the stores that sell for its gender, and
    a plain "not searched" report for each store that was searched before and is now left out.
    Nothing else changes, least of all the expiry."""
    kept = {store.id for store in searched}
    names = {store.display_name for store in searched}
    products = tuple(product for product in cached.products if product.store in names)
    by_id = {store.id: store for store in skipped}
    gender = effective_gender(item)
    reports: list[StoreReport] = []
    for report in cached.reports:
        left_out = report.store_id in cached.searched_ids and report.store_id not in kept
        if left_out and gender is not None and report.store_id in by_id:
            reason = messages.store_not_for_gender(by_id[report.store_id], gender)
            report = StoreReport(store_id=report.store_id, status=StoreStatus.EMPTY, reason=reason)
        reports.append(report)
    return replace(
        cached,
        item=item,
        store_ids=tuple(store.id for store in searched),
        products=products,
        image_scores={
            product.key: cached.image_scores[product.key]
            for product in products
            if product.key in cached.image_scores
        },
        reports=tuple(reports),
        searched_ids=cached.searched_ids & kept,
    )


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

    def reusable_after_gender(
        self,
        run: CachedRun | None,
        index: int,
        item: ItemIntent,
        searched: Sequence[StoreConfig],
    ) -> CachedItem | None:
        """The cached search of item ``index`` when ``item`` is the same garment with a different
        gender answer, and the earlier search asked for no gender; else ``None`` (the caller
        searches again). ``searched`` are the stores that sell this item for its gender: every one
        must have been searched before, so nothing new has to be asked.

        An earlier search that DID apply a gender (the keywords carried it) is no basis for another:
        its stores only returned that gender's products.
        """
        if run is None:
            return None
        cached = run.items.get(index)
        if cached is None or cached.expires_at <= self._clock.monotonic():
            return None
        if effective_gender(cached.item) is not None or not same_garment(cached.item, item):
            return None
        if not {store.id for store in searched} <= set(cached.store_ids):
            return None
        return cached

    def __len__(self) -> int:
        return len(self._runs)
