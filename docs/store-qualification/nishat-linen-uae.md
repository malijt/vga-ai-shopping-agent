# Nishat Linen UAE qualification (2026-10-08)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). It is the budget South Asian and long-dress source of the pass: printed and embroidered long dresses, kaftans, gowns and 2- and 3-piece embroidered suits, all in AED. It has no abayas, and its `kurta` query returned only men's kurtas. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Nishat Linen UAE, `https://www.nishatlinenuae.com/` (used directly, no redirect; the apex `nishatlinenuae.com` also appears in search results and was not requested). The UAE storefront of a Pakistani textile and fashion house, priced in AED; women's ready-to-wear, unstitched fabric and men's wear. Single-brand. `vendor` is not the brand but a season or collection label (for example "Fustan Summer 2026 Eid-2"), and `type` is a collection family: Fustan 18, Fustaan 4, Aura 5, Luxury Pret 2 (women's, 29 distinct records) and RTW Men 10.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`, `Shopify.currency`). Before fetching anything, the candidate was spotted by its `/collections/ready-to-wear`, `/products/pw23-09` and `/blogs/news/...` URL shapes in search results.
- Assortment seen in 40 search records (39 distinct handles): 29 women's (18 titled dress, 8 kaftan, 1 gown, 2 suits; 24 of the 29 descriptions say "long") and 10 men's kurtas. Titles are a garment word plus a code ("Printed Dress - AS26-92", "2 Piece - Embroidered Gown - FE26-128"), with no gender word and no brand name.
- By title and `body` only (the images were not compared): black long dresses exist ("Embroidered Dress - FE26-107", "Printed Dress - FE26-116", AED 84.50 and 79.50), printed kaftans in beige and green (AED 84.50 to 109.50), an embroidered gown in brick red (AED 119.50), a 3-piece embroidered suit with a white inner shirt (AED 114.50) and a pearl-white embroidered dress (AED 149.50). Colour is written in `body` as "Color: ...".
- Sale state: 38 of 39 distinct records carry the tags `50%` and `Sale by Category` and a `compare_at_price_max` of exactly double the price. The prices below are sale prices.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://www.nishatlinenuae.com/robots.txt`: 200, 3,656 bytes, no redirect. Shopify's current default file (identical, apart from a shop id line, to the files of Hanayen and Signature Studio).
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://www.nishatlinenuae.com/search?q=abaya`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested) and DISALLOW for `/cart.js` and `/recommendations/products`.
- Sitemap: one line, `https://www.nishatlinenuae.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for humans, and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request any of those URLs. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.nishatlinenuae.com/robots.txt` | 200 | 3656 | 0.9 s | text/plain |
| 2 | `https://www.nishatlinenuae.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19020 | 0.4 s | application/json, 10 products |
| 3 | `https://www.nishatlinenuae.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 18073 | 0.4 s | 10 products |
| 4 | `https://www.nishatlinenuae.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19200 | 0.4 s | 10 products |
| 5 | `https://www.nishatlinenuae.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 16682 | 0.4 s | 10 products |
| 6 | `https://www.nishatlinenuae.com/products/as26-92` | 200 | 211833 | 0.8 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://www.nishatlinenuae.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block with an `Offer` (`price`, `priceCurrency`, `availability`, `url`).

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `www.nishatlinenuae.com`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- Unlike The Bear House there is no field with a product name: the title is "garment word - code" and `vendor` is a collection label, so the title as given is all the name there is.
- Gender is not reliable in the fields: the tag `Women` is on only 17 of 39 records, though 29 are women's by `type`; men's wear is `type` "RTW Men". Use `type` for the men's kurtas and treat the rest as women's.
- Keywords: `kurta` returns only men's kurtas here, and `abaya` returns none (long dresses instead). For a women's embroidered set a query such as `embroidered suit` or `3 piece` is the likelier match (not queried).
- Colour is only in `body` ("Color: Black"), so a colour match needs the description, not a field.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Printed Dress - AS26-92"; code in the title, no brand) |
| price | yes | `price` (string with two decimals, for example `"79.50"`); `compare_at_price_max` is the pre-sale price (`"159.00"`), present on 38 of 39 records |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0283/9766/6388/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 40 of 40). Per-size stock is not in this response; `tags` lists sizes (`XS`, `S`, `M`, `L`) |
| colour | in `body` | "Color: Off White", "Color: Black" |
| gender | partial | `type` "RTW Men" for men; tag `Women` on some women's items |

## Hosts

- Store host (product links): `www.nishatlinenuae.com`. The apex `nishatlinenuae.com` was not requested; check where it redirects before adding it.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0283/9766/` on all 40 records. The product page JSON-LD uses store-host image URLs instead (`https://www.nishatlinenuae.com/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `www.nishatlinenuae.com`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "79.50"`, `"price": "239.00"`, `"price": "39.50"`, `"compare_at_price_max": "159.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": "79.50"`, `"priceCurrency": "AED"` (strings in both).
- Observed over 40 records (39 distinct): sale price AED 39.50 to 239, median 84.50; women's AED 59.50 to 239; men's kurtas AED 39.50 to 114.50; pre-sale prices AED 79 to 329.

## Currency / tier hint

AED. Tier: **budget** (women's long dresses and kaftans AED 59.50 to 164.50 on sale, one embroidered kaftan at AED 239; pre-sale prices AED 79 to 329). The prices will rise when the 50% sale ends.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dress | `https://www.nishatlinenuae.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 women's dresses: 5 "Aura" (AED 59.50 to 89.50) and 5 "Fustan" (AED 79.50 to 149.50); printed, solid and embroidered; the descriptions of all 10 say "long" (24 of the 29 women's records say so) |
| kaftan | `https://www.nishatlinenuae.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 8 titled kaftan (printed, embroidered; AED 84.50 to 239) and 2 dresses (AED 109.50 to 149.50) |
| abaya | `https://www.nishatlinenuae.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no abayas: 7 dresses, 1 gown, 2 suits (AED 69.50 to 164.50); the store pads the answer |
| kurta | `https://www.nishatlinenuae.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's kurtas (`type` RTW Men, AED 39.50 to 114.50, 9 distinct titles) |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/nishat-linen-uae/`

- `suggest-dress.json`, `suggest-kaftan.json`, `suggest-abaya.json`, `suggest-kurta.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD node (the one with the `Offer`) of the sampled product page.
- `robots.txt`: the file as served.

## Risks and fragility

- Single-brand store whose titles are codes; name-based ranking has little to work with beyond "Printed Dress" or "Embroidered Kaftan", and colour sits in free text.
- No abayas, and women's kurtas are not found by the word `kurta`; a shopper's "white kurta set" request needs a different keyword (for example `suit`), which was not tested.
- The whole range is on a 50% sale today (38 of 39 records); the prices and the budget band will move.
- Men's items come back for generic Pakistani-wear keywords; gender has to be parsed from `type`, because the `Women` tag is incomplete.
- 10 results per request, no pagination tested. Currency is not in the response, so the store config must pin the host and AED.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users. Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, the apex host, `limit` above 10, behaviour from the user's network, terms of use.
