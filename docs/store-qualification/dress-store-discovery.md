# Shopify storefront discovery for dresses, abayas, kaftans and South Asian wear (Module 2.5, 2026-10-08)

Why this exists: dresses became a fifth category on 2026-10-08 (assumption A23), because every photo the business supplied shows a dress, an abaya or ethnic wear, and the six demo stores were chosen before that. Three of them sell Western dresses and none was known to sell abayas, kaftans, kurtas or South Asian wear (A24). The business then added more photos: 16 in total, of which 5 are abayas, 3 are dresses (a burgundy evening gown, a floral kaftan-style dress, a teal colour-block maxi), 2 are South Asian sets (a coral embroidered set, a white embroidered kurta set), plus a black dress, palazzo trousers, a pleated skirt, skinny jeans and a satin blouse. This file holds the candidate list (2.5.1), the qualification outcomes (2.5.2) and the coverage table (2.5.3). Following the orchestrator's update, abayas were searched first, then kaftans and modest maxi dresses, then kurtas and South Asian sets.

## Result in one paragraph

31 candidate entries were listed (one entry groups six names that showed no store URL). 12 were tested, in an order that put abaya sellers first, and **4 are GO**: Hanayen (abayas, premium to luxury), Maison Arabelle (kaftans and abayas, luxury), Nishat Linen UAE (budget long dresses, kaftans, embroidered suits) and Signature Studio (a multi-brand Pakistani designer store). 5 were dropped on robots.txt (Lamis Abaya, Basic Abaya, KMansoori, CAS Basics and Bousni: `Disallow: /search`, or the whole site), 1 does not answer with Shopify's endpoint (Boksha), 1 reads fine but is priced in USD (East Essence), and 1 is unreachable from this machine (Kitty Girl). Testing stopped at the fourth good GO store, as the assignment asks, so 19 candidate entries were not tested. The finding that matters most for the new scope: **abaya sellers are mostly closed to an honest client**. Of the 8 abaya or kaftan sellers whose robots.txt was read, 5 close `/search`; the open ones are Hanayen, Maison Arabelle and East Essence (USD). No readable AED store sells everyday abayas below AED 600.

## Method and limits

- **Finding candidates.** `WebSearch` only, never memory, for the names and for whether a store uses Shopify. Generic queries (kaftans and abayas in the UAE, Pakistani and Indian wear in Dubai, evening gowns, multi-brand modest wear, affordable abayas) produced names; a second search restricted to each candidate's own domain (`allowed_domains`) showed that domain's URL shapes. `WebFetch` was never used. Some search summaries said "Powered by Shopify"; those statements were treated as hints and not as evidence.
- **Shopify identification, two levels.** Level A (tested candidates): confirmed from the store's own `robots.txt` (the comment `# Shopify storefront...` or `# we use Shopify as our ecommerce platform`, or Shopify-only rules such as `/.well-known/shopify/monorail`), plus `cdn.shopify.com` image URLs and, for GO stores, Shopify markers in the product page (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Level B (untested candidates): only the URL shape seen in search results (`/collections/{handle}`, `/products/{handle}`, `/blogs/{blog}/{article}`). These shapes are Shopify's defaults but are **not proof**; a Level B candidate is "probably Shopify" until its robots.txt is fetched. Maison Arabelle's robots.txt is a custom file with no Shopify comment, so for it the evidence is the JSON shape, the image host and the page markers.
- **Requests.** Every request to a store used `scripts/qualify_store.py`'s `Fetcher` and `Robots` classes unchanged: the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, https only, at most 1 request per second, no retries, no cookies, stop on the first 403/429 or challenge page, robots.txt fetched first and judged with protego 0.7.0 on the full URL including its query string. No block of any kind (403, 429, CAPTCHA, login wall, challenge) was met. **Total: 40 requests to 12 hosts**: 6 each for the 4 GO stores and for East Essence (the full plan: robots.txt, four searches, one product page), 1 each for the 5 robots drops, 1 for Kitty Girl (a failed connection) and **4 for Boksha**. Boksha overshot the limit of 2 for an early rejection: the first version of my driver followed the redirects of the first search URL (a 301, then a 302, then an HTML page), and each hop counted. The driver was corrected before the next store: on the first search URL a redirect that leaves `/search/suggest.json` now ends the run. No request went to any of the six current demo stores. No UCP/MCP, agent, cart, checkout, account or `/api/` URL was requested; the AI-agent comments in robots.txt were recorded as data.
- **Why a driver.** The script runs at most 3 queries (`MAX_QUERIES = 3`) and Module 2.5 asks for four (`dress`, `kaftan`, `abaya`, `kurta`). The script itself was not edited (it is outside this module's owned paths). A small driver imports its classes and runs the four queries plus one product page for the currency; it is reproduced in the appendix, and caps each store at 6 requests, redirects included.
- **Limits.** Only the honest client, from one machine and network, on one day. The sale state differs by store (Nishat Linen UAE had 38 of 39 records at 50% off), so price ranges will move. Terms of use were not read for any store. The coverage table is built from 10 products per query at most, so "not seen" means "not in these responses", never "the store does not sell it".

## What decided the outcome: two kinds of robots.txt

Shopify ships two default robots.txt templates. The older one (first line `# we use Shopify as our ecommerce platform`) contains `Disallow: /search`, which covers `/search/suggest.json`. The newer one (first line `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, followed by comments addressed to AI agents) has no search rule. Basic Abaya and KMansoori have the older file and disallow search; Bousni has the older rules without the comment line, and CAS Basics has its own file with the same `Disallow: /search`. All four stores with the newer file were open (Hanayen, Nishat Linen UAE, Signature Studio, East Essence). Lamis Abaya has the older comment and `Disallow: /` for every agent, which closes the whole site. Maison Arabelle has a short hand-written file that leaves search open. This is the same split the earlier pass saw (Ocean Drive and Mad Kicks were dropped for `Disallow: /search`; its six GO stores all had the newer file). Nothing in a search result shows which file a store has, which is why robots.txt is always the first request.

## Candidate list (2.5.1)

Tested candidates first, in test order; then untested ones.

| # | Candidate (host) | How identified as Shopify | Outcome | Reason |
|---|---|---|---|---|
| 1 | Boksha (`www.boksha.com`) | None: URL shapes `/en/product/...`, `/en/category/traditional-kaftans`, `/en/store/...`, `us.boksha.com` are not Shopify's. Tested because it is the one multi-brand modest-wear marketplace found (a search summary describes it as 200+ UAE designers) | DROP (not Shopify's endpoint) | robots.txt (174 bytes) allows everything for `*`. `/search/suggest.json` returned a 301 to `/en/search/suggest.json`, then a 302 to `/en/search-new?products[query]=suggest.json&...`, then an HTML page of 217,703 bytes: no JSON. 4 requests (see Method) |
| 2 | Hanayen (`hanayen.com`) | Level A: robots.txt `# Shopify storefront...`, `cdn.shopify.com`, page markers. Level B before: `/collections/essential-abayas`, `/collections/our-abaya-collection` | **GO** | 10 of 10 real abayas for `abaya`; AED 120 to 5,550. [report](hanayen.md) |
| 3 | Lamis Abaya (`lamisabaya.com`) | Level A: robots.txt `# we use Shopify as our ecommerce platform`. Level B before: `/products/inaya-abaya`, `/collections/frontpage`, `/blogs/news/...` | DROP (robots) | The file is `User-agent: *` / `Disallow: /`: the whole site is closed to agents. 1 request |
| 4 | Basic Abaya (`basicabaya.com`) | Level A: robots.txt `# we use Shopify...` and `Disallow: /.well-known/shopify/monorail` | DROP (robots) | `Disallow: /search` in the `*` group; protego DISALLOW. 1 request |
| 5 | KMansoori (`kmansoori.com`) | Level A: same two markers. Level B before: `/en-us/collections/...`, `/en-us/blogs/news/...` | DROP (robots) | `Disallow: /search` in the `*` group; protego DISALLOW. 1 request |
| 6 | CAS Basics (`casbasics.com`) | Level B: `/collections/kaftan`. robots.txt is a custom file with named groups for Googlebot, OAI-SearchBot, Claude-SearchBot and others | DROP (robots) | The `*` group has `Disallow: /search`; the groups for named bots do not apply to our User-Agent. 1 request |
| 7 | East Essence (`eastessence.com`) | Level A: robots.txt `# Shopify storefront...`, `cdn.shopify.com`, page markers | DROP (currency) | Readable: 40 records, 10 real abayas for `abaya`, 4 kaftans and 6 kaftan-style abayas for `kaftan`, men's kurta sets for `kurta`. But the product page says `priceCurrency: "USD"` and `Shopify.currency` active `USD` (the product tags name US schools), at USD 27.99 to 59.99. Not an AED store. If USD pricing were accepted, the fixed AED 3.6725 per USD peg would put that range at about AED 103 to 220 (computed, not observed). 6 requests |
| 8 | Maison Arabelle (`maisonarabelle.com`) | Level A, without a robots comment: JSON shape, `cdn.shopify.com`, page markers. Level B before: `/products/mira-pink-kaftan-embroidered`, `/collections/kaftans-and-abayas` | **GO** | Floral and embroidered kaftans and abayas; AED 790 to 2,400, luxury. [report](maison-arabelle.md) |
| 9 | Kitty Girl (`kittygirl.ae`) | Level B: `/collections/party-wear`, `/collections/kaftan`, `/collections/cord-sets` | UNDETERMINED | The host does not resolve from this machine (`ConnectError: nodename nor servname provided`); a DNS-only lookup of `www.kittygirl.ae` failed too. Not retried. 1 request |
| 10 | Nishat Linen UAE (`www.nishatlinenuae.com`) | Level A: robots.txt `# Shopify storefront...`, `cdn.shopify.com`, page markers. Level B before: `/collections/ready-to-wear`, `/products/pw23-09`, `/blogs/news/...` | **GO** | Budget long dresses, kaftans, gowns and embroidered suits; AED 39.50 to 239 on a 50% sale. [report](nishat-linen-uae.md) |
| 11 | Bousni (`www.bousni.com`) | Level A: robots.txt `Disallow: /.well-known/shopify/monorail` | DROP (robots) | `Disallow: /search` in the `*` group; protego DISALLOW. 1 request |
| 12 | Signature Studio (`www.signaturestudio.ae`) | Level A: robots.txt `# Shopify storefront...`, `cdn.shopify.com`, page markers. Level B before: `/collections/all?page=42`, `/collections/clothing` | **GO** | Multi-brand Pakistani designer wear, 16 labels, AED 174 to 2,753. [report](signature-studio.md) |
| 13 | Gul Ahmed UAE (`uae.gulahmedshop.com`) | Level B: `/collections/sale`, `/collections/mens`, `/collections/women-ideas-pret-solids` | Not tested | Stopped at 4 GO. Pakistani ready-to-wear kurtis and shirts for the UAE; the next South Asian store to try if Signature Studio or Nishat is lost |
| 14 | Al Boushiya (`www.alboushiya.com`) | Level B: `/collections/gowns`, `/collections/new-arrivals-1` | Not tested | Stopped at 4 GO. Multi-designer evening gowns and couture; luxury; the best untested candidate for the burgundy gown |
| 15 | Elilhaam (`www.elilhaam.com`) | Level B: `/collections/evening-dresses`, `/collections/tony-ward`, `/collections/mac-duggal/mac-duggal` | Not tested | Stopped at 4 GO. Multi-designer gowns and cocktail dresses (Tony Ward, Mac Duggal, Badgley Mischka among its collections) |
| 16 | Shaira Fashions (`www.shairaonline.com`) | Level B: `/collections/evening-wear` | Not tested | Stopped at 4 GO. Evening wear, resort wear and kaftans; AED 3,325 and up per a search snippet |
| 17 | CHI-KA (`chikacollection.com`) | Level B: `/products/kaftan-dress-in-navy-blue`, `/collections/kaftans`, `/collections/ready-to-wear` | Not tested | Stopped at 4 GO. Made-to-measure and ready-to-wear abayas, kaftans and kimonos; luxury |
| 18 | Nishida Shaheen (`nishidashaheen.com`) | Level B: `/collections/abaya`, `/collections/kaftans`, `/collections/dresses` | Not tested | Stopped at 4 GO. Luxury abayas, dresses, kaftans and jalabiyas |
| 19 | Anatomi (`www.anatomiofficial.com`) | Level B: `/collections/kaftans-ii` | Not tested | Stopped at 4 GO. Luxury modest brand: abayas, kaftans, dresses |
| 20 | Eleganza La Mode (`eleganzalamode.com`) | Level B: `/collections/new-collections?page=4`, `/pages/about-us` | Not tested | Stopped at 4 GO. Moroccan kaftans and jalabiyas at AED 1,450 to 2,900 per a search snippet; only 3 abayas; luxury |
| 21 | Sauce (`shopatsauce.com`) | Level B: `/collections/cat-clothing?page=4` (also listed in the earlier pass as candidate 20) | Not tested | Stopped at 4 GO. Multi-brand resort wear with kaftans |
| 22 | BySymphony (`bysymphony.com`) | Level B: `/products/belted-shirt-dress-kaftan-neutral` (the earlier pass marked its platform unclear) | Not tested | Stopped at 4 GO. Multi-brand luxury; the product URL now has Shopify's shape |
| 23 | Steve Madden Middle East (`stevemadden.me`) | Level B: `/collections/women-heels/heels`, `/products/jackpots-black-womens-heels-black` (candidate 16 of the earlier pass) | Not tested | Stopped at 4 GO. The only untested candidate for women's heels; AED 240 to 599 per a search snippet |
| 24 | MyBatua (`www.mybatua.com`) | Level B: `/collections/fancy-abaya`, `/products/shabana-abaya` | Not tested | Search snippet shows USD prices (USD 32 to 70): the same currency problem as East Essence |
| 25 | Sara Arabia (`saraarabia.com`) | None: URLs `/fabric/Rayon`, `/occasion/Party`, `/public/index.php` are not Shopify's | Not tested | Probably not Shopify; abayas and jalabiyas at AED 59 to 399 per a snippet, which would have filled the everyday-abaya gap |
| 26 | Hera Closet (`heracloset.com`) | None: `/product-category/abaya/`, `/product/...`, `/product-tag/...` are WooCommerce shapes | Not tested | Probably not Shopify |
| 27 | Khaadi UAE (`uae.khaadi.com`) | None: `/ready-to-wear/signature/kurta/` is not Shopify's shape | Not tested | Probably not Shopify; Pakistani kurtas at AED 54 to 230 per a snippet |
| 28 | MiYA (`miya.odoo.com`) | None: `/shop/stylish-dubai-abaya-237` is an Odoo shape | Not tested | Not Shopify |
| 29 | Zayan The Label, Manto UAE, By Noor, Balqees, Dazzle Abaya, Romantic Queen Abaya | None: names and articles only, no store URL seen | Not tested | Platform not evidenced. Manto's dresses and kaftans appear inside Signature Studio's results |
| 30 | Nukhbaa abayas | None: sold through Centrepoint (`/ae/en/p/...`) | Not tested | Centrepoint returned a challenge page in the earlier pass |
| 31 | Etoile La Boutique | Earlier pass | Not tested | Search was disallowed in the earlier pass (see `SUMMARY.md`) |

Candidates 14 to 17 are the first ones to test if a Western gown source or another luxury modest-wear store is wanted; candidates 13, 23 and 25 are the first for South Asian wear, heels and everyday abayas.

## Coverage table (2.5.3)

Cells say what the responses showed. "Not queried" means no saved response could say. For the six current stores the table uses only their saved responses under `tests/stores/` and their reports; none of the six was contacted. "Mini" and "maxi" are from titles. Colour and fabric claims rest on titles and descriptions, not on the images. The columns follow the orchestrator's update of 2026-10-08.

| Store | Abaya | Evening gown | Printed or colour-block long dress or kaftan | Embroidered South Asian set or kurta | Black dress | Palazzo trousers or skirt | Women's heels | Price range seen (AED) | Tier hint |
|---|---|---|---|---|---|---|---|---|---|
| **Hanayen** (GO) | **yes**: 21 outer abayas, 10 of 10 for `abaya`; open-front with buttons, embroidered, crystals, plain black | partial: embellished modest dresses AED 950 to 5,550; no gown | no: one under-abaya "Kaftan Style" inner (AED 850) | no | partial: black abayas only (AED 650, 1,300) | not queried; none in 40 records | not queried; none in 40 records | 120 to 5,550 (outer abayas 600 to 5,550) | premium to luxury |
| **Maison Arabelle** (GO) | **yes**: 10 of 10 for `abaya` (burgundy, beige, grey, butter yellow, lilac; open-front or belt mentions) | partial: "Zahra Gold Dress with Cape" AED 1,600; embroidered and velvet kaftans described for evening | **yes**: floral kaftans (green; pink with gold, AED 1,600) and 15 kaftans in all | no: kaftans only | partial: "Mayra Black" AED 980, garment type not stated | not queried; none in 40 records | not queried; none in 40 records | 790 to 2,400 | luxury |
| **Nishat Linen UAE** (GO) | no: `abaya` returned long dresses, a gown and suits | partial: "2 Piece - Embroidered Gown" AED 119.50 (brick red) | **yes**: printed long dresses and printed kaftans (18 dresses and 8 kaftans in the records) | **yes** for sets: 2- and 3-piece embroidered suits AED 114.50 to 159.50; `kurta` returned only men's kurtas | **yes**: two black long dresses (AED 84.50 and 79.50) | partial: one 3-piece suit lists trousers; not queried | not queried; none in 40 records | 39.50 to 239 (women's 59.50 to 239), on a 50% sale | budget |
| **Signature Studio** (GO) | no: `abaya` returned designer pret, none an abaya | partial: formal pieces (ZABRIC "Fusan" AED 2,396, ALEENA FAREENA "Midnight mirage" AED 2,753) | **yes**: printed kaftans (AED 419), a printed maxi (AED 416), a floral print dress (AED 357), "Kaftaan" dress (AED 174) | **yes** for sets: four records mention a dupatta (AED 630 to 1,843, three labels), one a three-piece raw-silk wedding set with crushed pants; `kurta` returned only men's sets | partial: "Midnight mirage" (formal), "Maya Black" set (AED 630) | partial: 7 women's records mention pants or culottes in a set; not queried | not queried; none in 40 records | 174 to 2,753 | mid, luxury tail |
| Giordano UAE | not queried | not queried; no women's item in 40 records | not queried | not queried | not queried | not queried (one men's shorts seen) | no: men's casual shoes and unisex sneakers | 39.50 to 199.50 | budget |
| Nautica UAE | not queried | no: `women dress` returned no dress (10 women's shirts, trousers, tops) | no dress seen | not queried | no dress seen | partial: women's trousers AED 139, not described as wide-leg | no footwear seen | 59 to 239 | mid |
| Sacoor Brothers UAE | not queried | not queried; the 4 women's items seen are a suit, suit blazers and a leather jacket | not queried | not queried | not queried | not queried; no bottoms seen | not queried; shoes seen were men's | 195 to 1,495 | premium |
| Oh Polly UAE | not queried | partial: dresses are 5 of 30 records in the report (titles not saved); a mini dress seen | not queried | no (a Western brand) | partial: "Single-Breasted Blazer Mini Dress in Black" AED 620 (mini) | not queried | **yes**: heeled mules, sandals, sling-backs AED 370 to 430, black among them | 170 to 970 | mid |
| Club L London UAE | not queried | partial: maxi occasion dresses (asymmetric maxi AED 649; black velvet halter maxi AED 1,790); none titled gown | partial: "Tate" black velvet maxi with bronze floral sequin (AED 1,790); a red floral sequin mini | no (a Western brand) | **yes**: black plunge-neck mini dresses AED 535 to 650, black velvet mini AED 1,499, black velvet maxi AED 1,790 | not queried | **yes**: black satin diamante heels, pointed court heels AED 299 to 449 | 199 to 1,790 (saved responses) | premium |
| Maison D'Vie | not queried | not queried; the report counts 6 dresses in 30 records (titles not saved) | not queried | not queried | not queried | **yes**: women's wide-leg trousers AED 745 to 1,300 (saved response); the report counts one skirt | no: the `shoes` query returned no shoes | 490 to 4,430 | luxury |

Notes on the table:

- **Abayas.** Hanayen and Maison Arabelle are the only readable abaya sellers. Both start at premium prices: the cheapest outer abaya seen at Hanayen is AED 600, and Maison Arabelle starts at AED 790 for a kaftan and AED 1,200 for an abaya. No readable store sells everyday abayas below AED 600 (see candidates 3 to 7 and 25).
- **Titles only.** At Hanayen a title reads "Neda Plain Abaya Front Open with Buttons" (AED 600), which has the wording of the taupe open-front photo; Maison Arabelle's descriptions mention an open front or a belt for several abayas (beige, grey, butter yellow, lilac). Whether any product looks like a given photo was not checked; that is the ranking step's job.
- **The `kurta` word.** At Nishat Linen UAE and Signature Studio it returned only men's items. Women's embroidered sets are found by other words (`embroidered suit`, `3 piece`, `dress`, `kaftan`), which were not queried.
- **Western stores and the new photos.** The saved responses of the six current stores come from queries for blazers, jackets, shirts, trousers and shoes. They were not dress queries, so most dress cells are "not queried". Club L London is the one current store whose saved responses show black, long and floral dresses.
- **Not seen anywhere.** Skinny jeans and a satin blouse were not in any column; no response was searched for them. Women's heels exist only at Oh Polly and Club L London.

## Which six stores

Keep Giordano UAE, Nautica UAE and Sacoor Brothers UAE as the men's sources for shirts and jackets (a men's shirt under AED 200 needs all three), add Hanayen for the abayas and Signature Studio for the South Asian sets, printed kaftans and long dresses, and keep Oh Polly UAE for the Western evening and black dresses and for heels; that drops Club L London and Maison D'Vie. Swapping Hanayen out costs the five abaya photos, because it is the only readable AED store whose abaya search returns real abayas across a wide price range, and the nearest substitute, Maison Arabelle, starts at AED 1,200 for an abaya. Swapping Signature Studio for Nishat Linen UAE keeps long printed dresses, black dresses and a gown at budget prices but loses the designer embroidered sets with a dupatta, the AED 174 to 2,753 spread and a multi-brand answer. Swapping Oh Polly out loses the heels and the Western evening dresses (Club L London is the like-for-like replacement, with more dress evidence in the saved responses, but at premium prices and without Oh Polly's AED 230 to 290 blazers). Swapping Nautica out loses men's shirts at AED 129 to 139, jackets at AED 209 to 239 and the third store for a men's shirt under AED 200 (Sacoor starts at AED 195 and Giordano is the only other). Swapping Sacoor Brothers out loses the only men's blazers seen and the premium men's tier, and swapping Giordano out loses the cheapest men's shirts (AED 87.50 to 148) and the unisex sneakers. Dropping Club L London and Maison D'Vie costs the Western luxury tier (women's blazers and jackets at AED 1,030 to 4,430), the only women's wide-leg trousers and skirt seen, and a second source of heels; luxury then rests on the top of Hanayen (to AED 5,550) and Signature Studio (to AED 2,753), and nothing in the six sells budget women's dresses, for which Nishat Linen UAE is the first reserve. Still open: no readable store sells everyday abayas below AED 600, and skinny jeans and satin blouses were not searched anywhere.

## Not verified

Terms of use for every store. Behaviour from any other network. Whether the apex or `www` variant of Nishat Linen UAE and Signature Studio redirects to the host used. The `/en-us/` path at Hanayen and its currency. Pagination and Shopify limits above 10. Women's kurta keywords at Nishat Linen UAE and Signature Studio. Whether the 50% sale at Nishat Linen UAE is permanent. The UCP/MCP endpoints (never requested). Tier hints for untested candidates (taken from search snippets, not observed prices).

## Appendix: the driver used for 2.5.2

Run from the repo root as `uv run --with httpx --with protego python qualify_dress.py <https origin> <slug>`. It is the script that was run, with the saved-bodies directory made relative; the requests it makes (robots.txt, four `suggest.json` URLs, one product page) and the checks around them are the same. It imports `scripts/qualify_store.py` unchanged and sets `MAX_REQUESTS` to 6 for the run.

```python
"""Shopify suggest.json qualification driver (Module 2.5.2).

Reuses scripts/qualify_store.py unchanged for everything that touches the network or robots.txt
(Fetcher: fixed honest User-Agent, https only, 1 request/s, no retries, stop on 403/429/challenge;
Robots: protego, full URL with query string). That script runs only 3 queries; this driver runs the
4 queries Module 2.5 asks for (dress, kaftan, abaya, kurta), then one product page for the currency.

Budget per store: robots.txt (1) + 4 searches + 1 product page = 6 requests, redirects included.
A store that fails the first check (robots, block, not Shopify) stops there: at most 2 requests.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx

spec = importlib.util.spec_from_file_location("qualify_store", Path("scripts/qualify_store.py"))
qs = importlib.util.module_from_spec(spec)
sys.modules["qualify_store"] = qs
spec.loader.exec_module(qs)
qs.MAX_REQUESTS = 6  # hard cap per store, redirects included

RAW = Path("raw")  # saved bodies go to raw/<slug>/
QUERIES = ["dress", "kaftan", "abaya", "kurta"]


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
            if i == 0:
                # First probe: a redirect that leaves the suggest.json path means this is not Shopify's
                # endpoint; stop there (2 requests in total) instead of following it.
                first, location = fetcher._once(url)
                if location is not None:
                    new = urljoin(url, location)
                    if qs.site(new) == qs.site(url) and urlsplit(new).path.endswith("/search/suggest.json"):
                        page = fetcher.get(new, save_as="suggest-" + re.sub(r"\W+", "-", q))
                    else:
                        verdict, why = "DROP (not Shopify: suggest.json redirects elsewhere)", f"{url} -> {new}"
                        break
                else:
                    page = first
                    fetcher._save(page, "suggest-" + re.sub(r"\W+", "-", q))
            else:
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
