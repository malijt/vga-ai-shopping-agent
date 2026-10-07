"""In-memory result cache (plan 6.5.3): one ``StoreResult`` per store and query variant.

Per process, nothing on disk. An entry lives ``Settings.store_cache_ttl_s`` seconds on the injected
``Clock``; a hit makes no request to the store and comes back with ``from_cache=True``. Only
results that say something true about the store are kept (``ok`` and ``empty``): a timeout, an
error, a block or a robots refusal is never replayed as if it were an answer.
"""

import unicodedata

from vga.interfaces import Clock
from vga.models import StoreResult, StoreStatus

MAX_ENTRIES = 256
"""A long-running process must not grow without bound; the oldest entry goes first."""

_CACHEABLE = frozenset({StoreStatus.OK, StoreStatus.EMPTY})


def variant_key(variant: str) -> str:
    """A query variant as used for caching: ``"Black  Blazer"`` and ``"black blazer"`` are the
    same search."""
    return " ".join(unicodedata.normalize("NFKC", variant).casefold().split())


class ResultCache:
    def __init__(self, clock: Clock, ttl_s: float, max_entries: int = MAX_ENTRIES) -> None:
        self._clock = clock
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._entries: dict[tuple[str, str], tuple[float, StoreResult]] = {}

    def get(self, store_id: str, variant: str) -> StoreResult | None:
        """The cached result with ``from_cache=True``, or ``None`` when there is none or it
        expired."""
        key = (store_id, variant_key(variant))
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if expires_at <= self._clock.monotonic():
            del self._entries[key]
            return None
        return result.model_copy(update={"from_cache": True})

    def put(self, store_id: str, variant: str, result: StoreResult) -> None:
        """Remember ``result`` (if it is cacheable and the TTL is not zero)."""
        if self._ttl_s <= 0 or result.status not in _CACHEABLE:
            return
        key = (store_id, variant_key(variant))
        self._entries.pop(key, None)  # re-insert at the end: newest last
        self._entries[key] = (
            self._clock.monotonic() + self._ttl_s,
            result.model_copy(update={"from_cache": False}),
        )
        while len(self._entries) > self._max_entries:
            del self._entries[next(iter(self._entries))]

    def __len__(self) -> int:
        return len(self._entries)
