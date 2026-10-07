"""Rate limiter and per-key cooldowns (plan 6.1.3 and 6.1.4), both on the injected ``Clock``.

``RateLimiter`` hands out send times. A request that asks for a slot is given the earliest time at
which it may go, and waits until then; the first request under a key goes at once and every later
one is spaced ``1 / rps`` seconds after the one before, however many tasks ask at the same time. N
requests therefore take at least ``(N - 1) / rps`` seconds, and a slow key never delays another,
because each key has its own bucket. The key is chosen by the caller: ``PoliteClient.contact_key``
gives a store's whole site one key, so the bare domain and ``www.`` share one queue (BRD Rule 2 is
per store), and a separate image CDN its own.

A key can also belong to a **shared limit**: every key that names the same one is spaced
``1 / rps`` apart from every other, whichever store it is. That is how the stores of one hosted
platform share a queue (``vga.fetch.platform``): thirteen shops behind one platform were all turned
away within 11 milliseconds of each other, so the limit that matters is the platform's, not the
shop's. A request takes a slot that satisfies both limits at once, so neither is ever broken, and
slots are given out in the order they are asked for, so every store gets its first request out
before any store gets its second. A request that cannot go yet because its own store is not ready
does not hold the shared queue up: later requests may take the free slots before it.

``Cooldowns`` remembers which stores or image hosts turned an honest request away and for
how long they must be left alone.
"""

import asyncio
import bisect
from collections.abc import Callable
from dataclasses import dataclass

from vga.fetch.deadline import waiting_in_queue
from vga.interfaces import Clock

_EPSILON = 1e-9
"""Float slack when comparing two send times, so 0.1 + 0.4 is not 'too close' to 0.5."""


@dataclass(frozen=True)
class SharedLimit:
    """A limit shared by several keys: its name, and the requests per second it allows in all."""

    name: str
    rps: float


class RateLimiter:
    """Spaces requests under one key, and under the shared limit the key belongs to, if any.

    ``group_of`` says which shared limit a key belongs to (``None`` for none). It is asked at every
    ``acquire``, so a key can join a limit as soon as the caller learns of it.
    """

    def __init__(
        self, clock: Clock, *, group_of: Callable[[str], SharedLimit | None] | None = None
    ) -> None:
        self._clock = clock
        self._group_of = group_of
        self._next_free: dict[str, float] = {}
        self._min_interval: dict[str, dict[str, float]] = {}
        self._taken: dict[str, list[float]] = {}
        """Send times already handed out under each shared limit, in ascending order."""

    def set_min_interval(self, key: str, seconds: float, *, source: str | None = None) -> None:
        """Never go faster than one request per ``seconds`` under ``key`` (a robots.txt
        ``Crawl-delay``). It can only slow a key down, never speed it up.

        ``source`` is who asked for the delay: several hosts share a key when they belong to one
        store, each with its own robots.txt, and the longest delay asked for wins. A source can
        change its own delay (its robots.txt was read again) but never lowers another's. It
        defaults to the key itself.
        """
        self._min_interval.setdefault(key, {})[source or key] = max(seconds, 0.0)

    async def acquire(self, key: str, rps: float) -> float:
        """Wait for this key's next free slot. Returns how long the caller waited, in seconds.

        A request cancelled while it waits (the deadline) gives its slot back.
        """
        interval = max([1.0 / rps, *self._min_interval.get(key, {}).values()])
        now = self._clock.monotonic()
        shared = self._group_of(key) if self._group_of is not None else None
        # No await between reading and writing the slots, so concurrent tasks cannot share one.
        before = self._next_free.get(key)
        slot = max(now, before if before is not None else now)
        if shared is not None:
            slot = self._take_shared_slot(shared, slot, now)
        self._next_free[key] = slot + interval
        wait = slot - now
        try:
            if wait > 0:
                await self._wait(wait)
            elif shared is not None:
                # Let the other tasks that are ready ask for their slots before this one asks for
                # its next: every store's first request is then queued before any store's second.
                await asyncio.sleep(0)
        except BaseException:
            self._give_back(key, shared, slot, before, interval)
            raise
        return max(wait, 0.0)

    # ------------------------------------------------------------------------------------

    def _take_shared_slot(self, shared: SharedLimit, not_before: float, now: float) -> float:
        """The earliest time at or after ``not_before`` that is a full interval away from every
        send time already given out under ``shared``. It is recorded as taken."""
        interval = 1.0 / shared.rps
        taken = self._taken.setdefault(shared.name, [])
        del taken[: bisect.bisect_left(taken, now - interval)]  # too old to be in anyone's way
        slot = not_before
        for other in taken:
            if other + interval <= slot + _EPSILON:
                continue  # well before this slot
            if slot + interval <= other + _EPSILON:
                break  # this slot fits in the gap before ``other``
            slot = other + interval  # too close to ``other``: go after it
        bisect.insort(taken, slot)
        return slot

    async def _wait(self, seconds: float) -> None:
        with waiting_in_queue():  # a request waiting for its slot has not started
            await self._clock.sleep(seconds)

    def _give_back(
        self,
        key: str,
        shared: SharedLimit | None,
        slot: float,
        before: float | None,
        interval: float,
    ) -> None:
        """Release the slot of a request that will never be sent, so it does not delay the next
        search (a request cancelled at the deadline)."""
        if shared is not None:
            taken = self._taken.get(shared.name, [])
            index = bisect.bisect_left(taken, slot)
            if index < len(taken) and taken[index] == slot:
                del taken[index]
        if self._next_free.get(key) == slot + interval:  # nobody has queued behind it
            if before is None:
                del self._next_free[key]
            else:
                self._next_free[key] = before


class Cooldowns:
    """Keys (a store id, or ``host:<name>`` for an image host) that must not be contacted until
    their cooldown ends."""

    def __init__(self, clock: Clock, duration_s: float) -> None:
        self._clock = clock
        self._duration_s = duration_s
        self._until: dict[str, float] = {}

    def start(self, key: str) -> None:
        """Begin a cooldown for ``key``. A zero duration (the setting allows it) disables it."""
        if self._duration_s > 0:
            self._until[key] = self._clock.monotonic() + self._duration_s

    def remaining(self, key: str) -> float:
        """Seconds left in ``key``'s cooldown; ``0.0`` when it is not cooling down."""
        until = self._until.get(key)
        if until is None:
            return 0.0
        left = until - self._clock.monotonic()
        if left <= 0:
            del self._until[key]
            return 0.0
        return left
