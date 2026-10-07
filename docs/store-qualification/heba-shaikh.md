# Heba Shaikh qualification (2026-10-08)

**Verdict:** GO, with a currency flag. The honest client received title, price, image URL and product URL (plus availability) for 13 distinct products over two searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). The store prices in **British pounds (GBP)**, not AED. Its currency picker lists AED, but the picker works through a form post that sets a cookie; there is no AED URL a stateless client could request. The assortment is women's ready-to-wear essentials (tops, shirts, trousers, skirts, outerwear) with very few dresses (one style, "Esme Dress", GBP 910), so the store would add to tops, outerwear and bottoms rather than to dresses. The product page has no JSON-LD; currency and price come from Open Graph tags.

## Storefront

- Store: Heba Shaikh, `https://hebashaikh.com/` (used directly, no redirect). A direct-to-consumer label for women's wardrobe essentials, made in the United Kingdom and Portugal per its own pages. Single-brand: `vendor` is "Heba Shaikh" on 13 of 13 records.
- **How it is known to be the brand's own shop.** Web search found the domain with the brand's own pages (`/pages/founder`, `/pages/philosophy`, `/pages/quality`, `/blogs/journal`, `/collections/new-arrivals`, `/collections/archivesale`) and a company page listing "heba shaikh ltd". The vendor field and the shop name (`hebashaikh.myshopify.com`) match the brand. It is not a stockist or marketplace.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 13 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.theme` (theme "Copy of Heba's Playground", Lorenza), `shopify-features`, `myshopify.com`, `/cdn/shop/` and `Shopify.currency`.
- Assortment seen in 20 search records (13 distinct handles): `type` "Tops" 4, "Outerwear" 3, "Dresses" 2 (both are "Esme Dress", two handles `esme-dress` and `esme-dress-1`), "Shirts & Blouses" 1, "Trousers" 1, "Skirts" 1 and one skirt with an empty `type` ("Ares Skirt"). Prices run from a GBP 35 T-shirt to a GBP 950 coat. Women's pieces by nature of the range; no gender field. No gowns, kaftans or abayas.
- **The store pads its answers.** For `dress`, only 2 of 10 results are dresses (the same style twice); for `kaftan`, none of the 10 is a kaftan (dress, top, skirt, blazer, coat and T-shirt come back). Ranking has to filter by category and cannot trust the store's order.

## robots.txt

- Parser: **protego 0.7.0**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, through the `MALFORMED_RULE` reading in `scripts/qualify_store.py`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://hebashaikh.com/robots.txt`: 200, 3,624 bytes, no redirect. Shopify's current default file, identical to Hanayen's except for the host and the shop id line (`Disallow: /28891545684`).
- Group `User-agent: *`: `Allow: /`, exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows for `/admin`, `/cart/`, `/checkout`, `/orders`, `/account`, `/cart.js`, `/recommendations/products`, `/collections/*sort_by*`, filter combinations and preview parameters. A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL requested (two suggest.json URLs and the product page): ALLOW.
- Sitemap: `https://hebashaikh.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents ("Agents should use UCP/MCP for catalog, cart, and checkout", `agents.md`, `/.well-known/ucp`, `/api/ucp/mcp`, a third-party "shop.app" skill). Quoted as data, not acted on, none of those URLs requested. Review at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://hebashaikh.com/robots.txt` | 200 | 3624 | 1.1 s | text/plain |
| 2 | `https://hebashaikh.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 15623 | 1.4 s | application/json, 10 products |
| 3 | `https://hebashaikh.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 14955 | 1.1 s | 10 products |
| 4 | `https://hebashaikh.com/products/esme-dress` | 200 | 229844 | 1.5 s | the one product page |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://hebashaikh.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: both responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list (empty in these records). **The product page has no `application/ld+json` block** (zero found in 229,809 characters), so the usual JSON-LD currency check was not possible; the page's Open Graph tags give `og:price:amount` `910.00` and `og:price:currency` `GBP`, and its Shopify globals say `Shopify.currency` `{"active":"GBP","rate":"1.0"}` and `Shopify.country` `"GB"`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores. Store-specific points:

- **Currency is GBP.** The config would say `currency: GBP`. The price format (`"910.00"`, two decimals) is already handled by `parse_price`. The tier shaper (`src/vga/tiers/shaper.py`) keeps only the products in the most common currency, so GBP products would be left out of an AED result set with a warning. How a non-AED store enters the demo is a decision for the orchestrator.
- Pin the host `hebashaikh.com`. Build the link from the host plus `/products/{handle}`; drop the tracking query.
- `type` is usable for category: "Dresses", "Tops", "Shirts & Blouses", "Outerwear", "Trousers", "Skirts"; an empty `type` happens (one skirt in 13). Category from `type` first, title second.
- `tags` hold ethical-sourcing labels ("Organic", "Locally made", "Cruelty-free", "Responsible Forestry") and marketing leftovers (`antla_in_funnel_2304`), not gender; many records have no tags. There is no gender field.
- Two handles can carry the same title (`esme-dress`, `esme-dress-1`); collapse by handle, not by title, or accept the duplicate.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Esme Dress", "Tale Blazer") |
| price | yes | `price`, a string with two decimals (`"910.00"`); `compare_at_price_max` is the pre-sale price when above `0.00` (5 of 13 records, for example `"955.00"` against `"290.00"` for "Tale Blazer") |
| currency | not in the response | GBP is store-level: `og:price:currency` `GBP` and `Shopify.currency` `GBP` on the product page. There is no JSON-LD |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0288/9154/5684/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 13 of 13) |
| colour | no | not in a field for these records (the sampled product's variants are named "Butter / Petite / XS" on the page) |
| gender | no | not a field |

## Hosts

- Store host (product links): `hebashaikh.com`. Language/market alternates exist at `/en-de/`, `/en-ie/`, `/en-fr/` and `/en-nl/` (hreflang, not requested; presumably euro markets).
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0288/9154/5684/` on all 13 records. The product page's Open Graph image uses the store host (`hebashaikh.com/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `hebashaikh.com`, `cdn.shopify.com`.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "910.00"`, `"price": "35.00"`, `"compare_at_price_max": "955.00"`, `"compare_at_price_max": "0.00"`.
- Product page: `<meta property="og:price:amount" content="910.00">`, `<meta property="og:price:currency" content="GBP">`.
- Observed over 13 distinct handles: price **GBP 35 to 950, median 480**. At roughly AED 4.9 per GBP (an approximation, not observed) that is about AED 170 to 4,650; the one dress is GBP 910, about AED 4,450.

## Currency / tier hint

**GBP** (not AED). Tier: **premium to luxury** for the garments (trousers GBP 190, blazers GBP 290, dresses and coats GBP 895 to 950; only the T-shirts, GBP 35, and one shirt, GBP 110, are lower).

AED storefront: the product page's currency picker lists AED, AUD, CAD, CNY, EUR, GBP, JPY and USD, but it is a form that posts to `/localization` and stores the choice in a cookie. That is not a URL, so no robots-allowed AED storefront URL can be recorded, and a stateless client always sees GBP. The market alternates in the page head are `/en-de/`, `/en-ie/`, `/en-fr/` and `/en-nl/` only.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dress | `https://hebashaikh.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: two "Esme Dress" (GBP 910), then tops, shirt, skirt, blazer, trousers and crop trench (GBP 35 to 895) |
| kaftan | `https://hebashaikh.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no kaftans: dresses, tops, skirts, a blazer, "Lila Coat" (GBP 950) and a T-shirt; the store pads the answer |

## Requests made

4 (1 for robots.txt, 2 searches, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/heba-shaikh/`

- `suggest-dress.json`, `suggest-kaftan.json`: the first 4 of the 10 products of the real response, same structure; each `body` string cut to 300 characters.
- `product-meta.txt`: the product page's Open Graph tags (there is no JSON-LD block to sample).
- `robots.txt`: the file as served.

## Risks and fragility

- Currency (GBP) and the AED-only design of the demo (see above). No AED URL exists for a stateless client.
- Very few dresses: one style in two handles. The store is a source of tops, shirts, trousers, skirts and outerwear, so it only helps categories the current stores already cover, at premium prices.
- Padded answers: a `kaftan` query returns nothing relevant, so a text search for a garment the store does not make still returns 10 items that must be filtered out.
- No JSON-LD on the product page; price and currency would have to be read from Open Graph tags if a product-page check is ever needed.
- 5 of 13 records are discounted today (the site has an "ARCHIVE SALE" collection, seen in a search result); the sale state is transient. `type` can be empty.
- `body` is store-supplied HTML (up to 870 characters here); never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint; review before real users. A template change could close `/search`.
- Not tested: HTML search page, the euro market prefixes, `limit` above 10, behaviour from the user's network, terms of use, men's wear (the store is reported to add a men's range; none appeared in these queries).
