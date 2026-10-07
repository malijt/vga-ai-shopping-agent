"""Small interfaces between the modules (Dependency Inversion).

Code depends on these ``Protocol`` classes, never on the OpenAI SDK, ``httpx`` or ``open_clip``
directly, so tests can swap in the fakes from ``tests/fakes.py``. The fakes and the real
implementations must pass the same contract suites in ``tests/foundation/contracts.py``.

Frozen after Phase 1, like ``models.py`` and ``errors.py``.
"""

import asyncio
import time
from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

from vga.models import (
    ItemIntent,
    Product,
    QueryImage,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    Step,
    StoreConfig,
    StoreResult,
    UnderstandResult,
)
from vga.settings import Settings

StepCallback = Callable[[Step], None]
"""Called with each ``Step`` as the pipeline starts it, so the UI can show progress."""


@runtime_checkable
class Clock(Protocol):
    """Time source that tests can replace, so rate limits, cache expiry, backoff and deadlines
    are tested without real waiting. Anything that waits or measures time takes a ``Clock``."""

    def monotonic(self) -> float:
        """Seconds on a clock that only moves forward. Differences are durations."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Wait for ``seconds`` (zero or negative returns at once)."""
        ...


class SystemClock:
    """The real clock."""

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


@runtime_checkable
class Understander(Protocol):
    """Turns a photo and/or text into what to search for (PRD R2)."""

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        """Raise ``LlmError`` / ``CallBudgetExceededError`` when no usable result can be made and
        no fallback applies. Never raises for a bad model answer that a fallback can cover."""
        ...


@runtime_checkable
class StoreSearcher(Protocol):
    """Searches the given stores for one item, in parallel, and never lets one store break
    another (PRD R5)."""

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        """Return exactly one ``StoreResult`` per store, in the order of ``stores``. A store that
        fails, times out or is blocked yields a result with that status, not an exception."""
        ...


@runtime_checkable
class ImageRanker(Protocol):
    """Scores how visually similar products are to the shopper's photo."""

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        """Map ``Product.key`` to a 0-1 score, or ``None`` when a product cannot be scored.

        Every product gets an entry. With ``query=None`` (no photo) every score is ``None``. May
        store the query embedding in ``query.embedding`` so a later call can pass ``image=None``.
        Failures must not raise: return all ``None`` instead (plan 8.3.2).
        """
        ...


@runtime_checkable
class Pipeline(Protocol):
    """The whole search, from request to response."""

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: StepCallback | None = None,
    ) -> SearchResponse:
        """Validate the request, understand it, search, rank, shape and assemble the response.
        Raises a ``VgaError`` for input that cannot be searched; degrades everything else."""
        ...
