# Maison D'Vie qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). This is a second luxury-leaning multi-brand source beside Luxury For You (which is only a conditional GO), but its men's coverage is thin: only the `men shirt` query returned men's items (10 of 10); the other three queries returned women's items only. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Maison D'Vie, `https://maisondvie.com/` (used directly, no redirect). A UAE online designer boutique that calls itself a high-end and luxury fashion store (its own search-result title and blog). Multi-brand: 10 vendors in 40 records (MC2 Saint Barth 10, Vivetta 8, Federica Tosi 6, Borgo de Nor 6, Avavav 2, Manoush 2, Hamel 2, Kukhareva London 2, Alessandro Vigilante 1, Violante Nessi 1). These are contemporary designer labels, not heritage luxury houses.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`). Before fetching anything, the candidate was spotted by its `/collections/new-products-men`, `/pages/men-collection` and `/blogs/news/...` URL shapes in search results.
- Assortment seen in 40 search records: **men 10** (8 shirts and 2 T-shirts, all MC2 Saint Barth, from the `men shirt` query); **women 30** (blazers 10, jackets 10, dresses 6, shorts 2, pants 1, skirt 1). Every record's tags carry `Men` or `Women`. Not seen: men's blazers, jackets, trousers or shoes (the `shoes` query returned dresses, shorts, pants and a skirt, no footwear). The men's blazer and jacket queries were not run with the word "men" in them, so whether men's outerwear exists and is findable is not established here.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://maisondvie.com/robots.txt`: 200, 3,624 bytes, no redirect.
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://maisondvie.com/search?q=black+blazer`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested).
- Sitemap: one line, `https://maisondvie.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also says checkouts are for humans and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request `/agents.md`, `/.well-known/ucp` or `/api/ucp/mcp`. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://maisondvie.com/robots.txt` | 200 | 3624 | 0.9 s | text/plain |
| 2 | `https://maisondvie.com/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 12011 | 0.6 s | application/json, 10 products |
| 3 | `https://maisondvie.com/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 9848 | 0.4 s | 10 products |
| 4 | `https://maisondvie.com/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10826 | 0.4 s | 10 products |
| 5 | `https://maisondvie.com/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 11605 | 0.4 s | 10 products |
| 6 | `https://maisondvie.com/products/pamplona-men-shirt-white` | 200 | 811356 | 1.1 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://maisondvie.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block whose `offers[]` have `price`, `priceCurrency` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the other Shopify stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `maisondvie.com`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- Gender is in `tags` (`Men` or `Women`) and in `type` (`Men shirts`, `Men T-shirts`, `Women blazers`). Brand is `vendor`. `type` is free-form and sometimes a comma list (`Women blazers, Jacket`), and a plain `Jacket` type was used for women's jackets here.
- Other tags are seasonal or campaign markers (`Spring / Summer 2024`, `EOS_W25`, `Ramadan24`, `Gifts collection`), not useful for ranking.
- Like the other stores, it pads results with off-category items when a query has no match: the `shoes` query returned dresses, shorts, pants and a skirt, none of them shoes, so ranking must filter by category rather than trust the store's order.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Pamplona Men Shirt White") |
| price | yes | `price` (string with two decimals, for example `"610.00"`); `compare_at_price_max` is the pre-sale price (`"3400.00"`), `"0.00"` when there is none. 15 of 40 were on sale |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0654/8160/5370/products/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (boolean; true for 40 of 40). Per-size stock is not in this response |
| colour | partial | in most titles ("Pamplona Men Shirt Bluette"); no colour field |
| gender | yes | `tags` and `type` |

## Hosts

- Store host (product links): `maisondvie.com`. `www.maisondvie.com` was not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0654/8160/5370/` on all 40 records. The product page JSON-LD uses the store host instead (`/cdn/shop/...`).
- Candidate `allowed_hosts`: `maisondvie.com`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above. Add `www.maisondvie.com` only after checking where it redirects.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "610.00"`, `"price": "2090.00"`, `"price": "4430.00"`, `"compare_at_price_max": "3400.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": "610.0"`, `"priceCurrency": "AED"`.
- Observed over 40 records: price AED 490 to 4,430 (men's AED 490 to 780, women's AED 825 to 4,430); pre-sale prices AED 1,460 to 4,650.

## Currency / tier hint

AED. Tier: **luxury** (designer boutique; observed AED 490 for a men's linen T-shirt, AED 610 to 780 for men's shirts, women's blazers AED 1,175 to 4,190, jackets AED 1,030 to 4,430). Contemporary designer labels rather than heritage houses, so "luxury" here means designer pricing, below the heritage houses seen at Luxury For You (Gucci, Prada, Fendi).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| men shirt | `https://maisondvie.com/search/suggest.json?q=men%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's: 8 shirts, 2 T-shirts, all MC2 Saint Barth (AED 490 to 780) |
| black blazer | `https://maisondvie.com/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all women's blazers (AED 1,175 to 4,190); no men's blazers |
| jacket | `https://maisondvie.com/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all women's jackets and bombers (AED 1,030 to 4,430); no men's |
| shoes | `https://maisondvie.com/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no shoes: dresses, shorts, pants, a skirt (AED 825 to 2,570), all women's |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/maison-dvie/`

- `suggest-men-shirt.json` and `suggest-black-blazer.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page; `offers` cut to the first 3 of the size offers and `description` cut to 300 characters.

## Risks and fragility

- Thin men's coverage: men's items appeared only for the `men shirt` query (one brand, MC2 Saint Barth). A men's blazer or jacket query may need the word "men" to surface men's items; this was not tested. For the demo it counts as a men's source for shirts and T-shirts only.
- Women's items fill the results of queries that do not say "men", so ranking must filter by gender once the shopper confirms it (Product Rule 8), not only by the store's order.
- No footwear in the results.
- Prices are high and many items carry past-season or end-of-season tags (`Autumn / Winter 23`, `EOS_W25`), so the range moves with sales (15 of 40 on sale).
- 10 results per request, no pagination tested.
- Currency is not in the response, so the store config must pin `maisondvie.com` and AED.
- `available` is product level only.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, `www` host, `limit` above 10, men's queries other than `men shirt`, behaviour from the user's network, terms of use.
