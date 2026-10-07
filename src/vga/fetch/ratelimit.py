"""Per-host rate limiter and per-key cooldowns (plan 6.1.3 and 6.1.4), both on the injected
``Clock``.

``RateLimiter`` is an async token bucket of capacity one: the first request to a host goes at once
and every later one is spaced ``1 / rps`` seconds after the one before, however many tasks ask at
the same time. N requests therefore take at least ``(N - 1) / rps`` seconds, and a slow host never
delays another, because each host has its own bucket.

``Cooldowns`` remembers which stores (or image hosts) turned an honest request away and for how
long they must be left alone.
"""

from vga.interfaces import Clock


class RateLimiter:
    """Spaces requests to one host. Wait slots are handed out in call order."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._next_free: dict[str, float] = {}
        self._min_interval: dict[str, float] = {}

    def set_min_interval(self, host: str, seconds: float) -> None:
        """Never go faster than one request per ``seconds`` to ``host`` (a robots.txt
        ``Crawl-delay``). It can only slow a host down, never speed it up."""
        self._min_interval[host] = max(seconds, 0.0)

    async def acquire(self, host: str, rps: float) -> float:
        """Wait for this host's next free slot. Returns how long the caller waited, in seconds."""
        interval = max(1.0 / rps, self._min_interval.get(host, 0.0))
        now = self._clock.monotonic()
        # No await between reading and writing the slot, so concurrent tasks cannot share one.
        slot = max(now, self._next_free.get(host, now))
        self._next_free[host] = slot + interval
        wait = slot - now
        if wait > 0:
            await self._clock.sleep(wait)
        return max(wait, 0.0)


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
