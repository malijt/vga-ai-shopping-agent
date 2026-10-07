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
    StoreReport,
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
    """The stores asked for it: those that sell for the item's stated gender."""
    gender_skipped: list[StoreConfig]
    """Active stores that were left out because they do not sell for the item's gender."""
    cached: CachedItem | None = None
    """The earlier search of this very item, when it can be reused (a mix or budget change)."""

    task: "asyncio.Task[list[StoreResult]] | None" = None
    results: list[StoreResult] | None = None
    """One result per store in ``stores``, or ``None`` while the search has not finished."""
    search_crashed: bool = False
    fetched_expires_at: float | None = None
    """When the products found for this item are too old to reuse."""

    products: list[Product] = field(default_factory=list)
    scored: list[ScoredProduct] | None = None
    """Filtered, with text and price scores. ``None`` until the filter step ran."""
    candidates: list[Product] = field(default_factory=list)
    """The best matches, chosen to be compared with the photo."""
    image_scores: dict[str, float | None] = field(default_factory=dict)
    image_asked: bool = False
    image_failed: bool = False
    ranked: list[ScoredProduct] | None = None
    group: GarmentGroup | None = None

    @property
    def search_done(self) -> bool:
        return self.cached is not None or self.results is not None


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
    query: QueryImage | None = None
    query_embedding: list[float] | None = None

    timings: list[StepTiming] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reports: list[StoreReport] = field(default_factory=list)
    timed_out: bool = False

    def warn(self, message: str) -> None:
        """Add a shopper-facing note once."""
        if message not in self.warnings:
            self.warnings.append(message)
