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
- A ``Crawl-delay`` slows the host's rate limiter; it never speeds it up.
- A block while fetching robots.txt (403, 429, challenge page) is a block like any other: the
  store goes into cooldown. Fetching robots.txt follows the same client rules as every request.

Verdicts are cached per host: 24 hours for a parsed file, ``store_cooldown_s`` for "unreachable"
(so a failing robots.txt is not asked for again on every search).
"""

import asyncio
import re
from dataclasses import dataclass

from protego import Protego

from vga.fetch.allowlist import check_url
from vga.fetch.blocking import looks_like_html
from vga.fetch.client import PoliteClient
from vga.fetch.errors import BlockedError, CooldownError, FetchError, RobotsDeniedError
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
            raise RobotsDeniedError(detail=f"{verdict.reason} ({host})")
        if not verdict.rules.can_fetch(url, self._user_agent):
            log.info(
                "robots.txt disallows the URL; skipped",
                extra={"store": store.id, "url": url[:200], "host": host},
            )
            raise RobotsDeniedError(detail=f"robots.txt disallows {url[:200]}")

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
            # Another search is already asking this host for robots.txt: share its answer.
            try:
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
            response = await self._client.fetch(url, store, self._client.page_policy(store))
        except (BlockedError, CooldownError):
            raise  # a block (the client started the cooldown) or a store still cooling: not cached
        except FetchError as exc:
            return self._unusable(host, f"robots.txt could not be read ({exc.code})")

        if 400 <= response.status < 500:  # RFC 9309: no robots.txt means everything is allowed
            log.info(
                "no robots.txt; everything allowed",
                extra={"store": store.id, "host": host, "status": response.status},
            )
            return self._parsed(host, Protego.parse(""))
        if not response.ok:
            return self._unusable(host, f"robots.txt answered HTTP {response.status}")
        if looks_like_html(response.body, response.content_type):
            return self._unusable(host, "an HTML page was served instead of robots.txt")

        text = response.text
        if MALFORMED_RULE.search(text):
            log.info(
                "robots.txt has a rule without a leading / or *; read as if it began with *",
                extra={"store": store.id, "host": host},
            )
        rules = Protego.parse(MALFORMED_RULE.sub(r"\1*", text))
        delay = rules.crawl_delay(self._user_agent)
        if delay:
            self._client.limiter.set_min_interval(host, float(delay))
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
        """Remember that robots.txt cannot be used: everything is disallowed until the cooldown
        period ends, with no request made in between."""
        ttl = float(self._client.settings.store_cooldown_s)
        verdict = _Verdict(None, reason, self._client.clock.monotonic() + ttl)
        self._cache[host] = verdict
        log.warning(
            "robots.txt unusable; treating everything on the host as disallowed",
            extra={"host": host, "reason": reason},
        )
        return verdict
