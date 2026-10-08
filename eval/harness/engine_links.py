"""The link check's page fetch, made with the project's own fetch engine (plan 11.2.3, 16.1.1).

``LinkChecker`` takes a ``LinkFetch`` by injection and makes no request itself. This is the one the
live run injects. It opens each product link through the same ``StoreSearchEngine`` the search used,
so a link is requested exactly as politely as a search page is (BRD Rule 2), with no second HTTP
client:

- the honest ``User-Agent`` of the settings, no cookies, no extra headers, no proxy;
- the store's ``robots.txt`` is checked first, and a page it disallows is not requested;
- the same per-host rate limiter, about 1 request per second per store;
- the URL and every redirect hop must be https on the store's ``allowed_hosts``, at most 3
  redirects, and a redirect to another registered domain is not followed;
- a store that turned an earlier request away is in cooldown and is not asked again: its remaining
  links are marked ``throttled`` (not checked, and not a broken link), they are not retried or
  worked around;
- no retries.

What the engine does not tell us, this class works out for ``LinkResult``:

- ``elapsed_s`` is the time the request took, without the wait for the rate limiter and without the
  ``robots.txt`` check, because rubric point 1 is about how fast the store answered. The wait is
  measured by a thin wrapper around the engine's limiter, installed once in ``__init__``.
- ``redirects`` is 0 when the address did not change and 1 when it did. The engine does not report
  the count; it refuses more than 3 itself (``too_many_redirects``), so the "at most 3" rule is
  enforced, only not counted.
- ``title`` is the page's ``<title>``, else its ``og:title``.
"""

from collections.abc import Sequence
from dataclasses import replace
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from eval.harness.links import LinkResult
from vga.fetch import FetchError, PoliteClient, RateLimiter, registered_domain
from vga.fetch.blocking import looks_like_html
from vga.fetch.client import FetchPolicy, FetchResponse
from vga.interfaces import Clock
from vga.models import StoreConfig, StoreStatus
from vga.stores import StoreSearchEngine

LINK_PAGE_MAX_BYTES = 5_000_000
"""A product page can be larger than the 2 MB cap meant for a search answer. Only the title is
read, but the whole body has to arrive, so a link is not failed for being a heavy page."""

ACCEPT_HTML = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"
"""A product page is HTML. (The search policy prefers JSON, which is what a search answer is.)"""

_MAX_TITLE_CHARS = 300


class MeteredLimiter(RateLimiter):
    """The engine's rate limiter, plus a running total of the time callers waited for a slot.

    It hands every call on to the limiter it wraps, so rates and ``Crawl-delay`` settings stay
    exactly the engine's own."""

    def __init__(self, inner: RateLimiter, clock: Clock) -> None:
        super().__init__(clock)
        self._inner = inner
        self.waited_s = 0.0

    def set_min_interval(self, key: str, seconds: float, *, source: str | None = None) -> None:
        self._inner.set_min_interval(key, seconds, source=source)

    async def acquire(self, host: str, rps: float) -> float:
        waited = await self._inner.acquire(host, rps)
        self.waited_s += waited
        return waited


def page_title(response: FetchResponse) -> str | None:
    """The ``<title>`` of an HTML response, else its Open Graph title, else ``None``."""
    if not looks_like_html(response.body, response.content_type):
        return None
    document = LexborHTMLParser(response.text)
    node = document.css_first("title")
    title = node.text() if node is not None else ""
    if not title.strip():
        og = document.css_first('meta[property="og:title"]')
        title = (og.attributes.get("content") or "") if og is not None else ""
    one_line = " ".join(title.split())
    return one_line[:_MAX_TITLE_CHARS] or None


def _problem(exc: FetchError) -> str:
    """What stopped the request, for the report: the error's code and its technical note."""
    return f"{exc.code} ({exc.detail})" if exc.detail else exc.code


class EngineLinkFetch:
    """A ``LinkFetch``: ``await fetch(url)`` opens one product link through the fetch engine.

    ``stores`` are the stores whose products are linked; a link is fetched under the store whose
    ``allowed_hosts`` hold its host (a store's own domain wins over a shared image CDN host).
    """

    def __init__(self, engine: StoreSearchEngine, stores: Sequence[StoreConfig]) -> None:
        self._engine = engine
        self._client: PoliteClient = engine.client
        self._by_host = self._index_by_host(stores)
        self._meter = MeteredLimiter(self._client.limiter, self._client.clock)
        self._client.limiter = self._meter

    @staticmethod
    def _index_by_host(stores: Sequence[StoreConfig]) -> dict[str, StoreConfig]:
        by_host: dict[str, StoreConfig] = {}
        # Pass 1: a store's own domain. Pass 2: anything else it may link to (a CDN).
        for own_domain_only in (True, False):
            for store in stores:
                own = registered_domain(urlsplit(store.search_url_template).hostname or "")
                for host in store.allowed_hosts:
                    if not own_domain_only or registered_domain(host) == own:
                        by_host.setdefault(host, store)
        return by_host

    def _policy(self, store: StoreConfig) -> FetchPolicy:
        page = self._client.page_policy(store)
        return replace(page, max_bytes=max(page.max_bytes, LINK_PAGE_MAX_BYTES), accept=ACCEPT_HTML)

    async def __call__(self, url: str) -> LinkResult:
        host = (urlsplit(url).hostname or "").lower()
        store = self._by_host.get(host)
        if store is None:
            return LinkResult(url=url, error=f"host {host!r} is not on any store's allowed_hosts")
        try:
            await self._engine.robots.ensure_allowed(url, store)
            waited_before = self._meter.waited_s
            started = self._client.clock.monotonic()
            response = await self._client.fetch(url, store, self._policy(store))
            took = self._client.clock.monotonic() - started
        except FetchError as exc:
            # A store that turned the request away (or is cooling down after it did) has not
            # said anything about this link: it was not looked at, so it is not a broken link.
            throttled = exc.store_status in (StoreStatus.BLOCKED, StoreStatus.COOLDOWN)
            return LinkResult(url=url, error=_problem(exc), throttled=throttled)
        waited = self._meter.waited_s - waited_before
        moved = response.url != url
        return LinkResult(
            url=url,
            final_url=response.url if moved else None,
            status=response.status,
            title=page_title(response),
            redirects=1 if moved else 0,
            elapsed_s=max(took - waited, 0.0),
        )
