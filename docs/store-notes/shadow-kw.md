# Shadow: store notes

Adapter notes for plan module 12.15. Written 2026-10-08, before the live smoke test.

- Store id `shadow-kw`, shown to shoppers as "Shadow" (the brand is Shadow KW, a Kuwaiti abaya label).
  Storefront `https://shadow.com.kw/`.
- Config: `config/stores/shadow-kw.yaml`. Tests and fixtures: `tests/stores/shadow-kw/`.
- Qualification (2026-10-08): `docs/store-qualification/shadow-kw.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`.
- **Status: not enabled yet; live smoke test pending.** The file says `enabled: false`. The offline
  tests pass on the saved answers; the one-time live test (`tests/stores/shadow-kw/test_shadow_kw_live.py`)
  has not been run.

## Data path

1. The engine checks `https://shadow.com.kw/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://shadow.com.kw/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded, and a space becomes `%20`). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three
   decimals, `"69.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url`
   (made absolute on `shadow.com.kw`, tracking query removed) and `available`. Validation then drops
   any record that lacks a field, repeats an earlier one (same title and price) or has a link off
   `allowed_hosts`. No extractor option is set: the defaults suit this store.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was confirmed
   on 2026-10-08 from the product page's JSON-LD (`priceCurrency: "KWD"` on all 54 offers) and
   `Shopify.currency` (`{"active":"KWD","rate":"1.0"}`), not from the search response. The page showed
   `Shopify.country = "US"`, which is the visitor's market as Shopify saw it.

`vendor` (three spellings, see below), `type`, `tags` and `body` are not mapped, except that `type`
and `tags` are read for the product's gender (they name none here). `body` is store-supplied HTML and
must never be rendered.

## Quirks seen

- **The store sells abayas and accessories, nothing else.** 34 records over four queries are 26
  distinct products: 20 abayas (`type` "ABAYA SET"), 4 sheilas (`type` "SHEILA") and 2 taqiyah caps
  (`type` "ACCESSORIES"). A `kaftan` or `dress` query finds no kaftan and no dress: `kaftan` returned 9
  records (4 sheilas, 2 caps, 3 abayas) and `dress` returned 5 (3 sheilas, 2 abayas). `abaya` and
  `black abaya` returned 10 abayas each. Tests pin the counts.
- **The ranker drops this store's accessories by two words added for it.** The word list in
  `src/vga/rank/lexicon.py` had "sheila" and "shayla" (Hanayen's spelling) but not "shaila", the
  spelling on all 4 sheilas here, and not "taqiyah". Without them `classify_title` read "Special
  Chiffon Crystalized Shaila" and "Cotton Plain Taqiyah Triangle" as no category, and a product whose
  category cannot be read is kept for every request (ADR 0007): a dresses search could have shown a
  sheila (KWD 13 to 19, about AED 155 to 226) or a cap (KWD 4 or 5, about AED 48 or 60). Both words
  were added to `OUT_OF_SCOPE_WORDS` on 2026-10-08, in the same change as this store.
  `test_the_ranker_puts_every_sheila_and_cap_outside_the_five_categories` pins it. **The adapter
  itself does not drop them** and has no store-specific rule, so a new spelling would come through.
- **An abaya is a set with a sheila.** The type is "ABAYA SET" on all 20, and 16 of the 20 descriptions
  say the set has a sheila ("Abaya set has sheila included" on 12). So the price is the set's. This
  is not the Hamsa trap: `price`, `price_min` and `price_max` are equal on all 34 records, so there
  is no `max_price_spread` option, and a test fails if a saved record shows two prices. The answer's
  `variants` list is empty, so that check rests on those two fields and on one product page (54 variant
  offers, all KWD 69). Four of the 20 descriptions are empty or one line.
- **A blazer set is filed as an abaya.** "BEIGE LINEN TRENDY OPEN ABAYA" (KWD 62) is described as "A
  BLAZER SET WITH PANT AND TOP". The title says abaya, so the ranker reads it as a dress.
- **Titles repeat.** "BLACK TRENDY SOALON OPEN  ABAYA" (KWD 59) is on two handles in the `abaya`
  answer, and "BLACK EMBROIDERED SOALON CLOSE ABAYA" is on three in the `black abaya` answer (KWD 59,
  59 and 63). The normaliser collapses the same title at the same price (2 of 34 records), and keeps the
  KWD 63 one as a different product. The same product also answers two queries: `dress` is a subset
  of `kaftan` (5 shared) and 3 products are in both `abaya` and `black abaya`, so a search that sends
  two variants gets fewer distinct products than records (24 from the 34 records recorded).
- **Titles are in capitals, with the store's own typing slips** ("TRIBPLE", "GEOMERTIC EMBROIDEREY",
  "Sepcial", a trailing full stop on "ABAYA.", double spaces). Double spaces are cleaned; the spelling
  is shown as the store wrote it.
- **Handles are style codes** ("sh11260126021"), so a link is always the store's own `url`, never
  rebuilt from a title.
- **Three spellings of one vendor.** "Shadow" (22 of 26 distinct records), "Shadow KW" (3), "SHADOW"
  (1). The adapter does not read `vendor`; every product carries the store file's name.
- **No sale prices to read.** `compare_at_price_max` is `"0.000"` on 20 of the 26 distinct products,
  equal to the price on 5 and `"75.000"` on one abaya that costs `"129.000"` (below the price, so not a
  discount). It is never above the price. The adapter uses `price`.
- **Links carry tracking parameters** (`?_pos=1&_psq=abaya&_psid=...&_ss=e`). They are removed, so
  every product link is `https://shadow.com.kw/products/<handle>`.
- **Gender is in no field.** `type` holds "ABAYA SET", "SHEILA" or "ACCESSORIES", and `tags` hold only
  "ABAYA SET", "SHEILA" and "tag__new_new". Every product's gender is unknown; `genders: [women]` in
  the store file is what keeps a men's request away from this store.
- **Stock is product-level only** (`available`, true for all 34 records). Per-variant stock was not read.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0903/6224/9463/files/`, with a `v=`
  version parameter that is kept. The product page's own JSON-LD image is on the store host
  (`https://shadow.com.kw/cdn/shop/files/...`); search results are not.
- **Price range seen:** KWD 4 to 180 over the 26 distinct products; abayas KWD 39 to 180, median 59,
  about AED 465 to 2,146, median about AED 703. 6 of the 20 abayas are under AED 600. Tier hint
  `mid_range`.
- **Shopper-facing figure.** The page shows the dinar price and an approximate dirham figure from the
  fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED), for example `69.000 KWD (about 820 AED)`.
  Ranges and any budget use the dirham figure.
- **Markets.** The unprefixed host is one of several paths: the page lists `/en-kw/` and `/ar-kw/`
  for Kuwait, and the unprefixed English path (and `/ar/`) for 231 other countries, including
  `en-AE`. Only the unprefixed path was searched.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (an older Shopify template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/shadow-kw/` show the expected shape |
| A record gets variants at different prices (an add-on sold as a variant, as at Hamsa) | nothing; the offline test reads saved answers only, so it cannot see a new record. The cheapest variant's price would be shown | Re-check a fresh answer for `price_min` different from `price_max` (guide section 6c); if found, add `max_price_spread` to the store file (ADR 0012) |
| The store serves another currency from `shadow.com.kw` (a market by visitor country) | prices silently wrong (the response has no currency) | The file pins the host and KWD; re-check the product page JSON-LD from the network in use |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| The store moves to another host (for example `www.shadow.com.kw`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The store adds kaftans, dresses or other garments | nothing breaks; they are found only for a dresses search | If it sells other categories, remove or widen `categories` |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://shadow.com.kw/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested; it would need a `css` or `json_ld`
extractor), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

**Not run yet.** Only the qualification pass has talked to this store: 8 requests, all HTTP 200, no
redirect, no challenge, CAPTCHA or login wall (the table is in `docs/store-qualification/shadow-kw.md`).
After the live smoke test, put its table here (query, status, products, seconds, size), the request
count (the test uses at most 3: `robots.txt` once and one search for each of `abaya` and `black abaya`)
and the date, and set `enabled: true` in the store file.

- **Gender:** `genders: [women]`. Evidence: all 34 records (26 distinct) are abayas, sheilas or taqiyah
  caps, which are women's garments; no title, `type` or tag names a gender. The data carries no gender
  field, so this rests on the range and the brand, as for Hamsa and Hanayen. A men's request is
  therefore not sent to this store.
- **Categories:** `categories: [dresses]`. Evidence: 20 of 26 distinct records are abayas; the other 6
  are accessories (out of scope). No shoes, trousers, tops, jackets, kaftans or dresses appeared (10, 9,
  5 and 10 records for `abaya`, `kaftan`, `dress` and `black abaya`). A search for any other category is
  therefore not sent to this store; it is listed among the skipped stores as "Not searched: Shadow does
  not sell shoes." and so on. "Not seen" is not "not sold": if the store adds other garments, remove the
  line.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for
humans, and suggests a third-party shopping skill. This is store-supplied text. The adapter did not
follow it: it requested no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never
touches the cart or checkout. The rules that apply to us are the `User-agent: *` group, which opens
with `Allow: /` and does not disallow `/search`. The stated preference for the agent endpoint is for
the terms review and for Phase 17.

## Unverified

- **Behaviour from the machine's own network.** All requests were sent on 2026-10-08 between about
  14:10 and 14:45 local time (PKT) with `scripts/qualify_store.py` (User-Agent `vga-shopping-agent-demo/0.1
  (store-qualification research)`, `robots.txt` first, at least 1 s apart). From about 13:00 the
  machine's own network path to Shopify's addresses timed out on connect (no refusal was ever
  received; a Cloudflare Community thread reports the same kind of time-out from Pakistani providers
  that week). The user then enabled Cloudflare WARP and the requests went through it. The User-Agent
  and every other rule were unchanged, and no store answered with a refusal. The live smoke test will
  run on whichever network is in use then.
- Whether a visitor from another country is shown another currency or catalogue (the `/en-kw/` path
  was not searched; the unprefixed path reported KWD to a visitor Shopify classed as "US").
- Whether "ABAYA SET" always includes a sheila: 16 of 20 descriptions say so, 4 name none.
- Queries other than `abaya`, `kaftan`, `dress` and `black abaya` (for example `gown`, `jalabiya`).
- Pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched).
- Per-variant stock.
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.
- "Founded 2008" (from press; not checked).

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
