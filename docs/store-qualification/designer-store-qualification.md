# Designer-brand qualification: seven Gulf designer brands (Module 2.6, 2026-10-08)

Why this exists: the business named eight Gulf designer brands it would like the demo to cover. Eight is Marzook (handbags and accessories, out of scope: **not tested, no request sent to its site**) plus seven clothing brands, which this pass tested with the honest client: could each be searched the way the six current stores are (a live search on the store's own endpoint, a link to the store's own product page, a price in the store's currency)? This file is the overview; each brand that was contacted has its own report next to it.

## Result in one paragraph

Of the seven clothing brands, **four are GO** (all Shopify, all reading through `/search/suggest.json`, all with a `robots.txt` that leaves search open): Bazza Alzouman (evening gowns), Heba Shaikh (ready-to-wear essentials), Hamsa by Sharifa AlGhanim (abayas and kaftans) and Manal Smaoui (tailored sets, kaftans and dresses). **Three are DROP**: Montaha Couture (the shop's TLS certificate does not verify, so `robots.txt` could not be read), Yousef Al-Jasmi (his domain now redirects to an unrelated site, and no working store was found) and N.BEE (no online store of its own found; only an Instagram account, so no request was sent). The finding that matters most: **none of the four GO stores prices in AED**. Bazza Alzouman, Hamsa and Manal Smaoui price in Kuwaiti dinars (KWD, with three decimals, such as `"260.000"`), and Heba Shaikh in pounds (GBP); none offers an AED storefront at a URL a stateless client could request. As the project stands, a KWD store would return no products (`parse_price` raises `PriceFormatError` on `"260.000"`, checked by running it) and, even once parsed, its products would be left out of a mixed AED result set by the tier shaper. So "GO" here means "can be read", and **adding any of them needs a currency decision before an adapter**. None of the four sells an abaya or any garment below about AED 660, so they do not fill the open gap for everyday abayas under AED 600.

## Method and limits

- **Finding the shops.** `WebSearch` only, for each brand name, then a second search restricted to a guessed domain (`allowed_domains`) to see which URL shapes were indexed. Two third-party blog pages (a Kuwait fashion-brands list and a "top women clothing brands" list) were read with `WebFetch` only to look for N.BEE's link; neither is a brand host. `WebFetch` was never used on a brand's own site. Search summaries were treated as hints. For each shop the evidence that it is the brand's own (not a stockist) is in its report.
- **Requests.** User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, https only, no cookies, no retries, no proxy, no browser, certificate verification on. `robots.txt` was the first request to every host and was judged with protego 0.7.0 on the full URL including its query string, using the same malformed-rule reading as `scripts/qualify_store.py`. At least 1.2 s between requests to a host. **Redirects were never followed automatically**: the driver sends one request per call and stops on a redirect so that the decision is mine (the one redirect met, at `yousefaljasmi.com`, led to a different domain and was not followed). A 403, 429, challenge or login wall would have marked the host blocked; none occurred. No UCP/MCP, agent, cart, checkout, account or `/api/` URL was requested, and no `?add-to-cart=` URL. The AI-agent comments that Shopify's default `robots.txt` carries (a preference for UCP/MCP endpoints) were recorded as data in each report and not acted on. No request went to any of the six current demo stores, to Marzook, or to any other store.
- **Driver.** `scripts/qualify_store.py` runs three queries and follows redirects itself, so a small driver was used instead (appendix). It imports that script's `Fetcher` and `MALFORMED_RULE` unchanged, sends one request per call, refuses any URL protego disallows, and keeps a per-host counter capped at 6 in a state file outside the repository. A second small script read the saved bodies offline (no network) to count products, prices and fields. Nothing under `src/`, `scripts/` or `config/` was changed.
- **Totals.** **20 requests to 6 hosts** (7 host names): 4 each to `bazzaalzouman.com`, `hebashaikh.com`, `manalsmaoui.com` and `hamsakw.com` (robots.txt, two searches, one product page); 2 to `yousefaljasmi.com` (a 404 robots.txt and a 301 home page); 2 to Montaha Couture (`robots.txt` on `montahacouture.com` and on `www.montahacouture.com`, both failed in the TLS handshake). N.BEE and Marzook: 0. No store exceeded 6 requests, and the two rejected stores stopped at 2.
- **Limits.** One machine and network, one day. Sale states are transient (for example 10 of 20 Hamsa records were discounted). KWD and GBP to AED figures below are **approximations** (roughly AED 12 per KWD and 4.9 per GBP), not observed and not an exchange-rate source; only the AED-per-USD peg is fixed. Terms of use were not read for any store. "Not seen" means "not in these responses".

## Overview table

| # | Brand (what the business said) | Official site, and how known | Platform | Verdict | Currency | Price span seen | What it sells (as seen) | Requests |
|---|---|---|---|---|---|---|---|---|
| 1 | **Bazza Alzouman** (evening gowns, modern couture) | `bazzaalzouman.com`: own About page, vendor and JSON-LD brand "Bazza Alzouman", shop `bazza-alzouman-shop`; stockists (Moda Operandi, Ounass) are separate | Shopify | **GO**, currency flag | **KWD** (the UAE country pick is also KWD) | KWD 206 to 380 (about AED 2,500 to 4,600) | 17 gowns and dresses | 4 |
| 2 | **N.BEE** (everyday and modest: abayas, kaftans, dresses) | None found. Only Instagram `@n.beekw`; a blog's "SHOP N.BEE" link points to it. (`nbee.shop` is an unrelated Florida footwear brand and was not contacted) | n/a | **DROP** (no own online store found) | n/a | n/a | n/a | 0 |
| 3 | **Montaha Couture** (luxury occasion wear) | `montahacouture.com` (probable: brand pages found, not cross-checked) | WooCommerce by URL shape (unconfirmed) | **DROP for now** (TLS certificate invalid on both names; robots.txt unread) | USD per search snippets (unconfirmed) | USD 620 to 1,140 per snippets, not observed | evening dresses, kaftans, abayas (snippets) | 2 |
| 4 | **Heba Shaikh** (sustainable luxury classics) | `hebashaikh.com`: Founder, Philosophy, Quality pages, vendor "Heba Shaikh", shop `hebashaikh` | Shopify | **GO**, currency flag | **GBP** (picker lists AED but only through a cookie form) | GBP 35 to 950 (about AED 170 to 4,650) | 13 women's essentials; one dress style | 4 |
| 5 | **Yousef Al-Jasmi** (crystal and sequin gowns) | `yousefaljasmi.com` named as official by a search answer; today `robots.txt` is 404 and the home page 301s to `poltekkeskrui.org`. The `.net` look-alike with a "Store" and spam pages was not contacted | unknown | **DROP** (no working store; domain redirects off-site) | n/a | n/a | n/a | 2 |
| 6 | **Hamsa** by Sharifa Al Ghanim (abayas, kaftans, modest wear) | `hamsakw.com`: own `/pages/stockist` lists other retailers separately, vendor "Hamsa by Sharifa AlGhanim", shop `hamsakw` | Shopify | **GO**, currency flag | **KWD** (all 201 regions in its table) | KWD 20 to 320 by `price`; KWD 55 to 365 for the garments (about AED 660 to 4,400) | 20 abayas, kaftans, kaftan dresses | 4 |
| 7 | **Manal Smaoui** (tailored understated luxury) | `manalsmaoui.com`: Our Story and Flagship Store pages, vendor "MANAL SMAOUI", shop `manalsmaoui-8058` | Shopify | **GO**, currency flag | **KWD** (a converter widget lists AED; the prices are KWD) | KWD 5 to 85 (about AED 60 to 1,000; garments about AED 350 to 1,020) | 13 kaftans, dresses, blazer, trousers, skirts, top | 4 |
| 8 | Marzook (handbags and accessories) | not tested: accessories are out of scope | n/a | not tested | n/a | n/a | n/a | 0 |

Per-brand reports: [Bazza Alzouman](bazza-alzouman.md), [Heba Shaikh](heba-shaikh.md), [Hamsa](hamsa-kw.md), [Manal Smaoui](manal-smaoui.md), [Montaha Couture](montaha-couture.md), [Yousef Al-Jasmi](yousef-aljasmi.md). Samples for the four GO stores are in `samples/bazza-alzouman/`, `samples/heba-shaikh/`, `samples/hamsa-kw/` and `samples/manal-smaoui/`.

## What adding the GO stores would give the demo, and what it would not

**What it would give.**

- A source of **evening gowns that no current store carries**: 17 gowns and dresses from Bazza Alzouman, which fits the burgundy evening gown photo better than any Western store seen so far (Club L London sells occasion dresses at AED 649 to 1,790, but not gowns).
- **Abayas and kaftans from Gulf labels**: Hamsa has 10 abayas and 10 kaftans in two searches, Manal Smaoui has kaftans and Hamsa kaftan-style dresses. Hanayen and Maison Arabelle (qualified earlier, not enabled) remain the other abaya sources; Hamsa would be a third.
- **Tailored sets for tops, outerwear and bottoms**: Manal Smaoui (blazer, trousers, skirts, a top) at an estimated AED 350 to 420 per piece, which is the one set of prices among the four that sits in the range of the existing Nautica, Sacoor Brothers and Oh Polly. Heba Shaikh adds tops, shirts, trousers, skirts and coats at premium prices.
- Brands that have a story the shopper recognises (the business chose them), each linking to its own shop.

**What it would not give.**

- **Abayas under AED 600.** Not met. The cheapest abaya in Hamsa's responses is KWD 75 (about AED 900) and its cheapest garment, a kaftan, is KWD 55 (about AED 660). No abaya appeared at Manal Smaoui, Heba Shaikh or Bazza Alzouman. Everyday abayas at AED 59 to 399 remain without a readable source (the earlier pass listed Sara Arabia, probably not Shopify, as the lead).
- **Anything budget.** The cheapest garments are Heba Shaikh's T-shirts at GBP 35 (about AED 170) and Manal Smaoui's trousers at KWD 29 (about AED 350). **No mid-priced gowns either:** Bazza Alzouman starts at KWD 206 (about AED 2,500).
- **Couture prices sit at the top of, not far beyond, the existing range.** The six enabled stores run from AED 39.50 to 4,430. Bazza Alzouman (about AED 2,500 to 4,600), the dearer Hamsa pieces (up to about AED 4,400) and Heba Shaikh's coats and dress (about AED 4,450) land in the upper end of that range, and a few just above it. They would populate Luxury, not Budget or Mid-range, so they add depth at the top and nothing below.
- **Shoes.** None of the four sells any.
- **Montaha Couture, Yousef Al-Jasmi and N.BEE** (three of the user's seven) stay unreachable: a TLS fault, a dead domain and no online shop.

**What it would cost (the currency decision).**

- Three stores (Bazza Alzouman, Hamsa, Manal Smaoui) price in KWD with three decimals; one (Heba Shaikh) in GBP. `src/vga/stores/prices.py` accepts only bare prices of the form `^\d+\.\d{2}$`, so every KWD record would be dropped with a `PriceFormatError` until a three-decimal format is added (its own docstring says new formats are added when a store report shows one; these reports do).
- `src/vga/tiers/shaper.py` shapes only the products in the most common currency of the result set, so with six AED stores the KWD and GBP products would be left out with a warning. To show them, the project would need one of: a dated fixed conversion rate in the store config (the KWD and GBP rates float, unlike the USD peg, so the rate is a documented approximation), a separate non-AED section, or no use of these stores. This is a decision for the orchestrator and, if a conversion is chosen, probably an ADR and a deliberate departure noted in plan section 12.3. It is not an adapter task.
- Hamsa also needs adapter work: on 5 of its 10 abaya records `price` is the cheapest variant (probably a scarf, KWD 20 to 35), not the abaya (KWD 75 to 365), and the `shopify` strategy reads `price` only.
- Manal Smaoui's and Hamsa's `type` fields are collection labels or inconsistent, and handles do not match titles; category and link need the right fields.
- Shopify's default `robots.txt` on all four carries a comment preferring UCP/MCP endpoints for agents. Our reads are allowed by the rules; the preference is for the terms-of-use review (BRD Rule 6).

## Adapter facts per GO store

| Store id (proposed) | Search URL | `allowed_hosts` | Currency | Tier guess | Images (`cdn.shopify.com` prefix) | Example record |
|---|---|---|---|---|---|---|
| `bazza-alzouman` | `https://bazzaalzouman.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10` | `bazzaalzouman.com`, `cdn.shopify.com` | KWD, 3 decimals | luxury | `/s/files/1/0244/0753/9793/` | "Halter Dress", `"265.000"` |
| `heba-shaikh` | `https://hebashaikh.com/search/suggest.json?...` (same shape) | `hebashaikh.com`, `cdn.shopify.com` | GBP, 2 decimals; no JSON-LD on product pages | premium to luxury | `/s/files/1/0288/9154/5684/` | "Esme Dress", `"910.00"` |
| `hamsa-kw` | `https://hamsakw.com/search/suggest.json?...` (same shape) | `hamsakw.com`, `cdn.shopify.com` | KWD, 3 decimals; `price` can be a scarf variant | premium to luxury | `/s/files/1/0107/8453/8705/` | "Riwaq Kaftan", `"95.000"` |
| `manal-smaoui` | `https://manalsmaoui.com/search/suggest.json?...` (same shape) | `manalsmaoui.com`, `cdn.shopify.com` | KWD, 3 decimals | mid to premium | `/s/files/1/0682/5885/7253/` | "AICHA KAFTAN - BROWN", `"85.000"` |

Examples from the responses (title, price in the store's currency): Bazza Alzouman "Strapless Gown With Side Organza Ruched Drape" 245.000, "Off Shoulder Mermaid Gown and Asymmetric Train" 330.000, "Off-Shoulder Statement Sleeve Crepe Gown" 380.000; Heba Shaikh "Tale Blazer" 290.00 (was 955.00), "Tale Trousers" 190.00, "Amina Crop Trench" 895.00; Hamsa "Heyah Abaya" 185.000, "Rania Kaftan" 320.000, "Amber Kaftan" 55.000; Manal Smaoui "THE BELLE DRESS - BLACK (LIMITED EDITION)" 55.000, "The Ladylike Blazer - White" 35.000, "THE MUSE PANTS - BLACK" 29.000.

Shared quirks (all four): the suggest response has no currency; links carry tracking parameters (`?_pos=...&_psq=...`) to be dropped; `body` is store HTML and must not be rendered; each search returns at most 10 records and the stores pad answers with unrelated items (Heba Shaikh's `kaftan` returned no kaftan), so the ranker must filter by category.

## Not verified

Terms of use for every store. Behaviour from any other network. Whether Montaha Couture's certificate problem is temporary, and everything about its platform, robots.txt, prices and currency (all from search snippets). Whether N.BEE has an online shop that web search could not find (the user may know a URL). Whether `yousefaljasmi.com`'s redirect is a lapse, parking or hijack, and whether the designer has any current shop. Whether `yousefaljasmi.net` is his (not contacted). The `/ar/` prefix at Bazza Alzouman, the euro market prefixes at Heba Shaikh and `/en-sa/` at Manal Smaoui. Pagination and `limit` above 10. Searches for words other than `dress`, `gown`, `kaftan` and `abaya` (for example blazer, trousers, shoes). Whether the KWD and GBP rates used for AED estimates match any rate the project would adopt. Menswear at Heba Shaikh (reported by press, not seen).

## Appendix: the driver used for 2.6

Saved outside the repository as `q.py`; run from the repo root as `uv run --with httpx --with protego python q.py robots https://<host>` first, then `... q.py fetch <https url> <name>` once per request, and `... q.py check <host> <url>...` or `... q.py show <host>` offline. It is the script that was run. It imports `scripts/qualify_store.py` unchanged.

```python
"""Designer-store qualification driver (Module 2.6): ONE request per call, redirects never followed.

Reuses scripts/qualify_store.py unchanged for the network (Fetcher._once: fixed honest User-Agent,
https only, no cookies, no retries, 403/429/challenge-page detection) and for the robots.txt reading
rule (MALFORMED_RULE). Run from the repo root:

    uv run --with httpx --with protego python q.py robots https://example.com
    uv run --with httpx --with protego python q.py fetch https://example.com/search/suggest.json?q=dress suggest-dress
    uv run --with httpx --with protego python q.py check example.com <url> [<url> ...]   # offline
    uv run --with httpx --with protego python q.py show example.com                    # offline

Per host: robots.txt must be the first request; at most 6 requests in total (redirect hops count);
at least 1 s between requests; a 403/429/challenge marks the host blocked and no further request is
made to it; a URL that robots.txt disallows (protego, full URL with query string) is refused before
any request is sent. State lives in work/state.json next to this file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from protego import Protego

spec = importlib.util.spec_from_file_location("qualify_store", Path("scripts/qualify_store.py"))
qs = importlib.util.module_from_spec(spec)
sys.modules["qualify_store"] = qs
spec.loader.exec_module(qs)

WORK = Path(__file__).resolve().parent / "work"
STATE = WORK / "state.json"
MAX_PER_HOST = 6
GAP_S = 1.2


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(state: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


def ext_for(ctype: str) -> str:
    if "json" in ctype:
        return "json"
    if "plain" in ctype:
        return "txt"
    return "html"


def parsers(host: str) -> tuple[Protego, Protego]:
    body = (WORK / host / "robots.txt").read_text(encoding="utf-8")
    return Protego.parse(body), Protego.parse(qs.MALFORMED_RULE.sub(r"\1*", body))


def do_fetch(url: str, name: str, is_robots: bool) -> int:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https":
        print("REFUSED: https only")
        return 2
    state = load()
    h = state.setdefault(host, {"count": 0, "last": 0.0, "blocked": None, "log": [], "robots_status": None})
    if h["blocked"]:
        print(f"REFUSED: host {host} is blocked ({h['blocked']}); no further requests")
        return 2
    if h["count"] >= MAX_PER_HOST:
        print(f"REFUSED: {host} already has {h['count']} requests")
        return 2
    if is_robots:
        if h["count"] != 0:
            print("REFUSED: robots.txt must be the first request to a host")
            return 2
    else:
        if h["robots_status"] is None:
            print("REFUSED: robots.txt not fetched yet for this host")
            return 2
        if h["robots_status"] == 200:
            strict, conservative = parsers(host)
            ok = conservative.can_fetch(url, qs.USER_AGENT)
            print(f"robots (protego): {'ALLOW' if ok else 'DISALLOW'} {url}  (strict: {strict.can_fetch(url, qs.USER_AGENT)})")
            if not ok:
                print("REFUSED: robots.txt disallows this URL; no request sent")
                return 2
        else:
            print(f"robots.txt status was {h['robots_status']}: no rules, everything allowed (RFC 9309)")
    wait = h["last"] + GAP_S - time.time()
    if wait > 0:
        time.sleep(wait)
    h["count"] += 1
    n = h["count"]
    h["last"] = time.time()
    save(state)
    fetcher = qs.Fetcher(None)
    fetcher.client.timeout = httpx.Timeout(15.0)
    entry = {"n": n, "url": url}
    try:
        page, location = fetcher._once(url)
    except qs.Stop as exc:
        entry["result"] = f"STOP: {exc.verdict}: {exc}"
        h["log"].append(entry)
        if not isinstance(exc, qs.Unreachable):
            h["blocked"] = str(exc)
        save(state)
        print(f"STOP ({n} requests to {host}): {exc.verdict}: {exc}")
        return 3
    entry.update(status=page.status, bytes=page.nbytes, ctype=page.content_type, location=location)
    h["log"].append(entry)
    if is_robots:
        h["robots_status"] = page.status
        if "html" in page.content_type.lower() and page.status == 200:
            h["robots_status"] = "html"
    save(state)
    out = WORK / host
    out.mkdir(parents=True, exist_ok=True)
    if location is None:
        (out / f"{name}.{ext_for(page.content_type)}").write_text(page.body, encoding="utf-8")
    print(f"request #{n} to {host}: status {page.status}, {page.nbytes} bytes, type {page.content_type!r}, location {location!r}")
    return 0


def main() -> int:
    cmd = sys.argv[1]
    if cmd == "robots":
        origin = sys.argv[2].rstrip("/")
        return do_fetch(origin + "/robots.txt", "robots", True)
    if cmd == "fetch":
        return do_fetch(sys.argv[2], sys.argv[3], False)
    if cmd == "check":
        strict, conservative = parsers(sys.argv[2])
        for u in sys.argv[3:]:
            print(f"{'ALLOW' if conservative.can_fetch(u, qs.USER_AGENT) else 'DISALLOW'} (strict {strict.can_fetch(u, qs.USER_AGENT)}): {u}")
        print("crawl-delay:", conservative.crawl_delay(qs.USER_AGENT), "| sitemaps:", list(strict.sitemaps)[:3])
        return 0
    if cmd == "show":
        state = load()
        print(json.dumps(state.get(sys.argv[2]), indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
```
