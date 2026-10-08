"""robots.txt: fetch, cache per host, and decide whether a URL may be requested (plan 6.2.1).

The decisions follow RFC 9309 and the findings of the store qualification:

- ``protego`` does the matching, never ``urllib.robotparser``: on Python 3.12 the standard parser
  ignores ``*`` and ``$`` and would allow Noon's and Level Shoes' disallowed search paths.
- The full URL is checked, including its query string (Noon's ``Disallow: /*/search?``).
- A 2xx answer is parsed. A 4xx answer means "no robots.txt": everything is allowed. A 5xx answer,
  a timeout, a network failure or any other failure means "unreachable": everything is
  *disallowed*.
- An HTML page served in place of robots.txt (Namshi's alias host redirects to a home page) counts
  as unreachable, not as an empty robots file.
- A rule whose value starts with neither ``/`` nor ``*`` (Namshi's ``Disallow: ?q=``) matches
  nothing under the RFC, but plainly means "any URL containing it", so it is read as if it began
  with ``*``.
- A ``Crawl-delay`` slows the rate limiter of the store the host belongs to (the store's own hosts
  share one queue); it never speeds it up, and the longest delay any of the store's hosts asks
  for applies.
- A block while fetching robots.txt (403, 429, challenge page) is a block like any other: the
  store goes into cooldown. Fetching robots.txt follows the same client rules as every request.

Verdicts are cached per host: 24 hours for a parsed file (or a 404, "no rules"), and only
``robots_unreadable_retry_s`` (60 s by default) for "unreachable". The short memory keeps a burst
of searches from hammering a struggling host, yet a timeout on our own side does not switch a store
off for long; after it, robots.txt is read again before any search is sent. A block (401, 403, 429,
a challenge page) is not a verdict at all: it starts the store's cooldown (``store_cooldown_s``).
"""

import asyncio
import re
from dataclasses import dataclass

from protego import Protego

from vga.fetch.allowlist import check_url
from vga.fetch.blocking import looks_like_html
from vga.fetch.client import PoliteClient
from vga.fetch.deadline import waiting_in_queue
from vga.fetch.errors import (
    ROBOTS_UNREADABLE_DETAIL,
    BlockedError,
    CooldownError,
    FetchError,
    RobotsDeniedError,
    RobotsUnreadableError,
)
from vga.log import get_logger
from vga.models import StoreConfig

log = get_logger(__name__)

ROBOTS_TTL_S = 24 * 3600
"""How long a parsed robots.txt is trusted (RFC 9309 says not to cache for more than a day)."""

# A rule value starting with neither / nor * (the site's `Disallow: ?q=`) matches nothing under
# RFC 9309, so a strict parser allows those URLs. The site plainly meant to block them: read as
# `*?q=`. Same rule as scripts/qualify_store.py.
MALFORMED_RULE = re.compile(r"(?im)^(\s*(?:dis)?allow\s*:\s*)(?![/*\s]|$)")


@dataclass(frozen=True)
class _Verdict:
    """What we know about one host's robots.txt."""

    rules: Protego | None
    """The parsed rules. ``None`` means "unreachable": everything is disallowed."""
    reason: str | None
    """Why the file is unusable (set exactly when ``rules`` is ``None``)."""
    expires_at: float


class RobotsChecker:
    """Answers "may we request this URL?" for any host of a store, fetching robots.txt once per
    host and caching the verdict."""

    def __init__(self, client: PoliteClient) -> None:
        self._client = client
        self._user_agent = client.settings.user_agent
        self._cache: dict[str, _Verdict] = {}
        self._in_flight: dict[str, asyncio.Future[_Verdict]] = {}

    async def ensure_allowed(self, url: str, store: StoreConfig) -> None:
        """Return if robots.txt allows ``url`` for our User-Agent; raise ``RobotsDeniedError``
        if it does not (or could not be read). Fetching robots.txt can itself raise
        ``BlockedError`` or ``CooldownError``."""
        host = check_url(url, store.allowed_hosts)
        verdict = await self._verdict(host, store)
        if verdict.rules is None:
            raise RobotsUnreadableError(detail=f"{verdict.reason} ({host})")
        if not verdict.rules.can_fetch(url, self._user_agent):
            log.info(
                "robots.txt disallows the URL; skipped",
                extra={"store": store.id, "url": url[:200], "host": host},
            )
            raise RobotsDeniedError(detail=f"robots.txt disallows {url[:200]}")

    async def preload(self, url: str, store: StoreConfig) -> None:
        """Read the robots.txt of ``url``'s host now and remember the verdict, so the first search
        does not have to. It is the very fetch ``ensure_allowed`` would make, through the same
        client (rate limits, platform queue, cooldowns), and the verdict is cached the same way,
        including "unreadable means disallowed" (for a short while only). It never raises for a
        robots.txt that cannot be read; a block (HTTP 429 and the rest) starts its cooldown as it
        always does and is logged."""
        host = check_url(url, store.allowed_hosts)
        try:
            await self._verdict(host, store)
        except FetchError as exc:
            log.warning(
                "robots.txt not read at start-up",
                extra={"store": store.id, "host": host, "reason": exc.code},
            )

    async def can_fetch(self, url: str, store: StoreConfig) -> bool:
        """``ensure_allowed`` as a yes/no question (a block still raises)."""
        try:
            await self.ensure_allowed(url, store)
        except RobotsDeniedError:
            return False
        return True

    # ------------------------------------------------------------------------------------

    async def _verdict(self, host: str, store: StoreConfig) -> _Verdict:
        while True:
            cached = self._cache.get(host)
            if cached is not None and cached.expires_at > self._client.clock.monotonic():
                return cached
            pending = self._in_flight.get(host)
            if pending is None:
                break
            # Another search is already asking this host for robots.txt: share its answer. This
            # one is waiting for that fetch (and its place in the queue), not working.
            try:
                with waiting_in_queue():
                    return await asyncio.shield(pending)
            except asyncio.CancelledError:
                if not pending.cancelled():
                    raise  # this task was cancelled, not the one doing the fetch
                # The fetching task was cancelled: go round again and fetch it ourselves.

        future: asyncio.Future[_Verdict] = asyncio.get_running_loop().create_future()
        self._in_flight[host] = future
        try:
            verdict = await self._load(host, store)
        except asyncio.CancelledError:
            future.cancel()
            raise
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark it retrieved, in case nobody else is waiting
            raise
        else:
            future.set_result(verdict)
            return verdict
        finally:
            del self._in_flight[host]

    async def _load(self, host: str, store: StoreConfig) -> _Verdict:
        """Fetch and parse ``https://<host>/robots.txt``, remember the verdict and return it."""
        url = f"https://{host}/robots.txt"
        try:
            policy = self._client.robots_policy(store, host)
            response = await self._client.fetch(url, store, policy)
        except (BlockedError, CooldownError):
            raise  # a block (the client started the cooldown) or a store still cooling: not cached
        except FetchError as exc:
            return self._unusable(host, f"{ROBOTS_UNREADABLE_DETAIL} ({exc.code})")

        if 400 <= response.status < 500:  # RFC 9309: no robots.txt means everything is allowed
            log.info(
                "no robots.txt; everything allowed",
                extra={"store": store.id, "host": host, "status": response.status},
            )
            return self._parsed(host, Protego.parse(""))
        if not response.ok:
            return self._unusable(host, f"{ROBOTS_UNREADABLE_DETAIL} (HTTP {response.status})")
        if looks_like_html(response.body, response.content_type):
            html = f"{ROBOTS_UNREADABLE_DETAIL} (an HTML page was served instead)"
            return self._unusable(host, html)

        text = response.text
        if MALFORMED_RULE.search(text):
            log.info(
                "robots.txt has a rule without a leading / or *; read as if it began with *",
                extra={"store": store.id, "host": host},
            )
        rules = Protego.parse(MALFORMED_RULE.sub(r"\1*", text))
        delay = rules.crawl_delay(self._user_agent)
        if delay:
            self._client.limiter.set_min_interval(
                self._client.contact_key(store, host), float(delay), source=host
            )
            log.info(
                "robots.txt asks for a crawl delay",
                extra={"store": store.id, "host": host, "delay_s": float(delay)},
            )
        return self._parsed(host, rules)

    def _parsed(self, host: str, rules: Protego) -> _Verdict:
        verdict = _Verdict(rules, None, self._client.clock.monotonic() + ROBOTS_TTL_S)
        self._cache[host] = verdict
        return verdict

    def _unusable(self, host: str, reason: str) -> _Verdict:
        """Remember that robots.txt cannot be used: everything is disallowed, with no request made
        in between, but only for ``robots_unreadable_retry_s``. Then it is read again."""
        ttl = float(self._client.settings.robots_unreadable_retry_s)
        verdict = _Verdict(None, reason, self._client.clock.monotonic() + ttl)
        self._cache[host] = verdict
        log.warning(
            "robots.txt unusable; treating everything on the host as disallowed",
            extra={"host": host, "reason": reason},
        )
        return verdict
