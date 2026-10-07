"""Slow the link check down (``--link-interval``), whatever the fetch engine does.

The engine keeps each store to about one request a second. That is polite to a store and not to a
platform: ten Shopify stores each asked once a second are ten requests a second from one address,
and the platform limits the address, not the shop. A live link check therefore sends at most one
request every ``interval`` seconds across all stores together, on top of the engine's own limits.

``SpacedLinkFetch`` wraps the injected ``LinkFetch`` and takes its time from the injected
``Clock``, so a test runs it on a fake clock and nothing really waits.
"""

from eval.harness.links import LinkFetch, LinkResult
from vga.interfaces import Clock

DEFAULT_LINK_INTERVAL_S = 2.0
"""One link request every two seconds: 30 a minute from the whole run."""


class SpacedLinkFetch:
    """A ``LinkFetch`` whose requests start at least ``interval_s`` apart.

    Each call reserves the next free turn before it waits, so even calls that start together
    (nothing in the harness does that today) get separate turns. An answer that itself takes
    longer than the interval is not waited for twice: the spacing is from one request's start to
    the next one's. A call that fails has still used its turn."""

    def __init__(self, inner: LinkFetch, interval_s: float, clock: Clock) -> None:
        self._inner = inner
        self._interval_s = interval_s
        self._clock = clock
        self._next_turn = float("-inf")

    async def __call__(self, url: str) -> LinkResult:
        if self._interval_s > 0:
            now = self._clock.monotonic()
            turn = max(now, self._next_turn)
            self._next_turn = turn + self._interval_s
            if turn > now:
                await self._clock.sleep(turn - now)
        return await self._inner(url)
