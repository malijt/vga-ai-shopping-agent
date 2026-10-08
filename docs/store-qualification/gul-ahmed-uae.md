# Gul Ahmed UAE qualification (2026-10-08)

**Verdict:** GO, with four caveats. The honest client received title, price, image URL and product URL (plus availability) for 40 records over four searches (32 distinct products), from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). It is the first readable source of **men's shalwar kameez** and one of very few for men's kurtas and women's kurtis, all in AED. The caveats: (1) many different products share one title, so the app's "same title, same price" rule turns the 32 products into 20; (2) a women's kurti is titled "Printed Shirt" and the ranker reads it as a top, not a dress; (3) 5 of the 32 products have variants at two prices, which is the sale price against the full price of the same garment and not a trap like Hamsa's; (4) the search answer has no currency and the product page has no JSON-LD, so AED rests on `Shopify.currency` and the variant prices in the page. The live smoke test is still to be run.

## Storefront

- Store: Gul Ahmed UAE, `https://uae.gulahmedshop.com/` (used directly, no redirect; the orchestrator found that the host is a CNAME to `shops.myshopify.com`). The UAE storefront of Gul Ahmed (the "Ideas" retail line), a Pakistani clothing and textile house, priced in AED. Single brand: `vendor` is "GulAhmed Ideas PK" on 33 of 40 records and "uae.gulahmedshop.com" on 7.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 40 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.shop = "uae-gulahmedshop-com.myshopify.com"`, `Shopify.country = "AE"`, `Shopify.currency` and `Shopify.theme` (name "GA-Production-UAE", Ella 6.7.3). The page's canonical link is on `uae.gulahmedshop.com`.
- Assortment seen in 40 search records (32 distinct handles): `type` "Men" on 20 products and "Women" on 12.
  - Men's: 9 shalwar kameez suits titled "Suits" (tag "Men Suits"), 10 kurtas titled "Kurta" (tags "Men Kurta" and one "Mens Kurta") and 1 waistcoat titled "Waist Coat" (tag "Men Waistcoat").
  - Women's: 11 kurtis titled "Printed Shirt", "Printed Long Shirt" or "Printed Embellished Shirt" (tag "Kurti"), and 1 two-piece set, "Printed Shirt With Embroidered And Dyed Trouser" (tag "Women Co-Ords").
  - Not seen: trousers or shalwars sold alone, jackets, shoes, dupattas, accessories. "Not seen" is not "not sold": only four queries were asked, all chosen for the core range.
- The product page's own recommendation data (saved, not searched for) names more women's items that no search returned: "UAE-2 Piece Printed Lawn Suit" (AED 89), "UAE-3 Piece Lacquer Printed Lawn Suit with Printed Denting Dupatta" (AED 109), "UAE-3 Piece Embroidered Lawn Suit with Embroidered Chiffon Dupatta" (AED 289) and "UAE-3 Piece Embroidered Raw Silk Suit with Embroidered Chiffon Dupatta" (AED 329). Their SKUs start `UAE-W-FB-`; whether `FB` means unstitched fabric is not verified.
- Sale state: 18 of the 32 products (23 of the 40 records) carry a pre-sale price (`compare_at_price_max`) and are priced at 60.1% of it, that is about 40% off. All 18 are men's. The women's kurtis have `compare_at_price_max` of `0.00`.

## robots.txt

- Parser: **protego**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://uae.gulahmedshop.com/robots.txt`: 200, 3,648 bytes, no redirect; the same size on all three fetches (the saved copies of the first and third are byte-identical). Shopify's current default file with a longer header comment, a `Disallow: /65221001325` line (the shop id) and some extra rules (`/services`, `/sf_*`, `/cdn/wpm/*.js`, `/collections/*sort_by*`, filter and preview parameters).
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
  (Most of these also have a `/*/...` twin for localised paths.) A second group is for `adsbot-google` only.
- Search path: **no Disallow rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL requested (four suggest.json URLs and the product page): ALLOW. A second, offline protego pass over the saved file also says ALLOW for `/search?q=kurta`, `/collections/all`, `/products.json` and `/sitemap.xml` (none requested) and DISALLOW for `/cart/`, `/cart.js`, `/checkout` and `/recommendations/products`.
- Sitemap: `https://uae.gulahmedshop.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. It is store-supplied text, quoted here as data and **not acted on**: "Agents should use UCP/MCP for catalog, cart, and checkout. Payment requires buyer approval." It also names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for humans and must not be completed automatically, and recommends that a personal-shopper agent install a third-party "shop.app" skill. These are comments, not robots rules. None of those URLs was requested and nothing was installed. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://uae.gulahmedshop.com/robots.txt` | 200 | 3648 | 0.7 s | text/plain; first run |
| 2 | `https://uae.gulahmedshop.com/search/suggest.json?q=shalwar%20kameez&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 24242 | 0.3 s | application/json, 10 products |
| 3 | `https://uae.gulahmedshop.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 22551 | 0.3 s | 10 products |
| 4 | `https://uae.gulahmedshop.com/search/suggest.json?q=kurti&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 23152 | 0.2 s | 10 products |
| 5 | `https://uae.gulahmedshop.com/robots.txt` | 200 | 3648 | 0.5 s | second run (product page) |
| 6 | `https://uae.gulahmedshop.com/products/uae-regular-fit-embroidered-suits-sk-emb25-042` | 200 | 954651 | 0.7 s | the one product page; no JSON-LD `Product` node |
| 7 | `https://uae.gulahmedshop.com/robots.txt` | 200 | 3648 | not recorded | third run (the extra query) |
| 8 | `https://uae.gulahmedshop.com/search/suggest.json?q=printed%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 26256 | not recorded | 10 products; a fourth query, added because the first three found only three women's items |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Network note

All requests were sent on 2026-10-08 between about 14:07 and 14:14 local time (PKT) by the orchestrator with `scripts/qualify_store.py` (User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first, at least 1 s apart, one store at a time). From about 13:00 the machine's own network path to Shopify's addresses timed out on connect (no refusal was ever received; a Cloudflare Community thread reports the same kind of time-out from Pakistani providers that week). The user then enabled Cloudflare WARP on the machine and the requests went through it. The User-Agent and every other rule were unchanged, and no store answered with a refusal. Behaviour from the machine's own network is untested.

## Search URL template

`https://uae.gulahmedshop.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list that is **empty on all 40 records**. The product page carries no JSON-LD at all (0 `application/ld+json` blocks) and no microdata price.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the other stores. Store-specific points for its config:

- Currency from config (`AED`), not from the response. Pin the host `uae.gulahmedshop.com`. Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`).
- **Gender is in `type`** ("Men" on 27 of 40 records, "Women" on 13), never in the title. The tags agree where they name a gender ("Men Suits", "Men Kurta", "Mens Kurta", "Men Waistcoat", "Women Co-Ords") and the women's kurti tag "Kurti" names none. Set `gender_fields: [type, tags]` so that `type` decides (ADR 0014).
- **Many products share one title.** Four handles are called "UAE-Regular Fit Styling Kurta" at AED 53.50 and are four different garments (design codes KR-STY25-079, -084, -086 and -001; four pictures; lite green, sky blue, beige, green). The app collapses a repeat of the same normalised title at the same price, so only the first of the four reaches the shopper. Across the four saved answers the 32 distinct products become **20**; 12 never reach the shopper. Nothing in the title tells them apart, so this is not fixable in the store file.
- **Titles start with `UAE-`** in three spellings ("UAE-" on 19 products, "UAE- " on 12, "UAE -" on 1) and 4 of 32 end with a style code ("KR-STY25-007"). The ranker splits at hyphens, so these are the harmless words "uae", "kr", "sty25" and "007". The spelling also changes what collapses: "UAE-Cambric Printed Shirt" and "UAE- Cambric Printed Shirt" at AED 79 stay two products.
- **Two prices on 5 of 32 products.** `price` is the lowest variant. On those five, `price_max` is 1.66 times higher and equals `compare_at_price_max` exactly: the full price of the same garment (53.50 against 89.00, 101.50 against 169.00; ratio 0.60, the same as the 40% sale on the 13 other products on sale). This is the sale price on some sizes and the full price on others, not a cheap add-on as at Hamsa (ADR 0012). The search answer lists no variants, so the size split is not confirmed. The store file leaves `max_price_spread` off: setting it to 1 or 1.25 drops 7 of the 40 records and leaves 18 distinct products; 1.7 or more drops none.
- **Categories by title.** A men's shalwar kameez is titled "Suits", and "suit" is deliberately ambiguous in `src/vga/rank/lexicon.py`, so it has no category and is kept for any request. A kurta is a dress. A women's kurti is titled "Shirt", which the ranker reads as tops, so it is dropped from a dresses request. "Waist Coat" is outerwear. Distinct products by title: dresses 10, tops 12, outerwear 1, no category 9. The store file therefore lists `dresses` and `tops`.
- Colour is not a field. It is in the picture file name ("...Color-Sky-Blue...") and the description.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "UAE-Regular Fit Styling Kurta", "UAE- Cambric Printed Shirt"); prefix `UAE-`, no brand word, a style code on 4 of 32 |
| price | yes | `price`, a string with two decimals (`"53.50"`); `price_min` and `price_max` give the variant range; `compare_at_price_max` is the pre-sale price (`"89.00"`) on 18 of 32 products and `"0.00"` on the rest |
| currency | not in the response | AED is store-level: `Shopify.currency` `{"active":"AED","rate":"1.0"}`, `Shopify.country` `"AE"`, and `"currencyCode":"AED"` on every variant price in the product page's data. No JSON-LD. Put `currency: AED` in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0652/2100/1325/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 40 of 40). Per-size stock is not in this response |
| colour | no | in the picture file name and the description only |
| gender | yes | `type` "Men" or "Women"; tags agree |

## Hosts

- Store host (product links): `uae.gulahmedshop.com` (`/products/<handle>` on all 40 records). It is a subdomain; the bare domain `gulahmedshop.com` was not requested.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0652/2100/1325/` on all 40 records. The product page's own variant data uses store-host image URLs instead (`//uae.gulahmedshop.com/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `uae.gulahmedshop.com`, `cdn.shopify.com`.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "113.50"`, `"price_min": "101.50"`, `"price_max": "169.00"`, `"compare_at_price_max": "189.00"`, `"compare_at_price_max": "0.00"`. Two decimals everywhere.
- Product page data: `"price":{"amount":113.5,"currencyCode":"AED"}` on each of four size variants (Small, Medium, Large, X-Large) of the sampled product.
- Observed over 32 distinct products, field `price` (the lowest variant price): **AED 41.50 to 149, median 91.25**. Men's (20): 41.50 to 113.50, median 100.25 (kurtas 41.50 to 101.50, suits 83.50 to 113.50, the waistcoat 101.50). Women's (12): 79 to 149, median 79 (kurtis 79 to 99, the two-piece set 149). Pre-sale prices AED 69 to 189.

## Currency / tier hint

AED. Tier: **budget** (AED 41.50 to 149 in the search answers; most men's items are about 40% off today, so the prices will rise when the sale ends; the women's suits seen only on the product page run to AED 329).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| shalwar kameez | `https://uae.gulahmedshop.com/search/suggest.json?q=shalwar%20kameez&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 men's: 9 "Suits" (AED 83.50 to 113.50) and 1 waistcoat (101.50); 8 distinct by title and price |
| kurta | `https://uae.gulahmedshop.com/search/suggest.json?q=kurta&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 men's kurtas (AED 41.50 to 101.50); 6 distinct by title and price |
| kurti | `https://uae.gulahmedshop.com/search/suggest.json?q=kurti&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 3 women's "Printed Shirt" (AED 79, tag "Kurti") and 7 men's kurtas; 7 distinct |
| printed shirt | `https://uae.gulahmedshop.com/search/suggest.json?q=printed%20shirt&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 women's: 9 kurtis (AED 79 to 99) and the two-piece set (149); 5 distinct |

## Requests made

8 (3 for robots.txt, 4 search requests, 1 product page). No redirects. Over the plan's "about 6" because robots.txt was fetched again for the product page and for the fourth query, each as a separate run; under the hard cap of 12.

## Sample

`docs/store-qualification/samples/gul-ahmed-uae/`

- `suggest-shalwar-kameez.json`, `suggest-kurta.json`, `suggest-kurti.json`, `suggest-printed-shirt.json`: the first 4 of the 10 products of the real response, same structure; each `body` string cut to 300 characters.
- `robots.txt`: the file as served.
- No `product-jsonld.json`: the product page has no JSON-LD.

## Risks and fragility

- Titles are not unique. A shopper sees one of four kurtas that share a title and price, and 12 of 32 products are hidden by the app's repeat rule. The right fix is in `dedupe_products` (for example, include the image in the key), which is shared code and not this store's file.
- A women's kurti is titled "Shirt", so a "kurti" or dresses search drops it. It is shown only for a tops request. The `kurti` query itself returns 7 men's kurtas and 3 women's kurtis.
- The whole men's range is on a 40% sale today (18 of 20 men's products); the prices and the budget band will move. A two-price product is shown at its lowest price; some sizes cost up to 66% more.
- No JSON-LD on the product page, so AED is confirmed only from `Shopify.currency` and the variant prices. A change of market or currency on this host would not show in the search answer.
- 10 results per request, no pagination tested. The search answer lists no variants and no per-size stock.
- The unseen range (women's 2 and 3 piece suits, possibly unstitched fabric) may come back for words such as "suit" or "lawn". Whether it does, and what it costs, is not known.
- `body` is store-supplied HTML; never render it. In 7 of the 40 records (6 distinct products) it holds U+FFFD replacement characters in the store's own response, 287 of 431 characters in the worst case ("UAE-Regular Fit Styling Kurta KR-STY25-007"). The adapter does not read it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but the stated preference should be reviewed before real users. Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.

## Not verified / limits

- Behaviour from the machine's own network (see "Network note"): the requests went through Cloudflare WARP, because the direct path to Shopify timed out.
- Terms of use.
- The HTML search page, the bare domain `gulahmedshop.com`, `limit` above 10 and pagination.
- Whether the two-price products are sizes at sale and full price (the search answer has no variants, and the one product page fetched has four sizes at one price).
- What `FB` means in the SKU of the women's suits, and whether they are stitched.
- Queries other than the four: `suit`, `lawn`, `waistcoat`, `trouser`, `shalwar`, `jacket`, `shoes`.
- That the sale is temporary.
- The UCP/MCP endpoints named in robots.txt (never requested).
