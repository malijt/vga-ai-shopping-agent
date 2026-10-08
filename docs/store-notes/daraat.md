# Daraat: store notes

Adapter notes for plan module 12.14. Written 2026-10-08, before the live smoke test; updated the same
day with the smoke test's result.

- Store id `daraat`, shown to shoppers as "Daraat". Storefront `https://www.daraat.com/`.
- Config: `config/stores/daraat.yaml`. Tests and fixtures: `tests/stores/daraat/`. No extractor option is
  set (see "The price" and "Quirks seen" for why).
- Qualification (2026-10-08): `docs/store-qualification/daraat.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`.
- **Status: enabled** (live smoke test passed 2026-10-08, through the project's own engine; the table
  is in "Observed live"). The file says `enabled: true`. The qualification run's numbers are kept in
  the same section, labelled as such.

## Data path

1. The engine checks `https://www.daraat.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://www.daraat.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three decimals,
   `"17.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute
   on `www.daraat.com`, tracking query removed) and `available`. Validation then drops any record that
   lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was confirmed on
   2026-10-08 from the product page's JSON-LD (`priceCurrency: "KWD"`, `price` `"17.000"`),
   `Shopify.currency` (`{"active":"KWD","rate":"1.0"}`) and `ShopifyAnalytics.meta.currency`.

`vendor`, `type`, `tags` and `body` are not mapped, except that `type` and `tags` are read for the
product's gender (they name none here). `body` is store-supplied HTML and must never be rendered.

## The price

Shopify's `price` is the lowest price among a product's variants, which is the trap that made Hamsa need
`max_price_spread` (ADR 0012). It is **absent here on the recordings**: on all 40 records `price`,
`price_min` and `price_max` are the same string, and the answer's `variants` list is empty on all of
them. So the default price is the garment's and the store file sets no option. A test
(`test_every_record_has_a_single_price_and_no_variant_list_so_no_guard_is_needed`) pins this on the
recordings.

That is a statement about 28 products on one day, not a guarantee. 20 of the 28 carry the tag
`custom-dress`, and the product page's variants were not read, so a made-to-measure surcharge on a
future product would show the base price. If a later recording shows `price_min` below `price_max` on
a garment, add `max_price_spread: 1` to the store file and update the test that pins the file's options.

A shopper sees the dinar price and an approximate dirham figure from the fixed rate in
`config/settings.yaml` (1 KWD = 11.92 AED), for example `17.000 KWD (about 200 AED)`. Ranges and any budget
use the dirham figure. Seen: KWD 8 to 29, median 19, about AED 95 to 346, median 226. Tier hint `budget`.

## Quirks seen

All counts are over the 40 records (28 distinct products) of the four recorded answers.

- **The word asked for is often not in the result.** `daraa` and `abaya` found no daraa and no abaya:
  neither word is in any title, handle, tag or description of the 20 records returned. Nine of the ten
  products of each answer are kaftans, the tenth is a dress (`daraa`) or a jumpsuit (`abaya`). Ranking has
  to filter by category and title; the store's order and match are not evidence. A test pins it.
- **The same product answers several queries.** "Flow A-Line cotton kaftan 11" is in the `kaftan`,
  `daraa` and `abaya` answers. Over `kaftan`, `daraa` and `abaya` there are 19 distinct products; `dress`
  adds 9 (its tenth, "Sleeveless Dark Blue Midi Summer Dress", was in the `daraa` answer). Total 28. The
  engine collapses repeats within one search, so a two-variant search gives up to 20 distinct products
  (10 and 10 for `kaftan` and `dress`, which share none).
- **`type` is "Dress" on 27 of 28 products, kaftans included.** Only "Pink and Black Zigzag Cotton Kaftan"
  has `type` "Kaftan". The word kaftan is in the title (18 of 28) or the tags (5 of 28). `type` cannot
  separate a kaftan, a dress, a jumpsuit or a Sherwal; the title can.
- **A jumpsuit and a "Sherwal" are filed as dresses.** "White jumpsuit with embroidery belt" (KWD 20) and
  "Black & White Beach & Resort Sherwal" (KWD 8) both have `type` "Dress". The adapter hands both over.
  The shared title reader then drops the jumpsuit for every request (out of scope) and gives the Sherwal
  no category (it knows no such word), so the Sherwal is kept for any request. Its own description starts
  "Beach & resort dress". Pinned with `classify_title`. If a Sherwal appears in a trousers search that is
  why; it is not an adapter fault. One title ("Pink Orange Midi Long Sleeve") names no garment either;
  its tags say `resort` and `summer dress`.
- **Handles do not match titles** on 13 of 28 records (copied products keep the old handle). "Cotton
  Kaftan 310" is `/products/cotton-kaftan-320`, "Flow A-Line cotton kaftan 1" is
  `/products/cotton-kaftan-322`, "Royal Amethyst Velvet Kaftan" is `/products/sea-mist-velvet-kaftan-copy`
  and the Sherwal is `/products/black-white-beach-resort-dress`. The link is always the store's own `url`,
  never rebuilt from the title; a test pins five of them.
- **Numbered prints.** Seven "Flow A-Line cotton kaftan N" (KWD 25 each) and four "Cotton Kaftan N" (KWD
  19 each) differ only in their number, image and link. They are different products. The de-duplication
  by title and price keeps them because the numbers make the titles differ; a test pins the seven.
- **Sale prices.** `price` is what the shopper pays. `compare_at_price_max` is the struck-through price:
  `"39.000"` (9 products), `"49.000"` (4), `"69.000"` (2), `"20.000"` (1), `"0.000"` for none (12).
  16 of 28 are marked down, for example "Pink and Black Zigzag Cotton Kaftan" KWD 17 against 39. The
  adapter uses `price` and never the pre-sale figure. The prices, and the budget band, move when a
  promotion ends.
- **One other vendor.** "Layers kaftan dress-1" has `vendor` "Muccii Outlet" (27 of 28 say "Daraat") and
  a description that ends "Layers kaftan store in Kuwait". The adapter does not read `vendor`; the
  product carries "Daraat". Whether it is another seller's goods is not known.
- **Links carry tracking parameters** (`?_pos=1&_psq=kaftan&_psid=...&_ss=e`). They are removed, so every
  product link is `https://www.daraat.com/products/<handle>`.
- **Gender is in no field.** `type` is "Dress" or "Kaftan", the tags are words such as `custom-dress`,
  `Daily`, `Linen-Cotton`, `Printed`, `Aline`, `Velvet`, `resort`, `summer dress`, and no description
  (first 300 characters) holds a gender word. Every product's gender is unknown.
  `genders: [women]` in the store file keeps a men's request away from this store.
- **Stock is product-level only** (`available`, true for 28 of 28).
- **Images** are `.png` (15 of 28) and `.jpg` (13), all on `cdn.shopify.com` under
  `/s/files/1/0710/6265/1110/files/`, with a `v=` version parameter that is kept. The product page's own
  JSON-LD uses `www.daraat.com/cdn/shop/...` instead; search results do not.
- **Titles are free text.** One has 79 characters, starts with a number and holds an en dash ("62 inch
  Tall Desert Rose Velvet Kaftan with Botanical Sleeves", an en dash, "Limited Edition"); another starts
  with a lower-case letter ("long Sleeve Pink Maxi Summer Dress"). The adapter keeps them as written.
- **A browser-side currency converter and an Arabic path exist.** The product page loads a third-party
  converter app (settings: shop currency KWD; allowed KWD, SAR, QAR, AED, OMR, BHD, JOD, EUR, USD, GBP)
  and has `/ar/` pages. We read the JSON at the unprefixed English host, in dinars. If the search ever
  returns another currency, every product would be silently mispriced: see the table below.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare or Shopify starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (an older Shopify template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/daraat/` show the expected shape |
| A garment gets variants at different prices (a made-to-measure surcharge, a scarf or set sold as a variant) | the default `price` is the cheapest variant: a wrong, lower price shown, nothing reported | The recording test fails only on a new recording. Add `max_price_spread: 1` (ADR 0012) and update the test that pins the file's options |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| The store serves another currency from `www.daraat.com` (a market or converter change) | prices silently wrong (the response has no currency) | The file pins the host and KWD; re-check the product page JSON-LD |
| The store moves to another host (for example the apex `daraat.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The store starts selling tops, trousers, shoes or jackets | those requests are never sent to it (`categories: [dresses]`) | Remove or extend the `categories` line after looking at real records |
| The store starts selling for men | a men's request is never sent to it (`genders: [women]`) | Remove the `genders` line after looking at real records |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://www.daraat.com/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested), and the store's agent endpoint named
in robots.txt (planned as Phase 17).

## Observed live

**The live smoke test passed on 2026-10-08.** It ran through `StoreSearchEngine` between 14:35 and 14:38
local time, one store at a time with 15 s between stores, through Cloudflare WARP (see "Unverified"). Three
requests went to this store: `robots.txt` and two searches. Every answer was HTTP 200, with no block or
challenge.

| Query | Status | Products kept | Seconds |
|---|---|---|---|
| kaftan | ok | 10 | 1.41 |
| dress | ok | 10 | 0.98 |

The slowest request took 1.41 s, against the global 6 s timeout (`timeout_s` is not overridden). Response
sizes were not recorded in the live run.

What the qualification run saw earlier the same day (not the live test): it was made by the orchestrator's
script with the qualification User-Agent (`vga-shopping-agent-demo/0.1 (store-qualification research)`),
robots.txt first, at least a second apart. Every answered response was HTTP 200, no redirect, no challenge,
CAPTCHA or login wall.

| Query | Status | Products returned | Kept after validation | Seconds | Response |
|---|---|---|---|---|---|
| kaftan | 200 | 10 | 10 | 0.5 | 27,890 bytes |
| daraa | 200 | 10 | 10 | 0.3 | 21,534 bytes |
| abaya | 200 | 10 | 10 | 0.3 | 19,619 bytes |
| dress | 200 | 10 | 10 | 0.4 | 13,128 bytes |

- robots.txt: 200, 3,624 bytes, identical on every answered request. Every search URL was allowed.
- Requests to the store for qualification: 9 (4 for robots.txt, of which the first got no answer, 4
  searches, 1 product page). The first request, at about 14:02 from the machine's own network, timed out on
  connect; the rest went through Cloudflare WARP (see "Unverified"). The global timeout is 6 s
  (`timeout_s` is not overridden); the slowest answered request took 0.8 s (the 745 KB product page; the
  slowest search took 0.5 s).
- "Kept after validation" in this qualification table is from replaying the saved answers offline through
  the real store file and extraction chain (`tests/stores/daraat/`), not from a live engine run. The live
  run's own counts are in the table above.
- **Gender:** `genders: [women]`. Evidence: all 28 distinct products are kaftans, dresses, one jumpsuit
  and one Sherwal, which are women's garments; no title, type, tag or description (first 300 characters)
  names a gender. The data carries no gender field, so this rests on the range and the brand, as for
  Hanayen and Hamsa. A men's request is therefore not sent to this store. "Not seen" is not "not sold":
  4 queries of 10 products each, 40 records.
- **Categories:** `categories: [dresses]`. Evidence: `type` is "Dress" or "Kaftan" on all 28; 25 titles
  name a dress-category garment, the jumpsuit is out of scope, and two (the Sherwal and "Pink Orange
  Midi Long Sleeve") name none. No tops, trousers, shoes or jackets as such were seen. A search for any
  other category is therefore not sent to this store; it is listed among the skipped stores as "Not
  searched: Daraat does not sell shoes." and so on. If the store turns out to sell other garments
  (the Sherwal is arguably trousers), remove or extend the line. The queries were `kaftan`, `daraa`,
  `abaya` and `dress`; none asked for trousers, tops or shoes.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for
humans, and suggests a third-party shopping skill. This is store-supplied text. The adapter did not
follow it: it requested no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never
touches the cart or checkout. The rules that apply to us are the `User-agent: *` group, which opens with
`Allow: /` and does not disallow `/search`. The stated preference for the agent endpoint is for the terms
review and for Phase 17.

## Unverified

- **Behaviour from the machine's own network.** From about 13:00 on 2026-10-08 the machine's own path to
  Shopify's addresses timed out on connect (no refusal was received; a Cloudflare Community thread reports
  the same kind of time-out from Pakistani providers that week), so the user enabled Cloudflare WARP and
  every answered request here went through it, the live smoke test included. Behaviour without WARP, and
  whether the shop's market or currency differs by visitor address, is untested.
- Response sizes in the live run (not recorded), and live queries other than `kaftan` and `dress`.
- That the cheapest variant is the garment's price on every product (the variant list is empty in the
  search answer, and no product page's variants were read), and whether made-to-measure options exist.
- Queries other than `kaftan`, `daraa`, `abaya` and `dress`; Arabic words as queries; the `/ar/` pages.
- Pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched).
- Per-size stock.
- Whether "Muccii Outlet" is another seller.
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
