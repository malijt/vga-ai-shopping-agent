# Club L London UAE: store notes (plan 12.5, written 2026-10-08)

**Status:** enabled in `config/stores/club-l-london.yaml`. The live smoke test passed on 2026-10-08. Qualification evidence: [`docs/store-qualification/club-l-london.md`](../store-qualification/club-l-london.md). Offline tests: `tests/stores/club-l-london/`.

## Data path

1. `StoreSearchEngine` fetches `https://www.clubllondon.ae/robots.txt` once (cached for 24 hours), checks the search URL with protego, then fetches one search URL per keyword variant:
   `https://www.clubllondon.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10` (the brackets go out percent-encoded as `%5B` and `%5D`).
2. The response is Shopify's predictive-search JSON, `{"resources": {"results": {"products": [...]}}}`, at most 10 products per call. The `shopify` extractor maps `title`, `price` (a string such as `"1199.00"`), `image` (falling back to `featured_image.url`), `url` (relative; made absolute against the www host, tracking query removed) and `available` (the in-stock flag).
3. The extractor options are the defaults: the name is read from `title`, and `image_width` is 400, so every image URL ends in `...?v=...&width=400` and the CDN serves a resized thumbnail (the original of the first product is 2040 x 3060 pixels).
4. Currency is not in the response. The store file pins `currency: AED`; AED was confirmed on 2026-10-07 from the product page's JSON-LD (`priceCurrency`).
5. Hosts: `www.clubllondon.ae` (links) and `cdn.shopify.com` (images). Every product seen on 2026-10-08 had a relative `/products/...` link and a `cdn.shopify.com` image, so nothing was dropped by the allow-list. The apex `clubllondon.ae` is not listed: it only redirects to `www`, and no request or product link uses it.

## Quirks seen

- **A single women's going-out brand.** `genders: [women]`. Evidence: every one of the 30 products returned on 2026-10-08 is womenswear (dresses, blazers, heels), and the 2026-10-07 report saw no menswear in 30 more. A men's request is not sent here.
- **Dresses dominate, and how much depends on the query.** The qualification run for "black blazer" returned 1 blazer and 9 dresses. On 2026-10-08, "blazer" returned 10 blazers (no dress), "jacket" returned 10 blazers and jackets (no dress), and "heels" returned 5 shoes and 5 dresses. Dresses are outside the app's four categories. Extraction keeps them; ranking removes them later. Use short, garment-only keywords for this store: multi-word queries with a colour or style drift to dresses.
- **Titles read `Name | Colour Style`** (for example `Hurley | Snake Print Plunge Long Sleeve Tailored Blazer`). The first word is a model name, not a brand.
- **Useful for women's outerwear (blazers) and heels only, so far.** No trousers, skirts, flat shoes or ordinary tops appeared in any result seen, but none of those was searched for, so the store may sell them. The 30 records of 2026-10-08 (the blazer and jacket queries repeat many of the same items) are 20 blazer or jacket records, 5 heeled shoes and 5 dresses.
- **`type` is not reliable** (a blazer typed `TOPS`, blazers typed `COATS & JACKETS` and `JACKETS & BLAZERS`). It is not mapped; the title is what ranking reads.
- **At most 10 products per request**, and pagination was not tested. The 10 are the store's own relevance order.
- **Prices** are strings with two decimals (`"1199.00"`). `compare_at_price_max` holds the pre-sale price (`"0.00"` when there is none) and is not used: the shown price is the current one. Prices seen across the 30 products: AED 199 to 1,790 (blazers 999 to 1,370, one cropped jacket 199, heels 299 to 449, dresses 649 to 1,790).
- **`available` is product level only**, and was true for all 30 products. There is no colour field in the search response (colour is in the title).
- **`body` is store-supplied HTML.** The extractor does not read it. Never render it. The fixtures keep the first 300 characters of each `body` only.
- **The product link carries tracking parameters** (`_pos`, `_psq`, `_psid`, `_ss`); the extractor removes them.

## What would break the adapter

| Change at the store | What the app does | What to do |
|---|---|---|
| The merchant turns off or restricts `/search/suggest.json` (the visible search is a custom `/pages/search`, so a search app is installed and the default endpoint is not essential to the site) | HTTP error or non-JSON: status `error`, store skipped for the request | Set `enabled: false`. Fallbacks: the store's UCP/MCP endpoint (Phase 17, not tested), or an HTML or `css` strategy on `/pages/search` after a new qualification pass |
| robots.txt starts disallowing `/search` | status `robots_denied`, no search request made | Set `enabled: false`; never bypass |
| Cloudflare (or the store) starts challenging or returning 403/429 | status `blocked`, the store goes into cooldown, no retry | Set `enabled: false` and re-qualify from another network; never bypass |
| The response shape changes (no `resources.results.products`, `price` no longer a string) | status `error` (extraction cannot read it) or all records dropped; the `shopify` fixture test fails on the next recording | Re-record a fixture, adjust the extractor in its own PR |
| The store moves host (for example to `clubllondon.ae`, or a regional domain) | The first request to the new host is refused by the allow-list, or a cross-domain redirect is not followed | Update `search_url_template` and `allowed_hosts` together |
| Images move off `cdn.shopify.com` | Records dropped as `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The store starts selling in another currency | Prices would be mislabelled as AED. The response has no currency field to compare | Re-check the product page JSON-LD; the live test does not catch this |
| The assortment changes (a new women's category, or a men's line) | Nothing breaks; results change | Update `genders` and these notes |

If the page changes in a way we cannot read, the fallback is to switch the store off (`enabled: false`). The demo then runs on the other stores, as it already must for any store that blocks (BRD Rule 2).

## Observed live on 2026-10-08

All requests went through `StoreSearchEngine` (honest User-Agent `vga-shopping-agent-demo/0.1 (store search demo)`, robots.txt checked first, 1 request/s, no retries). 8 requests in total: a recording run (robots.txt + 3 searches), then the live smoke test (robots.txt + 3 searches). The recording run only added a pass-through transport that saved response bodies; it did not change any request header.

| Query | Status | Products kept | Not dresses (by title) | Engine time |
|---|---|---|---|---|
| `blazer` | ok | 10 of 10 | 10 | 1.96 s (includes the robots.txt fetch and its 1 s spacing) |
| `jacket` | ok | 10 of 10 | 10 | 0.82 s |
| `heels` | ok | 10 of 10 | 5 (the other 5 are dresses) | 1.01 s |

- robots.txt: 200, 3,640 bytes (the same size as on 2026-10-07). `Allow: /`, with no rule that matches `/search/suggest.json`.
- Searches: 200 `application/json`, 29,857 / 29,211 / 32,603 bytes, 0.7 to 1.0 s each from this network. No challenge page, CAPTCHA or login wall; nothing was dropped by validation.
- The live test's pass rule (status `ok`, at least 3 valid products, inside the time budget) held for all three queries.

## robots.txt comment addressed to AI agents (data, not acted on)

The comment block at the top of robots.txt (the 2026-10-07 report found the same text in Oh Polly's file, apart from the shop's domain) says, briefly: "Agents should use UCP/MCP for catalog, cart, and checkout", gives the endpoint `https://www.clubllondon.ae/api/ucp/mcp` and an agent-instructions page at `/agents.md`, and says "Checkouts are for humans." It also asks agents that act as personal shoppers to install a third-party skill from `shop.app`. These are comments, not robots rules. I did not request any of those URLs or install anything. The stated preference for the UCP/MCP endpoint is the subject of Phase 17 and must be reviewed before real users (BRD Rule 6). This app never checks out or buys anything; it only links to the product page.

## Terms of use

Terms of use: not reviewed (demo only).
