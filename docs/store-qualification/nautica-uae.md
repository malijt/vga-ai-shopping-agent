# Nautica UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Men's tops, outerwear and bottoms came back at mid prices; no shoes. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Nautica UAE, `https://nautica-ae.com/` (used directly, no redirect). A single-brand store (vendor "Nautica" on all 40 records) priced in AED, menswear-led with a few women's accessories.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Before fetching anything, the candidate was spotted by its `/collections/men` and `/blogs/news/...` URL shapes in search results.
- Assortment seen in 40 search records: shirts 13, joggers 6, jackets 5, hoodies 3, trousers 3, polos 2, sweatshirt 1, jeans 1, swim shorts 1 (men, 35 records); women's handbags 4 and a wallet 1 (accessories, 5 records). Not seen in the four queries: shoes (the `shoes` query returned joggers, handbags, jeans, swim shorts, trousers, a shirt and a polo) and blazers (the `black blazer` query returned black trousers, shirts, a hoodie, joggers, a polo and accessories).

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://nautica-ae.com/robots.txt`: 200, 3,624 bytes, no redirect.
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://nautica-ae.com/search?q=black+blazer`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested).
- Sitemap: one line, `https://nautica-ae.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request `/agents.md`, `/.well-known/ucp` or `/api/ucp/mcp`. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://nautica-ae.com/robots.txt` | 200 | 3624 | 1.0 s | text/plain |
| 2 | `https://nautica-ae.com/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 15589 | 0.4 s | application/json, 10 products |
| 3 | `https://nautica-ae.com/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 15596 | 0.4 s | 10 products |
| 4 | `https://nautica-ae.com/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 16827 | 0.5 s | 10 products |
| 5 | `https://nautica-ae.com/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 15349 | 0.4 s | 10 products |
| 6 | `https://nautica-ae.com/products/mens-solid-linen-shirt-white` | 200 | 243676 | 0.9 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://nautica-ae.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block with `offers[]` (`price`, `priceCurrency`, `availability`).

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the other Shopify stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `nautica-ae.com`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- Gender and category are in `tags` (`men`, `Mens`, `Men Shirts`, `mens topwear`, `Jackets for men`; women's accessories carry `Women`) and in `type` (`Shirts`, `Jackets`, `Joggers`, `women handbag`). The title usually starts "Men's ...".
- The colour is the last part of the title ("Men's Solid Linen Shirt - White").
- 33 distinct titles in 40 records: the same item can come back for two queries.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Men's Solid Linen Shirt - White") |
| price | yes | `price` (string with two decimals, for example `"139.00"`); `compare_at_price_max` is the pre-sale price (`"349.00"`). All 40 records were on sale |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0566/4355/1369/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (boolean; true for 40 of 40). Per-size stock is not in this response |
| colour | partial | end of the title; no colour field |
| gender | yes | `tags` and `type` |

## Hosts

- Store host (product links): `nautica-ae.com`. `www.nautica-ae.com` was not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0566/4355/1369/` on all 40 records. The product page JSON-LD uses the store host instead (`/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `nautica-ae.com`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above. Add `www.nautica-ae.com` only after checking where it redirects.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "139.00"`, `"price": "239.00"`, `"price": "59.00"`, `"compare_at_price_max": "349.00"`, `"compare_at_price_max": "799.00"`.
- Product JSON-LD: `"price": "139.0"`, `"priceCurrency": "AED"`.
- Observed over 40 records: price AED 59 to 239; pre-sale prices AED 149 to 799.

## Currency / tier hint

AED. Tier: **mid** (observed AED 59 to 239 on sale: shirts AED 129 to 139, hoodies AED 149, joggers and trousers AED 139 to 149, jackets AED 209 to 239; pre-sale list prices AED 149 to 799).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| men shirt | `https://nautica-ae.com/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's shirts (AED 129 to 139) |
| black blazer | `https://nautica-ae.com/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no blazers: 2 trousers, 2 shirts, 1 hoodie, 1 jogger, 1 polo, 2 women's shoulder bags, 1 wallet (AED 59 to 149); the search matches the word "black" |
| jacket | `https://nautica-ae.com/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 5 jackets (AED 209 to 239), 2 hoodies, 2 joggers, 1 sweatshirt |
| shoes | `https://nautica-ae.com/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no shoes: 3 joggers, 2 women's shoulder bags, jeans, swim shorts, trousers, a shirt, a polo (AED 109 to 149). The store has no footwear in this response; the search pads with other items |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/nautica-uae/`

- `suggest-men-shirt.json` and `suggest-jacket.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page; `offers` cut to the first 3 of the size offers and `description` cut to 300 characters.

## Risks and fragility

- Single-brand store: all results are one label. Good for men's shirts, jackets, trousers and joggers; no shoes and no blazers.
- Padding with off-category items (women's bags, a wallet) when a query has few matches, so ranking must filter by category and gender rather than trust the store's order.
- Every record is on a deep discount today (`compare_at_price_max` about 2 to 3 times the price, several `B1G1` tags); the sale state is transient and the price range will move.
- 10 results per request, no pagination tested.
- Currency is not in the response, so the store config must pin `nautica-ae.com` and AED.
- `available` is product level only.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, `www` host, `limit` above 10, behaviour from the user's network, terms of use.
