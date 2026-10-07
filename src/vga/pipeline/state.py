"""What one run knows while it is running.

A run is a ``RunState`` (the request-wide facts) with one ``ItemRun`` per garment. The stages in
``pipeline.py`` fill the item runs in. Keeping the partial results here, outside the stages, is what
lets the deadline stop a stage half-way and still return what was ranked so far.

Nothing here is shared between runs: the only thing a pipeline keeps from one run to the next is the
re-run cache.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from vga.models import (
    Budget,
    GarmentGroup,
    ItemIntent,
    Product,
    QueryImage,
    ScoredProduct,
    SearchRequest,
    Step,
    StepTiming,
    StoreConfig,
    StoreResult,
    UnderstandResult,
    Usage,
)
from vga.pipeline.rerun import CachedItem, CachedRun
from vga.settings import Settings


@dataclass
class ItemRun:
    """One garment on its way from "what to look for" to "four price ranges"."""

    index: int
    item: ItemIntent
    """What is searched for: the understood item, with at most 2 keywords for an outfit."""
    stores: list[StoreConfig]
    """The stores asked for it: those that sell its category and sell for its stated gender."""
    skipped: list[StoreConfig]
    """Active stores that were left out because they do not sell the item's category or do not
    sell for its stated gender. No request is made to them for it."""
    cached: CachedItem | None = None
    """The earlier search of this very item, when it can be reused (a mix or budget change)."""

    tasks: dict[str, asyncio.Task[list[StoreResult]]] = field(default_factory=dict)
    """One running search per store, by store id, in the order the stores are searched."""
    store_results: dict[str, StoreResult] = field(default_factory=dict)
    """What each store gave, as it finished. A store missing here had not answered yet."""
    answered_at: dict[str, float] = field(default_factory=dict)
    """When each store's search came back, on the pipeline's clock."""
    fetched_expires_at: float | None = None
    """When the products found for this item are too old to reuse."""

    products: list[Product] = field(default_factory=list)
    scored: list[ScoredProduct] | None = None
    """Filtered, with text and price scores. ``None`` until the filter step ran."""
    candidates: list[Product] = field(default_factory=list)
    """The best matches, chosen to be compared with the photo."""
    image_scores: dict[str, float | None] = field(default_factory=dict)
    image_asked: bool = False
    image_scored: bool = False
    """The image ranker came back (with scores or without), so the comparison was not cut short."""
    image_failed: bool = False
    ranked: list[ScoredProduct] | None = None
    group: GarmentGroup | None = None

    @property
    def results(self) -> list[StoreResult]:
        """The results received so far, in the order of ``stores``."""
        return [self.store_results[s.id] for s in self.stores if s.id in self.store_results]

    @property
    def search_complete(self) -> bool:
        """Every store asked for this item has answered (or there was none to ask)."""
        return all(store.id in self.store_results for store in self.stores)


@dataclass
class RunState:
    req: SearchRequest
    settings: Settings
    """The settings for this run: the sidebar's mix applied, and "cheaper" handled."""
    started: float
    on_step: Callable[[Step], None] | None = None
    active_stores: list[StoreConfig] = field(default_factory=list)
    previous: CachedRun | None = None
    """The cache entry of the request being re-run, if any."""

    understood: UnderstandResult | None = None
    reused_understanding: bool = False
    usage: Usage = field(default_factory=Usage)
    budget: Budget | None = None
    items: list[ItemRun] = field(default_factory=list)
    compares_images: bool = True
    """Whether the products are compared with the shopper's photo in this run. False for an outfit
    photo (also on a re-run): it is searched garment by garment, with no thumbnail fetched, no
    photo embedded and no image score applied. Not a failure, so it raises no warning."""
    query: QueryImage | None = None
    query_embedding: list[float] | None = None

    timings: list[StepTiming] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timed_out: bool = False

    def warn(self, message: str) -> None:
        """Add a shopper-facing note once."""
        if message not in self.warnings:
            self.warnings.append(message)
