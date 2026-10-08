# Level Shoes qualification (2026-10-07)

**Verdict:** DROP (robots: the site search path `/catalogsearch/` is disallowed for `User-agent: *`; no robots-permitted keyword search found)

Scope: Level Shoes UAE English storefront, shoes only. Client: `httpx` 0.28.1 via `uv run --with httpx`, User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, no redirects followed, no other headers. Run from this machine on 2026-10-07. Three requests were made (see Reachability). After the search path was found to be disallowed, nothing further was requested.

Level Shoes is the one store in this module that is not blocked technically: it answered every request and its product pages carry good data. The drop is a robots decision about the search path.

## Storefront

- Base: `https://www.levelshoes.com/` (English, UAE, AED). Confirmed by web search results ("Shop Shoes & Accessories in UAE"). Category pages look like `https://www.levelshoes.com/women/shoes/sneakers.html`. Other countries use other hosts (`us.levelshoes.com`, `en-kuwait.levelshoes.com`, `en-qatar.levelshoes.com`, `en-saudi.levelshoes.com`, `en-bahrain.levelshoes.com`, `en-oman.levelshoes.com` and `ar-*` equivalents, seen in the product page HTML).
- Product page example fetched: `https://www.levelshoes.com/new-balance-574-sneakers-green-suede-women-low-tops-m0yrt8.html`.
- Stack seen in the product page HTML: Next.js (`__NEXT_DATA__`, buildId `TKJ6fNCbsvITBtbZYg4p7`) over a Magento back end (`/media/catalog/product/...` image paths, Magento paths in robots), with Apollo GraphQL state embedded in the page. Cloudflare in front.

## robots.txt

- `GET https://www.levelshoes.com/robots.txt` -> 200, 2020 bytes, `text/plain;charset=UTF-8`, `server: cloudflare`.
- Group for `User-agent: *` (shared with `Googlebot` and `Bingbot` in one group). Rules that matter (verbatim):
  ```
  Disallow: */catalogsearch/
  Disallow: */catalog/product_compare/
  Disallow: /*?*sortBy=
  Disallow: /*?price=
  Disallow: /*?color=
  Disallow: /*?size=
  Disallow: /*?brand=
  Disallow: /*?category=
  Disallow: /_next/data/*?*
  Disallow: /api/
  Disallow: /checkout/
  ```
  plus the standard Magento system paths. Product and category `.html` pages have no matching rule.
- Separate full-disallow groups: `meta-externalagent`, `Diffbot`, `omgili`, `omgilibot`, `cohere-ai`.
- `Crawl-delay`: none.
- `Sitemap:` line: `https://www.levelshoes.com/sitemap.xml` (not fetched).
- **Search path.** Magento's search results page is `/catalogsearch/result/?q=<term>`. A web search for it returned the indexed URL `https://www.levelshoes.com/catalogsearch/result/?q=jordan`, so that is the site's search results URL form (observed through a search engine, not through my own request). Evaluated offline with RFC 9309 wildcard matching on the file I fetched: `/catalogsearch/result/?q=sneakers` -> **disallowed** by `*/catalogsearch/`. `/women/shoes/sneakers.html` and the product page path -> allowed.
- Caveat I could not close: the on-site search box may call a back-end API instead of the `/catalogsearch/` page. The product page loads the Constructor.io beacon (`https://cnstrc.com/js/cust/level_shoes_<id>.js`), which suggests keyword search and browse are served by Constructor.io (inference only). That is a third-party host and a key embedded for the site's own pages. Using it would send requests to a host that is not Level Shoes' and outside this module's scope, so it was not touched. `/api/` is also disallowed.
- **Tooling finding:** Python 3.12.14's `urllib.robotparser` ignores `*` wildcards and reports `/catalogsearch/result/?q=sneakers` as allowed (wrong). Python 3.14.7's stdlib reports it disallowed. See `noon.md`.

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://www.levelshoes.com/robots.txt` | 200 | 2020 |
| 2 | `https://www.levelshoes.com/new-balance-574-sneakers-green-suede-women-low-tops-m0yrt8.html` (product page, to learn the data shape and look for a search template) | 200 | 730967 |
| 3 | `https://www.levelshoes.com/search?q=sneakers` (a guessed search template; not disallowed by robots) | 404 | 424942 |

No Cloudflare challenge was served on any request. Request 3 returned the site's Next.js 404 page (`page: /404`), so there is no `/search` page; the only search URL form I found is the Magento one above (seen via web search results).

## Search URL template

`https://www.levelshoes.com/catalogsearch/result/?q={query}` (observed only as an indexed URL in web search results, not requested). **Disallowed by `robots.txt`.** My guess `https://www.levelshoes.com/search?q={query}` is not a page (404).

## Data path

none for search (the search path is disallowed, so no search page was requested). For information only, the one product page I fetched (request 2) was readable:

- `json_ld`: one `<script type="application/ld+json">` array with a `Product` (name, image list, description, sku, color, brand, `offers` with url, `priceCurrency`, `price`, `availability`) and a `BreadcrumbList`.
- `embedded_json`: `__NEXT_DATA__` (about 525 KB) with `pageProps.productDetails` (id, vpn, brandName, name, `originalPrice` "500 AED", `rawSalePrice` 500, image, action.url, color) and an Apollo cache.

I did not fetch a category page or any search-like listing, so I cannot say whether listing pages include the same data.

## Extraction strategy needed

none (store dropped). If Level Shoes is re-opened later by a permitted route, the product-page evidence points to `json_ld` for single products; the shape of listing or search data is unknown.

## Fields available

Evidence below is from the one product page (request 2), not from a search page, so it does not meet the GO bar.

| Field | On the product page | Where |
|---|---|---|
| title | yes | JSON-LD `name` = "574 sneakers" (brand is separate: `brand.name` = "New Balance") |
| price | yes | JSON-LD `offers.price` = `500` (number) |
| currency | yes | JSON-LD `offers.priceCurrency` = `AED` |
| image URL | yes | JSON-LD `image[]` on `assets.levelshoes.com` |
| product URL | yes | JSON-LD `offers.url` on `www.levelshoes.com` |
| in stock | yes | JSON-LD `offers.availability` = `https://schema.org/OutOfStock` (this item) |
| colour | yes | JSON-LD `color` = "Green" |

## Hosts

- Store host: `www.levelshoes.com` (product and category pages).
- Image CDN host: `assets.levelshoes.com` (product images via `/cdn-cgi/image/width=720,height=1008,quality=85,format=webp/media/catalog/product/...`). Banner images on `images.assets.levelshoes.com` (non-product).
- Other Level Shoes hosts seen, not for use: `api.levelshoes.com` (size-guide API), country hosts `en-*.levelshoes.com`, `ar-*.levelshoes.com`, `us.levelshoes.com`.
- Third parties seen: `cnstrc.com` (Constructor.io), `checkout.tabby.ai`, `cdn.tamara.co`.
- Candidate `allowed_hosts` if this store were ever opened: `www.levelshoes.com`, `assets.levelshoes.com`. Not to be added now.

## Price formats seen

- JSON-LD: `"price": 500` with `"priceCurrency": "AED"` (a bare number; the currency is a separate field).
- Apollo state: `"originalPrice": "500 AED"`, `"salePrice": "500 AED"`, `"rawSalePrice": 500`, `"rawOriginalPrice": 500`.

## Currency / tier hint

AED. Tier hint: premium to luxury (web search snippets show a 450 to 950 AED band for Nike, adidas, New Balance and ASICS, and 2,950 to 4,350 AED for Gucci, Jimmy Choo and Miu Miu). Inference from snippets plus the one 500 AED item I fetched. It would have been the plan's luxury-leaning candidate, but it covers shoes only.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| `sneakers` | `https://www.levelshoes.com/search?q=sneakers` (guessed template) | 404 | 0 (not a search page) |
| `boots` | not requested (search path disallowed) | n/a | n/a |
| `loafers` | not requested (search path disallowed) | n/a | n/a |

## Requests made

3 (`robots.txt` 200; one product page 200; one guessed search URL 404).

## Sample

None (store is not GO). A product-page JSON-LD sample was not saved because the brief asks for samples only for GO stores.

## Risks and fragility

- The decision is a robots policy on the search path, not a technical block. It will not change by changing the client. Category and product pages are not disallowed, but this product searches by keyword and does not map queries to categories.
- Open question for the orchestrator: whether to design a category-listing path for shoe-only stores (for example `sneakers` -> `/women/shoes/sneakers.html`, which robots does not disallow). That is a different design from the plan's search-page template and was not tested here. Also whether to ask Level Shoes or Chalhoub Group for a partner or affiliate feed (an affiliate programme page for Level Shoes exists on `arabclicks.com` per web search; not verified).
- I did not verify that the on-site search does not use a different, robots-allowed route. The Constructor.io beacon suggests a third-party search service; that was deliberately left alone.
- Python 3.12 stdlib robots parsing would wrongly allow `/catalogsearch/` (see the tooling finding above).
- The page is Next.js with Apollo state and a changing build id; any future parser of its embedded JSON would be fragile. JSON-LD on product pages is the stable part.
