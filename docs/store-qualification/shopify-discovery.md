# Shopify storefront discovery (Module 2.4, 2026-10-07)

Why this exists: the Phase 2 gate failed because only three stores could be read, and two of those are women-only single-brand stores (see [`SUMMARY.md`](SUMMARY.md), risk R20). Route A was chosen: find more GCC fashion storefronts on Shopify, where one data path (`/search/suggest.json`) already worked. This file holds the candidate list (2.4.1), the qualification outcome of each candidate that was tested (2.4.2) and the coverage table (2.4.3).

## Result in one paragraph

23 named candidates were listed, plus 8 sneaker stores found by name only. 8 were tested, in an order chosen to spread tiers and to put menswear first, and **6 are GO**: Sacoor Brothers UAE, Giordano UAE, The Bear House UAE, Nautica UAE, Good Times and Maison D'Vie. 2 were dropped on robots.txt (Ocean Drive, Mad Kicks), each after one request. Testing stopped at the sixth GO store, as the assignment asks, so the other 15 named candidates were not tested. With Oh Polly UAE, Club L London UAE and Luxury For You there are now **9 readable stores**, 7 of which can answer a men's query (see the end of this file).

## Method and limits

- **Finding candidates.** `WebSearch` only, never memory, for whether a store uses Shopify. Generic queries (UAE menswear, streetwear, multi-brand boutiques, sneaker stores, formal wear, Pakistani brands, GCC Shopify directories) produced names; a second search restricted to each candidate's own domain (`allowed_domains`) showed that domain's URL shapes. Two directory pages (storeleads.app) were read with `WebFetch`, which is not a store site; they listed almost no GCC fashion stores. `WebFetch` was never used on a store site.
- **Shopify identification, two levels.** Level A (tested candidates): confirmed from the store's own `robots.txt` (the comment `# Shopify storefront...` or `# we use Shopify as our ecommerce platform`, or Shopify-only rules such as `/.well-known/shopify/monorail`), plus `cdn.shopify.com` image URLs and, for GO stores, Shopify markers in the product page (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Level B (untested candidates): only the URL shape seen in search results (`/collections/{handle}`, `/products/{handle}`, `/blogs/{blog}/{article}`, `?variant={id}`, `/password`). These shapes are Shopify's defaults but are **not proof**; a Level B candidate is "probably Shopify" until its robots.txt is fetched.
- **Requests.** Every request to a store used `scripts/qualify_store.py`'s `Fetcher` and `Robots` classes unchanged: the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, https only, at most 1 request per second per store, no retries, no cookies, stop on the first 403/429 or challenge page, robots.txt fetched first and judged with protego 0.7.0 on the full URL including its query string. No block of any kind was met. Total: 38 requests to 8 hosts (6 each for the 6 GO stores, 1 each for the 2 robots drops).
- **Why a driver.** The script runs at most 3 queries (`MAX_QUERIES = 3`) and Module 2.4 asks for four (`black blazer`, `jacket`, `shoes`, `men shirt`). The script itself was not edited (it is outside this module's owned paths). A small driver imports its classes and runs the four queries plus one product page for the currency; it is reproduced in the appendix. The first query was `men shirt`, because menswear is the gap this module exists to close.
- **Limits.** Only the honest client, from one machine and network, on one day. The sale state of the stores was high (every record at Giordano, Bear House and Nautica had a pre-sale price), so price ranges will move. Terms of use were not read for any store.

## Candidate list (2.4.1)

| # | Candidate (host) | How identified as Shopify | Outcome | Reason |
|---|---|---|---|---|
| 1 | Sacoor Brothers UAE (`ae.sacoorbrothers.com`) | Level A: URL shape `/collections/suits`; then robots.txt `# Shopify storefront...`, `cdn.shopify.com`, product page markers | **GO** | Men's shirts, blazers, jackets and shoes all returned; premium. [report](sacoor-brothers-uae.md) |
| 2 | Giordano UAE (`giordano.ae`) | Level A: `/collections/men-shirt`, `/blogs/fashion/...`; then robots.txt, `cdn.shopify.com`, page markers | **GO** | Men's shirts, jackets, shorts and shoes; budget; repeated titles. [report](giordano-uae.md) |
| 3 | The Bear House UAE (`www.thebearhouse.ae`) | Level A: `/collections/shirts`, `/products/...`; then robots.txt, `cdn.shopify.com`, page markers | **GO** | Men's shirts, tees, jackets, trousers; budget; no shoes; product name is in `vendor`, `title` is a code. [report](bear-house-uae.md) |
| 4 | Nautica UAE (`nautica-ae.com`) | Level A: `/collections/men`, `/blogs/news/...`; then robots.txt, `cdn.shopify.com`, page markers | **GO** | Men's shirts, jackets, joggers, trousers; mid; no shoes. [report](nautica-uae.md) |
| 5 | Good Times (`good-times.ae`) | Level A: `/collections/tops`, `/pages/men`; then robots.txt, `cdn.shopify.com`, page markers | **GO** | Multi-brand streetwear; men's and unisex tees; thin outerwear and bottoms; no shoes. [report](good-times.md) |
| 6 | Maison D'Vie (`maisondvie.com`) | Level A: `/collections/new-products-men`, `/pages/men-collection`; then robots.txt, `cdn.shopify.com`, page markers | **GO** | Luxury multi-brand; men's results only for shirts and T-shirts, rest women's. [report](maison-dvie.md) |
| 7 | Ocean Drive (`www.shopoceandrive.com`) | Level A: `/collections/mens-hoodies/hoodies`; robots.txt `# we use Shopify as our ecommerce platform` | DROP (robots) | The `User-agent: *` group has `Disallow: /search`, which covers `/search/suggest.json`; protego says DISALLOW for all four queries. 1 request |
| 8 | Mad Kicks (`madkicks.com`) | Level A: `/collections/men-sneakers`, Shopify market paths `/sa/en/`, `/kw/en/`; robots.txt has Shopify rules (`/a/downloads/-/*`, `/.well-known/shopify/monorail`) | DROP (robots) | `Disallow: /search` (and `/*/search` for localised paths) in the `User-Agent: *` group; protego DISALLOW. 1 request |
| 9 | Zapped (`zapped.ae`) | Level B: `/collections/mens-clothing`, `/products/...`, `/blogs/news/...` | Not tested | Stopped at 6 GO. Men's budget linen (shirts AED 75 to 105 per a search snippet): the most useful untested budget store |
| 10 | Theodore (`theodore.ae`) | Level B: `/collections/jacket`, `/products/the-ultimate-jacket` | Not tested | Stopped at 6 GO. Men's premium (jackets AED 700 to 1,150 per snippet) |
| 11 | The Giving Movement (`thegivingmovement.com`) | Level B: `/collections/hoodies-men`, `?variant=40678842826787`, regional hosts `us.` and `sa-en.` | Not tested | Stopped at 6 GO. Men's and women's streetwear; multi-region site, so the default host's currency would need confirming |
| 12 | AAPE UAE (`www.aapeae.com`) | Level B: `/collections/mens-sweatshirts`, `/products/...` | Not tested | Stopped at 6 GO. Single-brand streetwear, premium (hoodies AED 595 to 995 per snippet) |
| 13 | Flash Mob Nation (`flashmobnation.com`) | Level B: `/collections/men-collection`, `/collections/women-collection` | Not tested | Stopped at 6 GO. Local streetwear for men and women |
| 14 | Tanjim Squad (`tanjimsquad.com`) | Level B: `/collections/tanjim-squad/products/...` (a Shopify-only path form), `/collections/men-outwear` | Not tested | Stopped at 6 GO. Budget men's streetwear (AED 90 to 385 per snippet) |
| 15 | KA1 Clothing (`www.ka-1.com`) | Level B: `/products/hard-work-cargo-shorts`, `/collections/language-of-love`; but `ka-1.com` also shows old `/product-category/` URLs | Not tested | Stopped at 6 GO. Platform uncertain (looks migrated); men's streetwear |
| 16 | Steve Madden Middle East (`stevemadden.me`) | Level B: `/collections/mens` | Not tested | Stopped at 6 GO. Footwear-led, men's and women's (AED 149 to 699 per snippet): the best untested candidate for the shoes gap |
| 17 | Vavci (`vavci.ae`) | Level B: `/collections/mens-blazers` | Not tested | Stopped at 6 GO. Men's blazers, luxury positioning (per its search-result title): a candidate for the blazer gap |
| 18 | Diners (`diners.ae`) | Level B: `/collections/suiting` | Not tested | Stopped at 6 GO. Men's suiting |
| 19 | House of Tailors (`shop.houseoftailors.co`) | Level B: `/collections/men-blazers` | Not tested | Stopped at 6 GO. Made-to-measure tailoring; pricing probably by order, a poor fit for search |
| 20 | Sauce (`shopatsauce.com`) | Level B: `/collections/cat-clothing-jackets-and-cardigans`, `/products/...`, `/pages/shipping` | Not tested | Multi-brand, but resort and beachwear mostly for women; weak for menswear |
| 21 | 22Ahead (`22ahead.com`) | Level B: `/collections/new-in`, `/products/...`, `/password` | Not tested | Search snippet shows USD prices (a $110 hoodie), so a poor currency fit; the `/password` page may be a login wall |
| 22 | BySymphony (`bysymphony.com`) | Level B, weak: `/collections/...` mixed with `.html` product URLs | Not tested | Platform unclear; luxury multi-brand with a men's section |
| 23 | Remy Rue (`remyrue.com`) | None: a Gulf News launch article only; no pages from the domain in search results | Not tested | Platform and whether the store still exists are unconfirmed |
| 24 | Sneaker stores found by name only: Fairfax DXB, Dubai Sneakers, VIP Sneakers, Snkr Bubble, Dapper Beast, 3KICKS, CNCPTS, Newcop | None: names and home pages only, no URL shape seen | Not tested | Platform not evidenced; not pursued |

Candidates 9 to 19 are the first ones to test if more stores are wanted: Zapped for budget menswear, Steve Madden Middle East for shoes, Vavci or Diners for blazers, Theodore for premium menswear.

## Coverage table (2.4.3)

"Categories returned" lists which of the four categories (tops, outerwear, bottoms, shoes) came back at all for the stores' own queries; M is men's, W is women's, "none seen" means none of the queries returned one. The three earlier stores come from their reports, which used the queries `black blazer`, `jacket` and `shoes` only, so their tops and bottoms are "not queried" or only incidentally seen, and `men shirt` was not run against them.

| Store | Men / women | Tops | Outerwear | Bottoms | Shoes | Price range seen | Currency | Tier hint | `men shirt` results |
|---|---|---|---|---|---|---|---|---|---|
| Sacoor Brothers UAE | M 36, W 4 of 40 | M shirts | M blazers, jackets, coat; W | none seen | M loafers, sneakers | AED 195 to 1,495 | AED | premium | 10, all men's shirts |
| Giordano UAE | M and unisex; no W seen | M shirts, polos | M jackets, cardigan | M shorts (1) | M and unisex shoes | AED 39.50 to 199.50 | AED | budget | 10 men's shirts (4 distinct titles) |
| Nautica UAE | M 35; W accessories 5 | M shirts, polos, hoodies | M jackets | M joggers, trousers, jeans, swim shorts | none seen | AED 59 to 239 | AED | mid | 10, all men's shirts |
| The Bear House UAE | M | M shirts, T-shirts | M jackets, shackets, hoodie | M trousers | none seen | AED 49 to 119 | AED | budget | 10, all men's shirts |
| Good Times | unisex 20, M only 4, W only 5 of 38 (by tag) | M and unisex T-shirts, tops, knitwear | W denim jacket only; no M jacket seen | pants (1, M and W tags) | none seen (skate parts) | AED 70 to 330 | AED | mid | 10: 8 T-shirts, 2 tops |
| Maison D'Vie | M 10, W 30 of 40 | M shirts, T-shirts | W blazers and jackets only | W pants, shorts, skirt only | none seen | AED 490 to 4,430 | AED | luxury | 10: 8 shirts, 2 T-shirts (one brand) |
| Oh Polly UAE (report) | W only | not seen | W coats, jackets, blazers | not seen | W heels, mules, sandals | AED 170 to 970 | AED | mid | not queried (women-only store) |
| Club L London UAE (report) | W only | W top (1) | W jackets, blazers | not seen | W heels, boots, sandals | AED 199 to 1,499 | AED | premium | not queried (women-only store) |
| Luxury For You (report) | M and W (some children's items) | not queried | M and W blazers, jackets | not queried | M, W and children's shoes | AED 450 to 23,698 (struck-through list price AED 620 to 26,940) | AED | luxury | not queried; results for the other queries mixed men and women |

Notes on the table:

- Tier hints for the new stores come from the observed prices and are on the same scale the existing reports used (Oh Polly AED 170 to 970 is "mid", Club L AED 199 to 1,499 is "premium").
- Giordano, Bear House and Nautica results were every one on sale (a pre-sale price was present), so their ranges are sale ranges. Pre-sale prices were AED 79 to 399, 149 to 329 and 149 to 799.
- Counts of men's and women's items are over the 38 to 40 records returned by the four queries, not over the store's catalogue.

### How the men's acceptance queries fare

The acceptance queries are q06 (a black oversized blazer for men under AED 400) and q07 (an Arabic request for a white cotton men's shirt under AED 200, searched in English). This pass ran the generic queries `black blazer`, `jacket` and `men shirt`, not q06 and q07 themselves, so this is what the generic results suggest.

- **q07, men's shirts under AED 200:** four stores returned men's shirts at or under AED 200 (Giordano AED 87.50 to 148, The Bear House AED 50 to 59, Nautica AED 129 to 139, Sacoor Brothers from AED 195). Good Times adds men's tees at AED 140 to 190 (tees, not shirts), while Maison D'Vie (AED 490 and up) and Luxury For You return shirts above AED 200. Colour and fabric (white, cotton) were not checked. The 3-store rule looks reachable.
- **q06, a men's blazer:** only Sacoor Brothers returned men's blazers (7, at AED 695 to 795, so over budget and to be labelled so) and Luxury For You returned blazers for men and women at luxury prices. Giordano, Bear House and Nautica returned men's jackets but no blazer. Counting only real blazers, q06 reaches 2 stores, short of 3 by one. Counting men's jackets as near matches it reaches 5. How q06 is judged is a decision for the harness; this table only shows the shortfall before the acceptance run, as R20 asks.

## The answer for a men's query

For a men's query, 7 of the 9 readable stores can return results (Sacoor Brothers, Giordano, The Bear House and Nautica across most categories, Good Times and Maison D'Vie for tops only, and Luxury For You as its report shows men's items though it was not queried with a men's query here), while Oh Polly UAE and Club L London UAE cannot.

## Appendix: the driver used for 2.4.2

Run from the repo root as `uv run --with httpx --with protego python qualify_shopify.py <https origin> <slug>`. It is the script that was run, with the print statements shortened and the file paths made relative; the requests it makes (robots.txt, four `suggest.json` URLs, one product page) and the checks around them are the same.

```python
"""Shopify suggest.json qualification driver (Module 2.4.2).

Reuses scripts/qualify_store.py unchanged for everything that touches the network or robots.txt
(Fetcher: fixed honest User-Agent, https only, 1 request/s, no retries, stop on 403/429/challenge;
Robots: protego, full URL with query string). That script runs only 3 queries; this driver runs the
4 queries Module 2.4 asks for, then one product page for the currency.

Run from the repo root:
    uv run --with httpx --with protego python qualify_shopify.py https://store.example slug

Budget per store: robots.txt (1) + 4 searches + 1 product page = 6 requests. A store that fails the
first check (robots, block, not Shopify) stops there: at most 2 requests.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

spec = importlib.util.spec_from_file_location("qualify_store", Path("scripts/qualify_store.py"))
qs = importlib.util.module_from_spec(spec)
sys.modules["qualify_store"] = qs
spec.loader.exec_module(qs)

RAW = Path("raw")  # saved bodies go to raw/<slug>/
QUERIES = ["men shirt", "black blazer", "jacket", "shoes"]


def suggest_url(origin: str, query: str) -> str:
    return f"{origin}/search/suggest.json?q={quote(query, safe='')}&resources%5Btype%5D=product&resources%5Blimit%5D=10"


def products_of(body: str):
    try:
        return True, json.loads(body)["resources"]["results"]["products"]
    except (ValueError, KeyError, TypeError):
        return False, []


def currencies(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            found.append(v) if k == "priceCurrency" else currencies(v, found)
    elif isinstance(node, list):
        for v in node:
            currencies(v, found)
    return found


def ld_blocks(html: str):
    out = []
    for attrs, body in qs.script_blocks(html):
        if "ld+json" in attrs.lower():
            try:
                out.append(json.loads(body))
            except ValueError:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("origin")
    ap.add_argument("slug")
    args = ap.parse_args()
    origin = args.origin.rstrip("/")
    fetcher = qs.Fetcher(RAW / args.slug)
    seen: list[tuple[str, dict]] = []
    verdict, why = "UNDETERMINED", "not finished"
    try:
        robots = qs.Robots(fetcher, origin)  # robots.txt first, judged with protego
        for i, q in enumerate(QUERIES):
            url = suggest_url(origin, q)
            if not robots.allows(url):
                verdict, why = "DROP (robots)", f"robots.txt disallows {url}"
                break
            page = fetcher.get(url, save_as="suggest-" + re.sub(r"\W+", "-", q))
            ok, prods = products_of(page.body)
            print(f"  {q!r}: status {page.status}, {page.nbytes} bytes, shape_ok={ok}, products={len(prods)}")
            if not ok:
                verdict, why = ("DROP (no Shopify suggest.json)" if i == 0 else "PARTIAL"), f"not predictive-search JSON: {url}"
                break
            for p in prods:
                seen.append((q, p))
                print(f"   - {p.get('title')} | {p.get('type')} | {p.get('vendor')} | {p.get('price')} | {p.get('available')}")
        else:
            verdict, why = "SEARCH OK", f"{len(seen)} product records"
        if verdict == "SEARCH OK" and seen:  # one product page, only for the currency
            purl = origin + urlsplit(seen[0][1].get("url") or f"/products/{seen[0][1]['handle']}").path
            fetcher.client.timeout = httpx.Timeout(15.0)  # product pages are large
            if not robots.allows(purl):
                verdict, why = "PARTIAL (product page disallowed; currency unconfirmed)", purl
            else:
                html = fetcher.get(purl, save_as="product").body
                cur = sorted({c for n in ld_blocks(html) for c in currencies(n)})
                print(f"  product page: priceCurrency={cur}")
                why = f"currency from JSON-LD: {cur}"
    except qs.Stop as exc:
        verdict, why = exc.verdict, str(exc)
    print(f"\nVERDICT: {verdict}\n  why: {why}\n  requests made: {fetcher.count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
