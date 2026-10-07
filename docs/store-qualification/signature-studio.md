# Signature Studio qualification (2026-10-08)

**Verdict:** GO. The honest client received title, price, image URL and product URL (plus availability) for 40 products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). It is the only multi-brand store of the pass: 16 Pakistani designer labels in 40 records, from AED 174 to 2,753, with embroidered 3-piece sets that include a dupatta, kaftans, printed long dresses and formal wear. It has no abayas, and its `kurta` query returned only men's kurta sets. One caveat: the search response carries no currency field; AED is store-level and was confirmed only from the product page (`priceCurrency: "AED"` in the JSON-LD and `Shopify.currency` set to `AED`).

## Storefront

- Store: Signature Studio, `https://www.signaturestudio.ae/` (used directly, no redirect; the apex was not requested). A Dubai boutique for Pakistani designer wear (its own search-result title is "Pakistani Clothing Store Dubai, Buy Pakistani Dresses"), priced in AED. Multi-brand: `vendor` is the designer label, and the title repeats it ("HAFSA MALIK - Noor Jahan"). Labels seen in the 40 records: KUNZUL CHANNAR 10, ALEENA FAREENA 5, MARIA RAO 3, MANTO 3, Wajeeha Ansari 3, Hafsa Malik 2, ZAH STUDIO 2, Karishma Talreja 2, ZAINAB ZULFIQAR 2, ZABRIC BY ZULEKHA AND SANA 2, and six labels with one each.
- Platform: Shopify. Evidence: the robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries Shopify markers (`Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/`, `Shopify.currency`). Before fetching anything, the candidate was spotted by its `/collections/all?page=42`, `/collections/clothing` and `/pages/about-us` URL shapes in search results.
- Assortment seen in 40 search records (40 distinct handles): women's designer pieces 30 (dresses, kaftans, 3-piece sets with a dupatta, co-ords, formal wear) and 10 men's kurta-trouser sets (all KUNZUL CHANNAR, tagged `Menswear`). `type` is "Clothing" on all 40.
- By title and `body` only (the images were not compared): a three-piece raw-silk set with crushed pants and an organza dupatta (HAFSA MALIK "Noor Jahan", AED 1,838, described as wedding wear), printed maxi and kaftan styles (MARIA RAO "Printed new style" AED 416, "Printed kaftan" AED 419; MANTO "Deedar Dress Kaftaan" AED 174), a floral print dress (ZAH STUDIO "Nera" AED 357), kaftans with embroidery (AED 480 to 1,194), and a black formal piece (ALEENA FAREENA "Midnight mirage", AED 2,753). Four descriptions mention a dupatta.
- The `abaya` query matched designer pieces whose names resemble the word (Aysal, Maya, Amaya, Abiha, Pavlova...); no title, `type` or description in the 40 records is an abaya.

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`), run through `scripts/qualify_store.py`'s `Robots` class. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://www.signaturestudio.ae/robots.txt`: 200, 3,656 bytes, 3.7 s (the slowest request of the pass), no redirect. Shopify's current default file (identical, apart from a shop id line, to the files of Hanayen and Nishat Linen UAE).
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
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL actually requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `https://www.signaturestudio.ae/search?q=abaya`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested) and DISALLOW for `/cart.js` and `/recommendations/products`.
- Sitemap: one line, `https://www.signaturestudio.ae/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for humans, and points to a third-party "shop.app" skill. These are comments, not robots rules. I did not act on them and did not request any of those URLs. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.signaturestudio.ae/robots.txt` | 200 | 3656 | 3.7 s | text/plain |
| 2 | `https://www.signaturestudio.ae/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 22092 | 0.4 s | application/json, 10 products |
| 3 | `https://www.signaturestudio.ae/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19180 | 0.4 s | 10 products |
| 4 | `https://www.signaturestudio.ae/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 18888 | 1.2 s | 10 products, none an abaya |
| 5 | `https://www.signaturestudio.ae/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 18109 | 0.4 s | 10 products |
| 6 | `https://www.signaturestudio.ae/products/hafsa-malik-noor-jahan` | 200 | 191369 | 0.7 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://www.signaturestudio.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) I asked for 10 products, the cap the plan's module 6.4.6 assumes, and got 10 each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries a `Product` JSON-LD block with an `Offer` (`price`, `priceCurrency`, `availability`, `url`).

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores, so one implementation serves this store. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `www.signaturestudio.ae`.
- Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- The brand is `vendor`, and the title starts with it ("MANTO - Deedar Dress Kaftaan Beige"); show the designer from `vendor` and strip the prefix when displaying the name. `vendor` capitalisation varies ("MARIA RAO", "Wajeeha Ansari").
- `type` is "Clothing" for everything and the tag `Buy Dresses` is on all 40 records, so neither separates a kaftan from a kurta set. The useful tags are `Luxury Pret` (18), `Pret Wear` (7), `Formal` (6), `Menswear` (10), `Co-ord` and `SALE`. Category has to come from the title and `body`.
- Men's kurta sets carry the tag `Menswear` (and, for some, the word MENSWEAR in the title); filter on the tag once the shopper confirms a gender (Product Rule 8).
- A product title can end with a non-breaking space (seen on "MANTO - Deedar Dress Kaftaan Beige"); trim it.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "HAFSA MALIK - Noor Jahan") |
| price | yes | `price` (string with two decimals, for example `"1838.00"`; fractions occur, for example `"554.40"`, `"1843.34"`); `compare_at_price_max` is the pre-sale price on 3 of 40 records |
| currency | not in the response | AED is store-level: `priceCurrency: "AED"` in the product page JSON-LD, `Shopify.currency` `{"active":"AED","rate":"1.0"}`. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0549/4394/0663/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 40 of 40). Per-size stock is not in this response |
| colour | partly | in the title for some ("Beige", "Maroon"), in the `body` for a few ("Colour: Butter Yellow") |
| gender | partial | tag `Menswear` for men's; women's items carry no gender tag |

## Hosts

- Store host (product links): `www.signaturestudio.ae`. The apex `signaturestudio.ae` was not requested; check where it redirects before adding it.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0549/4394/` on all 40 records. The product page JSON-LD uses store-host image URLs instead (`https://www.signaturestudio.ae/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `www.signaturestudio.ae`, `cdn.shopify.com`. `cdn.shopify.com` is shared by all Shopify merchants, so consider also restricting the image path prefix above.
- Other hosts present in the product page (apps, analytics) were not catalogued and are not used by us.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "1838.00"`, `"price": "174.00"`, `"price": "554.40"`, `"price": "1843.34"`, `"compare_at_price_max": "2625.00"`, `"compare_at_price_max": "0.00"`.
- Product JSON-LD: `"price": 1838.0` (a number), `"priceCurrency": "AED"`.
- Observed over 40 records: price AED 174 to 2,753, median 589.20, quartiles 359.75 / 589.20 / 973; men's kurta sets AED 289 to 368; kaftans AED 419 to 1,194; pre-sale prices seen on 3 records (for example AED 2,625 against 1,838).

## Currency / tier hint

AED. Tier: **mid-range with a luxury tail** (median AED 589; printed and casual pieces roughly AED 170 to 625; designer formal and wedding sets AED 1,200 to 2,753). On the scale of the existing reports (Oh Polly at AED 170 to 970 is "mid", Club L London at AED 199 to 1,499 is "premium") the median sits in the mid-to-premium band.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dress | `https://www.signaturestudio.ae/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 women's designer pieces from 5 labels (AED 174 to 2,753): a wedding 3-piece with dupatta, formal dresses, printed and "kaftaan" dresses, saree-dresses |
| kaftan | `https://www.signaturestudio.ae/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 kaftans from 7 labels (AED 419 to 1,194), printed, floral-embroidered and hand-worked |
| abaya | `https://www.signaturestudio.ae/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, no abayas: pret and formal pieces with names like "Aysal", "Maya", "Abiha" from 7 labels (AED 308 to 2,396); several mention a dupatta or pants |
| kurta | `https://www.signaturestudio.ae/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all men's kurta-trouser sets from one label (AED 289 to 368); no women's kurta surfaced |

## Requests made

6 (1 for robots.txt, 4 search requests, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/signature-studio/`

- `suggest-dress.json`, `suggest-kaftan.json`, `suggest-abaya.json`, `suggest-kurta.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string (the HTML description) is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page (here with an `offers` list); `description` cut to 300 characters.
- `robots.txt`: the file as served.

## Risks and fragility

- A fuzzy store search: the `abaya` query returned 10 designer pieces that are not abayas, so a shopper asking for an abaya would get unrelated sets unless ranking filters by category from the title and description.
- `type` and most tags carry no category; everything depends on free text in `title` and `body`, which are written per designer and are inconsistent.
- The `kurta` word surfaced only the men's label; women's kurta sets exist in the store (a search-result title read "AMNA IQBAL- Beige floral kurta set") but were not returned by this query, so "white kurta set" may need `kurta set`, `suit` or `3 piece` as the keyword (not queried).
- Multi-brand, so the same garment type is spread over many labels with different title conventions and a 10-result cap per query.
- Fractional prices (AED 554.40, 1,843.34) suggest the prices are computed rather than set by hand; the `price` string is still the amount shown.
- Only 3 of 40 records are discounted, so the price band is stable compared with the other stores of the pass.
- 10 results per request, no pagination tested. Currency is not in the response, so the store config must pin the host and AED.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users. Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, the apex host, `limit` above 10, behaviour from the user's network, terms of use.
