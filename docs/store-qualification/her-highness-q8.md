# Her Highness Q8 qualification (2026-10-08)

**Verdict:** GO, with a currency flag and a data-quality caveat. The honest client received title, price, image URL and product URL (plus availability) for 21 distinct products over three searches (30 records, 9 of them repeats), from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). Every price is in **Kuwaiti dinars (KWD)**, three decimals (`"45.000"`): KWD 28.5 to 85, median 45, which is about AED 340 to 1,013 (median 536) at the project's fixed rate. The currency is handled by ADR 0006, as for Hamsa, Manal Smaoui and Bazza Alzouman. The data is thin on labels: 11 of the 21 titles name no garment ("Crescent", "Crystal Black", one is just "2"), `type` is mostly empty, `tags` and `variants` are empty on every record, and no field names a gender. Three pieces are blazer-and-trousers suits by their description, one is a top, and four are girls' pieces. The store file is written (`enabled: false`); the live smoke test is still to be run.

## Storefront

- Store: Her Highness Q8, `https://herhighnessq8.com` (used directly: the apex answered with no redirect). Shopify shop `0inss8-r6.myshopify.com`, `Shopify.country` `"KW"`. A Kuwaiti modest-wear label. The shop's own name in its markup is `herhighnessq8` (`og:site_name`, JSON-LD brand, `vendor` on 21 of 21 records); its policy text calls itself "Her Highness". The display name `Her Highness Q8` is the orchestrator's choice.
- **How it is known to be the brand's own shop.** No web search was made in this task (no network was allowed to me). From the saved product page and answers: `vendor` is the same string, `herhighnessq8`, on all 21 records and is also the site name; the page's exchange and return policy is written in the first person ("At Her Highness, we are committed to ..."); the delivery panel gives times for Kuwait and for "The Gulf (or GCC)" (7 to 10 days each); and the descriptions are mostly in Arabic. That points to a single-brand shop that ships to the GCC. It is not proof that it is not a stockist.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 21 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.shop`, `Shopify.theme` (a custom theme, "Klicks Media", schema "Ella" 6.7.2), `Shopify.currency`, `Shopify.country`, `shopify-features` and `/cdn/shop/` paths.
- Assortment seen in 30 search records (21 distinct handles). `type` is empty on 17, "Dress" on 3 and "set" on 1; `vendor` is `herhighnessq8` on all 21; `tags` is empty on all 21. By title or, where the title is only a name, by the Arabic description (store text, read as data):
  - **14 daraas, kaftans or dresses:** "Dara'a 2026", "Aura Dress", "Ivory Glow Dress", "Pearl Dress", "Brown Mist Dress", "Burgundy Kaftan", "Plum Kaftan", "Olive Garden", "Desert Palm Luxury", "Crescent", "MZIANA – Moroccan" (a Moroccan three-piece daraa), "Kids Olive Kaftan", "Kids Burgundy Kaftan" and "Crescent Kids" (a velvet daraa with an inner dress, girls').
  - **3 suits** (a blazer with a belt and wide trousers, by their description only): "Crystal Dark Beige", "Crystal Black", "Royal Midnight Full set" (the one with `type` "set").
  - **1 top:** "Sahara Oversized Top".
  - **3 whose title and description name no garment:** "Beige strips Sets" (empty description), "2" (empty description) and "MZIANA – Moroccan Kids" (empty description; by analogy with the adult "MZIANA – Moroccan" a daraa, not verified).
  - **4 are girls' pieces,** each with "Kids" in the title (the three kaftan and daraa pieces above, and "MZIANA – Moroccan Kids"). They are the cheapest in the store.
- No shoes, jeans, jackets (as separate items) or abayas by title were seen. The word `abaya` appears in no title and in none of the saved descriptions. "Not seen" is not "not sold": three queries of 10 products each were read.
- Women's by nature of the range (daraas, kaftans, dresses, a suit "for a feminine look" in one description) and girls'; no field names a gender.

## robots.txt

- Parser: **protego 0.7.0**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`. The stdlib `urllib.robotparser` was not used. The orchestrator ran the check live with `scripts/qualify_store.py`; it was repeated offline in this task on the saved file with the same result.
- Fetched from `https://herhighnessq8.com/robots.txt`: 200, 3,636 bytes, twice (requests 1 and 5), no redirect. Shopify's current default file, identical to Hamsa's and Manal Smaoui's except for the host and the shop-id line (`Disallow: /69546311733`).
- Group `User-agent: *`: `Allow: /`, exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows for `/admin`, `/cart/`, `/checkout`, `/orders`, `/account`, `/services`, `/sf_*`, `/cdn/wpm/*.js`, `/cart.js`, `/recommendations/products`, `/collections/*sort_by*`, filter combinations and preview parameters. A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`.** Protego result: ALLOW for the three suggest.json URLs and the product page that were requested; ALLOW offline for `https://herhighnessq8.com/search?q=daraa` (not requested); DENY for `/cart/` and `/checkout`.
- Sitemap: `https://herhighnessq8.com/sitemap.xml`. Crawl-delay: none.
- **The comment block at the top is addressed to AI agents (data, not acted on).** It says "Agents should use UCP/MCP for catalog, cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, suggests that an assistant install a third-party shopping skill (`shop.app/SKILL.md`), and says checkouts are for humans and must not be completed automatically. This is store-supplied text. None of those URLs was requested by me or, as far as the request log shows, by the orchestrator; nothing was installed; no instruction in it was followed. The rule that applies to us is the `User-agent: *` group. Review the stated preference for the agent endpoint at the terms-of-use step (BRD Rule 6) and for Phase 17.

## Reachability

All six requests were sent on 2026-10-08 by the orchestrator through Cloudflare WARP (see "Not verified / limits").

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://herhighnessq8.com/robots.txt` | 200 | 3636 | 0.6 s | first request |
| 2 | `https://herhighnessq8.com/search/suggest.json?q=daraa&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 9760 | 0.4 s | 10 products |
| 3 | `https://herhighnessq8.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10158 | 0.4 s | 10 products |
| 4 | `https://herhighnessq8.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10815 | 0.3 s | 10 products |
| 5 | `https://herhighnessq8.com/robots.txt` | 200 | 3636 | 0.6 s | second run (the product-page run); same size |
| 6 | `https://herhighnessq8.com/products/daraa-2026` | 200 | 704615 | 0.8 s | the one product page (JSON-LD check), one `Product` block |

No challenge page, CAPTCHA, login wall or redirect was reported. Response headers were not recorded.

## Search URL template

`https://herhighnessq8.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all three responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list, which is **empty on all 21 distinct records** (also on the two whose `price_min` and `price_max` differ). The product page carries one `Product` JSON-LD block with 21 `Offer` entries, each with `price` `"35.0"` (a string), `priceCurrency` `"KWD"` and `availability` InStock.

## Extraction strategy needed

`shopify` (plan module 6.4.6), with **no options**. Store-specific points:

- **Currency is KWD** (decision made: ADR 0006, fixed rate, as for Hamsa, Manal Smaoui and Bazza Alzouman). Three-decimal prices are accepted for KWD. Kuwait is already among `extra_store_countries`.
- **Price: `max_price_spread` stays off.** Of the 21 distinct records, 19 have `price_min` equal to `price_max` equal to `price`. The other two, "Crescent Kids" (`price` 35.000, `price_max` 37.000) and "MZIANA – Moroccan Kids" (40.000 to 43.000), are girls' pieces with a size surcharge (ratios 1.06 and 1.08), not a cheap add-on beside an expensive garment (the trap at Hamsa, ADR 0012). With `max_price_spread: 1` those two would be dropped for no gain (the ranker drops children's items by title when the shopper states a gender); with `1.25` nothing seen would be dropped. Left off, to avoid a way for the store to fail (every record is dropped if Shopify stops sending `price_min`). A test pins the facts; if add-ons ever appear, set `1.25`.
- **Gender: `gender_fields` stays at the default** `[type, tags]`. `type` is empty, "Dress" or "set" and `tags` is empty on every record, so no field names a gender and all 21 products come out with an unknown gender. `genders: [women]` in the store file carries it.
- Pin the host `herhighnessq8.com`. Build the link from the host plus `/products/{handle}` (the `url` field) and drop the tracking query. **Handles do not match titles:** "Crystal Black" is `/products/new2-mar-6`, "Kids Olive Kaftan" is `/products/untitled-nov22_19-25` and the piece titled "2" is `/products/2-1`. Always use `url` or `handle`.
- `name_field` stays `title` (`vendor` is the brand on every record, not a product name).
- Categories: dresses only (see "Fields available" and the note). 14 of the 21 are daraas, kaftans or dresses.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes, but often only a name | `title` ("Aura Dress", "Plum Kaftan", but also "Crescent", "Crystal Black" and "2"); one has a double space ("Kids Olive  Kaftan") |
| price | yes | `price`, a string with three decimals (`"45.000"`); `compare_at_price_max` is the pre-sale price when above `price` (3 of 21: "Plum Kaftan" `"48.000"` against `"42.000"`, "Burgundy Kaftan" and "Olive Garden" `"39.500"` against `"36.500"`), else `"0.000"` |
| currency | not in the response | KWD is store-level: `priceCurrency: "KWD"` on all 21 offers of the product JSON-LD, `og:price:currency` `KWD`, `Shopify.currency` `{"active":"KWD","rate":"1.0"}`, `Shopify.country` `"KW"` |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0695/4631/1733/files/...?v=...` (`.jpg` and `.png`) |
| product URL | yes | `url` (relative, with `?_pos=..&_psq=..&_psid=..&_ss=e` tracking) or build from `handle` |
| in stock | yes, product level | `available` (true for 21 of 21); all 21 offers of the sampled page are InStock |
| colour | partly | in some titles ("Burgundy Kaftan", "Plum Kaftan", "Crystal Black", "Brown Mist Dress") and not in others |
| category | no | `type` is empty on 17 of 21 ("Dress" 3, "set" 1); the title holds a garment word the ranker knows on 10 of 21 ("Dress", "Kaftan", "Top" and, since the lexicon learned it, "Dara'a") |
| gender | no | not a field (`type` and `tags` name none) |
| variants | no | `variants` is an empty list on all 21 |

## Hosts

- Store host (product links): `herhighnessq8.com`.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0695/4631/1733/files/` on all 21 records. The product page's own JSON-LD and `og:image` point at `herhighnessq8.com/cdn/shop/files/...` instead (the store's own host); search results use the CDN host.
- Candidate `allowed_hosts`: `herhighnessq8.com`, `cdn.shopify.com`.
- An Arabic version exists at `/ar/` (hreflang `ar` on the product page; not requested).

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "45.000"`, `"price": "46.800"`, `"price": "38.750"`, `"price_max": "37.000"`, `"compare_at_price_max": "48.000"`, `"compare_at_price_max": "0.000"`.
- Product JSON-LD: `"price": "35.0"` (a string), `"priceCurrency": "KWD"`; `<meta property="og:price:amount" content="35.00">`.
- Observed over 21 distinct handles, field `price`: **KWD 28.5 to 85, median 45.** The adult pieces (without the four girls' ones) are KWD 35 to 85, median 45. At the project's fixed rate (1 KWD = 11.92 AED, `config/settings.yaml`): about **AED 340 to 1,013, median 536**; adult pieces about AED 417 to 1,013. Dresses KWD 45 to 55, kaftans KWD 36.5 to 42, the suits KWD 50 to 58, the dearest ("2") KWD 85.

## Currency / tier hint

**KWD** (not AED). Tier: **mid range** at the converted level (median about AED 536). It sits at the level of Manal Smaoui (KWD 29 to 85) and of Signature Studio (median AED 589), below Hamsa (AED 660 to 4,400) and above Nishat Linen UAE.

AED storefront: none found. The product page has a footer currency-converter widget that lists KWD, SAR, AED, QAR, BHD, OMR, JOD, IQD, LBP and EGP. Its script computes the other prices in the browser from rates it fetches from a third-party rates API (named in the page script; not requested, not acted on). It is a display tool: the server-rendered prices, the JSON-LD and the Open Graph tags are KWD, and the search answer is KWD.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| daraa | `https://herhighnessq8.com/search/suggest.json?q=daraa&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: "Dara'a 2026" (35), "Beige strips Sets" (46.8), "Sahara Oversized Top" (38.75), "Crystal Dark Beige" (50), "Aura Dress" (55), "Desert Palm Luxury" (40), "Ivory Glow Dress" (45), "2" (85), "Pearl Dress" (45), "Brown Mist Dress" (45). Only one title has "Dara'a" in it |
| kaftan | `https://herhighnessq8.com/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: "Burgundy Kaftan" (36.5, was 39.5), "Plum Kaftan" (42, was 48), "Kids Olive Kaftan" (28.5), "Kids Burgundy Kaftan" (28.5), "Olive Garden" (36.5, was 39.5) and five repeats of the daraa answer ("Desert Palm Luxury", "Pearl Dress", "Brown Mist Dress", "Ivory Glow Dress", "Dara'a 2026"). 5 new |
| abaya | `https://herhighnessq8.com/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: "Crescent" (48), "Crystal Black" (50), "Royal Midnight Full set" (58), "Crescent Kids" (35 to 37), "MZIANA – Moroccan" (55), "MZIANA – Moroccan Kids" (40 to 43) and four repeats ("Beige strips Sets", "Olive Garden", "Dara'a 2026", "Aura Dress"). 6 new. **No title contains "abaya"** |

## Requests made

6 (2 for robots.txt, 3 searches, 1 product page), all on 2026-10-08, through Cloudflare WARP. No redirects. Fewer than the script's cap of 12.

## Sample

`docs/store-qualification/samples/her-highness-q8/`

- `suggest-daraa.json`, `suggest-kaftan.json`, `suggest-abaya.json`: the first 4 of the 10 products of the real response, same structure; each `body` string cut to 300 characters.
- `robots.txt`: the file as served.
- No `product-jsonld.json` was saved (it is optional in the guide).

The offline test fixtures (`tests/stores/her-highness-q8/fixtures/`) hold all 10 products of each answer, with each `body` cut to 300 characters.

## Risks and fragility

- **Many titles name no garment** (11 of 21): the ranker can read a category only from a garment word, so these products have none and pass the category filter for any dresses search. Three of them are suits by their description, and "Crystal Black" is the second result for `abaya`. The adapter cannot read the description (`body` is store-supplied HTML and is never used), so a shopper asking for an abaya or a daraa may be shown a blazer-and-trousers suit.
- **Four girls' pieces are the cheapest in the store** (KWD 28.5 to 40). The ranker drops children's items by title only when the shopper has stated a gender; otherwise they stay and sit at the low end of the price range.
- **The store pads its answers:** no title in the `abaya` answer has "abaya" in it; `daraa` returns one "Dara'a" among nine other pieces. Ranking must filter by category and text, not trust the store's order.
- Size surcharges on girls' pieces (35 to 37, 40 to 43): shown at the smallest size. If add-on variants appear, set `max_price_spread` (see above).
- `body` is store-supplied HTML in Arabic (right-to-left markup) and English; never render it. `url` carries tracking parameters; do not link to them.
- A footer currency widget exists; if the store ever serves another currency from the same host, the response has no currency and prices would be silently wrong. The file pins the host and KWD.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint; review before real users. A theme or template change could close `/search`.
- Handles do not match titles; `type` is mostly empty, `tags` and `variants` are empty.
- Single brand: daraas, kaftans, dresses and suits; nothing for shoes.

## Not verified / limits

- **Network.** All requests were sent on 2026-10-08 between about 14:07 and 14:14 local time (PKT) by the orchestrator with `scripts/qualify_store.py` (User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first, at least 1 s apart, one store at a time). From about 13:00 the machine's own network path to Shopify's addresses timed out on connect (no refusal was ever received; a Cloudflare Community thread reports the same kind of time-out from Pakistani providers that week). The user then enabled Cloudflare WARP on the machine and the requests went through it. The User-Agent and every other rule were unchanged, and no store answered with a refusal. **Behaviour from the machine's own network is untested.**
- No request was made by the author of this report; it was written from the saved files only.
- Not tested: the HTML search page, `limit` above 10, pagination, the `/ar/` market, queries for `dress`, `abaya` in Arabic, `blazer`, `suit` or `trousers`, the rest of the catalogue, per-size stock, the shop's terms of use.
- Not verified: that the three suits are suits (the evidence is the Arabic description, read as data); what "Beige strips Sets", "2" and "MZIANA – Moroccan Kids" are (empty descriptions).
- Not checked: whether `cdn.shopify.com` serves the `width=400` image to the honest client (no image was fetched).
