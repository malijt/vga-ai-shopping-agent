# Shadow (Shadow KW) qualification (2026-10-08)

**Verdict:** GO, with a currency flag and a padding caveat. The honest client received title, price, image URL and product URL (plus availability) for 26 distinct products over four searches, from Shopify's public `/search/suggest.json`, and `robots.txt` leaves that path open (checked with protego). 20 of the 26 are abayas (all `type` "ABAYA SET", KWD 39 to 180); the other 6 are sheilas and taqiyah caps, which are accessories and out of scope. Every price is in **Kuwaiti dinars (KWD)** with three decimals, so it needs the fixed rate of ADR 0006 and the Kuwait country entry, both already in `config/settings.yaml`. Unlike Hamsa, no record has variants at different prices, so no price guard is needed. Two caveats: the store sells no kaftan and no dress (a `kaftan` or `dress` search returns mostly sheilas and caps), and the ranker's word list does not yet recognise the store's spellings "Shaila" and "Taqiyah" as accessories. At the converted level the abayas run about AED 465 to 2,146 (median about AED 703), and 6 of the 20 are under AED 600, a thin spot the README names.

## Storefront

- Store: Shadow KW, `https://shadow.com.kw/` (the bare domain answered directly, no redirect; `www.` was never requested). Shopify shop `shadow-kw.myshopify.com`. A Kuwaiti abaya label; "founded 2008" comes from press and was **not verified** by us.
- **How it is known to be the brand's own shop.** The product page carries an `Organization` JSON-LD block named "Shadow KW" with `url` `https://shadow.com.kw`, an Instagram account `shadowabayakw` and a Snapchat account `shadowabayaq8`; the product's `brand` is "Shadow KW"; the page title is "Sumou Abaya (Linen) – Shadow KW"; `vendor` is "Shadow" (22 of 26 records), "Shadow KW" (3) or "SHADOW" (1). Single brand.
- Platform: Shopify. Evidence: `robots.txt` opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, all 26 images are on `cdn.shopify.com`, `/search/suggest.json` answers in Shopify's predictive-search shape, and the product page carries `Shopify.shop`, `Shopify.theme` (a "minimog" 5.5.0 theme), `Shopify.currency` and `myshopify.com`.
- Assortment seen in 34 search records (26 distinct handles): `type` "ABAYA SET" 20 distinct (25 records), "SHEILA" 4 distinct (7 records), "ACCESSORIES" 2 (2 records, both taqiyah caps). Women's garments by nature of the range; **no field names a gender** (`tags` hold only "ABAYA SET", "SHEILA" and "tag__new_new"). No kaftan, dress, shoes, trousers, tops or jackets appeared.
- **An abaya here is a set with a sheila.** The descriptions of 16 of the 20 abaya records say the set has a sheila: 12 read "Abaya set has sheila included" (or the same with "SHAILA"), and 4 say it in other words (for example "with sheila"). The other 4 have an empty or one-line description that names none. So the price is the set's. The sheilas also sell on their own as separate records (KWD 13 to 19), which is why this is not the Hamsa trap (a scarf priced as a variant of an abaya). One "abaya" (BEIGE LINEN TRENDY OPEN ABAYA, KWD 62) is described as "A BLAZER SET WITH PANT AND TOP".
- Titles are mostly capitals, with the store's own spelling slips ("TRIBPLE", "GEOMERTIC EMBROIDEREY", "Sepcial") and double spaces. Handles are style codes ("sh11260126021"), not words.
- **Markets.** The product page's head lists 465 language and country alternates: 231 country codes in English at the unprefixed path, the same 231 in Arabic under `/ar/`, and three entries (`x-default`, `ar`, `en`) under `/ar-kw/` and `/en-kw/`. So Kuwait has its own prefixed paths, while the unprefixed path (the one this report qualified, and the page's `en-AE` alternate) serves the other countries. `Shopify.country` read "US", which is the visitor's market as Shopify saw it, not the store's. See "Risks and fragility".

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`). The stdlib `urllib.robotparser` was not used.
- Fetched from `https://shadow.com.kw/robots.txt`: 200, 3,620 bytes, no redirect, three times (once per run of the script), always the same size. It is Shopify's current default file: identical to Hanayen's, apart from the host name and the shop id line (`Disallow: /90362249463`). The saved copy in `tests/stores/shadow-kw/fixtures/` and in the samples folder is byte for byte the file served.
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
  (Each of these also has a `/*/...` twin for localised paths.) The group also closes `/services`, `/sf_*` and `/cdn/wpm/*.js`. A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search` or `/search/suggest.json`**; they are covered by `Allow: /`. Protego result with the qualification User-Agent, run offline over the saved file: ALLOW for the `abaya` and `black abaya` suggest URLs, the product page, `/search?q=abaya` and `/collections/all`; DISALLOW for `/cart/`, `/cart.js`, `/checkout`, `/account` and `/recommendations/products`. (Only the suggest URLs and the product page were requested; the other addresses were checked offline against the saved file and not fetched.)
- Sitemap: `https://shadow.com.kw/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data: "Agents should use UCP/MCP for catalog, cart, and checkout." It also names `https://shadow.com.kw/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for humans and must not be completed automatically, points to a third-party shopping skill at `https://shop.app/SKILL.md`, and gives a contact address for bots. These are comments, not robots rules. **Not acted on:** none of those addresses was requested, nothing was installed, and the cart and checkout were never touched. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://shadow.com.kw/robots.txt` | 200 | 3620 | 0.9 s | text/plain |
| 2 | `https://shadow.com.kw/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 13067 | 0.5 s | application/json, 10 products |
| 3 | `https://shadow.com.kw/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 6631 | 0.3 s | 9 products |
| 4 | `https://shadow.com.kw/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 3706 | 0.3 s | 5 products |
| 5 | `https://shadow.com.kw/robots.txt` | 200 | 3620 | 0.5 s | second run, for the product page |
| 6 | `https://shadow.com.kw/products/sh11260126021` | 200 | 935578 | 1.2 s | the one product page (JSON-LD check) |
| 7 | `https://shadow.com.kw/robots.txt` | 200 | 3620 | not recorded | third run, for the extra query; the size is that of the saved file |
| 8 | `https://shadow.com.kw/search/suggest.json?q=black%20abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 13829 | 0.3 s | 10 products |

No challenge page, CAPTCHA or login wall, no redirects. Response headers were not recorded. All eight requests went through Cloudflare WARP (see "Not verified / limits").

## Search URL template

`https://shadow.com.kw/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`; a space in the query becomes `%20`.) 10 asked for; 10, 9, 5 and 10 received, so `kaftan` and `dress` came back short because the store had nothing else to match. Larger limits and pagination were not tested.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and an empty `variants` list. The product page carries one `Product` JSON-LD block with 54 `Offer` entries (one per variant), each with `price` `69.0`, `priceCurrency` `"KWD"` and `InStock`.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the 13 current stores. Store-specific points:

- **Currency is KWD** (same as Bazza Alzouman, Hamsa and Manal Smaoui): `"69.000"` is accepted only because the store file says KWD (ADR 0006), and the fixed rate in `config/settings.yaml` gives the approximate dirham figure. Nothing new is needed in `src/`.
- **No price guard.** `price`, `price_min` and `price_max` are equal on all 34 records (26 distinct products), and the `variants` list is empty, so the check rests on those two fields and on the one product page (54 offers, all KWD 69). If a record ever shows two prices, add `max_price_spread` (guide section 6c, ADR 0012).
- Pin the host `shadow.com.kw`. Build the link from the host plus `/products/{handle}`; drop the tracking query (`?_pos=1&_psq=abaya&_psid=...&_ss=e`). Handles are style codes, so always use `url` or `handle`.
- `type` is "ABAYA SET" on every garment and "SHEILA" or "ACCESSORIES" on the rest. It is consistent here, but it names no gender; the title decides the category.
- **Sheilas and caps are accessories** (out of scope) and come back for `kaftan` and `dress` queries. The adapter does not drop them; see "Risks and fragility" for what the ranker's word list does with them today.
- There is no gender field; the range is women's.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` (for example "Sumou Abaya (Linen)", "BLACK EMBROIDERED SOALON CLOSE ABAYA") |
| price | yes | `price`, a string with three decimals (`"69.000"`); `compare_at_price_max` is `"0.000"` on 20 of 26 distinct products, equal to the price on 5 and KWD 75 on one abaya that costs KWD 129. It is never above the price, so there is no strike-through discount in this data |
| currency | not in the response | KWD is store-level: `priceCurrency: "KWD"` on all 54 offers of the product JSON-LD, `Shopify.currency` `{"active":"KWD","rate":"1.0"}`. `Shopify.country` read `"US"` (the visitor's market) |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0903/6224/9463/files/...jpg?v=...`. The product page's JSON-LD image is on the store host (`https://shadow.com.kw/cdn/shop/files/...`); search results are not |
| product URL | yes | `url` (relative, with tracking query) or build from `handle` |
| in stock | yes, product level | `available` (true for 34 of 34 records); all 54 variant offers of the sampled abaya are InStock |
| colour | partly | in most titles ("BLACK ...", "BEIGE ...", "GREY ...", "Abaya Black Crepe") |
| gender | no | not a field |

## Hosts

- Store host (product links): `shadow.com.kw`.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0903/6224/9463/files/` on all 26 distinct records.
- Candidate `allowed_hosts`: `shadow.com.kw`, `cdn.shopify.com`.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "69.000"`, `"price_max": "69.000"`, `"compare_at_price_max": "0.000"`, `"compare_at_price_max": "75.000"` (on a record whose `price` is `"129.000"`).
- Product JSON-LD: `"price" : 69.0`, `"priceCurrency" : "KWD"` (a number here, a string in the search JSON).
- Observed over 26 distinct handles, field `price`: **KWD 4 to 180, median 57**. Abayas (20): **KWD 39 to 180, median 59** (39, 39, 45, 45, 49, 49, 55, 59, 59, 59, 59, 62, 63, 65, 68, 69, 78, 89, 129, 180). Sheilas (4): KWD 13, 16.9, 18.9 and 19. Taqiyah caps (2): KWD 4 and 5. At the fixed rate of 11.92 AED per KWD (`config/settings.yaml`): abayas about AED 465 to 2,146, median about AED 703; sheilas about AED 155 to 226; caps about AED 48 and 60.

## Currency / tier hint

**KWD** (not AED). Tier: **mid_range**. The abayas' median of about AED 703 sits near Signature Studio (median AED 589) and Manal Smaoui (about AED 350 to 1,010), both mid_range, and under Hanayen (median AED 1,290) and Hamsa (cheapest abaya about AED 890), both premium. 16 of the 20 abayas are at or below KWD 69 (about AED 822) and only 2 are above KWD 100 (129 and 180), so the top of the range is thin. This store does fill the README's "abayas below about AED 600" spot: 6 of the 20 abayas (KWD 39, 39, 45, 45, 49, 49) are under it (3 of those 6 are described as sets with a sheila; the other 3 have no description of that kind).

AED storefront: none seen. The unprefixed path reported KWD for a visitor classed as "US"; whether a visitor from the UAE would be shown dirhams was not tested.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| abaya | `https://shadow.com.kw/search/suggest.json?q=abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all abayas (KWD 39 to 180); two of them are the same title at KWD 59 under two handles |
| kaftan | `https://shadow.com.kw/search/suggest.json?q=kaftan&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 9: 4 sheilas (KWD 13 to 19), 2 taqiyah caps (KWD 4 and 5), 3 abayas (KWD 39, 49, 55); no kaftan as a garment |
| dress | `https://shadow.com.kw/search/suggest.json?q=dress&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 5: 3 sheilas (KWD 16.9 to 19), 2 abayas (KWD 49 and 55), all five also in the `kaftan` answer; no dress as a garment |
| black abaya | `https://shadow.com.kw/search/suggest.json?q=black%20abaya&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10, all abayas (KWD 39 to 89); three of them also in the `abaya` answer, and a title that repeats at KWD 59 |

In total 34 records, 26 distinct handles; through the project's own extraction chain 32 are valid (2 repeat an earlier title and price in the same answer) and 24 are distinct once a product that answers two queries is counted once.

## Requests made

8 (3 for robots.txt, one per run of the script; 4 searches; 1 product page). No redirects.

## Sample

`docs/store-qualification/samples/shadow-kw/` (filled by the orchestrator, not edited here)

- `suggest-abaya.json`, `suggest-kaftan.json`, `suggest-dress.json`, `suggest-black-abaya.json`: the first products of the real response, same structure, each `body` cut to 300 characters.
- `robots.txt`: the file as served.
- The fuller, full-answer copies used by the tests are in `tests/stores/shadow-kw/fixtures/`.

## Risks and fragility

- **Padding with accessories, and the ranker's word list.** A `kaftan` or `dress` query returns 6 and 3 accessories (sheilas and taqiyah caps). When the store was qualified the ranker dropped the words "sheila" and "shayla" as accessories but not "shaila" (the spelling on all 4 of the store's sheilas) and not "taqiyah", so those titles had no category and were kept for every request (ADR 0007). Both words were added to `OUT_OF_SCOPE_WORDS` in `src/vga/rank/lexicon.py` on 2026-10-08, in the same change as this store, and a test in `tests/stores/shadow-kw/` pins it. A new spelling would come through again: the adapter has no rule of its own. An `abaya` or `black abaya` query was never affected (10 of 10 abayas each).
- **Currency by visitor market.** The unprefixed host reported KWD to a visitor Shopify classed as "US", and the page lists Kuwait-specific prefixes (`/en-kw/`, `/ar-kw/`). The store file pins the unprefixed host and KWD. If the store shows dirhams or another currency to a visitor in another country, prices would be silently wrong (the search response has no currency). Re-check the product-page JSON-LD from the network that will be used.
- **A different catalogue per market** is possible on Shopify; only the unprefixed path was searched, and `/en-kw/` was not.
- Single brand: abayas (as sets with a sheila), sheilas and caps; nothing for tops, outerwear, bottoms or shoes. No kaftan or dress was found, so a kaftan or dress shopper gets abayas.
- Titles repeat under several handles (a title at the same price twice in one answer is collapsed; the same title at KWD 59 and 63 is two products). `vendor` has three spellings. All prices are plain (no discounts), so the budget band does not move when a sale ends.
- A "blazer set with pant and top" is titled and filed as an abaya, so the ranker will read it as a dress.
- `body` is store-supplied HTML (up to 806 characters here); never render it. `url` carries tracking parameters; do not link to them.
- The `robots.txt` asks agents to prefer the store's UCP/MCP endpoint; review before real users. A template change could close `/search` (the older Shopify default does).

## Not verified / limits

- **Network path.** All requests were sent on 2026-10-08 between about 14:07 and 14:14 local time (PKT) by the orchestrator with `scripts/qualify_store.py` (User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, `robots.txt` first, at least 1 s apart, one store at a time). From about 13:00 the machine's own network path to Shopify's addresses timed out on connect (no refusal was ever received; a Cloudflare Community thread reports the same kind of time-out from Pakistani providers that week). The user then enabled Cloudflare WARP on the machine and the requests went through it. The User-Agent and every other rule were unchanged, and no store answered with a refusal. **Behaviour from the machine's own network is untested.**
- "Founded 2008" is from press and was not checked.
- Pagination and `limit` above 10; the HTML search page; the `/en-kw/` and `/ar-kw/` paths.
- Whether a visitor from another country is shown another currency (see Risks).
- Per-variant stock (only the product-level `available` and the 54 offers of one product were seen).
- Whether `cdn.shopify.com` serves the `width=400` image to the honest client (no image was fetched).
- Whether "ABAYA SET" always includes a sheila: 16 of 20 descriptions say so, the other 4 do not mention it.
- Terms of use.
