# The Bear House UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). It is a menswear store at budget prices covering men's tops, outerwear and bottoms, but no shoes. Two caveats: the search response carries no currency field (AED is store-level and was confirmed only from the product page's JSON-LD, `priceCurrency: "AED"`), and this store's product name is in the `vendor` field while `title` holds only a short style code (see Extraction strategy).

## Storefront

- Store: The Bear House UAE, `https://www.thebearhouse.ae/` (the `www` host was used directly; no redirect). A menswear brand store priced in AED (page titles in search results call it men's clothing; its main site is a separate domain that was not requested). Single-brand, broad within menswear.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Before fetching anything, the candidate was spotted by its `/collections/shirts` and `/products/...` URL shapes in search results.
- Assortment seen in 40 search records: shirts 14, T-shirts 8, jackets 7, "shackets" (shirt-jackets) 5, trousers 5, hoodie 1. Men only. Not seen in the four queries: shoes (the `shoes` query returned 8 T-shirts and 2 shirts), blazers (the `black blazer` query returned trousers, shirts, jackets and a hoodie), denim.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://www.thebearhouse.ae/robots.txt`: 200, 3,644 bytes, no redirect.
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://www.thebearhouse.ae/search?q=black+blazer`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested).
- Sitemap: one line, `https://www.thebearhouse.ae/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request `/agents.md`, `/.well-known/ucp` or `/api/ucp/mcp`. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.thebearhouse.ae/robots.txt` | 200 | 3644 | 1.2 s | text/plain |
| 2 | `https://www.thebearhouse.ae/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 22049 | 0.5 s | application/json, 10 products |
| 3 | `https://www.thebearhouse.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 28547 | 0.5 s | 10 products |
| 4 | `https://www.thebearhouse.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 26139 | 0.4 s | 10 products |
| 5 | `https://www.thebearhouse.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 29172 | 0.4 s | 10 products |
| 6 | `https://www.thebearhouse.ae/products/boali` | 200 | 143069 | 1.0 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://www.thebearhouse.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `ProductGroup` JSON-LD block whose variants each have an `Offer` with `price`, `priceCurrency` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the other Shopify stores, with one store-specific mapping that the plain strategy would get wrong:

- **Name field.** `title` is a short style code (for example `"BOALI"`, `"Tilos"`, `"Ted"`) and the human-readable product name is in `vendor` (for example `"Olive Checked Slim Fit Casual Shirt"`). The product page's JSON-LD has the same inversion (`name: "BOALI"`, `brand.name: "Olive Checked Slim Fit Casual Shirt"`). A `shopify` extractor that reads `title` would show codes and match keywords badly, so its store config needs a way to name the title field (`vendor` here), or the extractor must fall back to `vendor` when `title` is a single short token.
- Currency from config (`AED`), not from the response. Pin the host `www.thebearhouse.ae`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- There is no gender field and most records do not say "men" (12 of 40 do). Treat the whole store as men's in its config.
- Colour, fit and fabric are in `tags` (for example `Olive`, `Slim Fit`, `Cotton Blend`) and in `body`, which is store-supplied HTML.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes, but see above | the readable name is in `vendor`; `title` is a style code |
| price | yes | `price` (string with two decimals, for example `"59.00"`); `compare_at_price_max` is the pre-sale price (`"169.00"`). All 40 records were on sale |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0683/6751/5787/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (boolean; true for 40 of 40). The sampled product page shows two of its three listed sizes as `OutOfStock` |
| colour | partial | `tags` (for example `Olive`, `Black`) and `body` |

## Hosts

- Store host (product links): `www.thebearhouse.ae`. The apex `thebearhouse.ae` was not requested. `thebearhouse.com` is a different storefront and is not part of this store.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0683/6751/5787/` on all 40 records. The product page JSON-LD uses the store host instead (`https://www.thebearhouse.ae/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `www.thebearhouse.ae`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above. Add the apex only after checking where it redirects.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "59.00"`, `"price": "119.00"`, `"price": "49.00"`, `"compare_at_price_max": "169.00"`, `"compare_at_price_max": "329.00"`.
- Product JSON-LD: `"price": "59.00"`, `"priceCurrency": "AED"`.
- Observed over 40 records: price AED 49 to 119; pre-sale prices AED 149 to 329.

## Currency / tier hint

AED. Tier: **budget** (observed AED 49 to 119 on sale: shirts AED 50 to 69, T-shirts AED 55 to 79, trousers AED 49 to 99, jackets AED 69 to 119; pre-sale list prices AED 149 to 329).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| men shirt | `https://www.thebearhouse.ae/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's shirts (AED 50 to 59), titles are style codes |
| black blazer | `https://www.thebearhouse.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no blazers: 5 trousers, 2 shirts, 2 jackets (a black varsity jacket, a check jacket), 1 hoodie (AED 49 to 119); the search matches the word "black" |
| jacket | `https://www.thebearhouse.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 5 jackets and 5 shackets (AED 69 to 119) |
| shoes | `https://www.thebearhouse.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no shoes: 8 T-shirts and 2 shirts (AED 55 to 79). The store has no footwear; the search pads with other menswear |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/bear-house-uae/`

- `suggest-men-shirt.json` and `suggest-black-blazer.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters. They show the `title` / `vendor` inversion.
- `product-jsonld.json`: the `ProductGroup` JSON-LD block of the sampled product page; `hasVariant` cut to the first 3 of the size variants and `description` cut to 300 characters.

## Risks and fragility

- The title/vendor inversion above. If the merchant fixes it, a config that reads `vendor` for the name would then show the brand instead; the config should be checked after any theme change.
- Single-brand, menswear only, no shoes and no blazers. It helps men's shirt, T-shirt, jacket and trouser queries and adds nothing for women's queries.
- Every record is on a deep discount today (`compare_at_price_max` about 2 to 3 times the price); the sale state is transient and the budget band will move.
- 14 of the 40 records carry a `delistedstyles` tag while `available` is true. What that tag means to the merchant is not verified; such items may not be orderable.
- 10 results per request, no pagination tested.
- Currency is not in the response, so the store config must pin `www.thebearhouse.ae` and AED.
- `available` is product level only; the sampled page shows sizes out of stock while the search flag says available.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, apex host, `limit` above 10, behaviour from the user's network, terms of use.
