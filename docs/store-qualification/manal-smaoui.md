# Manal Smaoui qualification (2026-10-08)

**Verdict:** GO, with a currency flag. The honest client received title, price, image URL and product URL (plus availability) for 13 distinct products over two searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Every price is in **Kuwaiti dinars (KWD)**: KWD 5 to 85, which is roughly AED 60 to 1,000 by an approximate rate (not observed). A currency-converter widget in the page lists AED, but the server-rendered prices and the JSON-LD say KWD. The store is the one of the four GO brands whose prices sit near the demo's existing mid and premium stores, and it sells tailored sets (blazers, trousers, skirts, tops), kaftans and dresses. Same two adapter issues as Bazza Alzouman: three-decimal prices (`"85.000"`) are rejected by the project's price parser, and the tier shaper keeps only the most common currency.

## Storefront

- Store: Manal Smaoui, `https://manalsmaoui.com/` (used directly, no redirect). A Kuwaiti ready-to-wear label with a flagship boutique at The Avenues, Kuwait (page `/pages/flagship-store`). Single-brand: `vendor` is "MANAL SMAOUI" on 13 of 13 records.
- **How it is known to be the brand's own shop.** Web search found the domain with the brand's own pages (`/pages/about-us` "Our Story", `/pages/flagship-store`) and product pages for her named lines (The Frankie Blazer, The Muse, The Alaia, Belle Dress, Qout Kaftan Set). The vendor field is the brand name on every record, the theme is named "MANAL SMAOUI | Boutique Availability ..." and the Shopify shop is `manalsmaoui-8058.myshopify.com`. It is not a stockist or marketplace.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 13 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.theme` (Stiletto), `shopify-features`, `myshopify.com`, `/cdn/shop/` and `Shopify.currency`.
- Assortment seen in 20 search records (13 distinct handles): "The Belle Dress" in black and white (limited edition, KWD 55), "Aicha Kaftan" in brown, baby blue and royal green (KWD 85), "The Muse" pants, top and skirts in black, baby pink, white and grey (KWD 29 to 32), "The Ladylike Blazer - White" (KWD 35) and a headband (KWD 5, an accessory, out of scope). Women only by nature of the range; no gender field. No abayas, gowns or shoes appeared.
- **The store pads its answers.** For `dress` only 2 of 10 results are dresses; for `kaftan`, 3 of 10 are kaftans (one colour each), and the rest are dresses, skirts and trousers.

## robots.txt

- Parser: **protego 0.7.0**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, through the `MALFORMED_RULE` reading in `scripts/qualify_store.py`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://manalsmaoui.com/robots.txt`: 200, 3,628 bytes, no redirect. Shopify's current default file, identical to Hanayen's except for the host and the shop id line.
- Group `User-agent: *`: `Allow: /`, exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows for `/admin`, `/cart/`, `/checkout`, `/orders`, `/account`, `/cart.js`, `/recommendations/products`, `/collections/*sort_by*`, filter combinations and preview parameters. A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`** (a separate offline protego pass also says ALLOW for `https://manalsmaoui.com/search?q=dress`, which was not requested). Protego result for every URL requested (two suggest.json URLs and the product page): ALLOW.
- Sitemap: `https://manalsmaoui.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents (UCP/MCP preference, `agents.md`, `/.well-known/ucp`, `/api/ucp/mcp`, a third-party "shop.app" skill). Quoted as data, not acted on, none of those URLs requested. Review at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://manalsmaoui.com/robots.txt` | 200 | 3628 | 2.2 s | text/plain |
| 2 | `https://manalsmaoui.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 11546 | 0.8 s | application/json, 10 products |
| 3 | `https://manalsmaoui.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 11091 | 0.9 s | 10 products |
| 4 | `https://manalsmaoui.com/products/aicha-kaftan-brown` | 200 | 348946 | 1.2 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://manalsmaoui.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: both responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list (empty in these records). The product page carries one `Product` JSON-LD block with five `Offer` entries (one per size), each with `price` `85.0`, `priceCurrency` `"KWD"` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores. Store-specific points:

- **Currency is KWD** (same blockers as Bazza Alzouman): `src/vga/stores/prices.py` accepts only two-decimal bare prices, and this store writes `"85.000"`, so every record would be dropped by `parse_price`; and `src/vga/tiers/shaper.py` keeps only the most common currency of a result set, so KWD products would be left out of an AED run with a warning. A decision for the orchestrator.
- Pin the host `manalsmaoui.com`. Build the link from the host plus `/products/{handle}`; drop the tracking query. **Handles do not always match titles**: "THE MUSE SKIRT - BABY PINK" lives at `/products/the-muse-skirt-striped-grey`, and "AICHA KAFTAN - BABY BLUE" at `/products/aicha-kaftan-royal-blue`. Always use the `url` or `handle` field, never rebuild from the title.
- **`type` is a collection label, not a garment type**: "EID COLLECTION", "BLACK SETS", "BABY PINK SETS", "WHITE SETS", "KAFTANS". It cannot give a category; the category has to come from the title ("DRESS", "KAFTAN", "PANTS", "TOP", "SKIRT", "BLAZER"). A headband carries `type` "KAFTANS" (an accessory; skip it by title).
- Titles are upper case ("THE BELLE DRESS - BLACK (LIMITED EDITION)") and mix case ("The Ladylike Blazer - White"). Colour is in the title after a dash.
- There is no gender field; the range is women's. `tags` are empty on most records.
- The same product repeats across queries (13 distinct handles in 20 records); collapse by handle.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "AICHA KAFTAN - BROWN") |
| price | yes | `price`, a string with three decimals (`"85.000"`); `compare_at_price_max` was `"0.000"` for all 13 records (no discount today) |
| currency | not in the response | KWD is store-level: `priceCurrency: "KWD"` on all five offers in the product JSON-LD, `og:price:currency` `KWD`, `Shopify.currency` `{"active":"KWD","rate":"1.0"}`, `Shopify.country` `"KW"` |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0682/5885/7253/files/...jpg?v=...`. The product JSON-LD `image` is malformed: `"https:files/0S5A7706.jpg"` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 13 of 13). The product page shows per-size stock (the sampled kaftan had both in-stock and out-of-stock sizes) |
| colour | partly | in the title after the dash |
| gender | no | not a field |

## Hosts

- Store host (product links): `manalsmaoui.com`. A Saudi market alternate exists at `/en-sa/` (hreflang, not requested).
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0682/5885/7253/` on all 13 records.
- Candidate `allowed_hosts`: `manalsmaoui.com`, `cdn.shopify.com`.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "85.000"`, `"price": "29.000"`, `"price": "5.000"`, `"compare_at_price_max": "0.000"`.
- Product JSON-LD: `"price": 85.0`, `"priceCurrency": "KWD"`; `<meta property="og:price:amount" content="85.00">`.
- Observed over 13 distinct handles: price **KWD 5 to 85, median 32** (without the headband, KWD 29 to 85). At roughly AED 12 per KWD (an approximation, not observed) that is about AED 350 to 1,020 for garments: dresses KWD 55 (about AED 660), kaftans KWD 85 (about AED 1,020), trousers and skirts KWD 29 to 32 (about AED 350 to 385), the blazer KWD 35 (about AED 420).

## Currency / tier hint

**KWD** (not AED). Tier: **mid to premium** at the converted level. It is the only one of the four GO brands whose estimated AED prices fall in the range of the existing Nautica, Sacoor Brothers and Oh Polly stores.

AED storefront: the product page has a currency-converter widget whose configuration lists KWD, SAR, QAR, AED, USD, EUR, GBP, CAD, BHD, AUD, HKD and RUB. That appears to be a script-driven display tool (not checked, since no JavaScript was run); the server-rendered prices, the JSON-LD and the Open Graph tags are KWD, and no AED URL exists. The only market alternate in the page head is `/en-sa/`.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dress | `https://manalsmaoui.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 2 dresses ("THE BELLE DRESS - BLACK (LIMITED EDITION)" and white, KWD 55), 1 kaftan (KWD 85), 3 muse trousers and top (KWD 29), a blazer (KWD 35), 2 skirts (KWD 32), a headband (KWD 5) |
| kaftan | `https://manalsmaoui.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 3 "AICHA KAFTAN" (brown, baby blue, royal green, KWD 85), the headband, 2 dresses, 4 skirts and trousers (KWD 29 to 32) |

## Requests made

4 (1 for robots.txt, 2 searches, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/manal-smaoui/`

- `suggest-dress.json`, `suggest-kaftan.json`: the first 4 of the 10 products of the real response, same structure; each `body` string cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page (`description` cut to 300 characters; the malformed `image` value is left as served).
- `robots.txt`: the file as served.

## Risks and fragility

- Currency and price format (see above): without a decision and a parser change this store yields no products in the demo.
- A small catalogue: 13 distinct products across two queries, with the same pieces appearing for different words. A third query would likely show little more.
- `type` is a collection label and handles do not match titles; category and link must come from the right fields.
- Single-brand, women's, modest cuts; no shoes, no abayas.
- `body` is store-supplied HTML (up to 615 characters here); never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint; review before real users. A template change could close `/search`.
- Not tested: HTML search page, `/en-sa/`, `limit` above 10, behaviour from the user's network, terms of use, queries for blazer, trousers or shoes.
