# Maison Arabelle qualification (2026-10-08)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). It is a luxury kaftan and abaya house: all four queries returned kaftans or abayas, including floral kaftans, embroidered kaftans and abayas in burgundy, beige, butter yellow and grey. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Maison Arabelle, `https://maisonarabelle.com/` (used directly, no redirect). A Dubai atelier selling kaftans and abayas, priced in AED. Single-brand: vendor "MAISON ARABELLE" or "Maison Arabelle" (two spellings of one brand: 24 and 8 of 32 distinct records).
- Platform: Shopify. Evidence: all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`, `Shopify.currency`). The robots.txt is a custom file with no Shopify comment, so the robots-based evidence the other reports use is missing here. Before fetching anything, the candidate was spotted by its `/products/mira-pink-kaftan-embroidered` and `/collections/kaftans-and-abayas` URL shapes in search results. One search result for the same domain had the shape `/en/item/zarina-orx0353mh8` (title "ZARINA-Maison Arabelle Trading LLC"), which is not a Shopify path; it was not requested.
- Assortment seen in 40 search records (32 distinct handles): 15 titled "kaftan", 10 titled "abaya", and 7 with neither word in the title (a gold "dress with cape", and named pieces such as "MARWA WHITE", "SHIMMER", "MAYRA BLACK", "SHAMAA", "BADER LINEN NAVY BLUE", "CHARLOTTE BLUSH PINK"). `type` is "Kaftans and Abayas" on all 32. Women only by nature of the range. No kurtas, no shoes, no trousers.
- By title and description only (the images were not compared): floral kaftans ("JALILA GREEN FLORAL KAFTAN", "JALILA PINK GOLD FLORAL KAFTAN", AED 1,600), burgundy abayas ("GIGI BURGUNDY ABAYA" AED 1,200, "NOUF BURGUNDY FEATHER ABAYA" AED 2,400), open-front and belted abayas in beige, grey, butter yellow and lilac (AED 1,200 to 1,800), velvet kaftans (AED 980) and a linen style (AED 790). Descriptions use the words evening and wedding for many pieces.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://maisonarabelle.com/robots.txt`: 200, 445 bytes, no redirect. A short custom file, not Shopify's default. Quoted in full except blank lines:
  ```
  User-agent: *
  Disallow: /admin
  Disallow: /cart
  Disallow: /orders
  Disallow: /checkouts/
  Disallow: /checkout
  Disallow: /cgi-bin
  Disallow: /wp-admin
  Disallow: /wp-login.php
  Allow: /

  User-agent: GPTBot            (Allow: /)
  User-agent: ClaudeBot         (Allow: /)
  User-agent: PerplexityBot     (Allow: /)
  User-agent: Google-Extended   (Allow: /)

  Sitemap: https://maisonarabelle.com/sitemap.xml

  Content-Signal: ai-train=yes, search=yes, ai-retrieval=yes, ai-personalization=no
  ```
- Our User-Agent is not one of the named groups, so the `*` group applies. Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://maisonarabelle.com/search?q=abaya`, `/collections/all`, `/products.json`, `/sitemap.xml` and `/recommendations/products` (none requested) and DISALLOW for `/cart.js`.
- Sitemap: one line. Crawl-delay: none.
- The `Content-Signal` line is a statement about AI use of content (training, search and retrieval yes, personalisation no). It is data, not an Allow or Disallow rule, and it played no part in the protego decision. Our use (live search shown to a shopper, no training) falls under "search" and "ai-retrieval", but the terms of use were not read.
- There is no comment block addressed to AI agents in this file, and I requested no UCP/MCP or agent URL.

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://maisonarabelle.com/robots.txt` | 200 | 445 | 1.2 s | text/plain |
| 2 | `https://maisonarabelle.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 26700 | 0.6 s | application/json, 10 products |
| 3 | `https://maisonarabelle.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 28299 | 0.5 s | 10 products |
| 4 | `https://maisonarabelle.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 44964 | 0.5 s | 10 products |
| 5 | `https://maisonarabelle.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 26846 | 0.4 s | 10 products |
| 6 | `https://maisonarabelle.com/products/zahra-gold-dress-with-cape` | 200 | 264899 | 1.1 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://maisonarabelle.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block with an `Offer` (`price`, `priceCurrency`, `availability`, `url`).

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `maisonarabelle.com`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- `type` is the same string on every item, `tags` is empty on 29 of 32 records, and many titles are only a name ("SHIMMER", "SHAMAA"). Category has to come from the `type` plus words in the title and `body`; for this store every item is a one-piece garment (kaftan, abaya or dress), which is the "dresses" category.
- `vendor` is spelled two ways; compare it case-insensitively.
- There is no gender field; the range is women's wear.
- The same item appears under several queries (32 distinct handles in 40 records); collapse by handle across queries.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (upper case, for example "JALILA GREEN FLORAL KAFTAN") |
| price | yes | `price` (string with two decimals, for example `"1600.00"`); `compare_at_price_max` is `"0.00"` on 29 of 32 records, and on 3 it is below or equal to the price (see Risks), so it is not a reliable pre-sale price here |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0747/8444/0557/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 40 of 40). Per-size stock is not in this response |
| colour | partly | in the title for most ("... BURGUNDY ABAYA", "... GREEN FLORAL KAFTAN") and in the `body` as "Colour: ..." for some |
| gender | no | not a field; the range is women's |

## Hosts

- Store host (product links): `maisonarabelle.com`. `www.maisonarabelle.com` was not requested. A `/en/item/` path form seen in one search result was not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0747/8444/` on all 40 records. The product page JSON-LD uses store-host image URLs instead (`https://maisonarabelle.com/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `maisonarabelle.com`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "1600.00"`, `"price": "790.00"`, `"price": "2400.00"`, `"compare_at_price_max": "0.00"`, and the odd `"compare_at_price_max": "890.00"` beside `"price": "1040.00"`.
- Product JSON-LD: `"price": "1600.00"`, `"priceCurrency": "AED"` (strings in both).
- Observed over 40 records (32 distinct handles): price AED 790 to 2,400, median 1,600, quartiles 1,200 / 1,600 / 1,800.

## Currency / tier hint

AED. Tier: **luxury** (every item AED 790 to 2,400; the cheapest are velvet and linen kaftans at AED 790 to 980, embroidered abayas AED 1,200 to 1,800, feathered and heavily embroidered kaftans AED 2,200 to 2,400). On the scale of the existing reports this is at the level of Maison D'Vie's women's wear, with a far narrower assortment.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dress | `https://maisonarabelle.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 1 "ZAHRA GOLD DRESS WITH CAPE" (AED 1,600), 2 abayas, 1 kaftan and 6 named pieces (AED 790 to 1,800); no item is a plain western dress |
| kaftan | `https://maisonarabelle.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all kaftans (AED 980 to 2,400), including two floral ones and several embroidered |
| abaya | `https://maisonarabelle.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all abayas (AED 1,200 to 2,400) |
| kurta | `https://maisonarabelle.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no kurtas: 9 kaftans and 1 abaya (AED 980 to 2,400); the store pads the answer |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/maison-arabelle/`

- `suggest-dress.json`, `suggest-kaftan.json`, `suggest-abaya.json`, `suggest-kurta.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD node (the one with the `Offer`) of the sampled product page.
- `robots.txt`: the file as served.

## Risks and fragility

- Single-brand, luxury-only store with one garment family. It cannot answer a kurta, gown, trouser or shoe query; those are padded with kaftans, so ranking must filter by category rather than trust the store's order.
- `compare_at_price_max` is unreliable: "MARWA WHITE" has price 1040.00 and compare-at 890.00, "SHAMAA" 980.00 and 790.00, "SHIMMER" 1600.00 and 1600.00. Do not read these as a discount.
- `type` and `tags` carry almost no information, and many titles are names only, so the extractor cannot infer the garment from structured fields.
- The robots.txt is a hand-edited file (it carries a `Content-Signal` line); the owner may change it, and a `Disallow: /search` would close the path. Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- 10 results per request, no pagination tested. Currency is not in the response, so the store config must pin `maisonarabelle.com` and AED.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- Not tested: HTML search page, `www` host, the `/en/item/` path form, `limit` above 10, behaviour from the user's network, terms of use.
