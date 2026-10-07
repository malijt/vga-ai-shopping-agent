#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "protego>=0.7"]
# ///
"""Store qualification: can an honest client read this store's search results?

    uv run scripts/qualify_store.py https://en-ae.aivi.com "black blazer" jacket shoes
    uv run scripts/qualify_store.py https://en-ae.aivi.com --product-url <https url>
    uv run scripts/qualify_store.py https://www.namshi.com "black blazer" --search-path "/uae-en/search?q={query}"

Rules enforced here (BRD Rule 2): one fixed identifying User-Agent, robots.txt first and
honoured, https only, at most 1 request/s (slower if robots.txt asks), at most 12 requests,
no retries, and a stop on the first 403/429, CAPTCHA/challenge page or login wall.
It never changes headers or uses cookies, proxies or a browser to get past a block.

Exit code: 0 GO, 1 PARTIAL or NO DATA, 2 DROP, 3 UNDETERMINED.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx
from protego import Protego  # not urllib.robotparser: on Python 3.12 it ignores * and $ wildcards

USER_AGENT = "vga-shopping-agent-demo/0.1 (store-qualification research)"
TIMEOUT_S = 6.0
MAX_REQUESTS = 12
MAX_QUERIES = 3
MAX_REDIRECTS = 3
MAX_BYTES = 4_000_000
# Specific page-level markers of a bot challenge, looked for in the first 20 KB of a response.
CHALLENGE_MARKERS = (
    "just a moment...",
    "cf-browser-verification",
    "cf-chl-",
    "px-captcha",
    "captcha-delivery",
    "attention required! | cloudflare",
    "access denied",
    "pardon our interruption",
    "_incapsula_resource",
    "are you a robot",
    "verify you are human",
    "enable javascript and cookies to continue",
)
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|customer/account/login|account/login)\b", re.I)
NAME_KEYS = {"name", "title", "productname", "product_name"}
CARD_CLASS = re.compile(
    r'class="[^"]*(?:product-?card|product-?tile|product-?item|plp-?product|product-?list-?item)[^"]*"',
    re.I,
)
FIELD_HINTS = {
    "title": ("name", "title"),
    "price": ("price",),
    "currency": ("currency",),
    "image": ("image", "img", "thumbnail", "media"),
    "url": ("url", "link", "href", "slug"),
}


class Stop(Exception):
    """Ends the run with a verdict."""

    verdict = "UNDETERMINED"


class Blocked(Stop):
    verdict = "DROP (blocked)"


class Unreachable(Stop):
    verdict = "UNDETERMINED (unreachable from this machine; re-test from the user's network)"


class Moved(Stop):
    """A redirect to another domain is not a block, but it is not followed either: the new host
    has its own robots.txt, so the run is repeated against it."""

    def __init__(self, target: str) -> None:
        super().__init__(f"redirected to another domain: {target}")
        self.verdict = f"UNDETERMINED (store moved to {urlsplit(target).hostname}; re-run against that base URL)"


class BudgetExhausted(Stop):
    verdict = "UNDETERMINED (request budget exhausted)"


@dataclass
class Page:
    url: str
    status: int
    content_type: str
    body: str
    nbytes: int


@dataclass
class Analysis:
    path: str  # store_json | json_ld | embedded_json | css | none
    count: int
    evidence: list[str] = field(default_factory=list)
    hints: dict[str, list[str]] | None = None  # which keys look like each required field


def site(url_or_host: str) -> str:
    host = urlsplit(url_or_host).hostname or url_or_host
    return ".".join(host.split(".")[-2:])


class Fetcher:
    """The only code that touches the network: https only, rate limited, counted, no retries."""

    def __init__(self, save_dir: Path | None) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
            timeout=TIMEOUT_S,
            follow_redirects=False,  # followed by hand so that every hop is counted and checked
        )
        self.count = 0
        self.interval = 1.0  # raised to the robots.txt Crawl-delay when that is larger
        self.save_dir = save_dir
        self._last = 0.0

    def get(self, url: str, save_as: str | None = None) -> Page:
        origin_site = site(url)
        for _ in range(MAX_REDIRECTS + 1):
            page, location = self._once(url)
            if location is None:
                self._save(page, save_as)
                return page
            url = urljoin(url, location)
            if site(url) != origin_site:
                raise Moved(url)
            if LOGIN_PATH.search(urlsplit(url).path):
                raise Blocked(f"login wall: redirected to {url}")
        raise Blocked(f"more than {MAX_REDIRECTS} redirects")

    def _save(self, page: Page, stem: str | None) -> None:
        if stem and self.save_dir:
            ext = "json" if "json" in page.content_type else "txt" if "plain" in page.content_type else "html"
            self.save_dir.mkdir(parents=True, exist_ok=True)
            (self.save_dir / f"{stem}.{ext}").write_text(page.body, encoding="utf-8")

    def _once(self, url: str) -> tuple[Page, str | None]:
        if urlsplit(url).scheme != "https":
            raise Blocked(f"refusing non-https URL {url}")
        if self.count >= MAX_REQUESTS:
            raise BudgetExhausted()
        time.sleep(max(0.0, self._last + self.interval - time.monotonic()))
        self.count += 1
        started = self._last = time.monotonic()
        try:
            with self.client.stream("GET", url) as r:
                raw = b""
                for chunk in r.iter_bytes():
                    raw += chunk
                    if len(raw) >= MAX_BYTES:
                        break
                status, ctype = r.status_code, r.headers.get("content-type", "")
                location = r.headers.get("location")
                text = raw.decode(r.charset_encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            print(f"  GET {url} -> ERROR {type(exc).__name__}")
            raise Unreachable(f"{type(exc).__name__}: {exc}") from exc
        print(f"  GET {url} -> {status}, {len(raw)} bytes, {time.monotonic() - started:.1f}s")
        if status in (403, 429):
            raise Blocked(f"HTTP {status} on {url}")
        if status in (301, 302, 303, 307, 308) and location:
            return Page(url, status, ctype, "", len(raw)), location
        marker = next((m for m in CHALLENGE_MARKERS if m in text[:20_000].lower()), None)
        if marker:
            raise Blocked(f"challenge page marker {marker!r} on {url}")
        return Page(url, status, ctype, text, len(raw)), None


# ---------------------------------------------------------------- robots.txt


# A rule value that starts with neither / nor * (the site's `Disallow: ?q=`) matches nothing under
# RFC 9309, so a strict parser allows those URLs. The site plainly meant to block them: read as `*?q=`.
MALFORMED_RULE = re.compile(r"(?im)^(\s*(?:dis)?allow\s*:\s*)(?![/*\s]|$)")


class Robots:
    """robots.txt decisions with Protego. `allows` reads malformed rules conservatively;
    `strict_allows` is Protego on the file exactly as served (the two differ only for such rules)."""

    def __init__(self, fetcher: Fetcher, origin: str) -> None:
        page = fetcher.get(f"{origin}/robots.txt", save_as="robots")
        if page.status >= 500:
            raise Stop(f"robots.txt returned HTTP {page.status}; RFC 9309 says treat as disallow-all")
        if page.status >= 400:  # no robots.txt at all: everything allowed (RFC 9309)
            print(f"robots.txt: HTTP {page.status}, no rules, everything allowed")
            self.strict = self.conservative = Protego.parse("")
            return
        if "html" in page.content_type.lower():
            raise Stop(f"{page.url} is an HTML page, not a robots file (redirect?); re-run against the canonical host")
        self.strict = Protego.parse(page.body)
        self.conservative = Protego.parse(MALFORMED_RULE.sub(r"\1*", page.body))
        lines = [ln.strip() for ln in page.body.splitlines()]
        rules = [ln for ln in lines if re.match(r"(?i)(dis)?allow\s*:", ln)]
        print(f"robots.txt: HTTP {page.status}, {page.nbytes} bytes, {len(rules)} Allow/Disallow lines (Protego)")
        for ln in rules:
            if re.search(r"search|\bq=", ln, re.I):
                print(f"  search-related rule: {ln}")
            if MALFORMED_RULE.match(ln):
                print(f"  note: malformed rule {ln!r} is read conservatively as '*{ln.partition(':')[2].strip()}'")
        delay = self.conservative.crawl_delay(USER_AGENT)
        if delay and float(delay) > fetcher.interval:
            fetcher.interval = float(delay)
        print(f"  crawl-delay: {delay or 'none'}; request interval {fetcher.interval:g}s")
        sitemaps = list(self.strict.sitemaps)
        for sitemap in sitemaps[:2]:
            print(f"  Sitemap: {sitemap}")
        if len(sitemaps) > 2:
            print(f"  ... {len(sitemaps)} Sitemap lines in total")

    def allows(self, url: str) -> bool:
        return self.conservative.can_fetch(url, USER_AGENT)

    def strict_allows(self, url: str) -> bool:
        return self.strict.can_fetch(url, USER_AGENT)


# ---------------------------------------------------------------- data path detection


def find_products(node: object, path: str = "$", out: list | None = None) -> list[tuple[str, dict]]:
    """Dicts that look like product records (a name/title plus a price/offers key) and their path."""
    out = [] if out is None else out
    if isinstance(node, dict):
        keys = [k.lower() for k in node]
        if any(k in NAME_KEYS for k in keys) and any("price" in k or k == "offers" for k in keys):
            out.append((path, node))
        for k, v in node.items():
            find_products(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for v in node:
            find_products(v, f"{path}[]", out)
    return out[:2000]


def field_hints(record: dict) -> dict[str, list[str]]:
    keys = {k.lower(): k for k in record}
    if isinstance(record.get("offers"), dict):
        keys.update({f"offers.{k}".lower(): f"offers.{k}" for k in record["offers"]})
    return {
        name: [orig for low, orig in keys.items() if any(h in low for h in hints)]
        for name, hints in FIELD_HINTS.items()
    }


def script_blocks(html: str) -> list[tuple[str, str]]:
    return [(m[1], m[2]) for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S | re.I)]


def json_ld_products(html: str) -> list[dict]:
    found: list[dict] = []
    for attrs, body in script_blocks(html):
        if "ld+json" not in attrs.lower():
            continue
        try:
            stack = [json.loads(body)]
        except ValueError:
            continue
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                types = node.get("@type")
                if "Product" in (types if isinstance(types, list) else [types]):
                    found.append(node)
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return found


def embedded_json_products(html: str) -> tuple[str, list[tuple[str, dict]]]:
    """Best product-like records inside <script type=application/json>, __NEXT_DATA__ or window.X = {...}."""
    candidates: list[tuple[str, str]] = []
    for attrs, body in script_blocks(html):
        label = re.search(r'id="([^"]+)"', attrs)
        if "json" in attrs.lower() or "__NEXT_DATA__" in attrs:
            candidates.append((label[1] if label else "script[application/json]", body))
        candidates += [
            (f"window.{m[1]}", body[m.end() :]) for m in re.finditer(r"window\.(__\w+__|\w+State)\s*=\s*", body)
        ]
    best: tuple[str, list[tuple[str, dict]]] = ("", [])
    for label, text in candidates:
        try:
            data, _ = json.JSONDecoder().raw_decode(text.lstrip())
        except ValueError:
            continue
        products = find_products(data)
        if len(products) > len(best[1]):
            best = (label, products)
    return best


def analyse(page: Page) -> Analysis:
    """Look for product data in this order: store_json, json_ld, embedded_json, css."""
    text = page.body.lstrip()
    if "json" in page.content_type.lower() or text[:1] in ("{", "["):
        try:
            records = find_products(json.loads(text))
        except ValueError:
            records = []
        if records:
            return Analysis(
                "store_json",
                len(records),
                [f"JSON response; product records at {records[0][0]}"],
                field_hints(records[0][1]),
            )
    ld = json_ld_products(page.body)
    if ld:
        return Analysis("json_ld", len(ld), [f"{len(ld)} JSON-LD Product node(s)"], field_hints(ld[0]))
    label, records = embedded_json_products(page.body)
    if records:
        return Analysis(
            "embedded_json",
            len(records),
            [f"in {label}; product records at {records[0][0]}"],
            field_hints(records[0][1]),
        )
    cards = CARD_CLASS.findall(page.body)
    if cards:
        return Analysis("css", len(cards), [f"{len(cards)} product-card class matches, e.g. {cards[0][:100]}"])
    shell = re.findall(r'id="(root|app|__next|__nuxt)"', page.body)
    return Analysis("none", 0, [f"no product data; HTML shell markers: {shell or 'none'}; {len(page.body)} chars"])


def verdict_for(a: Analysis) -> str:
    if a.path == "none":
        return "NO DATA (no product data for a plain HTTP client)"
    if a.hints is None:
        return "PARTIAL (card markup only; check the fields by hand)"
    missing = [name for name, keys in a.hints.items() if not keys]
    return f"PARTIAL (no key found for: {', '.join(missing)})" if missing else "GO"


# ---------------------------------------------------------------- main


def run(args: argparse.Namespace, fetcher: Fetcher) -> tuple[str, str]:
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(args.base_url))
    if not origin.startswith("https://"):
        raise Stop("base_url must be https")
    robots = Robots(fetcher, origin)
    verdicts: list[str] = []
    for i, query in enumerate(args.queries[:MAX_QUERIES], 1):
        url = origin + args.search_path.format(query=quote(query, safe=""))
        allowed = robots.allows(url)
        print(f"search {query!r}: robots {'allows' if allowed else 'DISALLOWS'} {url}")
        if allowed != robots.strict_allows(url):
            print("  note: Protego on the file as served would ALLOW this URL (see malformed rule above)")
        if not allowed:
            return "DROP (robots)", f"robots.txt disallows the search path for us: {url}"
        a = analyse(fetcher.get(url, save_as=f"search-{i}"))
        print(f"  data path: {a.path}, products found: {a.count}")
        for line in a.evidence + ([f"first record fields: {a.hints}"] if a.hints else []):
            print(f"    {line}")
        verdicts.append(verdict_for(a))
    if args.product_url:
        if site(args.product_url) != site(origin):
            raise Stop("product URL is off the store's domain")
        if not robots.allows(args.product_url):
            return "DROP (robots)", f"robots.txt disallows the product page: {args.product_url}"
        ld = json_ld_products(fetcher.get(args.product_url, save_as="product").body)
        print(f"  product page: {len(ld)} JSON-LD Product node(s)" + (f"; fields {field_hints(ld[0])}" if ld else ""))
    if not verdicts:
        return "UNDETERMINED (no query given)", "robots.txt checked only"
    return min(
        verdicts, key=lambda v: ("GO", "PARTIAL", "NO DATA").index(v.split(" (")[0])
    ), f"{len(verdicts)} search page(s) read"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url", help="store origin, e.g. https://en-ae.aivi.com")
    ap.add_argument("queries", nargs="*", help=f"search queries (at most {MAX_QUERIES} are used)")
    ap.add_argument("--search-path", default="/search?q={query}", help="path template with {query}")
    ap.add_argument("--product-url", help="one public product page to check for JSON-LD")
    ap.add_argument("--save-dir", type=Path, help="write the fetched bodies here (to build samples)")
    args = ap.parse_args()
    fetcher = Fetcher(args.save_dir)
    try:
        verdict, why = run(args, fetcher)
    except Stop as exc:
        verdict, why = exc.verdict, str(exc)
    print(f"\nVERDICT: {verdict}\n  why: {why}\n  requests made: {fetcher.count}")
    return {"GO": 0, "PARTIAL": 1, "NO DATA": 1, "DROP": 2}.get(verdict.split(" (")[0], 3)


if __name__ == "__main__":
    sys.exit(main())
