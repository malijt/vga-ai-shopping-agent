# Sacoor Brothers UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). This is the broadest menswear store found so far: all four categories returned men's results (shirts, blazers, jackets and coats, shoes). One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Sacoor Brothers, UAE market storefront `https://ae.sacoorbrothers.com/`. The host is a market subdomain, so other markets presumably have their own hosts and currencies (not checked). A single-brand store (vendor "Sacoor Brothers" on all 40 records) with a menswear-led range and a smaller women's range. Not a GCC multi-brand retailer, but broad in category.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Before fetching anything, the candidate was spotted by its `/collections/suits` URL shape in a search result.
- Assortment seen in 40 search records: men 36 (shirts 10, blazers 7, jackets 8 plus 1 coat, shoes 10: loafers, casual and formal shoes, sneakers), women 4 (suit 1, suit blazers 2, leather jacket 1). Not seen in the four queries: trousers or other bottoms, knitwear other than inside jackets.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://ae.sacoorbrothers.com/robots.txt`: 200, 3,652 bytes, no redirect.
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://ae.sacoorbrothers.com/search?q=black+blazer`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested).
- Sitemap: one line, `https://ae.sacoorbrothers.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request `/agents.md`, `/.well-known/ucp` or `/api/ucp/mcp`. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://ae.sacoorbrothers.com/robots.txt` | 200 | 3652 | 0.9 s | text/plain |
| 2 | `https://ae.sacoorbrothers.com/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 22148 | 0.4 s | application/json, 10 products |
| 3 | `https://ae.sacoorbrothers.com/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 18984 | 0.4 s | 10 products |
| 4 | `https://ae.sacoorbrothers.com/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 12705 | 0.4 s | 10 products |
| 5 | `https://ae.sacoorbrothers.com/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 16399 | 0.4 s | 10 products |
| 6 | `https://ae.sacoorbrothers.com/products/slim-fit-travel-poplin-shirt-in-comfort-cotton-185` | 200 | 711090 | 1.0 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://ae.sacoorbrothers.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block whose `offers[]` have `price`, `priceCurrency` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as Oh Polly and Club L London, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `ae.sacoorbrothers.com`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- `type` is a path of the form `Season / Gender / Category`, for example `Winter 2025 / Man / Blazer`, `Never Out of Stock / Man / Shoes Formal`, `Winter 2025 / Woman / Suit Blazer`. The gender and category can be parsed from it; the season part is noise.
- The same title can appear under several handles (34 distinct titles in 40 records), so de-duplicate on title and price.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Structured Wool Blazer With Patch Pockets") |
| price | yes | `price` (string with two decimals, for example `"795.00"`); `compare_at_price_max` is the pre-sale price (`"2195.00"`), `"0.00"` when there is none. 25 of 40 records were on sale |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0561/5422/6743/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (boolean; true for 40 of 40). The sampled product page lists every size offer as `OutOfStock` in its JSON-LD while the search flag was true, so treat `available` as "some variant may be orderable" |
| gender | yes | inside `type` (`Man` / `Woman`) |
| colour | no | not a field; colour appears in some titles only |

## Hosts

- Store host (product links): `ae.sacoorbrothers.com`. The apex `sacoorbrothers.com` and other market hosts were not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0561/5422/6743/` on all 40 records. The product page JSON-LD uses the store host instead (`/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `ae.sacoorbrothers.com`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above. Add any other host only after checking where it redirects.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "795.00"`, `"price": "195.00"`, `"price": "1495.00"`, `"compare_at_price_max": "2195.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": "495.0"`, `"priceCurrency": "AED"`.
- Observed over 40 records: price AED 195 to 1,495; pre-sale prices up to AED 2,495.

## Currency / tier hint

AED. Tier: **premium** (shirts AED 195 to 495, men's blazers AED 695 to 795 on sale from AED 2,195, jackets AED 295 to 895, shoes AED 295 to 1,495; many items are heavily discounted from list prices of up to AED 2,495).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| men shirt | `https://ae.sacoorbrothers.com/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's shirts (AED 195 to 495) |
| black blazer | `https://ae.sacoorbrothers.com/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 7 men's blazers (AED 695 to 795), 3 women's suits and suit blazers (AED 497.50 to 957) |
| jacket | `https://ae.sacoorbrothers.com/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 9 men's (jackets, 1 leather jacket, 1 coat; AED 295 to 895), 1 women's leather jacket |
| shoes | `https://ae.sacoorbrothers.com/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's shoes (loafers, casual and formal shoes, sneakers; AED 295 to 1,495) |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/sacoor-brothers-uae/`

- `suggest-men-shirt.json` and `suggest-black-blazer.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page; `offers` cut to the first 3 of the size offers and `description` cut to 300 characters.

## Risks and fragility

- Single-brand store: results for any query are all one label. Within that it is the best category coverage seen: shirts, blazers, jackets and shoes for men.
- 10 results per request, no pagination tested, so at most 10 candidates per keyword variant.
- Currency is not in the response, so the store config must pin `ae.sacoorbrothers.com` and AED. Other Sacoor market hosts will price in other currencies.
- `type` packs season, gender and category into one string; its format is the merchant's and can change. Women's items do appear in queries that do not say "men" (3 of 10 for `black blazer`, 1 of 10 for `jacket`), so filter by the parsed gender.
- Many items are on deep discounts today (25 of 40 with a `compare_at_price_max`); the sale state is transient and the price range will move.
- `available` is product level only; the sampled page shows sizes out of stock while the search flag says available.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, other market hosts, `limit` above 10, behaviour from the user's network, terms of use.
