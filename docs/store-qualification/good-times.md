# Good Times UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 38 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). It is a multi-brand streetwear and skate store, strong for men's T-shirts and tops, thin for outerwear and bottoms, and with no footwear in the results. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Good Times, `https://good-times.ae/` (used directly, no redirect). A UAE online streetwear and skate shop (its own search-result description) priced in AED. Multi-brand: 11 vendors in 38 records (Ripndip 7, Taka Original 7, The Ragged Priest 4, Ethik 3, Minga London 3, Rockabilia 2, We Are Not Friends, Human Society, Thrasher, Foundation Skateboards, PushCA).
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 38 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Before fetching anything, the candidate was spotted by its `/collections/tops` and `/pages/men` URL shapes in search results.
- Assortment seen in 38 search records: T-shirts 16, tops 2, jumpers 4, sweater 1, cardigan 1, vest 1, jacket 1 (a women's denim jacket), pants 1, skirt 1, headwear 1, skate parts 9 (8 griptape sheets and a deck). Gender is in `tags`: 24 records carry `men`, 25 carry `women`, 20 carry both (unisex), 9 carry neither (exactly the skate parts). Not seen: men's jackets or coats, shoes (the `shoes` query returned only 8 griptape sheets), blazers, more than one pair of pants.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://good-times.ae/robots.txt`: 200, 3,620 bytes, no redirect.
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://good-times.ae/search?q=black+blazer`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested).
- Sitemap: one line, `https://good-times.ae/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request `/agents.md`, `/.well-known/ucp` or `/api/ucp/mcp`. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://good-times.ae/robots.txt` | 200 | 3620 | 1.1 s | text/plain |
| 2 | `https://good-times.ae/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 23313 | 0.4 s | application/json, 10 products |
| 3 | `https://good-times.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 20988 | 0.4 s | 10 products |
| 4 | `https://good-times.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 25208 | 0.4 s | 10 products |
| 5 | `https://good-times.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 26310 | 0.6 s | 8 products |
| 6 | `https://good-times.ae/products/marble-tee` | 200 | 152224 | 0.6 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://good-times.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 for three queries and 8 for `shoes`. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block whose `offers[]` have `price`, `priceCurrency` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the other Shopify stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `good-times.ae`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- Gender and category come from `tags`: `men`, `women` (both on unisex items), `top`, `bottom`. The same list also holds sizes (`S`, `M`, `L`, `XL`) and internal markers (`box3`, `2021-1`, `secret-m`), which are noise. `type` is free-form (`T-Shirt`, `Top`, `Jumper`, `Pants`, `Griptape`).
- Brand is `vendor` and is a real brand name here.
- Skate hardware (griptape, decks) and hats come back for fashion queries; ranking must filter them out by category.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Marble Tee", "Daytona Pants") |
| price | yes | `price` (string with two decimals, for example `"150.00"`); `compare_at_price_max` is the pre-sale price (`"220.00"`), `"0.00"` when there is none. 10 of 38 were on sale |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0539/3285/1399/products/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (boolean; true for 37 of 38, false for one griptape sheet). Per-size stock is not in this response |
| colour | partial | in some titles ("Sweet Life Flower T-Shirt, Black"); no colour field |
| gender | yes | `tags` (`men`, `women`) |

## Hosts

- Store host (product links): `good-times.ae`. `www.good-times.ae` was not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0539/3285/1399/` on all 38 records. The product page JSON-LD uses the store host instead (`https://good-times.ae/cdn/shop/products/...`).
- Candidate `allowed_hosts`: `good-times.ae`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above. Add `www.good-times.ae` only after checking where it redirects.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "150.00"`, `"price": "280.00"`, `"price": "70.00"`, `"compare_at_price_max": "220.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": "150.0"`, `"priceCurrency": "AED"`.
- Observed over 38 records: price AED 70 to 330; pre-sale prices AED 175 to 380.

## Currency / tier hint

AED. Tier: **mid** (observed AED 70 to 330: T-shirts AED 130 to 200, jumpers AED 170 to 280, pants AED 180, a women's denim jacket AED 180; griptape AED 70 and a skate deck AED 330). Branded streetwear tees at AED 130 to 200 sit above budget retail, below premium.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| men shirt | `https://good-times.ae/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's or unisex tops: 8 T-shirts, 2 tops (AED 140 to 190) |
| black blazer | `https://good-times.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no blazers: 6 T-shirts, 1 jumper, 1 pair of pants, 1 hat, 1 skate deck (AED 130 to 330); the search matches the word "black" |
| jacket | `https://good-times.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, 1 jacket (a women's denim jacket) plus 3 jumpers, 2 T-shirts, a skirt, a vest, a sweater, a cardigan (AED 150 to 280) |
| shoes | `https://good-times.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 8, no shoes: all griptape sheets for skateboards (AED 70) |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/good-times/`

- `suggest-men-shirt.json` and `suggest-jacket.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page; `offers` cut to the first 3 of the size offers and `description` cut to 300 characters.

## Risks and fragility

- Narrow fashion coverage: strong for men's and unisex tees, little else. No men's outerwear, one pair of pants and no footwear in four queries. It adds a mid-priced streetwear option for men's tops and nothing for blazers, jackets or shoes.
- Off-category padding: skate decks, griptape and hats are returned for fashion queries (8 of 8 results for `shoes` were griptape), so ranking must filter by category rather than trust the store's order.
- Gender signals are in free-form `tags` that mix sizes and internal markers; the 9 records without a gender tag were all skate parts, but the tag convention could change.
- 10 results per request, no pagination tested.
- Currency is not in the response, so the store config must pin `good-times.ae` and AED.
- `available` is product level only.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, `www` host, `limit` above 10, behaviour from the user's network, terms of use.
