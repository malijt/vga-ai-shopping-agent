"""The link checker (plan 11.2.3): points 1 to 3 of "A working link" in ``rubric.md``.

This module makes no HTTP request itself. It takes a fetch function by injection,
``LinkFetch = Callable[[str], Awaitable[LinkResult]]``. Phase 16 passes one built on the project's
polite client, which must (BRD Rule 2) respect robots.txt, send the honest User-Agent, rate-limit
to about 1 request per second per store, follow redirects and report how many it followed. The
checker calls it one URL at a time, never in parallel, and asks for each URL once per run even when
several queries return the same product.

What is checked automatically, per result:

1. The page opens: status 200 after at most 3 redirects, in at most 6 s, and the title is not an
   error, "not found", login or CAPTCHA page.
2. The final address is ``https`` on a host in the store's ``allowed_hosts``.
3. It is the product's own page, not the home page, a search page or a listing. This is a
   heuristic on the address and the page title. It can miss a listing that looks like a product
   address, which is why a person still opens the top 10 of each query.

Point 4 (the page shows the same product as the card) is left to the human labeller.
"""

import re
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit

from pydantic import Field

from eval.harness.groups import displayed_results, top_results
from vga.models import Product, SearchResponse, StoreConfig, VgaModel


class LinksMode(StrEnum):
    """Which results of a query get a link check (``--links``)."""

    TOP10 = "top10"
    ALL = "all"
    NONE = "none"


class LinkResult(VgaModel):
    """What the fetch function saw when it opened one product link."""

    url: str
    """The address that was requested."""
    final_url: str | None = None
    """The address after redirects. ``None`` means no redirect happened (same as ``url``); a
    fetch that followed a redirect must report it, or the link fails."""
    status: int | None = None
    """Final HTTP status, or ``None`` when no response came back."""
    title: str | None = None
    """The page's ``<title>`` (or its Open Graph title), if it has one."""
    redirects: int = Field(default=0, ge=0)
    elapsed_s: float | None = Field(default=None, ge=0)
    """Time the request itself took, excluding any wait for the rate limiter. A page that opened
    without this figure fails, because the 6 s rule would otherwise go unchecked."""
    error: str | None = None
    """Set instead of a status when there was no page: ``timeout``, ``connection error``, a
    robots.txt refusal, and so on."""
    throttled: bool = False
    """True when the store turned the request away (blocked, or in its cooldown after it did). The
    link was not looked at, so it is *not checked*, not a broken link."""


LinkFetch = Callable[[str], Awaitable[LinkResult]]


class LinkCheck(VgaModel):
    """The verdict on one result's link."""

    url: str
    store: str
    product_title: str
    ok: bool
    problems: list[str] = Field(default_factory=list)
    """Plain sentences saying why the link failed (or, when ``not_checked``, why it was not
    looked at). Empty when ``ok``."""
    not_checked: bool = False
    """True when the store turned the request away (blocked or in cooldown): the link is neither
    good nor broken, and the query's links stay undecided."""
    result: LinkResult | None = None
    """What the fetch function returned. ``None`` when it raised instead."""


@dataclass(frozen=True)
class LinkRules:
    """The numbers from ``rubric.md``, in one place."""

    max_redirects: int = 3
    max_seconds: float = 6.0
    min_title_overlap: float = 0.5
    """Share of the product title's words that must appear in the page title."""


THROTTLED_LINK_NOTE = (
    "the store turned the request away (blocked or in cooldown), so this link was not checked"
)

_LANGUAGE_HOME = re.compile(r"^[a-z]{2}(?:[-_][a-z]{2})?$", re.IGNORECASE)
_SEARCH_KEYS = frozenset({"q", "query", "search", "s", "keyword", "keywords", "term", "text"})
_SEARCH_SEGMENTS = frozenset({"search", "catalogsearch", "results", "find"})
_LISTING_SEGMENTS = frozenset(
    {
        "collections",
        "category",
        "categories",
        "shop",
        "catalog",
        "catalogue",
        "new-in",
        "new-arrivals",
        "sale",
        "women",
        "men",
        "kids",
        "brands",
    }
)
_ERROR_TITLE = re.compile(
    r"\b(404|not found|access denied|forbidden|captcha|just a moment|attention required"
    r"|are you a (?:robot|human)|sign in|log in|login|error)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W_]+")


def title_words(text: str) -> set[str]:
    """Lower-cased words of a title, without one-letter noise. Works for Arabic and digits."""
    return {word for word in (found.casefold() for found in _WORD.findall(text)) if len(word) > 1}


def allowed_hosts_from_stores(stores: Sequence[StoreConfig]) -> dict[str, frozenset[str]]:
    """Map a store's display name (what ``Product.store`` holds) and its id to its allowed hosts."""
    mapping: dict[str, frozenset[str]] = {}
    for store in stores:
        hosts = frozenset(store.allowed_hosts)
        mapping[store.display_name] = hosts
        mapping.setdefault(store.id, hosts)
    return mapping


def _segments(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _page_problem(final_url: str, requested_url: str) -> str | None:
    """Why ``final_url`` is not a product's own page, or ``None`` if it looks like one."""
    final = urlsplit(final_url)
    segments = _segments(final.path)
    lowered = [segment.lower() for segment in segments]

    if not segments or (len(segments) == 1 and _LANGUAGE_HOME.match(segments[0])):
        return "the link ends on the store's home page, not a product page"
    query_keys = {key.lower() for key in parse_qs(final.query)}
    if query_keys & _SEARCH_KEYS or set(lowered) & _SEARCH_SEGMENTS:
        return "the link ends on a search page, not a product page"
    if "products" not in lowered:
        shopify_collection = lowered[0] == "collections"
        if shopify_collection or lowered[-1] in _LISTING_SEGMENTS:
            return "the link ends on a listing page, not a product page"
    requested = _segments(urlsplit(requested_url).path)
    if len(segments) < len(requested) and requested[: len(segments)] == segments:
        return "the link redirected up to a parent page, not the product page"
    return None


def _title_problems(product_title: str, page_title: str | None, rules: LinkRules) -> list[str]:
    if not page_title or not page_title.strip():
        return ["the page has no title to compare with the product"]
    problems: list[str] = []
    if _ERROR_TITLE.search(page_title):
        problems.append(
            f"the page title looks like an error, login or CAPTCHA page: {page_title!r}"
        )
    wanted = title_words(product_title)
    if wanted:
        overlap = len(wanted & title_words(page_title)) / len(wanted)
        if overlap < rules.min_title_overlap:
            problems.append(
                f"the page title shares {overlap:.0%} of the product title's words "
                f"(at least {rules.min_title_overlap:.0%} needed): {page_title!r}"
            )
    return problems


def evaluate_link(
    product: Product,
    result: LinkResult,
    allowed_hosts: Collection[str] | None,
    rules: LinkRules | None = None,
) -> list[str]:
    """Apply points 1 to 3 of "A working link". Returns the problems; an empty list means ok."""
    rules = rules or LinkRules()
    if result.error:
        return [f"no page opened: {result.error}"]
    if result.status != 200:
        shown = "no HTTP status" if result.status is None else f"HTTP {result.status}"
        return [f"{shown}, not 200"]

    problems: list[str] = []
    if result.redirects > rules.max_redirects:
        problems.append(f"{result.redirects} redirects (at most {rules.max_redirects})")
    if result.elapsed_s is None:
        problems.append("the fetch did not report how long the request took, so 6 s is unchecked")
    elif result.elapsed_s > rules.max_seconds:
        problems.append(f"took {result.elapsed_s:.1f} s (at most {rules.max_seconds:g} s)")
    if result.redirects > 0 and not result.final_url:
        problems.append(
            f"{result.redirects} redirect(s) followed but the final address was not reported, "
            "so its host and page cannot be checked"
        )

    final_url = result.final_url or result.url
    final = urlsplit(final_url)
    if final.scheme != "https":
        problems.append(f"the final address is not https ({final.scheme or 'no scheme'})")
    host = (final.hostname or "").lower()
    if allowed_hosts is None:
        problems.append(f"store {product.store!r} is not known, so its hosts cannot be checked")
    elif host not in allowed_hosts:
        problems.append(f"the final host {host!r} is not one of the store's own hosts")

    page = _page_problem(final_url, result.url)
    if page:
        problems.append(page)
    problems.extend(_title_problems(product.title, result.title, rules))
    return problems


def products_to_check(response: SearchResponse, mode: LinksMode) -> list[Product]:
    """The products whose links ``mode`` asks for, each product URL once, in a stable order."""
    if mode is LinksMode.NONE:
        return []
    chosen: list[Product] = []
    for group in response.groups:
        scored = displayed_results(group) if mode is LinksMode.ALL else top_results(group)
        chosen.extend(item.product for item in scored)
    unique: dict[str, Product] = {}
    for product in chosen:
        unique.setdefault(product.product_url, product)
    return list(unique.values())


class LinkChecker:
    """Checks product links through an injected fetch function, one at a time."""

    def __init__(
        self,
        fetch: LinkFetch,
        allowed_hosts: Mapping[str, Collection[str]],
        rules: LinkRules | None = None,
        known: Iterable[LinkCheck] = (),
    ) -> None:
        """``known`` are checks an earlier session of the same run already made: those URLs are
        not asked again."""
        self._fetch = fetch
        self._allowed_hosts = allowed_hosts
        self._rules = rules or LinkRules()
        self._seen: dict[str, LinkCheck] = {check.url: check for check in known}

    @property
    def requests_made(self) -> int:
        """How many distinct URLs were fetched so far."""
        return len(self._seen)

    async def check(self, product: Product) -> LinkCheck:
        cached = self._seen.get(product.product_url)
        if cached is not None:
            return cached
        result: LinkResult | None = None
        try:
            result = await self._fetch(product.product_url)
        except Exception as exc:  # any failure of the fetch is a failed link
            problems = [f"the request failed ({type(exc).__name__})"]
        else:
            problems = (
                [THROTTLED_LINK_NOTE]
                if result.throttled
                else evaluate_link(
                    product, result, self._allowed_hosts.get(product.store), self._rules
                )
            )
        checked = LinkCheck(
            url=product.product_url,
            store=product.store,
            product_title=product.title,
            ok=not problems,
            problems=problems,
            not_checked=result is not None and result.throttled,
            result=result,
        )
        self._seen[product.product_url] = checked
        return checked

    async def check_all(self, products: Sequence[Product]) -> list[LinkCheck]:
        """Check each product in turn. Sequential on purpose: store politeness (BRD Rule 2)."""
        return [await self.check(product) for product in products]
