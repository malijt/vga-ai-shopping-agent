# Hanayen qualification (2026-10-08)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). This is the one store of the pass whose `abaya` query returned real abayas (10 of 10), and it carries a wide price range. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Hanayen, `https://hanayen.com/` (used directly, no redirect). A UAE abaya and modest-wear brand priced in AED. Single-brand: vendor "Hanayen" on 40 of 40 records. Search-result pages for the domain used a regional prefix (`hanayen.com/en-us/collections/...`, a Shopify Markets path); only the unprefixed host was requested, and it answered in AED.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`, `Shopify.currency`). Before fetching anything, the candidate was spotted by its `/collections/our-abaya-collection` and `/collections/essential-abayas` URL shapes in search results.
- Assortment seen in 40 search records (35 distinct handles): 31 items of `type` Abaya, of which 21 are outer abayas (AED 600 to 5,550, median 1,290) and 10 are "inner" under-dresses worn beneath an abaya (tag `Inner`, AED 250 to 850; eight are plain slips at AED 250 to 275), and 4 sheilas (head scarves, `type` SHEILA, AED 120 to 290; an accessory, out of scope). Women only by nature of the range; no gender field. No kurtas, no kaftans as a garment type (the `kaftan` query returned a "Kaftan Style Under Abaya" and abayas), no shoes, no trousers.
- By title only (the images were not compared), the abayas include an open-front style ("Neda Plain Abaya Front Open with Buttons", AED 600), embroidered styles with crystals or pearls (AED 950 to 4,500), plain black and everyday styles (AED 650 to 825) and modest "dress" styles (AED 385 to 5,550).

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://hanayen.com/robots.txt`: 200, 3,612 bytes, no redirect. It is Shopify's current default file (identical, apart from a shop id line, to the files of Nishat Linen UAE and Signature Studio).
- Group `User-agent: *` opens with `Allow: /`, then `Allow:` exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows. Rules that matter here, quoted:
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
  ```
  (Each of these also has a `/*/...` twin for localised paths.)
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://hanayen.com/search?q=abaya`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested) and DISALLOW for `/cart.js` and `/recommendations/products`.
- Sitemap: one line, `https://hanayen.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for humans, and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request any of those URLs. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://hanayen.com/robots.txt` | 200 | 3612 | 1.0 s | text/plain |
| 2 | `https://hanayen.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 22299 | 0.6 s | application/json, 10 products |
| 3 | `https://hanayen.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19949 | 0.4 s | 10 products |
| 4 | `https://hanayen.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 21260 | 0.4 s | 10 products |
| 5 | `https://hanayen.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19399 | 0.3 s | 10 products |
| 6 | `https://hanayen.com/products/modern-sheer-summer-dress-2022` | 200 | 624116 | 1.7 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://hanayen.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block with an `Offer` (`price`, `priceCurrency`, `availability`).

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `hanayen.com`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- `type` is `Abaya` for every garment (including the inner slip dresses) and `SHEILA` for scarves. Skip `SHEILA` (accessory), and treat items tagged `Inner` as under-dresses, not abayas. Category for the new "dresses" category comes from the title and `type`.
- There is no gender field; the range is women's wear.
- The same abaya appears under several queries (35 distinct handles in 40 records); collapse by handle across queries. Each single response had 10 distinct handles; the `kurta` response repeated one title ("Royal Blue Plain Inner") under two handles.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Neda Plain Abaya Front Open with Buttons") |
| price | yes | `price` (string with two decimals, for example `"600.00"`); `compare_at_price_max` is the pre-sale price when above `0.00` (15 of 35 records, for example `"6500.00"` against `"4500.00"`) |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0528/4682/1565/products/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 40 of 40). Per-size stock is not in this response |
| colour | partly | in the title for many ("Off-White Under Abaya Dress In Satin", "Green Abaya ..."), `tags` for some (`BLACK`, `OFF WHITE`) |
| gender | no | not a field; the range is women's |

## Hosts

- Store host (product links): `hanayen.com`. A `/en-us/` path prefix exists on the site (seen in search results, not requested); the unprefixed host is the one qualified.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0528/4682/` on all 40 records. The product page JSON-LD uses store-host image URLs instead (`https://hanayen.com/cdn/shop/products/...`).
- Candidate `allowed_hosts`: `hanayen.com`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "600.00"`, `"price": "5550.00"`, `"price": "120.00"`, `"compare_at_price_max": "6500.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": 3800.0`, `"priceCurrency": "AED"` (a number here, a string in the search JSON).
- Observed over 40 records (35 distinct handles): price AED 120 to 5,550, median 850; outer abayas AED 600 to 5,550, median 1,290; inner under-dresses AED 250 to 850; sheilas AED 120 to 290; pre-sale prices up to AED 6,500.

## Currency / tier hint

AED. Tier: **premium, reaching luxury** (outer abayas AED 600 to 5,550, median 1,290; the cheapest outer abayas seen are plain ones at AED 600 to 675; quartiles of everything seen 275 / 850 / 1,300, pulled down by inners and scarves). On the scale of the existing reports this sits with Club L London and Sacoor Brothers at the low end and with Maison D'Vie at the top end.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dress | `https://hanayen.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all abayas styled as dresses ("Abaya Dress Embroidered Design", "Modern Modest Dress", "Khaleeji Modest Dress", "Crystalized Special Event Abaya Dress"), AED 385 to 5,550 |
| kaftan | `https://hanayen.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 1 "Kaftan Style Under Abaya" (an inner, AED 850), 5 outer abayas, 4 sheilas (AED 120 to 290); no kaftan garment as such |
| abaya | `https://hanayen.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all abayas (AED 600 to 4,500), open-front, embroidered, crystal, floral-embroidered brown, plain black |
| kurta | `https://hanayen.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no kurtas: 1 open-front abaya, 8 plain inner dresses (AED 250 to 275), 1 A-line abaya (AED 675); the store pads the answer |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/hanayen/`

- `suggest-dress.json`, `suggest-kaftan.json`, `suggest-abaya.json`, `suggest-kurta.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block (the one with the `Offer`) of the sampled product page; `description` cut to 300 characters.
- `robots.txt`: the file as served.

## Risks and fragility

- Single-brand store. The range is abayas, inner dresses and scarves only: nothing for kurtas, kaftans as garments, gowns, trousers or shoes. A `kurta` or `kaftan` query is padded with abayas and inners, so ranking must filter by category rather than trust the store's order.
- Every garment has `type` "Abaya", so type cannot separate an abaya from an inner dress; the tag `Inner` and the title can.
- Sheilas (scarves) come back for generic queries and are an accessory, out of scope.
- 15 of 35 records are discounted today; the sale state is transient. `compare_at_price_max` is `"0.00"` when there is no discount.
- 10 results per request, no pagination tested. Currency is not in the response, so the store config must pin `hanayen.com` and AED.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- The robots.txt of other abaya stores in this pass (Basic Abaya, KMansoori, CAS Basics, Bousni) carries `Disallow: /search`, which is the older Shopify default; a template change at this store would close the path. Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, the `/en-us/` prefix and its currency, `limit` above 10, behaviour from the user's network, terms of use.
