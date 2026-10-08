# Her Highness Q8: store notes

Adapter notes for plan module 12.16. Written 2026-10-08, before the live smoke test.

- Store id `her-highness-q8`, shown to shoppers as "Her Highness Q8" (the shop's own markup says
  `herhighnessq8`; its policy text says "Her Highness"). Storefront `https://herhighnessq8.com/`.
- Config: `config/stores/her-highness-q8.yaml`. Tests and fixtures: `tests/stores/her-highness-q8/`.
- Qualification (2026-10-08): `docs/store-qualification/her-highness-q8.md`; the pass it belongs to:
  `docs/store-qualification/modest-ethnic-wear-discovery.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`. Price rule considered and not
  used: `docs/adr/0012-drop-records-with-several-prices.md`. Gender: `docs/adr/0014-product-gender-from-the-stores-own-fields.md`.
- **Status: not enabled yet; live smoke test pending.** The store file says `enabled: false`. The offline
  tests pass on the saved answers. Run the live test once, alone
  (`uv run pytest -m live tests/stores/her-highness-q8 -q`), then switch the flag and fill in
  "Observed live" below.

## Data path

1. The engine checks `https://herhighnessq8.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://herhighnessq8.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three decimals,
   `"45.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute
   on `herhighnessq8.com`, tracking query removed) and `available`. No option is set. Validation then
   drops any record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was confirmed on
   2026-10-08 from the product page's JSON-LD (`priceCurrency: "KWD"` on all 21 offers),
   `og:price:currency` and `Shopify.currency`. A currency-converter widget in the page footer lists AED
   and eight other currencies, but it is a script-driven display tool: the server-rendered prices are
   KWD and no AED URL exists.

`vendor` (`herhighnessq8` on all 21 records), `type`, `tags` (empty on all 21), `variants` (empty on all
21) and `body` are not mapped, except that `type` and `tags` are read for the product's gender (they name
none). `body` is store-supplied HTML, mostly Arabic with right-to-left markup, and must never be
rendered.

## Price

- **Three decimals.** Prices are Kuwaiti dinars written with the fils: `"45.000"`. The price parser
  accepts three decimals only for a store whose currency is KWD, BHD or OMR (ADR 0006), so `45.000` is
  KWD 45. A test pins `"46.800"` as 46.8 and `"38.750"` as 38.75.
- **`max_price_spread` is off, on the evidence (ADR 0012).** The trap at Hamsa was a cheap add-on (a head
  scarf) listed as a variant of the same product as an expensive garment, so `price`, the cheapest
  variant, was 2 to 5 times too low. Here, of the 21 distinct records, **19 have one price on every
  variant** (`price`, `price_min` and `price_max` equal) and **`variants` is an empty list on all 21**.
  The only two records whose variants differ are girls' pieces:

  | Record (KWD) | `price` (= `price_min`) | `price_max` | Ratio |
  |---|---|---|---|
  | Crescent Kids | 35 | 37 | 1.06 |
  | MZIANA – Moroccan Kids | 40 | 43 | 1.08 |

  That is a surcharge for a size, not a different item, and `price` is the smallest size, within 7.5% of
  the largest. With `max_price_spread: 1` the option would drop these two records and gain nothing (the
  ranker drops children's items by title when the shopper has stated a gender, and the price is
  nearly right when not). With `1.25` it would drop nothing seen and would only add a way to fail: if
  Shopify stopped sending `price_min` or `price_max`, every record would be dropped and the store would
  return an error. So the line is left out. Two tests pin it: one shows that exactly these two records
  have a spread and that none has an add-on variant, the other shows what the option would do at `1`
  and `1.25`. **If the store ever lists add-ons, the first test fails: set `max_price_spread: 1.25` and
  re-check the store.**
- **Sales.** 3 of the 21 records carry a pre-sale price above their price: "Plum Kaftan" (42, was 48),
  "Burgundy Kaftan" (36.5, was 39.5) and "Olive Garden" (36.5, was 39.5). The other 18 carry
  `"0.000"`. The adapter uses `price`, what the shopper pays.
- **Shopper-facing figure.** The page shows the dinar price and an approximate dirham figure from the
  fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED), for example `45.000 KWD (about 536 AED)`.
  Ranges and any budget use the dirham figure.
- **Range seen:** KWD 28.5 to 85, median 45 (21 distinct records), about AED 340 to 1,013, median 536.
  Without the four girls' pieces: KWD 35 to 85, about AED 417 to 1,013. Dresses KWD 45 to 55, adult
  kaftans 36.5 to 42, suits 50 to 58, "2" 85. Tier hint `mid_range`: the level of Manal Smaoui (KWD 29 to
  85) and Signature Studio.

## Gender

- **`genders: [women]`.** All 21 distinct records are daraas, kaftans, dresses, suits, a top or girls'
  pieces; by the range and the brand they are women's and girls'. A men's request is therefore not
  sent to this store.
- **No field names a gender.** `type` is empty on 17 of 21 records ("Dress" on 3, "set" on 1) and `tags` is
  empty on all 21, so the `shopify` reader (default `gender_fields: [type, tags]`) leaves every
  product's gender unknown. The option is left at its default because there is nothing to read; the
  ranker reads the title when it needs a gender. A test pins `type` and `tags`.
- **Girls' pieces are in the answers.** Four titles have "Kids" in them. With `genders: [women]` a
  request for women is sent to the store, and the ranker drops children's items by title **only when
  the shopper has stated or confirmed a gender**; with no stated gender they stay (BRD Rule 8: an
  inferred gender is shown, not applied). They are the cheapest products in the store (KWD 28.5 to 40),
  so they sit at the low end of the price range. A test pins both cases. See "Quirks seen".

## Categories

- **`categories: [dresses]`.** Of the 21 distinct records, **14 are daraas, kaftans or dresses** by title
  or by description ("Dara'a 2026", "Aura Dress", "Ivory Glow Dress", "Pearl Dress", "Brown Mist
  Dress", "Burgundy Kaftan", "Plum Kaftan", "Olive Garden", "Desert Palm Luxury", "Crescent",
  "MZIANA – Moroccan", and the girls' "Kids Olive Kaftan", "Kids Burgundy Kaftan", "Crescent Kids").
  The other seven: **3 suits** (a blazer with a belt and wide trousers, by their Arabic description
  only: "Crystal Dark Beige", "Crystal Black", "Royal Midnight Full set"), **1 top** ("Sahara Oversized
  Top") and **3 whose title and description name no garment** ("Beige strips Sets", "2", "MZIANA –
  Moroccan Kids"). No shoes, jeans or jackets by title were seen.
- A search for shoes, tops, outerwear or bottoms is therefore not sent to this store, and it is listed
  among the skipped stores as "Not searched: Her Highness Q8 does not sell shoes." and so on. **The cost
  is real:** the one top is out of reach, and so are the three suits when a shopper asks for a blazer
  or trousers (their titles say neither, so the search cannot be aimed at them anyway).
- "Not seen" is not "not sold" (three queries, 10 products each, none about shoes, blazers or
  trousers): if a larger recording shows tops, blazers or trousers sold on their own, add them to the
  line. A `categories` line was kept rather than left out because without it a search for shoes would
  be sent here and would come back with unrelated pieces whose titles the ranker cannot classify.

## Quirks seen

- **Many titles name no garment.** 11 of the 21: "Beige strips Sets", "Crystal Dark Beige", "Desert Palm
  Luxury", "2", "Olive Garden", "Crescent", "Crystal Black", "Royal Midnight Full set", "Crescent Kids",
  "MZIANA – Moroccan" and "MZIANA – Moroccan Kids". The ranker reads a category only from a garment
  word, so these have none and pass the category filter for a dresses search. The adapter hands them
  over as they are. A test pins the 11.
- **Three suits come back for abaya and daraa searches.** "Crystal Dark Beige", "Crystal Black" and
  "Royal Midnight Full set" are described (in Arabic) as a blazer with a belt and wide trousers. Their
  titles say nothing, so they are products of unknown category; "Crystal Black" and "Royal Midnight
  Full set" are the 2nd and 3rd results for `abaya`. The adapter cannot tell them from dresses and does
  not read `body`. A shopper asking for a daraa may be shown a suit. A test pins this.
- **Girls' pieces beside women's.** "Kids Olive Kaftan", "Kids Burgundy Kaftan", "Crescent Kids" and
  "MZIANA – Moroccan Kids" (KWD 28.5, 28.5, 35 and 40) come back for the same words as the women's
  pieces. The adapter has no rule for them; the ranker drops them when a gender is stated.
- **The store pads its answers.** For `abaya`, no title has "abaya" in it (and the word is in none of
  the saved descriptions); for `daraa`, one of 10 is a "Dara'a"; for `kaftan`, 4 of 10 have "Kaftan" in
  the title. The rest are other pieces. Ranking must filter by category and text rather than trust
  the store's order.
- **A small catalogue.** 21 distinct products over three queries: 9 of the 30 records were repeats of an
  earlier one ("Dara'a 2026" answered all three queries), which the engine collapses. More queries
  would likely show more pieces, but the same ones answer many words.
- **Handles do not match titles.** "Crystal Black" is `/products/new2-mar-6` and "Crystal Dark Beige"
  `/products/new2-mar-7`; "Kids Olive Kaftan" is `/products/untitled-nov22_19-25`; "MZIANA – Moroccan
  Kids" is `/products/untitled-dec19_22-35`; "Royal Midnight Full set" is `/products/new-set-17-2`;
  the piece titled "2" is `/products/2-1`. The link is always the store's own `url`, never rebuilt
  from the title; a test pins all six.
- **A title with two spaces.** The store writes "Kids Olive  Kaftan"; the product comes out with single
  spaces. A test pins it.
- **"Dara'a" has an apostrophe.** The title is "Dara'a 2026" and the handle `daraa-2026`. The ranker's
  tokenizer drops the apostrophe, so the word is `daraa`, which is among the dresses words in
  `src/vga/rank/lexicon.py` (present in the worktree when this was written). A test pins that "Dara'a
  2026" is read as a dress; it fails if that word is ever removed.
- **Titles with an en dash.** "MZIANA – Moroccan" uses a real en dash (U+2013). It is kept as written.
- **`type`, `tags` and `variants` are almost empty.** `type` is "" (17), "Dress" (3) or "set" (1);
  `tags` and `variants` are empty lists on all 21. Neither can name a category or a gender.
- **Descriptions are Arabic, right-to-left HTML,** some in English ("Dress length: 43 inches"), and some
  empty (7 of 21 within the first 300 characters). They are cut to 300 characters in the fixtures and
  are never used.
- **Links carry tracking parameters** (`?_pos=1&_psq=daraa&_psid=...&_ss=e`). They are removed, so every
  product link is `https://herhighnessq8.com/products/<handle>`.
- **Stock is product-level only** (`available`, true for all 21 records). The product page's 21 offers
  are all InStock.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0695/4631/1733/files/`, with a `v=` version
  parameter that is kept; the file names are mixed (`.jpg`, `.png`, `IMG_0411.JPG1.png`,
  `olivegardenkaftan.png`). The product page's own JSON-LD and `og:image` use
  `herhighnessq8.com/cdn/shop/files/...` instead; search results do not.
- **An Arabic version exists** at `/ar/` (hreflang on the product page); the English search at the root
  was used and the Arabic one was not requested.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare or Shopify starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (an older Shopify template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/her-highness-q8/` show the expected shape |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| The store adds variants priced differently (a scarf, a belt, a set beside a piece) | the test that pins "no add-on variant" fails; wrong prices if it is not run | Set `max_price_spread: 1.25` in the store file (ADR 0012) and re-check the store with a new recording |
| The store serves another currency from `herhighnessq8.com` (a currency widget and an `/ar/` path exist) | prices silently wrong (the response has no currency) | The file pins the host and KWD; re-check the product page JSON-LD |
| The store moves to another host (for example `www.herhighnessq8.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The store starts putting a gender in `type` or `tags` | genders become known; a women-only filter still holds | Nothing to do; add a test with the new record |
| The store starts selling shoes or men's wear, or tops and trousers on their own | those requests are not sent here | Edit `categories` and `genders` in the store file (both rest on the range and the brand) |
| The word `daraa` is removed from the dresses words in the ranker's lexicon | "Dara'a 2026" has no category; the test that pins it fails | Restore the word, or accept that the daraa piece is no longer matched by title |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://herhighnessq8.com/search?q=`
(allowed by robots.txt per protego, never requested), and the store's agent endpoint named in
robots.txt (planned as Phase 17).

## Observed live

**Not run yet.** The live smoke test (`tests/stores/her-highness-q8/test_her_highness_q8_live.py`,
queries `daraa` and `kaftan`, at most 3 requests) is for the orchestrator, alone and once. Fill in the
table below from its output, then set `enabled: true` and **Status: enabled** above.

| Query | Status | Products returned | Kept after validation | Seconds | Response |
|---|---|---|---|---|---|
| daraa | pending | | | | |
| kaftan | pending | | | | |

What the qualification run saw on 2026-10-08, through the same honest client (not the live test): six
requests in all (robots.txt twice, three searches, one product page), every one HTTP 200 and none
refused, all through Cloudflare WARP:

| Query | Status | Products returned | Response | Time |
|---|---|---|---|---|
| daraa | 200 | 10 | 9,760 bytes | 0.4 s |
| kaftan | 200 | 10 | 10,158 bytes | 0.4 s |
| abaya | 200 | 10 | 10,815 bytes | 0.3 s |

- robots.txt: 200, 3,636 bytes, both times. Every search URL was allowed. The timeout is the global 6 s
  (`timeout_s` is not overridden).
- **Gender:** `genders: [women]`. Evidence: all 21 distinct records are daraas, kaftans, dresses,
  suits, a top or girls' pieces; no title, type or tag names a gender (`type` empty on 17, "Dress" on 3,
  "set" on 1; `tags` empty on 21). The data carries no gender field, so this rests on the range and
  the brand, as for Hanayen and Manal Smaoui.
- **Categories:** `categories: [dresses]`. Evidence: 14 of 21 are daraas, kaftans or dresses; the other
  seven are 3 suits, 1 top and 3 unnamed. Nothing for shoes. "Not seen" is not "not sold" (three
  queries of 10 products): remove or widen the line if a larger recording shows more.
- **Behaviour from the machine's own network is untested** (see the qualification report, "Not
  verified / limits").

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, suggests a third-party
shopping skill, and says checkouts are for humans and must not be completed automatically. This is
store-supplied text. The adapter did not follow it: it requested no UCP, MCP, `agents.md` or
`.well-known` URL, installed nothing, and never touches the cart or checkout. The rules that apply to us
are the `User-agent: *` group, which opens with `Allow: /` and does not disallow `/search`. The stated
preference for the agent endpoint is for the terms review and for Phase 17.

## Unverified

- The live smoke test (not run yet), and behaviour from the machine's own network.
- That the three suits are suits (the evidence is the Arabic description), and what "Beige strips Sets",
  "2" and "MZIANA – Moroccan Kids" are (their descriptions are empty).
- Whether the store sells tops, blazers, trousers or shoes on their own (`dress`, `blazer`, `trousers`,
  `shoes` and Arabic queries were never asked for).
- The `/ar/` market and whether it changes the answer or the currency.
- Pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched).
- Per-size stock (the answer has `variants: []`).
- Whether add-on variants exist anywhere in the catalogue (none in the 21 distinct records seen).
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
