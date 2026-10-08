# Sacoor Brothers UAE: store notes (plan 12.3.4)

> **Update 2026-10-08:** where this note says a product has no gender field or that the reader
> ignores `type` and `tags`, that is no longer true. The Shopify reader now sets a product's gender
> from those fields, `type` first (ADR 0014).

Store id `sacoor-brothers-uae`, storefront `https://ae.sacoorbrothers.com/`. Config:
`config/stores/sacoor-brothers-uae.yaml`. Tests: `tests/stores/sacoor-brothers-uae/` (offline fixture
tests; a `live` smoke test). Qualification: `docs/store-qualification/sacoor-brothers-uae.md`.
Status: **enabled** since the live smoke test passed on 2026-10-08.

## Data path

1. `GET https://ae.sacoorbrothers.com/robots.txt`, checked with protego (once, then cached).
2. `GET https://ae.sacoorbrothers.com/search/suggest.json?q={query}&resources%5Btype%5D=product&resources%5Blimit%5D=10`
   (the brackets are percent-encoded by the URL builder). Shopify's predictive-search endpoint.
3. The response is JSON, `resources.results.products[]`, at most 10 products. The `shopify` extractor
   maps:

   | `Product` field | Source |
   |---|---|
   | `title` | `title` |
   | `price` | `price` (a string such as `"795.00"`); the price the shopper pays today |
   | `currency` | **not in the response**; `currency: AED` from the store file |
   | `image_url` | `image` (absolute, `cdn.shopify.com`), with `width=400` set by the extractor |
   | `product_url` | `url` (relative) made absolute against the store host, tracking query dropped |
   | `in_stock` | `available` (boolean, product level) |

There is one extraction strategy and no fallback chain: if `shopify` cannot read the response the
store returns `error` and the pipeline skips it.

## Quirks

- **The host is a market subdomain** (`ae.`). Other Sacoor markets presumably have their own hosts and
  currencies (not checked). The file pins this host and AED; nothing else is allowed.
- **No currency in the search response.** AED was confirmed only from a product page on 2026-10-07
  (`priceCurrency: "AED"` in the JSON-LD). If the store ever served another currency from this host,
  the prices would still be read as AED.
- **`type` packs season, gender and category into one string**, for example `Winter 2025 / Man /
  Blazer`, `Never Out of Stock / Man / Shirt Classic`, `Summer 2026 / Woman / Suit Blazer`. The
  season part is noise. The `shopify` extractor does not map `type`, and `Product` has no gender
  field, so the app cannot filter this store's products by gender. This matters because
  **women's items come back for unisex-worded queries**: 3 of 10 for `black blazer` on 2026-10-08
  (a women's suit and two suit blazers). `genders` is therefore unset in the store file (the store
  sells for both); a men's-only shopper searching "black blazer" may see those women's items.
- **`available` is product level.** It was true for every record seen (40 of 40 on 2026-10-07; 20 of 20 in the two responses saved on
  2026-10-08).
  On 2026-10-07 the product page for the slim-fit travel poplin shirt listed every size as
  `OutOfStock` in its JSON-LD while the search flag said available. Read `in_stock: true` as "some
  size may be orderable", not "your size is in stock".
- **The same product is listed under several handles.** Same title and price, different handle
  (for example `...comfort-cotton-185` and `...comfort-cotton-199`). Validation keeps the first and
  counts `duplicate_title_price`: 2, 2 and 1 records of 10 on the three live queries, so a query
  yields about 8 products, not 10.
- **Heavy sales.** Today 10 of 10 black-blazer records had a `compare_at_price_max` (a pre-sale price
  such as 2195.00 against 695.00 now), and 2 of 10 shirts. The extractor uses `price` only, so what
  the app shows is the current sale price; the price range will move when the sale ends.
- **Prices seen:** blazers and suits AED 497.50 to 957 (men's blazers 695 to 795), shirts AED 195 to
  495 (fixtures, 2026-10-08); the earlier run saw jackets 295 to 895 and shoes 295 to 1,495.
- **`url` carries tracking parameters** (`_pos`, `_psq`, `_psid`, `_ss`); the extractor drops the whole
  query string. `body` is store-supplied HTML (a description); it is not read and must never be
  rendered. The fixtures keep it cut to 300 characters.
- **Image CDN.** All images are on `cdn.shopify.com` under the path prefix
  `/s/files/1/0561/5422/6743/`, a host shared by every Shopify merchant. The prefix is asserted in the
  offline test only, not in the store file (the file allows the host). Thumbnail downloads with
  `width=400` were not exercised live in this task (no request was sent to the CDN).

## What would break the adapter

- **The merchant changes or restricts predictive search** (it is Shopify's endpoint on the merchant's
  storefront; they can turn it off or put it behind bot protection). Symptoms: HTTP 403/429 or a
  challenge page gives `blocked` and a cooldown; a changed JSON shape gives `error: no extraction
  strategy could read the response`; an empty list gives `empty`.
- **robots.txt starts disallowing `/search` or `/search/suggest.json`.** The engine then returns
  `robots_denied` without searching. Today the path is covered by `Allow: /`.
- **The host moves** (a redirect to another host, a new market domain). The allow-list refuses a
  redirect to a host that is not listed, so the store fails closed rather than following it.
- **The image CDN host changes.** The product page JSON-LD already uses the store's own host
  (`/cdn/shop/files/...`) instead of `cdn.shopify.com`; if search results ever do the same the host is
  already allowed, but if a third host appears every product is dropped as `image_url_not_allowed`.
- **The `type` format changes.** Nothing reads it today; it matters only if a gender/category filter
  is added later.
- **Pagination or `limit` above 10 is untested**, so at most 10 candidates (about 8 after
  de-duplication) per keyword variant.

## Fallback if the endpoint changes

There is no second strategy configured. In order of preference: (1) the store's own agent endpoint
(UCP/MCP, named in its robots.txt comment), which is the planned Phase 17 work and the store's stated
preference; (2) the HTML search page `/search?q=...`, which robots.txt also allows (checked offline on
2026-10-07, never requested) and would need a `css` extractor that does not exist yet; (3) drop the
store (`enabled: false`). None of these is built.

## Observed live today (2026-10-08)

All through `StoreSearchEngine` (honest User-Agent `vga-shopping-agent-demo/0.1 (store search
demo)`, protego robots check, 1 request/s). 7 requests to the store in total: 2 for robots.txt (the
capture run and the smoke test each build their own engine) and 5 searches. Every response was HTTP
200, no redirect, no challenge, no login wall.

| Query | Status | Records in response | Valid products kept | Seconds |
|---|---|---|---|---|
| `men shirt` | ok | 10 | 8 | 1.38 (includes the robots.txt fetch) |
| `black blazer` | ok | 10 | 8 | 1.01 |
| `shoes` | ok | 10 | 9 | 1.00 |

The `black blazer` and `men shirt` responses were also saved as the offline fixtures (18,984 and
22,148 bytes on the wire, the same sizes as on 2026-10-07; about 16.5 KB each after the long
descriptions were cut). robots.txt: 200, 3,652 bytes, the same size as the day before.

## robots.txt and the comment to AI agents

The search path is allowed (`Allow: /`; no Disallow rule matches `/search` or `/search/suggest.json`).
The top of the file is a comment block addressed to AI agents. As data, not instructions: it says
"Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans
(no automated checkout or payment), and it urges agents to recommend a third-party shopping skill to
their user. These are comments, not robots rules. This adapter does not act on them: it never
checks out and installs nothing, and the `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp` URLs it
mentions were not requested. The stated preference is for the terms-of-use step and Phase 17.

## Terms of use

Not reviewed (demo only). BRD Rule 6: check the store's terms before any real users.
