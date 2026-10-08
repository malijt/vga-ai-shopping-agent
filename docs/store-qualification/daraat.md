# Daraat qualification (2026-10-08)

**Verdict:** GO, pending the live smoke test. The honest client received title, price, image URL and product URL (plus availability) for 28 distinct products over four searches (40 records), from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Every price is in **Kuwaiti dinars (KWD)** with three decimals. The store is a Kuwaiti online label of kaftans and summer dresses at the low end of the dinar stores: KWD 8 to 29, about AED 95 to 346 at the project's fixed rate. Unlike Hamsa, every record has one price (`price_min` equals `price_max` on 40 of 40), so no price guard is needed. Two things to know: the `daraa` and `abaya` queries find no daraa and no abaya (the store pads the answer with kaftans), and the store files a jumpsuit and a "Sherwal" under the same `type` as its dresses. Nothing in the data names a gender.

## Storefront

- Store: Daraat, `https://www.daraat.com/` (the `www.` host answered with no redirect; the apex `daraat.com` was never requested). A Kuwaiti online store for kaftans and dresses ("Layers kaftan store in Kuwait" is how one description ends). Single brand: `vendor` is "Daraat" on 27 of 28 distinct products and "Muccii Outlet" on one ("Layers kaftan dress-1").
- Shopify shop `4aea7e-1a.myshopify.com` (`Shopify.shop` in the product page). `www.daraat.com` is a CNAME to `shops.myshopify.com`. `Shopify.country` is `"KW"`. The page offers English (the default) and Arabic (`/ar/` path prefix, from the `hreflang` links); only the unprefixed English host was requested.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, its `Disallow: /71062651110` line is the shop id (the image folder `/s/files/1/0710/6265/1110/` is the same number), all 28 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.theme` (Dawn 15.2.0), `Shopify.shop`, `Shopify.currency` and `ShopifyAnalytics`.
- Assortment seen in 40 search records (28 distinct handles): `type` "Dress" 27 and "Kaftan" 1. By title: 18 say kaftan (cotton, velvet and A-line kaftans), 8 say dress (summer, resort, midi and maxi dresses; one of the 8, "Layers kaftan dress-1", also says kaftan), one jumpsuit ("White jumpsuit with embroidery belt", KWD 20), one "Sherwal" ("Black & White Beach & Resort Sherwal", KWD 8; its own description says "Beach & resort dress"), and one title with no garment word ("Pink Orange Midi Long Sleeve", tags `resort`, `summer dress`). Women's garments by nature of the range; no field names a gender. No abaya, shoes, trousers, tops or jackets as such were seen.
- Several products are numbered prints of one design ("Flow A-Line cotton kaftan 1, 5, 7, 8, 9, 10, 11", all KWD 25; "Cotton Kaftan 187, 303, 310, 323", all KWD 19). They are different products with different links and images.

## robots.txt

- Parser: **protego 0.7.0**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, through `scripts/qualify_store.py`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://www.daraat.com/robots.txt`: 200, 3,624 bytes, no redirect, the same bytes on all three answered requests (runs 1, 2 and 3). Shopify's current default file (the same shape as Hanayen's and Hamsa's, with this shop's id line).
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
  (Each of these also has a `/*/...` twin for localised paths.) A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL requested (four suggest.json URLs and the product page): ALLOW. An offline protego pass over the saved file also says ALLOW for `https://www.daraat.com/search?q=kaftan` (never requested) and DISALLOW for `/cart/`, `/cart.js`, `/checkout` and `/recommendations/products`.
- Sitemap: `https://www.daraat.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data, **not acted on**: "Agents should use UCP/MCP for catalog, cart, and checkout." It also names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for humans and must not be completed automatically, asks an agent that acts as a "personal shopper" to recommend that its user install a third-party shopping skill (`shop.app/SKILL.md`), and gives a contact address. These are comments, not robots rules. None of those URLs was requested, nothing was installed, and no cart, checkout or account address was touched. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.daraat.com/robots.txt` (about 14:02, the machine's own network) | none | none | connect time-out | no answer; no refusal was received. Not a block (see "Not verified / limits") |
| 2 | `https://www.daraat.com/robots.txt` (about 14:07, through WARP, as are all rows below) | 200 | 3624 | 0.6 s | text/plain |
| 3 | `https://www.daraat.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 27890 | 0.5 s | application/json, 10 products |
| 4 | `https://www.daraat.com/search/suggest.json?q=daraa&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 21534 | 0.3 s | 10 products |
| 5 | `https://www.daraat.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 19619 | 0.3 s | 10 products |
| 6 | `https://www.daraat.com/robots.txt` (second run) | 200 | 3624 | 0.7 s | the script reads robots.txt first on every run |
| 7 | `https://www.daraat.com/products/pink-and-black-zigzag-cotton-kaftan` | 200 | 744849 | 0.8 s | the one product page (JSON-LD check): one `Product` block, `priceCurrency` KWD |
| 8 | `https://www.daraat.com/robots.txt` (third run, for the extra query) | 200 | 3624 | not recorded | |
| 9 | `https://www.daraat.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 13128 | 0.4 s | 10 products |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not saved with the answers.

## Search URL template

`https://www.daraat.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list, which is **empty on all 40 records**. The product page carries one `Product` JSON-LD block with one `Offer` (`price` `"17.000"` as a string, `priceCurrency` `"KWD"`, `availability` InStock) and its `category` is "Dresses".

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the other stores. Store-specific points:

- **Currency is KWD** with three decimals (`"17.000"`). The project already reads three-decimal prices for KWD (ADR 0006) and has a fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED); Kuwait is already among `extra_store_countries`. Nothing in `src/` or `config/settings.yaml` needs to change for this store.
- **No price trap.** `price_min`, `price_max` and `price` agree on all 40 records, so the default `price` is the garment's and no `max_price_spread` is set. This is a recorded fact, not a promise: a store can add a made-to-measure surcharge later, and 20 of 28 products carry the tag `custom-dress`. If a later recording shows differing variant prices, add `max_price_spread: 1` as at Hamsa (ADR 0012).
- Pin the host `www.daraat.com`. Build the link from the host plus `/products/{handle}`; the tracking query (`?_pos=1&_psq=kaftan&_psid=...&_ss=e`) is dropped. **Handles do not match titles** on 13 of 28 records; real mismatches include "Cotton Kaftan 310" at `/products/cotton-kaftan-320` and "Royal Amethyst Velvet Kaftan" at `/products/sea-mist-velvet-kaftan-copy`. Always use `url` or `handle`.
- `type` is "Dress" on 27 of 28 products, kaftans included, so it cannot name a kaftan or separate a jumpsuit; the title has to.
- There is no gender field. Nothing in `type`, `tags` or the first 300 characters of any description holds a gender word, so the gender reader leaves every product unknown and `genders: [women]` in the store file carries it.
- Images are `.png` (15 of 28) and `.jpg` (13), all on `cdn.shopify.com` under `/s/files/1/0710/6265/1110/files/`.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Pink and Black Zigzag Cotton Kaftan") |
| price | yes | `price`, a string with three decimals (`"17.000"`); `compare_at_price_max` is the pre-sale price when above `"0.000"` (16 of 28 products, for example `"39.000"` against `"17.000"`) |
| currency | not in the response | KWD is store-level: `priceCurrency: "KWD"` in the product JSON-LD, `Shopify.currency` `{"active":"KWD","rate":"1.0"}`, `ShopifyAnalytics.meta.currency` `'KWD'`, `Shopify.country` `"KW"` |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0710/6265/1110/files/...?v=...` |
| product URL | yes | `url` (relative, with tracking) or build from `handle` |
| in stock | yes, product level | `available` (true for 28 of 28); the product JSON-LD offer is InStock |
| colour | partly | in some titles ("Pink Orange Maxi Dress Long sleeves", "Black Floral Velvet Free-Size Kaftan") |
| gender | no | not a field |

## Hosts

- Store host (product links): `www.daraat.com`.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0710/6265/1110/files/` on all 28 products. The product page's own JSON-LD uses `www.daraat.com/cdn/shop/files/...` instead; search results do not.
- Candidate `allowed_hosts`: `www.daraat.com`, `cdn.shopify.com`.
- The product page also loads a third-party currency converter app (script host `currency.grizzlyapps.com`) that converts displayed prices in the visitor's browser; its settings list `shopCurrency` KWD and `allowedCurrencies` KWD, SAR, QAR, AED, OMR, BHD, JOD, EUR, USD, GBP. We run no JavaScript and read the shop's JSON, which is in KWD. It is named here because it is the reason to re-check the currency if the store ever changes how it serves it (see "Risks and fragility"). It was not contacted.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "17.000"`, `"price_max": "17.000"`, `"compare_at_price_max": "39.000"`, `"compare_at_price_max": "0.000"`.
- Product JSON-LD: `"price": "17.000"` (a string), `"priceCurrency": "KWD"`.
- Observed over 28 distinct products, field `price`: **KWD 8 to 29, median 19** (quartiles 13.25, 19, 25; mean 19.5). Kaftans (18 by title) KWD 12 to 29, median 25; the other 10 KWD 8 to 20, median 12. Pre-sale prices seen: `"39.000"` (9 products), `"49.000"` (4), `"69.000"` (2), `"20.000"` (1), none (12).

## Currency / tier hint

**KWD**. At the project's fixed rate (1 KWD = 11.92 AED, ADR 0006) the range is about **AED 95 to 346, median 226**. Tier: **budget**. For comparison, Nishat Linen UAE (budget) sits at AED 39.50 to 239 and Signature Studio (mid-range) at AED 174 to 2,753. 16 of 28 products are marked down from KWD 20 to 69, so the budget band may move when a promotion ends.

AED storefront: none seen. The prices come in dinars at the unprefixed host.

Fit: this is the cheapest dinar store and a source of low-priced kaftans and summer dresses. It does not fill the "abaya below about AED 600" gap: the `abaya` query returned no abaya.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| kaftan | `https://www.daraat.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all kaftans by title (cotton prints, velvet, "Flow A-Line"), KWD 17 to 29 |
| daraa | `https://www.daraat.com/search/suggest.json?q=daraa&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 9 kaftans and 1 dress ("Sleeveless Dark Blue Midi Summer Dress", KWD 12); no title, handle, tag or description holds the word "daraa"; 6 of the 10 are new after the kaftan answer |
| abaya | `https://www.daraat.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 9 kaftans and 1 jumpsuit; no abaya, and the word is in no title, handle, tag or description; 3 of the 10 are new |
| dress | `https://www.daraat.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, KWD 8 to 18: 8 titles say dress (one of them, "Layers kaftan dress-1" with vendor Muccii Outlet, also says kaftan), plus the "Sherwal" and "Pink Orange Midi Long Sleeve", which name no dress; 9 are new (the tenth is in the daraa answer) |

Distinct products: 19 over kaftan, daraa and abaya together; 28 with dress.

## Requests made

9 to `www.daraat.com`: 4 for robots.txt (the first got no answer), 4 searches, 1 product page. 8 were answered, all with HTTP 200. No redirects. The script's cap is 12.

## Sample

`docs/store-qualification/samples/daraat/`

- `suggest-kaftan.json`, `suggest-daraa.json`, `suggest-abaya.json`, `suggest-dress.json`: the first 4 of the 10 products of the real response, same structure; each `body` string cut to 300 characters.
- `robots.txt`: the file as served.
- No `product-jsonld.json` was saved with the samples; the facts above about the product page were read from the saved `product.html` outside the repository.

The test fixtures in `tests/stores/daraat/fixtures/` hold all 10 products of each answer (only each `body` cut to 300 characters).

## Risks and fragility

- **Search padding.** The word asked for is often not in the result: `daraa` and `abaya` found neither. The ranker must filter by category and title; the store's order is not trusted.
- **Odd listings under `type` "Dress":** a jumpsuit (out of scope for every request, dropped by the shared title reader) and a "Sherwal" (the reader knows no category for it, so it is kept without one). Both were seen once in 28.
- **Pre-sale prices** on 16 of 28 products: the price a shopper pays can change when a promotion ends.
- **Currency and market.** The search answer has no currency. The shop is in dinars and the product page confirms it, but the page also runs a browser-side currency converter and has an `/ar/` language path. A change in how the shop serves a currency would silently misprice every product: re-check the product page JSON-LD if prices look 10 times too big or small.
- **No price guard is set.** If variant prices start to differ (20 of 28 products are tagged `custom-dress`), the default `price` would be the cheapest variant. A test pins the current state.
- **A single small brand:** kaftans and dresses only as far as seen; nothing for tops, outerwear, bottoms or shoes.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint; review before real users. A template change could close `/search`.

## Not verified / limits

- **Network path.** All requests were sent on 2026-10-08 between about 14:07 and 14:14 local time (PKT) by the orchestrator with `scripts/qualify_store.py` (User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first, at least 1 s apart, one store at a time). The saved files carry modification times of 14:07 (first run) and 14:13 (the `dress` query). From about 13:00 the machine's own network path to Shopify's addresses timed out on connect (no refusal was ever received; a Cloudflare Community thread reports the same kind of time-out from Pakistani providers that week). The user then enabled Cloudflare WARP on the machine and the requests went through it. The User-Agent and every other rule were unchanged, and no store answered with a refusal. **Behaviour from the machine's own network is untested.** That includes whether Shopify's market or currency choice for `www.daraat.com` differs by visitor address: every answer here came through WARP.
- The HTML search page `https://www.daraat.com/search?q=` (allowed by robots.txt per protego, never requested), the Arabic path `/ar/`, `limit` above 10 and pagination.
- Queries other than `kaftan`, `daraa`, `abaya` and `dress`; Arabic words as queries.
- That the cheap pre-sale marking is permanent; per-size stock; whether made-to-measure options exist and how they are priced (the variant list is empty in the search answer, and the product page's variants were not read).
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no image was fetched).
- The terms of use of the store, and whether `Muccii Outlet` is a separate seller whose goods the store resells.
- The live smoke test through the project's own engine: pending, run by the orchestrator.
