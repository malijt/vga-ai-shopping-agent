# Bazza Alzouman qualification (2026-10-08)

**Verdict:** GO, with a currency flag. The honest client received title, price, image URL and product URL (plus availability) for 17 distinct products over two searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Every price is in **Kuwaiti dinars (KWD)**, not AED, and the store offers no AED storefront: its own country picker lists "United Arab Emirates (KWD)". The range is evening gowns at KWD 206 to 380, which is luxury pricing (roughly AED 2,500 to 4,600 by an approximate rate, not observed). Two adapter blockers beyond configuration: prices have three decimals (`"260.000"`), which the project's price parser rejects, and the tier shaper keeps only the most common currency.

## Storefront

- Store: Bazza Alzouman, `https://bazzaalzouman.com/` (used directly, no redirect). A Kuwaiti evening-wear label (founded 2014 in Kuwait, per the press pieces that came up in the search). Single-brand: `vendor` is "Bazza Alzouman" on 17 of 17 records.
- **How it is known to be the brand's own shop.** Web search found the domain with the brand's own pages (`/pages/about` with the designer's biography, `/collections/clothing` titled "Gowns", product pages titled "... - Bazza Alzouman"). The product JSON-LD names the brand "Bazza Alzouman", the Shopify shop is `bazza-alzouman-shop.myshopify.com` and the theme is called `bazza-alzouman-v3`. The press results named the stockists Moda Operandi and Ounass as separate retailers; neither was contacted.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 17 product images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.theme`, `shopify-features`, `myshopify.com`, `/cdn/shop/` and `Shopify.currency`.
- Assortment seen in 20 search records (17 distinct handles): 15 of `type` "Dresses", one "Dress", one "Gown". Titles are all gowns or dresses: strapless, off-shoulder and one-shoulder crepe and tulle gowns, a mermaid gown, a halter dress, ball gowns. Women only by nature of the range; no gender field. The `gown` and `dress` queries returned only dresses and gowns (no padding with other garments in these two queries). The site also sells at least a jumpsuit (seen in a search-engine title, not in our responses).

## robots.txt

- Parser: **protego 0.7.0**, run through `scripts/qualify_store.py`'s malformed-rule reading (`MALFORMED_RULE`) on the file as served, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://bazzaalzouman.com/robots.txt`: 200, 3,636 bytes, no redirect. It is Shopify's current default file; it differs from the Hanayen file only in the host name and the shop id line (`Disallow: /24407539793`).
- Group `User-agent: *` opens with `Allow: /`, then `Allow:` exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows (`/admin`, `/cart/`, `/checkout`, `/orders`, `/account`, `/cart.js`, `/recommendations/products`, `/collections/*sort_by*`, filter combinations, preview parameters). A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result for every URL requested (two suggest.json URLs and the product page): ALLOW.
- Sitemap: `https://bazzaalzouman.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents ("Agents should use UCP/MCP for catalog, cart, and checkout", an `agents.md` page, `/.well-known/ucp`, `/api/ucp/mcp`, a third-party "shop.app" skill, and a note that checkouts are for humans). Quoted as data: they are comments, not robots rules. I did not act on them and did not request any of those URLs. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://bazzaalzouman.com/robots.txt` | 200 | 3636 | 1.0 s | text/plain |
| 2 | `https://bazzaalzouman.com/search/suggest.json?q=gown&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 11952 | 1.0 s | application/json, 10 products |
| 3 | `https://bazzaalzouman.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 12056 | 1.0 s | 10 products |
| 4 | `https://bazzaalzouman.com/products/halter-dress` | 200 | 409727 | 1.2 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://bazzaalzouman.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 products asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: both responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list. The product page carries one `Product` JSON-LD block with eight `Offer` entries (one per size variant), each with `price`, `priceCurrency` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores. Store-specific points:

- **Currency is KWD, and the project is built around AED.** The config would say `currency: KWD` (the model accepts any three-letter code). Two things then go wrong without code changes:
  - `src/vga/stores/prices.py` accepts only `^\d+\.\d{2}$` for a bare price. This store writes `"260.000"` (three decimals, as KWD has 1,000 fils), so `parse_price` would raise `PriceFormatError` and every record would be dropped. A new format would be added when a store report shows one; this report is that evidence.
  - `src/vga/tiers/shaper.py` keeps only the products in the most common currency of the result set. With six AED stores, KWD products would be left out with a warning.
  Deciding how a KWD store enters an AED result set (a documented fixed conversion, a separate list, or leaving it out) is a decision for the orchestrator, not for an adapter.
- Pin the host `bazzaalzouman.com`. Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=...&_psq=...&_psid=...&_ss=e`). The `/ar/` prefix exists for Arabic (hreflang `ar`); only the unprefixed English host was requested.
- `type` is "Dresses", "Dress" or "Gown": all one category (dresses). There is no gender field; the range is women's.
- The same product can come back under both queries (17 distinct handles in 20 records); collapse by handle.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Off-Shoulder Crepe Gown With Wrap Skirt") |
| price | yes | `price`, a string with three decimals (`"250.000"`); `compare_at_price_max` is the pre-sale price when above `0.000` (2 of 17 records: `"345.000"` against `"242.000"`, `"295.000"` against `"206.000"`) |
| currency | not in the response | KWD is store-level: `priceCurrency: "KWD"` on all eight offers in the product JSON-LD, `Shopify.currency` `{"active":"KWD","rate":"1.0"}`. Put it in the store config |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0244/0753/9793/files/...jpg?v=...` |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 17 of 17). The product page shows per-size stock (three of the eight size variants of the sampled dress were out of stock) |
| colour | partly | in the title or the `body` text ("Color: Off-white") |
| gender | no | not a field; the range is women's |

## Hosts

- Store host (product links): `bazzaalzouman.com`.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0244/0753/9793/` on all 17 records. The product page JSON-LD uses store-host image URLs instead (`https://bazzaalzouman.com/cdn/shop/files/...`).
- Candidate `allowed_hosts`: `bazzaalzouman.com`, `cdn.shopify.com` (consider restricting the image path prefix above).

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "260.000"`, `"price": "206.000"`, `"price": "380.000"`, `"compare_at_price_max": "295.000"`, `"compare_at_price_max": "0.000"`.
- Product JSON-LD: `"price": 265.0`, `"priceCurrency": "KWD"` (a number here, a string in the search JSON).
- Observed over 17 distinct handles: price **KWD 206 to 380, median 255**; every record has `price_min` equal to `price_max`. At roughly AED 12 per KWD (an approximation, not observed; the dinar is pegged to a basket) that is about AED 2,500 to 4,600.

## Currency / tier hint

**KWD** (not AED). Tier: **luxury**. Even converted loosely, the lowest price seen (KWD 206, about AED 2,500) is close to the top of Signature Studio (AED 2,753) and in the upper half of Maison D'Vie's range (AED 490 to 4,430). Nothing here is budget or mid-range.

If the same store visibly offers an AED storefront at a robots-allowed URL: it does not. The product page's country picker shows every country, including "United Arab Emirates", priced in KWD (the picker posts a form to `/localization`, which was not requested). The only language alternate is Arabic (`/ar/`).

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| gown | `https://bazzaalzouman.com/search/suggest.json?q=gown&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all gowns, KWD 206 to 290: "Slim Cut Crepe Gown With Gathered Tulle Illusion Neckline And Sleeve" 260, "Strapless Gown With Side Organza Ruched Drape" 245, "Long Sleeve Collared Wrap A Line Gown" 206 (was 295) |
| dress | `https://bazzaalzouman.com/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all gowns and dresses, KWD 235 to 380: "Halter Dress" 265, "Strapless Gathered Dress" 335, "Off-Shoulder Statement Sleeve Crepe Gown" 380, "Mikado Gown with Oversized Puff Sleeve and Gazaar Drape" 242 (was 345) |

## Requests made

4 (1 for robots.txt, 2 searches, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/bazza-alzouman/`

- `suggest-gown.json`, `suggest-dress.json`: the first 4 of the 10 products of the real response, same structure. The only edit is that each `body` string is cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page (`description` cut to 300 characters).
- `robots.txt`: the file as served.

## Risks and fragility

- Currency and price format (see "Extraction strategy needed"): without a decision and a parser change this store yields no products in the demo.
- Single-brand, evening wear only: nothing for tops, outerwear, bottoms, shoes or abayas. Useful for the dresses category only, and only at luxury prices (about AED 2,500 and up), so it adds nothing for a budget or mid-range gown.
- Collection codes (`PS26`, `AW26`, `PF25`, `AW24`) sit in `tags`; several records belong to older collections, so the catalogue carries more than the current season.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint. Our use of `/search/suggest.json` is allowed by the robots rules, but this stated preference should be reviewed before real users. Shopify's predictive-search endpoint is the merchant's to change or restrict at any time.
- Not tested: HTML search page, the `/ar/` prefix, `limit` above 10, behaviour from the user's network, terms of use, a non-dress query.
