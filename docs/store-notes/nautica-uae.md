# Nautica UAE: store notes (plan 12.2.4)

> **Update 2026-10-08:** where this note says a product has no gender field or that the reader
> ignores `type` and `tags`, that is no longer true. The Shopify reader now sets a product's gender
> from those fields, `type` first (ADR 0014).

Store id `nautica-uae`, storefront `https://nautica-ae.com/`, a Shopify store of one brand
(vendor "Nautica", all 40 records seen on 2026-10-08). Config: `config/stores/nautica-uae.yaml`
(`enabled: true`, mid_range, `genders` unset). Qualification report (2026-10-07):
`docs/store-qualification/nautica-uae.md`. Offline tests and the saved responses:
`tests/stores/nautica-uae/`. Live smoke test: `uv run pytest -m live tests/stores/nautica-uae -q`.

## Data path

One GET per query, to Shopify's public predictive-search endpoint, no HTML:

```
https://nautica-ae.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10
```

The engine sends the brackets percent-encoded (`%5B`, `%5D`), checks `robots.txt` first, and reads
the JSON `resources.results.products[]` with the `shopify` strategy. What each Product field comes
from:

| Field | Source in the response |
|---|---|
| title | `title` |
| price | `price`, a string such as `"139.00"` (the sale price) |
| currency | not in the response; `currency: AED` from the store file (the product page's JSON-LD says `AED`) |
| image_url | `image` (else `featured_image.url`), on `cdn.shopify.com`; the extractor sets `width=400` |
| product_url | `url` with its tracking query removed (`?_pos=..&_psq=..&_psid=..&_ss=e`), on `nautica-ae.com` |
| in_stock | `available` (product level; the per-size `variants` list is always empty) |

Not extracted, by design of the shared `shopify` strategy: colour, category, gender (see Quirks).
At most 10 products per call; larger `limit` values and paging were never tried.

## Quirks seen

- **Gender and category live in `tags` and `type`, which the extractor does not carry.** Men's
  items have tags such as `Mens`, `men`, `Men Shirts`, `Jackets for men`; women's items have
  `Women`, `women-new`. `type` holds `Shirts`, `Jackets`, `Joggers`, `Trousers`, `Hoodies`,
  `Sleeveless top`. The title often says it ("Men's Solid Linen Shirt - White", "Women's Trouser")
  but not always: "Litus FZ Jacket", "Nelson Pant - Black" and "Coron FZ Jacket - Dark Navy" have no
  gender word. A `Product` has no gender field and ranking reads the title, so for those items
  only the tags (which we drop) would say who they are for.
- **Both genders are sold, so `genders` is unset.** The 2026-10-07 report saw men's clothing and
  women's bags and a wallet, and suggested a men's store. On 2026-10-08 one extra query,
  `women dress`, returned 10 women's items: shirts, trousers and sleeveless tops (13 of the 40
  records seen that day carry the `Women` tag, 27 carry `Mens`/`men`). A women's shopper must still
  reach the store. No dresses were seen.
- **Results are padded when a query has few matches.** `black blazer` and `shoes` (report) returned
  women's shoulder bags and a wallet, joggers and trousers, no blazers and no shoes. Today's
  `trousers` returned three women's trousers among the men's; `women dress` returned no dress at
  all. The store sells no footwear that these queries found. Good queries: shirts, jackets,
  trousers, joggers, hoodies, polos, jeans, swim shorts.
- **Colour variants of women's items collapse.** Women's titles carry no colour ("Women's Trouser");
  the colour is only in the handle (`womens-trouser-navy`). The shared validation treats the same
  title at the same price as one product, so 4 colours of "Women's Long Sleeve Shirt" become 1
  (the first one returned). Men's titles end in " - Colour", so they stay separate.
- **Everything was on sale.** All 40 records seen on 2026-10-08 had a `compare_at_price_max` 1.9 to
  3.3 times the `price`, many with a `B1G1` or `Sale` tag. The price we show is the sale price and
  will move when the sale ends. Seen: AED 99 to 239 (report on 2026-10-07: AED 59 to 239).
- **Vendor and `body`.** The vendor is always "Nautica", so the title is the right name field
  (no `name_field: vendor`). `body` is store-supplied HTML: never read or shown. The saved
  responses cut it to 300 characters.
- **Same item, several queries.** 40 records are 30 distinct titles and 38 distinct handles; the
  engine collapses repeats within one store's result.

## What would break the adapter, and what to do

| Change | What we would see | Fallback |
|---|---|---|
| The store removes or restricts `/search/suggest.json`, or changes the JSON shape | `error` status "no extraction strategy could read the response" | Set `enabled: false`; use the store's HTML search page (`/search?q=`, which the 2026-10-07 offline robots check allowed, never requested) with a `css` or `json_ld` strategy, or the store's agent endpoint (plan Phase 17) |
| robots.txt starts to disallow the path | `robots_denied`, no search sent | Stop using it; do not work around it |
| A bot challenge, 403, 429 or login page | `blocked`; the store is not contacted for the cooldown (900 s) | Drop the store (BRD Rule 2); never bypass |
| Images move to the store's own host (the product page's JSON-LD already uses `nautica-ae.com/cdn/shop/files/`) | every record dropped as `image_url_not_allowed` | Add the new image host to `allowed_hosts` after looking at it |
| The apex redirects to `www.nautica-ae.com` | the request is refused (the host is not allowed) | Switch the template and `allowed_hosts` to `www`, after checking the redirect |
| The store changes its currency | prices wrong with no error, because the response has no currency | Compare with the product page JSON-LD and update `currency` |
| The sale ends | prices rise to the `compare_at` values (AED 149 to 799); the mid_range hint may be too low | Re-check prices, update `tier_hint` |
| Shopify raises the 10-product cap or changes ranking | more or different products | Re-record the fixtures (below) |

To re-record: run a handful of queries through `StoreSearchEngine` (4 to 5 requests, one engine so
`robots.txt` is fetched once), save each raw response, cut each `body` to 300 characters, keep every
product, and update the counts at the top of `tests/stores/nautica-uae/test_nautica_uae_fixtures.py`.

## Observed live on 2026-10-08

All requests went through `StoreSearchEngine` (honest User-Agent `vga-shopping-agent-demo/0.1
(store search demo)`, robots.txt checked with protego, 1 request per second). No block, no
challenge, no redirect, no robots denial. 9 requests in total: 2 runs, each fetching `robots.txt`
once, plus 4 searches in the capture run and 3 in the live test.

| Query | Run | Status | Products returned | Kept after validation | Seconds |
|---|---|---|---|---|---|
| men shirt | capture | ok | 10 | 10 | 1.77 (includes `robots.txt`) |
| jacket | capture | ok | 10 | 10 | 0.76 |
| trousers | capture | ok | 10 | 8 | 0.93 |
| women dress | capture (extra, to decide `genders`) | ok | 10 | 3 | 1.00 |
| men shirt | live test | ok | 10 | 10 | 1.54 (includes `robots.txt`) |
| jacket | live test | ok | 10 | 10 | 1.02 |
| trousers | live test | ok | 10 | 8 | 0.79 |

The live test passed (each query ok, at least 3 valid products, within the 6 s timeout). Every
dropped record was a repeat (`duplicate_title_price`), none was invalid. The capture run's four
responses are the fixtures in `tests/stores/nautica-uae/fixtures/`.

## robots.txt and terms

- `robots.txt` leaves `/search/suggest.json` open under `User-agent: *` (`Allow: /`; the engine's
  protego check passed on every request on 2026-10-08). It disallows `/admin`, `/cart/`, `/checkout`,
  `/orders`, `/account`, `/cart.js`, `/recommendations/products`, `/collections/*sort_by*` and
  `/collections/*+*`.
- Its opening comment is addressed to AI agents. Quoted as data, from the 2026-10-07 report (the
  file was not re-read as text today): "Agents should use UCP/MCP for catalog, cart, and checkout."
  It is a comment, not a rule. It was not acted on: no `/agents.md`, `/.well-known/ucp` or
  `/api/ucp/mcp` was requested. Whether to follow that preference is for the terms-of-use review
  and plan Phase 17.
- Terms of use: not reviewed (demo only).
