# Club L London UAE qualification (2026-10-07)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 30 products over three searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page's JSON-LD (`priceCurrency: "AED"`).

## Storefront

- Store: Club L London, UAE storefront `https://www.clubllondon.ae/` (the apex `https://clubllondon.ae/` redirects 301 to `www`). A UK going-out, occasion and evening-wear brand with a localised UAE Shopify store priced in AED; the vendor/brand value in the data is "Club L London - UAE". It is a single-brand store, not a GCC multi-brand retailer.
- Platform: Shopify. Evidence: robots.txt comment `# Shopify storefront...` (the same text as Oh Polly's file apart from the shop id and domain names), images on `cdn.shopify.com`, Shopify predictive-search JSON shape, Shopify script ids on the product page. Behind Cloudflare. The site's own search form posts to `/pages/search` (a custom search page), but `/search/suggest.json` still answers.
- Assortment seen in 30 search records: Dress (13), Coats & Jackets (7), Jackets & Blazers (4), Shoes (5, heels, sandals and boots), Tops (1). Women only. Not checked: trousers or skirts, flat shoes.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`). The stdlib `urllib.robotparser` was not used for any verdict.
- Fetched from `https://www.clubllondon.ae/robots.txt`: 200, 3,640 bytes (the apex host answered 301 first).
- Group `User-agent: *` opens with `Allow: /` and then lists disallows. Rules that matter here, quoted:
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (three suggest.json URLs, product page): ALLOW. Protego also reports ALLOW for `https://www.clubllondon.ae/search?q=black+blazer` (not requested).
- Category/listing pages: ALLOW (protego) for `https://www.clubllondon.ae/collections/jackets`; collection URLs that contain `sort_by` or `+` are disallowed. Not requested.
- Sitemap: ALLOW (protego) for `https://www.clubllondon.ae/sitemap.xml`, the single `Sitemap:` line. Not requested.
- Crawl-delay: none.
- The file's comment block is addressed to AI agents (same text as Oh Polly's): prefer the store's UCP/MCP endpoint, install a third-party "shop.app" skill, checkout is for humans. These are comments, not robots rules; I did not act on them or request those URLs. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://clubllondon.ae/robots.txt` | 301 | 0 | 2.48 s | to `https://www.clubllondon.ae/robots.txt` |
| 2 | `https://www.clubllondon.ae/robots.txt` | 200 | 3640 | 2.80 s | text/plain |
| 3 | `https://www.clubllondon.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 34376 | 1.90 s | application/json, 10 products |
| 4 | `https://www.clubllondon.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 29499 | 1.65 s | 10 products |
| 5 | `https://www.clubllondon.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 30236 | 1.72 s | 10 products |
| 6 | `https://www.clubllondon.ae/products/unbeaten-white-fitted-corset-blazer-jacket-cl126398005` | 200 | 497,311 | 3.12 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall. `server: cloudflare`, HTTP/1.1.

## Search URL template

`https://www.clubllondon.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time; larger limits and pagination were not tested. The HTML search page is `https://www.clubllondon.ae/pages/search` (form action seen in the page) and was not requested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all three responses are JSON `{"resources": {"results": {"products": [ ... ]}}}` with the same product keys as every Shopify store (`title`, `handle`, `url`, `price`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `variants` empty). The product page carries a `ProductGroup` JSON-LD block with an `Offer` (`price`, `priceCurrency`, `availability`).

## Extraction strategy needed

`shopify` (plan module 6.4.6, an optional strategy; this store needs it, and it is the same strategy as `oh-polly.md`, so one implementation serves both). Currency comes from store config; links are built from `https://www.clubllondon.ae` plus `/products/{handle}` (drop the tracking query `?_pos=...&_psq=...`); prices stay strings; respect the 10-result cap.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (format "Name \| Colour Style", for example "Unbeaten \| White Fitted Corset Blazer Jacket") |
| price | yes | `price` (string, for example `"999.00"`); `compare_at_price_max` is the pre-sale price (`"1105.00"`), `"0.00"` when there is none |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `.ae` storefront. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0558/4135/7935/files/...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes | `available` (boolean, product level; true for all 30 records) |
| colour | partial | no colour field in the search response (colour is written in the title); the product page JSON-LD has `"color": "WHITE"` for the sampled product |

## Hosts

- Store host (product links): `www.clubllondon.ae` (redirect source `clubllondon.ae`).
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0558/4135/7935/`. The product page JSON-LD uses the store host (`https://www.clubllondon.ae/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `www.clubllondon.ae`, `clubllondon.ae`, `cdn.shopify.com` (shared by all Shopify merchants, so consider also restricting the path prefix above).
- Other hosts in the product page, not used by us: `cdn-static.okendo.io`, `swymstore-v3premium-01.swymrelay.com`, regional `clubllondon.*` sites.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "999.00"`, `"price": "1199.00"`, `"price": "299.00"`, `"compare_at_price_max": "999.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": "999.0"`, `"priceCurrency": "AED"`.
- Observed over 30 records: price AED 199 to 1,499.

## Currency / tier hint

AED. Tier: **premium** (observed AED 199 to 1,499; blazers and dresses mostly AED 535 to 1,370; shoes on sale at AED 299 to 449 against list prices of AED 949 to 1,499).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| black blazer | `https://www.clubllondon.ae/search/suggest.json?q=black%20blazer&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 1 blazer and 9 dresses (relevance is weak for this phrase) |
| jacket | `https://www.clubllondon.ae/search/suggest.json?q=jacket&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 blazers and jackets (9 typed as jackets or blazers, 1 blazer typed as TOPS) |
| shoes | `https://www.clubllondon.ae/search/suggest.json?q=shoes&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 5 shoes (heels, boots), 1 blazer, 4 dresses |

## Requests made

6 (2 for robots.txt including one redirect hop, 3 search requests, 1 product page).

## Sample

`docs/store-qualification/samples/club-l-london/`

- `suggest-black-blazer.json` and `suggest-shoes.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `ProductGroup` JSON-LD block (the one with the `Offer`) of the sampled product page; `description` cut to 300 characters.

## Risks and fragility

- Narrow assortment: one women's going-out brand; dresses dominate (13 of 30 records). `black blazer` is mostly dresses, so ranking must filter by category rather than trust the store's order. No menswear.
- 10 results per request, no pagination tested.
- Currency is not in the response, so the store config must pin `www.clubllondon.ae` and AED.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users.
- The site's visible search is a custom page (`/pages/search`), which suggests a search app is installed; `/search/suggest.json` is Shopify's own endpoint and could be changed or restricted by the merchant.
- Cloudflare is in front of the store; it did not challenge the honest client today.
- `available` is product level only.
- Not tested: HTML search page, other locales, behaviour from the user's network.
