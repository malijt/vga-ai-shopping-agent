# Oh Polly UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 30 products over three searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page's JSON-LD (`priceCurrency: "AED"`).

## Storefront

- Store: Oh Polly "AE" storefront, `https://ohpolly.ae/` (`https://www.ohpolly.ae/` redirects 301 to the apex). A UK women's occasion and going-out fashion brand with a localised UAE Shopify store priced in AED. It is a single-brand store (vendor values seen: "Oh Polly" and, for ski jackets, "Bo+Tee"), not a GCC multi-brand retailer.
- Platform: Shopify. Evidence: the robots.txt opens with the comment `# Shopify storefront...`, product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page has Shopify script ids (`shopify-features`, `__st`). Behind Cloudflare. Third-party apps seen in the page: Nosto, Okendo, LoyaltyLion (not used by us).
- Assortment seen in 30 search records: Coats & Jackets (15), Dresses (5), Footwear (10, all heeled mules, sandals and heels). Women only. Not checked: tops, bottoms, flat shoes.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`). The stdlib `urllib.robotparser` was not used for any verdict.
- Fetched from `https://ohpolly.ae/robots.txt`: 200, 3,608 bytes (the `www` host answered 301 first).
- Group `User-agent: *` opens with `Allow: /` and then lists disallows. Rules in that group that matter here, quoted:
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
  Disallow: /*?*preview_theme_id=*
  ```
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (all three suggest.json URLs and the product page): ALLOW. Protego also reports ALLOW for `https://ohpolly.ae/search?q=black+blazer` (the HTML search page; not requested).
- Category/listing pages: ALLOW (protego) for `https://ohpolly.ae/collections/jackets` and for `https://ohpolly.ae/products.json`; collection URLs that contain `sort_by` or `+` are disallowed. None was requested.
- Sitemap: ALLOW (protego) for `https://ohpolly.ae/sitemap.xml`, which is also the single `Sitemap:` line. Not requested.
- Crawl-delay: none.
- The file's comment block is addressed to AI agents: it says agents should use the store's UCP/MCP endpoint (`https://ohpolly.ae/api/ucp/mcp`) for catalog, cart and checkout, and suggests installing a third-party "shop.app" skill. Those are comments, not robots rules, and I did not act on them or request any of those URLs. It also says checkout is for humans. Treat the stated preference for the UCP/MCP endpoint as something to check at the terms-of-use review (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.ohpolly.ae/robots.txt` | 301 | 0 | 2.42 s | to `https://ohpolly.ae/robots.txt` |
| 2 | `https://ohpolly.ae/robots.txt` | 200 | 3608 | 1.82 s | text/plain |
| 3 | `https://ohpolly.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19556 | 1.55 s | application/json, 10 products |
| 4 | `https://ohpolly.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19609 | 1.07 s | 10 products |
| 5 | `https://ohpolly.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 14274 | 1.23 s | 10 products |
| 6 | `https://ohpolly.ae/products/edessa-oversized-single-breasted-blazer-soft-lilac` | 200 | 1,271,219 | 3.32 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall. `server: cloudflare`, HTTP/1.1.

## Search URL template

`https://ohpolly.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(The brackets were sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time; larger limits and pagination were not tested (this is Shopify's predictive-search endpoint, which is not paginated). The HTML search page `https://ohpolly.ae/search?q={query}` exists (the site's search form posts to `/search`) but was not requested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all three responses are JSON with the shape `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_max`, `compare_at_price_min`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id`, and an empty `variants` list. The product page also carries a `Product` JSON-LD block with `offers[].priceCurrency`, `price` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6, an optional strategy; this store needs it). It must: read `resources.results.products`; take the currency from store config (not from the response); build the link from `https://ohpolly.ae` plus `/products/{handle}` (ignore the tracking query in `url`, `?_pos=...&_psq=...&_psid=...&_ss=e`); keep prices as strings; respect the 10-result cap.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` |
| price | yes | `price` (string, for example `"230.00"`); `compare_at_price_max` is the pre-sale price (`"450.00"`), `"0.00"` when there is none |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `.ae` storefront. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0757/9670/9661/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes | `available` (boolean, product level; true for all 30 records). Per-size stock is not in this response; the sampled product page lists one size as `OutOfStock` while the product-level flag was true |
| colour | no | no colour field; colour only appears inside the title (for example "in Soft Lilac") and in the product page `sku` (`9460__SoftLilac_6`) |

## Hosts

- Store host (product links): `ohpolly.ae` (redirect source `www.ohpolly.ae`).
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0757/9670/9661/`. The JSON-LD on the product page uses the store host instead (`https://ohpolly.ae/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `ohpolly.ae`, `www.ohpolly.ae`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above.
- Other hosts present in the product page, not used by us: `ohpollyae.zendesk.com`, Nosto, Okendo, LoyaltyLion, `*.ohpolly.com` regional sites.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "230.00"`, `"price": "620.00"`, `"compare_at_price_max": "450.00"`, `"compare_at_price_max": "0.00"`, `"price_min": "230.00"`.
- Product JSON-LD: `"price": "230.0"`, `"priceCurrency": "AED"`.
- Observed over 30 records: price AED 170 to 970.

## Currency / tier hint

AED. Tier: **mid** (observed AED 170 to 970; jackets and blazers mostly AED 230 to 300, ski jackets AED 570 to 970, shoes AED 395 to 430).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| black blazer | `https://ohpolly.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 4 blazers, 1 ski jacket (Coats & Jackets), 5 dresses |
| jacket | `https://ohpolly.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all Coats & Jackets (ski, zip-up, faux leather) |
| shoes | `https://ohpolly.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all Footwear (heeled mules, sandals, heels) |

## Requests made

6 (2 for robots.txt including one redirect hop, 3 search requests, 1 product page).

## Sample

`docs/store-qualification/samples/oh-polly/`

- `suggest-black-blazer.json` and `suggest-shoes.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page; `offers` cut to the first 3 of the size offers and `description` cut to 300 characters.

## Risks and fragility

- Narrow assortment: one women's occasion-wear brand. It covers `blazer`, `jacket` and `shoes` queries but no menswear, and `black blazer` is padded with dresses (5 of 10 results).
- 10 results per request, no pagination tested, so at most 10 candidates per keyword variant.
- Currency is not in the response, so a wrong market (for example a different country's storefront) would silently change prices; the store config must pin `ohpolly.ae` and AED.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- Cloudflare is in front of the store; it did not challenge the honest client today, but nothing guarantees it will not later.
- `available` is product-level only. A result can have its requested size sold out.
- Not tested: HTML search page, other locales, behaviour from the user's network.
