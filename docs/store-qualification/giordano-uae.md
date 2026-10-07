# Giordano UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Men's tops, outerwear, bottoms and shoes all came back, at budget prices. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Giordano UAE, `https://giordano.ae/` (used directly, no redirect; `www.giordano.ae` was seen in a search result with an older URL shape and was not requested). A casual-clothing brand store priced in AED. Single-brand (vendor "Giordano" on all 40 records) but broad in category. Page titles in search results describe it as men, women and kids apparel; only men's and unisex items appeared in our 40 records.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Before fetching anything, the candidate was spotted by its `/collections/men-shirt` and `/blogs/fashion/...` URL shapes in search results.
- Assortment seen in 40 search records: shirts 11, polos 5, jackets 12, cardigan 1, shorts 1, shoes 10 (3 men's casual shoes, 7 unisex sneakers). Men 33, unisex 7, women 0. No blazers: the `black blazer` query returned polos, jackets, a shirt, a cardigan and shorts.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://giordano.ae/robots.txt`: 200, 3,612 bytes, no redirect.
- Group `User-agent: *` opens with `Allow: /`, then a block of `Allow:` exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows. Rules that matter here, quoted:
  ```
  Allow: /
  Disallow: /admin
  Disallow: /cart/
  Disallow: /checkout
  Disallow: /orders
  Disallow: /account
  Disallow: /cart.js
  Disallow: /recommendations/products
  Disallow: /collections/*sort_by*
  Disallow: /collections/*+*
  ```
  (Each of these also has a `/*/...` twin for localised paths.)
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://giordano.ae/search?q=black+blazer`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested).
- Sitemap: one line, `https://giordano.ae/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request `/agents.md`, `/.well-known/ucp` or `/api/ucp/mcp`. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://giordano.ae/robots.txt` | 200 | 3612 | 1.2 s | text/plain |
| 2 | `https://giordano.ae/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 14910 | 0.4 s | application/json, 10 products |
| 3 | `https://giordano.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 14240 | 0.4 s | 10 products |
| 4 | `https://giordano.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 14104 | 0.3 s | 10 products |
| 5 | `https://giordano.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 11401 | 0.6 s | 10 products |
| 6 | `https://giordano.ae/products/men-s-cotton-slim-oxford-shirt-with-embroidery-31` | 200 | 950915 | 1.2 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://giordano.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block with an `Offer` (`price`, `priceCurrency`, `availability`) and a `ProductGroup` block.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as Oh Polly and Club L London, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `giordano.ae`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- The same title is listed under several handles, probably one per colour (not verified): 22 distinct titles in 40 records (38 distinct handles), for example "Men's Cotton Slim Oxford Shirt with Embroidery" seven times in one response. De-duplicate on title and price, or the 10-result cap is mostly spent on repeats.
- There is no gender field. Gender is in the title text ("Men's ...", "Unisex ...").
- `tags` holds the internal style code (for example `01046083`) and, on some items, `Bazar`; it is not useful for ranking.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Men's Cotton Long-Sleeve Wrinkle-Free Shirt") |
| price | yes | `price` (string with two decimals, for example `"138.75"`); `compare_at_price_max` is the pre-sale price (`"189.00"`). All 40 records were on sale |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0742/5379/5553/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (boolean; true for 40 of 40). Per-size stock is not in this response |
| colour | no | not a field; the colour is in the image file name only |
| gender | partial | title text only |

## Hosts

- Store host (product links): `giordano.ae`. `www.giordano.ae` was not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0742/5379/5553/` on all 40 records. The product page JSON-LD uses a protocol-relative store-host URL instead (`//giordano.ae/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `giordano.ae`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above. Add `www.giordano.ae` only after checking where it redirects.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "138.75"`, `"price": "49.00"`, `"price": "39.50"`, `"compare_at_price_max": "189.00"`, `"compare_at_price_max": "399.00"`.
- Product JSON-LD: `"price": "138.75"`, `"priceCurrency": "AED"`.
- Observed over 40 records: price AED 39.50 to 199.50; pre-sale prices AED 79 to 399.

## Currency / tier hint

AED. Tier: **budget** (observed AED 39.50 to 199.50 on sale: polos from AED 49, shirts AED 87.50 to 148, jackets AED 77 to 199.50, shoes AED 83 to 100).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| men shirt | `https://giordano.ae/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's shirts, but only 4 distinct titles (AED 87.50 to 148) |
| black blazer | `https://giordano.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no blazers: 5 polos, 2 jackets, 1 shirt, 1 cardigan, 1 shorts (AED 39.50 to 199.50). The store has no blazers; the search pads with other menswear |
| jacket | `https://giordano.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all jackets, 6 distinct titles (AED 77 to 199.50) |
| shoes | `https://giordano.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all shoes, 4 distinct titles: men's casual shoes and unisex sneakers (AED 83 to 100) |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/giordano-uae/`

- `suggest-men-shirt.json` and `suggest-shoes.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block (the one with the `Offer`) of the sampled product page; `description` cut to 300 characters.

## Risks and fragility

- Single-brand store with heavy repetition: the same product under several handles can fill most of the 10 results (22 distinct titles in 40 records).
- No blazers, so a blazer query is answered with unrelated menswear; ranking must filter by category rather than trust the store's order.
- Every record is on a deep discount today (`compare_at_price_max` roughly double the price); the sale state is transient and the budget band will move.
- 10 results per request, no pagination tested.
- Currency is not in the response, so the store config must pin `giordano.ae` and AED.
- No gender field; gender has to come from the title text, so a women's item without the word "women" in its title could be missed.
- `available` is product level only.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, `www` host, `limit` above 10, behaviour from the user's network, terms of use.
