# Hamsa by Sharifa AlGhanim qualification (2026-10-08)

**Verdict:** GO, with a currency flag and a price caveat. The honest client received title, price, image URL and product URL (plus availability) for 20 distinct products over two searches (10 abayas and 10 kaftans or kaftan-style dresses), from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Every price is in **Kuwaiti dinars (KWD)**, and the store has no AED storefront: its own region table prices all 201 regions, the UAE included, in KWD. This is the one brand of the seven that sells abayas and kaftans, but at the converted level nothing seen is below about AED 660, so it does not fill the "abayas under AED 600" gap. Two further quirks: three-decimal prices, and on 5 of 10 abaya records the `price` field is the cheapest variant (probably a scarf), not the abaya.

## Storefront

- Store: Hamsa by Sharifa AlGhanim, `https://hamsakw.com/` (used directly, no redirect). A Kuwaiti label of abayas, kaftans, dresses and loungewear with boutiques at The Avenues and the old souk in Kuwait. Single brand, but `vendor` takes two spellings: "Hamsakw" on 12 of 20 records and "Hamsa by Sharifa AlGhanim" on 8.
- **How it is known to be the brand's own shop.** Web search found the domain with the title "HAMSA By SHARIFA ALGHANIM", its collection pages (`/collections/evening`, `/collections/loungewear`, `/collections/discount-on-items`) and a `/pages/stockist` page that lists the brand's own boutiques and names other retailers separately (Tefaseel, Thouqi, Farfetch), which shows `hamsakw.com` itself is not one of the stockists. The Shopify shop is `hamsakw.myshopify.com`; the product JSON-LD names the brand "Hamsa by Sharifa AlGhanim".
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 20 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.theme` (Stiletto), `shopify-features`, `myshopify.com`, `/cdn/shop/` and `Shopify.currency`.
- Assortment seen in 20 search records (20 distinct handles): `type` "ABAYA" 10, "KAFTAN" 8, "DRESS" 1 ("Ameera Kaftan"), "casual dresses" 1 ("Short Amar Kaftan"). Open abayas, abaya sets with a scarf, a coat ("Star Dust Coat"), and kaftans in gazar, velvet and embroidered styles. Women only by nature of the range; no gender field. No shoes, trousers, tops or gowns appeared.
- **Old catalogue.** Product codes such as `S-20-005` and `W-22-029` (2020 and 2022 collections) are still searchable and marked available, next to `W-26-033`; image versions (`?v=1596723938`) date the oldest to 2020.

## robots.txt

- Parser: **protego 0.7.0**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, through the `MALFORMED_RULE` reading in `scripts/qualify_store.py`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://hamsakw.com/robots.txt`: 200, 3,612 bytes, no redirect. Shopify's current default file, identical to Hanayen's except for the host and the shop id line (`Disallow: /10784538705`).
- Group `User-agent: *`: `Allow: /`, exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows for `/admin`, `/cart/`, `/checkout`, `/orders`, `/account`, `/cart.js`, `/recommendations/products`, `/collections/*sort_by*`, filter combinations and preview parameters. A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`**. Protego result for every URL requested (two suggest.json URLs and the product page): ALLOW.
- Sitemap: `https://hamsakw.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents (UCP/MCP preference, `agents.md`, `/.well-known/ucp`, `/api/ucp/mcp`, a third-party "shop.app" skill). Quoted as data, not acted on, none of those URLs requested. Review at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://hamsakw.com/robots.txt` | 200 | 3612 | 1.0 s | text/plain |
| 2 | `https://hamsakw.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 11976 | 0.8 s | application/json, 10 products |
| 3 | `https://hamsakw.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 14139 | 1.0 s | 10 products |
| 4 | `https://hamsakw.com/products/riwaq-kaftan` | 200 | 403805 | 1.4 s | the one product page (JSON-LD check) |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded.

## Search URL template

`https://hamsakw.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: both responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list. The product page carries one `Product` JSON-LD block with six `Offer` entries (one per size), each with `price` `95.0`, `priceCurrency` `"KWD"` and `availability`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the six current stores. Store-specific points:

- **Currency is KWD** (same blockers as Bazza Alzouman and Manal Smaoui): `src/vga/stores/prices.py` accepts only two-decimal bare prices, and this store writes `"95.000"`, so `parse_price` would drop every record; and `src/vga/tiers/shaper.py` keeps only the most common currency of a result set, so KWD products would be left out of an AED run with a warning. A decision for the orchestrator.
- **`price` can be the cheapest variant, not the garment.** For 5 of the 10 abaya records `price_min` differs from `price_max`, the `url` carries `&variant=...`, and `variants[0]` holds the variant the search matched, which is the abaya. Examples (all KWD): "Fire Works Abaya" `price` 20.000 but abaya variant 80.000; "Shooting Star Abaya" 95.000 against 365.000; "Collage Abaya" 35.000 against 130.000; "Stardust Abaya" 35.000 against 95.000; "Tonal Abaya/Scarf" 20.000 against 75.000. The `body` of "Stardust Abaya" lists an abaya and a "Head Scarf" as separate items, so the low figure is probably the scarf (not verified). The `shopify` strategy reads `price` only, so for these records it would show the add-on price. For the other 15 records `price_min` equals `price_max` and `price` is the garment price. A fix is to read `variants[0].price` when it exists and the `url` names a variant; that is adapter work, not configuration.
- Pin the host `hamsakw.com`. Build the link from the host plus `/products/{handle}`; drop the tracking query (and with it the `variant` parameter). **Handles do not match titles**: "Amber Kaftan" lives at `/products/short-seline-kaftan-copy-1`, "Short Seline Kaftan" at `/products/long-seline-kaftan-copy`. Always use `url` or `handle`.
- `type` is usable but inconsistent in case and value: "ABAYA", "KAFTAN", "DRESS", "casual dresses". Category for dresses, abayas and kaftans can come from `type` first, title second. Two `vendor` spellings for one brand (see above).
- There is no gender field; the range is women's.
- 10 of 20 records are discounted today (`compare_at_price_max` above `price`); records with an equal pre-sale price ("Amber Kaftan" 55.000 against 55.000) are not discounts.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Riwaq Kaftan", "Heyah Abaya") |
| price | yes, with the caveat above | `price`, a string with three decimals (`"95.000"`); `compare_at_price_max` is the pre-sale price when above `price` (for example `"365.000"` against `"75.000"` for "Star Dust Coat") |
| currency | not in the response | KWD is store-level: `priceCurrency: "KWD"` on all six offers of the product JSON-LD, `Shopify.currency` `{"active":"KWD","rate":"1.0"}`, `Shopify.country` `"KW"`; the page's region table gives KWD for all 201 regions including `AE` |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0107/8453/8705/products/...jpg?v=...`. The product JSON-LD `image` is malformed: `"https:files/W-26-0332.jpg"` |
| product URL | yes | `url` (relative, with tracking and sometimes `variant=`) or build from `handle` |
| in stock | yes, product level | `available` (true for 20 of 20); all six size offers of the sampled kaftan are InStock |
| colour | partly | in some titles ("Pistachio Lotfia Kaftan", "Brick Acker Kaftan") and in the variant title ("Black-Gold / Free Size / Abaya") |
| gender | no | not a field |

## Hosts

- Store host (product links): `hamsakw.com`.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0107/8453/8705/` on all 20 records.
- Candidate `allowed_hosts`: `hamsakw.com`, `cdn.shopify.com`.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "95.000"`, `"price_max": "365.000"`, `"compare_at_price_max": "385.000"`, `"compare_at_price_max": "0.000"`.
- Product JSON-LD: `"price": 95.0`, `"priceCurrency": "KWD"`.
- Observed over 20 distinct handles, field `price`: **KWD 20 to 320, median 87.5**. Using the garment variant where the two differ: **KWD 55 to 365**. Abayas: KWD 75 to 365 (the cheapest abaya variants are "Tonal Abaya/Scarf" and "Star Dust Coat" at KWD 75). Kaftans and kaftan-style dresses: KWD 55 to 320 (cheapest "Amber Kaftan" KWD 55, then "Short Seline Kaftan" and "Short Amar Kaftan" KWD 65). At roughly AED 12 per KWD (an approximation, not observed) that is about AED 660 to 4,400; the cheapest abaya is about AED 900 and the cheapest kaftan about AED 660.

## Currency / tier hint

**KWD** (not AED). Tier: **premium to luxury** at the converted level (about AED 660 to 4,400 for garments). Nothing seen is under about AED 660, so it does not meet the "abayas under AED 600" need.

AED storefront: none. The page's region table (`tmsRegionData`) maps all 201 regions, including `AE`, `SA` and `GB`, to KWD, and there are no language or market alternates in the page head.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| abaya | `https://hamsakw.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all abayas: "Fire Works Abaya", "Stardust Abaya", "Collage Abaya", "Shooting Star Abaya", "Duma Abaya" (KWD 135), "Long Palm Tree Velvet Abaya" (148), "Heyah Abaya" (185), "Duma Abaya Set" (212), "Star Dust Coat" (75), "Tonal Abaya/Scarf"; 5 with variable prices |
| kaftan | `https://hamsakw.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all kaftans: "Amber Kaftan" 55, "Long Cord Kaftan" 80, "Ameera Kaftan" 115 (was 320), "Rhadiah Kaftan" 70 (was 230), "Rania Kaftan" 320, "Pistachio Lotfia Kaftan" 160 (was 295), "Riwaq Kaftan" 95 |

## Requests made

4 (1 for robots.txt, 2 searches, 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/hamsa-kw/`

- `suggest-abaya.json`, `suggest-kaftan.json`: the first 4 of the 10 products of the real response, same structure; each `body` string cut to 300 characters.
- `product-jsonld.json`: the `Product` JSON-LD block of the sampled product page (`description` cut to 300 characters; the malformed `image` value is left as served).
- `robots.txt`: the file as served.

## Risks and fragility

- Currency and price format (see above): without a decision and a parser change this store yields no products in the demo.
- The `price` field understates the garment on half the abaya records; reading it blindly would put an abaya at KWD 20 to 35 when it costs KWD 75 to 365.
- Old catalogue entries (2020 and 2022 codes) are searchable and "available", so some results may be from past seasons.
- Handles do not match titles; `type` and `vendor` are inconsistent.
- Single brand: abayas, kaftans, dresses and loungewear only; nothing for tops, outerwear, bottoms or shoes.
- `body` is store-supplied HTML (up to 1,423 characters here); never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint; review before real users. A template change could close `/search`.
- Not tested: HTML search page, `limit` above 10, `dress` and `gown` queries, behaviour from the user's network, terms of use.
