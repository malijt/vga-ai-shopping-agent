"""The only code in the app that talks to a store (plan 6.1.1 to 6.1.4).

One honest ``httpx`` client, and these rules for every request, whatever it is for:

- the ``User-Agent`` is ``settings.user_agent`` (it identifies this app and never imitates a
  browser); no proxy, no cookies, no extra headers, no impersonation;
- https only, every URL and every redirect hop checked against the store's ``allowed_hosts``
  (``vga.fetch.allowlist``); at most 3 redirects; a redirect to another registered domain stops
  the request instead of following the store to its new home; and a redirect is followed only
  after the caller's ``vet_redirect`` (robots.txt of the page it leads to) agrees;
- one slot per request, before it is sent, from a rate limiter that works per *store* across all
  the hosts of the store's own site (the bare domain and ``www.``, say) and per host for any
  other host such as a shared image CDN; and every request to a store's own site also takes a
  slot in the queue its whole platform shares (``Settings.rps_per_platform``, see
  ``vga.fetch.platform``), because a hosted platform counts requests per client, not per shop;
- a total time limit and a response size limit; a response that grows past the cap is aborted;
- a 401, 403 or 429, a login redirect or a bot-challenge page means the store is *blocked*: the
  request is not repeated, and the key it belongs to is put in cooldown (``vga.fetch.ratelimit``).
  A 429 from a store's own site is also the whole platform's answer: every store on the platform
  goes into cooldown at once, at least as long as the ``Retry-After`` it names, and the requests
  still queued for the platform are dropped unsent. Any other block is that store's alone;
- **no retries, ever.** A failed request is reported, not repeated.

The client holds no store knowledge beyond what a ``StoreConfig`` says about hosts, rate and size.
"""

import asyncio
import http.cookiejar
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from vga.fetch.allowlist import belongs_to_store_site, check_url, normalise_host, registered_domain
from vga.fetch.blocking import (
    BLOCKING_STATUSES,
    LOGIN_PATH,
    RATE_LIMITED_STATUS,
    REDIRECT_STATUSES,
    find_challenge_marker,
    parse_retry_after,
)
from vga.fetch.deadline import run_with_deadline
from vga.fetch.errors import (
    BlockedError,
    CooldownError,
    CrossDomainRedirectError,
    FetchFailedError,
    FetchTimeoutError,
    ResponseTooLargeError,
    TooManyRedirectsError,
    UrlNotAllowedError,
)
from vga.fetch.platform import platform_of
from vga.fetch.ratelimit import Cooldowns, RateLimiter, RequestDropped, SharedLimit
from vga.interfaces import Clock, SystemClock
from vga.log import get_logger
from vga.models import StoreConfig
from vga.settings import Settings

log = get_logger(__name__)

RedirectCheck = Callable[[str, StoreConfig], Awaitable[None]]
"""Asked about the target of a redirect before it is followed: it returns to allow it and raises a
``FetchError`` to refuse it. The store search passes ``RobotsChecker.ensure_allowed`` so that a
redirect never gets round the robots.txt of the page it leads to."""

MAX_REDIRECTS = 3
ACCEPT_PAGE = "application/json, text/html;q=0.9, text/plain;q=0.8, */*;q=0.5"
ACCEPT_IMAGE = "image/*"
IMAGE_TIMEOUT_S = 4.0
"""A thumbnail, or the robots.txt of an image host, that takes longer is not worth waiting for
(plan 8.3.1)."""


@dataclass(frozen=True)
class FetchPolicy:
    """How one request is made: its rate, time and size limits and its cooldown key."""

    rps: float
    timeout_s: float
    max_bytes: int
    cooldown_key: str
    """What a block puts in cooldown, and what a cooldown stops: ``PoliteClient.contact_key`` of
    the host asked, so the store id for every host of the store's own site (pages, robots.txt and
    thumbnails alike) and ``host:<name>`` for any other host, such as a shared image CDN."""
    accept: str = ACCEPT_PAGE


@dataclass(frozen=True)
class FetchResponse:
    """A finished response. The body is held in memory only."""

    url: str
    """The URL that produced this response, after any redirects."""
    status: int
    content_type: str
    body: bytes
    charset: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        """The body as text. Undecodable bytes become U+FFFD; an unknown charset falls back to
        UTF-8."""
        try:
            return self.body.decode(self.charset or "utf-8", errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class _RawResponse:
    status: int
    content_type: str
    location: str | None
    body: bytes
    charset: str | None
    retry_after: str | None = None


class _RejectAllCookies(http.cookiejar.CookiePolicy):
    """No cookie is ever stored or sent: every request stands alone (BRD Rule 2)."""

    netscape = True
    rfc2965 = False
    hide_cookie2 = False

    def set_ok(self, cookie: http.cookiejar.Cookie, request: urllib.request.Request) -> bool:
        return False

    def return_ok(self, cookie: http.cookiejar.Cookie, request: urllib.request.Request) -> bool:
        return False

    def domain_return_ok(self, domain: str, request: urllib.request.Request) -> bool:
        return False

    def path_return_ok(self, path: str, request: urllib.request.Request) -> bool:
        return False


class PoliteClient:
    """Fetches one URL under the rules in the module docstring.

    ``transport`` is for tests and for dependency injection; leave it ``None`` in production. The
    underlying ``httpx.AsyncClient`` is created on first use and re-created when a different event
    loop is running (a UI that calls ``asyncio.run`` per request must not reuse a client whose
    loop is closed). Rate-limit, cooldown and cache state live outside it and survive that.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Clock | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        limiter: RateLimiter | None = None,
        cooldowns: Cooldowns | None = None,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.clock: Clock = clock or SystemClock()
        self._platform_limits: dict[str, SharedLimit] = {}
        """The platform queue each store's own site belongs to, by store id, filled as the stores
        are first requested."""
        self.limiter = limiter or RateLimiter(self.clock, group_of=self._platform_limits.get)
        self.cooldowns = cooldowns or Cooldowns(self.clock, settings.store_cooldown_s)
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        """The date, for a ``Retry-After`` given as one. Tests pass a fixed one."""
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------------------------
    # Policies
    # ------------------------------------------------------------------------------------

    def page_policy(self, store: StoreConfig) -> FetchPolicy:
        """Limits for a search page or a robots.txt: the store's own settings, else the global
        ones."""
        return FetchPolicy(
            rps=store.rps or self.settings.rps_per_store,
            timeout_s=store.timeout_s or self.settings.timeout_s,
            max_bytes=store.max_response_bytes or self.settings.max_response_bytes,
            cooldown_key=store.id,
        )

    @staticmethod
    def contact_key(store: StoreConfig, host: str) -> str:
        """Who a request to ``host`` is addressed to, for the rate limit and for cooldowns: the
        store (its id) for any host of the store's own site, else that host alone
        (``host:<name>``, which cannot clash with a store id). The BRD's "about one request a
        second" and "not contacted again during its cooldown" are both per store, so the bare
        domain and its ``www.`` share one queue and one cooldown; a shared image CDN is another
        party with its own."""
        return store.id if belongs_to_store_site(store, host) else f"host:{normalise_host(host)}"

    def image_policy(self, store: StoreConfig, host: str, *, timeout_s: float) -> FetchPolicy:
        """Limits for a thumbnail. A host that belongs to the store itself keeps the store's
        rate and, with it, the store's cooldown: a store that has just refused us is not asked for
        thumbnails on its own host, and a thumbnail it refuses puts the store in cooldown. Only a
        separate image CDN gets the faster ``rps_images_per_host`` (assumption A5) and its own
        cooldown, so a CDN that refuses us never puts the store in cooldown."""
        rps = (
            store.rps or self.settings.rps_per_store
            if belongs_to_store_site(store, host)
            else self.settings.rps_images_per_host
        )
        return FetchPolicy(
            rps=rps,
            timeout_s=timeout_s,
            max_bytes=store.max_response_bytes or self.settings.max_response_bytes,
            cooldown_key=self.contact_key(store, host),
            accept=ACCEPT_IMAGE,
        )

    def robots_policy(self, store: StoreConfig, host: str) -> FetchPolicy:
        """Limits for fetching ``host``'s robots.txt. The store's own domain uses the page
        policy, so a block there blocks the store. Any other host (an image CDN) uses the image
        rate and timeout and its own cooldown key, so a CDN that refuses us never puts the store
        in cooldown."""
        page = self.page_policy(store)
        if belongs_to_store_site(store, host):
            return page
        return replace(
            page,
            rps=self.settings.rps_images_per_host,
            timeout_s=IMAGE_TIMEOUT_S,
            cooldown_key=self.contact_key(store, host),
        )

    # ------------------------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------------------------

    async def fetch(
        self,
        url: str,
        store: StoreConfig,
        policy: FetchPolicy,
        *,
        vet_redirect: RedirectCheck | None = None,
    ) -> FetchResponse:
        """GET ``url`` for ``store`` and return the final response (any status except a block).

        The caller has already checked ``url`` itself against robots.txt. ``vet_redirect`` is how
        the client keeps that promise for the pages a redirect leads to: it is called with each
        redirect target, after the allow-list check and before the request, and a ``FetchError``
        it raises ends the fetch. Every request except a robots.txt fetch should pass one; a
        robots.txt is the file that rules are read from, so there is nothing to check it against.

        Raises a ``FetchError`` subclass for everything that is not a response: a refused URL,
        a block, a cooldown, a timeout, a too-large body, a transport failure.
        """
        first_domain = registered_domain(check_url(url, store.allowed_hosts))
        current = url
        for hop in range(MAX_REDIRECTS + 1):
            host = check_url(current, store.allowed_hosts)
            contact = self.contact_key(store, host)
            own_site = contact == store.id  # else an image host, which is not on the platform
            on_platform = store if own_site else None
            self._raise_if_cooling(policy.cooldown_key, on_platform)
            if hop > 0 and vet_redirect is not None:
                await vet_redirect(current, store)
            if own_site:  # the store's own site shares its platform's queue
                self._platform_limits[store.id] = SharedLimit(
                    platform_of(store), self.settings.rps_per_platform
                )
            try:
                await self.limiter.acquire(contact, policy.rps)
            except RequestDropped as exc:  # the platform was told to stop while this one queued
                self._raise_if_cooling(policy.cooldown_key, on_platform)
                msg = f"dropped from the queue of {platform_of(store)}"
                raise CooldownError(detail=msg) from exc
            # Another task may have been turned away while this one waited for its slot.
            self._raise_if_cooling(policy.cooldown_key, on_platform)
            raw = await self._send(current, policy, store.id)

            if raw.status in BLOCKING_STATUSES:
                rate_limited = raw.status == RATE_LIMITED_STATUS and own_site
                raise self._blocked(
                    policy,
                    store,
                    current,
                    f"HTTP {raw.status}",
                    platform_wide=rate_limited,
                    retry_after=raw.retry_after if rate_limited else None,
                )
            if raw.status in REDIRECT_STATUSES and raw.location:
                current = self._next_hop(current, raw.location, first_domain, policy, store)
                continue
            marker = find_challenge_marker(raw.body, raw.content_type)
            if marker:
                raise self._blocked(policy, store, current, f"challenge page ({marker!r})")
            return FetchResponse(current, raw.status, raw.content_type, raw.body, raw.charset)
        # The last response was yet another redirect: it is not followed.
        raise TooManyRedirectsError(
            detail=f"more than {MAX_REDIRECTS} redirects, the next target was {current[:200]}"
        )

    def _next_hop(
        self,
        current: str,
        location: str,
        first_domain: str,
        policy: FetchPolicy,
        store: StoreConfig,
    ) -> str:
        """The URL a redirect points at, or an error if following it is not allowed."""
        target = urljoin(current, location)
        try:
            target_host = normalise_host(httpx.URL(target).host)
        except (httpx.InvalidURL, ValueError) as exc:
            raise UrlNotAllowedError(detail=f"redirect to an unusable URL: {target[:200]}") from exc
        if registered_domain(target_host) != first_domain:
            log.warning(
                "redirect to another domain not followed",
                extra={"store": store.id, "from_url": current[:200], "to_host": target_host},
            )
            raise CrossDomainRedirectError(
                detail=f"redirected from {first_domain} to another domain: {target_host}"
            )
        if LOGIN_PATH.search(urlsplit(target).path):
            raise self._blocked(policy, store, target, "login wall (redirect to a login page)")
        return target

    def cooldown_remaining(self, store: StoreConfig) -> float:
        """Seconds left before ``store``'s own site may be asked again: the longer of its own
        cooldown and its platform's. ``0.0`` when it may be asked now."""
        return max(self.cooldowns.remaining(store.id), self.cooldowns.remaining(platform_of(store)))

    def _raise_if_cooling(self, key: str, store: StoreConfig | None = None) -> None:
        """Raise ``CooldownError`` if ``key`` is cooling down or, for a request to ``store``'s own
        site (pass ``store``), if the platform it is on is."""
        remaining, cooling = self.cooldowns.remaining(key), key
        if store is not None:
            platform = platform_of(store)
            on_platform = self.cooldowns.remaining(platform)
            if on_platform > remaining:
                remaining, cooling = on_platform, platform
        if remaining > 0:
            raise CooldownError(detail=f"{cooling} is in cooldown for another {remaining:.0f} s")

    def _blocked(
        self,
        policy: FetchPolicy,
        store: StoreConfig,
        url: str,
        why: str,
        *,
        platform_wide: bool = False,
        retry_after: str | None = None,
    ) -> BlockedError:
        """Start the cooldown a refusal earns and return the error to raise.

        The store (or image host) that refused is always put in cooldown. With ``platform_wide``
        (an HTTP 429 from a store's own site) every store on its platform is too, and the requests
        queued for the platform are dropped unsent. A ``Retry-After`` in the answer sets the least
        time the cooldown lasts.
        """
        asked_s = parse_retry_after(retry_after, self._wall_clock()) or 0.0
        cooldown_s = self.cooldowns.start(policy.cooldown_key, at_least_s=asked_s)
        extra = {"store": store.id, "url": url[:200], "reason": why, "key": policy.cooldown_key}
        if not platform_wide:
            log.warning("store blocked the request; no retry, cooldown started", extra=extra)
            return BlockedError(detail=f"{why} on {url[:200]}")

        platform = platform_of(store)
        platform_cooldown_s = self.cooldowns.start(platform, at_least_s=asked_s)
        dropped = self.limiter.drop_waiting(platform) if platform_cooldown_s > 0 else 0
        log.warning(
            "platform answered too many requests; every store on it is paused, no retry",
            extra={
                **extra,
                "platform": platform,
                "retry_after": (retry_after or "")[:60] or None,
                "retry_after_s": asked_s or None,
                "cooldown_s": max(cooldown_s, platform_cooldown_s),
                "dropped_requests": dropped,
            },
        )
        return BlockedError(detail=f"{why} on {url[:200]}")

    async def _send(self, url: str, policy: FetchPolicy, store_id: str) -> _RawResponse:
        try:
            raw = await run_with_deadline(self.clock, policy.timeout_s, self._get(url, policy))
        except TimeoutError as exc:
            log.warning(
                "request timed out",
                extra={"store": store_id, "url": url[:200], "timeout_s": policy.timeout_s},
            )
            raise FetchTimeoutError(
                detail=f"no complete answer within {policy.timeout_s:g} s from {url[:200]}"
            ) from exc
        log.debug(
            "response",
            extra={
                "store": store_id,
                "url": url[:200],
                "status": raw.status,
                "bytes": len(raw.body),
            },
        )
        return raw

    async def _get(self, url: str, policy: FetchPolicy) -> _RawResponse:
        client = self._http_client()
        try:
            async with client.stream(
                "GET", url, headers={"Accept": policy.accept}, timeout=policy.timeout_s
            ) as response:
                content_type = response.headers.get("content-type", "")
                location = response.headers.get("location")
                if response.status_code in BLOCKING_STATUSES | REDIRECT_STATUSES:
                    return _RawResponse(
                        response.status_code,
                        content_type,
                        location,
                        b"",
                        None,
                        response.headers.get("retry-after"),
                    )
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > policy.max_bytes:
                    raise ResponseTooLargeError(
                        detail=f"declared {declared} bytes, cap {policy.max_bytes}, {url[:200]}"
                    )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > policy.max_bytes:
                        raise ResponseTooLargeError(
                            detail=f"more than {policy.max_bytes} bytes from {url[:200]}"
                        )
                    chunks.append(chunk)
                return _RawResponse(
                    response.status_code,
                    content_type,
                    location,
                    b"".join(chunks),
                    response.charset_encoding,
                )
        except httpx.TimeoutException as exc:
            raise FetchTimeoutError(detail=f"{type(exc).__name__} from {url[:200]}") from exc
        except httpx.HTTPError as exc:
            raise FetchFailedError(
                detail=f"{type(exc).__name__}: {str(exc)[:200]} ({url[:200]})"
            ) from exc

    # ------------------------------------------------------------------------------------
    # The httpx client
    # ------------------------------------------------------------------------------------

    def _http_client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            client = httpx.AsyncClient(
                headers={"User-Agent": self.settings.user_agent},
                follow_redirects=False,  # followed by hand: every hop is checked and rate limited
                trust_env=False,  # never pick up proxy settings from the environment
                transport=self._transport,
            )
            client.cookies.jar.set_policy(_RejectAllCookies())
            self._client = client
            self._client_loop = loop
        return self._client

    async def aclose(self) -> None:
        """Close the connection pool (if it belongs to the running loop)."""
        client, loop = self._client, self._client_loop
        self._client = self._client_loop = None
        if client is not None and loop is asyncio.get_running_loop():
            await client.aclose()
