# Giordano UAE: store notes (plan 12.1.4)

Store id `giordano-uae`, storefront `https://giordano.ae/`, config `config/stores/giordano-uae.yaml`,
tests `tests/stores/giordano-uae/`. Qualification evidence: `docs/store-qualification/giordano-uae.md`.
State on 2026-10-08: **`enabled: true`** (the live smoke test passed once, with 4 requests to the store).

## Data path

1. Search URL (from the store file, brackets sent percent-encoded):
   `https://giordano.ae/search/suggest.json?q={query}&resources%5Btype%5D=product&resources%5Blimit%5D=10`.
   Shopify's public predictive-search endpoint. It answers `{"resources":{"results":{"products":[...]}}}`
   with at most 10 products and no pagination.
2. The engine checks `https://giordano.ae/robots.txt` with protego first (cached 24 h per host),
   then sends one request per keyword variant, 1 request/s, with the honest User-Agent from settings.
3. The `shopify` extractor maps `title`, `price` (a string such as `"138.75"`), `image`, `url` and
   `available`. The product link is built from the host plus `/products/{handle}` with Shopify's
   tracking query (`_pos`, `_psq`, `_psid`, `_ss`) removed. The image URL gets `width=400` (the `v=`
   version is kept). Currency is **not** in the response: `currency: AED` comes from the store file.
4. Normalisation validates the six required fields, `allowed_hosts` (`giordano.ae`,
   `cdn.shopify.com`) and https, then collapses repeats (same title and price).

`genders` is deliberately unset. Qualification saw men's and unisex items, and the store's page
titles also describe women's and kids' lines, so it is not a single-gender store. Today's 30 records
were all "Men's ..." or "Unisex ...", with no women's item. A women's query is therefore sent here
and will probably be answered with men's or unisex items; that was not tested (it would need a
fourth query). The ranker and gender filter must deal with it, not this store file.

## Quirks seen

- **One title under several handles.** A product is listed once per colour, each with its own handle,
  image and URL, and the same title and price. Today the 10 records of each query collapsed to 4
  ("men shirt"), 6 ("jacket") and 4 ("shoes") distinct products (reason `duplicate_title_price`, by
  design). With the endpoint capped at 10 records, the store supplies only 4 to 6 products per query:
  never more than the per-store cap of 6, and below the plan's "10 valid products per query" milestone.
- **Everything is on sale.** Every record carries a `compare_at_price_*` about double `price`
  (for example AED 113.50, was AED 225.00). `price` is what the shopper pays and is what we use.
  The sale is transient, so the budget band may move.
- **Two apostrophes.** Titles use both `Men’s` (U+2019) and `Men's` (ASCII), sometimes within one
  response. Title normalisation (NFKC and case folding) does not equate them, so text matching and
  de-duplication must not rely on one form.
- **No gender, colour or size field.** Gender is in the title text only. `tags` holds an internal
  style code, `type` is a category word (`Shirts`, `Jackets`, `Shoes`), colour is only in the image
  file name, and `available` is product-level (true for all 30 records today).
- `body` is store-supplied HTML: it is never used or rendered. `variants` is an empty list.
- The search pads short answers with other menswear (a "black blazer" query returned polos and
  jackets on 2026-10-07; the store has no blazers).

## What would break this adapter

| Change at the store | What the engine does |
|---|---|
| robots.txt starts disallowing `/search` or `/search/suggest.json` | `robots_denied`, no search request is sent, store listed as skipped |
| Bot challenge, 403, 429 or login redirect | `blocked`, one request only, cooldown (900 s); never retried or bypassed |
| Shopify changes or removes predictive search, or the JSON shape moves | `error`: "no extraction strategy could read the response"; other stores are unaffected |
| The merchant redirects `giordano.ae` to `www.giordano.ae` (or another domain) | A cross-domain redirect is not followed (`error`); add the new host to `search_url_template` and `allowed_hosts` |
| Images move to another CDN host | Records dropped as `image_url_not_allowed`; add the host to `allowed_hosts` |
| Prices stop being plain decimals, or another currency appears | Records dropped (`unknown_price_format`, `currency_mismatch`) |
| Endpoint returns many more repeats | Fewer distinct products per query; nothing breaks, results thin out |

**Fallbacks if the endpoint changes** (none is built or tested): the HTML search page
`/search?q=` and `/products.json` are not disallowed by robots.txt (offline protego check, not
requested) and would need a `css` or `store_json` extractor; the store's own agent endpoint is the
subject of Phase 17. If the endpoint breaks, set `enabled: false` and the demo uses the other stores.

To refresh the fixture after a store change, run the live test once and keep the raw responses
(4 requests, honest client): `VGA_STORE_RECORD_DIR=/some/folder uv run pytest -m live tests/stores/giordano-uae -q -s`.

## Observed live on 2026-10-08

Run through `StoreSearchEngine` with the real store file (4 requests in total: robots.txt, then one
search per query, each answered 200, no redirect, no challenge):

| Query | Status | Records / kept | Seconds (engine) | Prices seen (AED) |
|---|---|---|---|---|
| `men shirt` | ok | 10 / 4 | 1.40 | 87.50 to 148.00 |
| `jacket` | ok | 10 / 6 | 0.98 | 77.00 to 199.50 |
| `shoes` | ok | 10 / 4 | 0.96 | 83.00 to 100.00 |

The seconds include the 1 request/s wait. Response sizes (14,910, 14,104 and 11,401 bytes) and
robots.txt (3,612 bytes) matched the 2026-10-07 qualification exactly. The `jacket` answer is saved
unedited as `tests/stores/giordano-uae/fixtures/suggest-jacket.json` (14 KB; the longest `body` is 552
characters, so nothing was trimmed) and robots.txt as `fixtures/robots.txt`.

## robots.txt

The path is open: `Allow: /`, with disallows for carts, checkout, orders, accounts, `/cart.js`,
`/recommendations/products` and filtered or sorted collections. Nothing matches `/search`.

The comment block at the top of robots.txt is addressed to AI agents. It is recorded here as data;
nothing was done because of it, and `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp` were not
requested. It says, in part: "Agents should use UCP/MCP for catalog, cart, and checkout." It also
asks agents acting as personal shoppers to recommend that their user install a third-party skill, and
says checkout is for humans. A later comment labels `Disallow: /cart.js` as an AJAX surface for which
agents "should use UCP/MCP instead"; that is a comment above a rule that does not cover our path.
Whether the store's stated preference should change our route is a decision for Phase 17 and the
terms review.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before any real users.
