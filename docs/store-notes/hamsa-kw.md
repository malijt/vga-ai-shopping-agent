# Hamsa: store notes

Adapter notes for plan module 12.12. Written 2026-10-08, after the live smoke test.

- Store id `hamsa-kw`, shown to shoppers as "Hamsa" (the brand is Hamsa by Sharifa AlGhanim).
  Storefront `https://hamsakw.com/`.
- Config: `config/stores/hamsa-kw.yaml`. Tests and fixtures: `tests/stores/hamsa-kw/`. The price option
  lives in the shared extractor (`src/vga/stores/extractors/shopify.py`, option `max_price_spread`)
  and is tested in `tests/fetch/test_shopify_price_spread.py`.
- Qualification (2026-10-08): `docs/store-qualification/hamsa-kw.md`; the designer-brand pass it
  belongs to: `docs/store-qualification/designer-store-qualification.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`.
- **Status: enabled, and only because of the price guard.** The live smoke test passed on 2026-10-08
  (see "Observed live today"). Take `max_price_spread` out of the store file and the store shows
  wrong prices: disable it first. A test pins that the shipped file keeps the option.

## Data path

1. The engine checks `https://hamsakw.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://hamsakw.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three decimals,
   `"95.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute
   on `hamsakw.com`, tracking query and `variant=` removed) and `available`. With
   `max_price_spread: 1` it first drops any record whose variants do not all cost the same (see "The
   price rule"). Validation then drops any record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was confirmed on
   2026-10-08 from the product page's JSON-LD (`priceCurrency: "KWD"` on all six size offers) and
   `Shopify.currency`, and the page's region table prices all 201 regions, the UAE included, in KWD.
   There is no AED storefront.

`vendor` (two spellings, see below), `type`, `tags` and `body` are not mapped, except that `type` and
`tags` are read for the product's gender (they name none here). `body` is store-supplied HTML and must
never be rendered.

## The price rule

**The trap.** Shopify's `price` is the lowest price among a product's variants. Hamsa lists a cheap
variant (apparently a head scarf) on the same product as an abaya. On 5 of the 10 records in the
`abaya` answer, `price` is that cheap variant, not the abaya:

| Record (all KWD) | `price` (= `price_min`) | `price_max` | Variant the search matched ("... / Abaya") |
|---|---|---|---|
| Fire Works Abaya | 20 | 80 | 80 |
| Stardust Abaya | 35 | 95 | 95 |
| Collage Abaya | 35 | 130 | 130 |
| Shooting Star Abaya | 95 | 365 | 365 |
| Tonal Abaya/Scarf | 20 | 95 | **75** |

Read blindly, these would be shown at KWD 20 to 95 (about AED 240 to 1,130) for abayas that cost KWD 75
to 365 (about AED 890 to 4,350): the wrong price range, and a false "within your budget". The other 15
records of the two answers have one price (`price_min` equals `price_max`).

**The rule (chosen).** A generic option of the `shopify` strategy, `max_price_spread: 1` in this store's
file: a record is kept only when its highest variant price is at most 1 times its lowest, that is, all
its variants cost the same. Any other record is **dropped, not corrected**, and so is a record whose
`price_min` or `price_max` is missing or unreadable (fail closed). A dropped record is counted as
`missing_price` in the store result (the extractor logs the real reason at info level with the range).
Exact decimals are compared, so there is no rounding noise.

**What it does to the 20 recorded records:** keeps 15 (5 of 10 abayas, 10 of 10 kaftans), corrects 0,
drops 5 (Fire Works, Stardust, Collage, Shooting Star and Tonal Abaya/Scarf). The five dropped are
all 2020 pieces (product codes `S-20-001` to `S-20-007`), so the store loses old, heavily discounted
stock, not its current range; the loss is still real: a shopper who would like one of them will not
see it.

**Why not take the highest price?** It is the abaya's price on four of the five records, but not on
"Tonal Abaya/Scarf": its abaya variant is KWD 75 and its maximum KWD 95 (probably a set). Showing 95
would be a wrong price with no way to tell from the response which records are like that.

**Why not use the variant the search matched?** `variants[0]` was the abaya on all five and its price
was the abaya's every time, and this could rescue the five records. It was not adopted: Shopify picks
that variant by matching the typed words against variant titles, so a different query (for example
"black" or "scarf") could match the scarf variant and hand back its price, and nothing in the
response says which variant is the garment. The rule needs no such trust. If the business wants the
five back, this is the next step, to be tested against a recording of more queries.

**Not verified:** that the cheap variant is a scarf (the evidence is the description of "Stardust
Abaya", which lists "Abaya" and "Head Scarf" as two items, and the title "Tonal Abaya/Scarf"). No
product page was fetched to check; the search response alone was used, as agreed.

## Quirks seen

- **Handles do not match titles.** "Amber Kaftan" is `/products/short-seline-kaftan-copy-1` and "Short
  Seline Kaftan" is `/products/long-seline-kaftan-copy`. The link is always the store's own `url`,
  never rebuilt from the title; a test pins both.
- **Two spellings of one vendor.** `vendor` is "Hamsakw" on 12 of 20 records and "Hamsa by Sharifa
  AlGhanim" on 8. The adapter does not read it; every product carries the store file's name.
- **`type` is inconsistent.** "ABAYA" (10), "KAFTAN" (8), "DRESS" (1, "Ameera Kaftan"), "casual dresses"
  (1, "Short Amar Kaftan"). It cannot name a category; the title has to.
- **An abaya coat.** "Star Dust Coat" (KWD 75) is filed under `type: ABAYA`. A coat-like title means the
  ranker may read it as outerwear, and `categories: [dresses]` means an outerwear search is not sent
  to this store at all.
- **Old catalogue still on sale.** Product codes `S-20-xxx` (2020) and `W-22-xxx` (2022) are searchable
  and `available`, next to `W-26-xxx`. The adapter reports the store's own stock flag and nothing more.
- **Sale prices.** `price` is what the shopper pays. `compare_at_price_max` is the struck-through price
  (`"295.000"` against `"160.000"` for the Pistachio Lotfia Kaftan, `"365.000"` against `"75.000"` for
  the Star Dust Coat); when it equals `price` ("Amber Kaftan", 55 against 55) it is not a discount. The
  adapter uses `price`. 6 of the 15 kept records carried a compare-at price above their price (10 of
  the 20 recorded, counting the 4 dropped ones).
- **Links carry tracking parameters** (`?_pos=1&_psq=abaya&_psid=...&_ss=e`, and on some records
  `&variant=<id>`). They are removed, so every product link is `https://hamsakw.com/products/<handle>`.
- **Gender is in no field.** `type` and `tags` carry garment words ("ABAYA", "Kaftan", "Long Dresses",
  "Evening 2021"), never a gender, so every product's gender is unknown. `genders: [women]` in the store
  file is what keeps a men's request away from this store.
- **Stock is product-level only** (`available`, true for all 20 records). Per-size stock was not read.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0107/8453/8705/` (`/products/` for the
  older pieces, `/files/` for the newer), with a `v=` version parameter that is kept. The product page's
  own JSON-LD image is malformed (`https:files/...`); search results are not.
- **Price range seen (kept records):** KWD 55 to 320, about AED 660 to 3,810. Abayas KWD 75 to 212
  (about AED 890 to 2,530), kaftans and kaftan dresses KWD 55 to 320. Tier hint `premium`. Nothing is
  under about AED 660, so this store does not fill the everyday-abaya gap.
- **Shopper-facing figure.** The page shows the dinar price and an approximate dirham figure from the
  fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED), for example
  `95.000 KWD (about 1,130 AED)`. Ranges and any budget use the dirham figure.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (an older Shopify template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/hamsa-kw/` show the expected shape |
| Shopify stops sending `price_min` / `price_max` | every record is dropped (`missing_price`), the store returns an error | Fail closed on purpose: the guard cannot check, so no price is shown. Fix the extractor, do not remove the option |
| The `max_price_spread` line is removed from the store file | scarf-priced abayas are shown | The test that pins the file's options fails. Restore the line, or disable the store |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| Most of the current range gets a surcharge variant (sizes, lengths) | records dropped, fewer results | Raise `max_price_spread` (for example 1.25) after looking at real ranges; the five known trap records have a spread of 2.7 or more |
| The store serves another currency from `hamsakw.com` | prices silently wrong (the response has no currency) | The file pins the host and KWD; re-check the product page JSON-LD |
| The store moves to another host (for example `www.hamsakw.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://hamsakw.com/search?q=`
(not requested), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after the price guard and validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| abaya | ok | 10 | 5 (5 dropped as `missing_price`, the price guard) | 1.32 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.37 | 11,976 bytes |
| kaftan | ok | 10 | 10 | 1.10 | 0.97 | 14,139 bytes |

- robots.txt: 200, 3,612 bytes, byte for byte the file saved in the qualification pass. Every search URL
  was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail and no product page was fetched. The timeout is the global 6 s
  (`timeout_s` is not overridden); the slowest query took 1.37 s.
- Both answers had the same sizes (11,976 and 14,139 bytes) as the qualification pass's earlier in
  the day, and the live test returned the same counts as the recording, so the data held steady over
  the day.
- **Gender:** `genders: [women]`. Evidence: all 20 records recorded today (and the 20 of the
  qualification pass) are abayas, kaftans or kaftan dresses, women's garments; no title, type or tag
  names a gender. The data carries no gender field, so this rests on the range and the brand, as for
  Hanayen and Oh Polly. A men's request is therefore not sent to this store.
- **Categories:** `categories: [dresses]`. Evidence: 20 of 20 records are abayas (including an abaya
  coat and an abaya set), kaftans or kaftan dresses; no shoes, trousers, tops, jackets or gowns appeared.
  A search for any other category is therefore not sent to this store; it is listed among the skipped
  stores as "Not searched: Hamsa does not sell shoes." and so on. "Not seen" is not "not sold" (10
  products per query, two queries; `dress` and `gown` were never queried): if the store turns out to
  sell other garments, remove the line.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and suggests a
third-party shopping skill. This is store-supplied text. The adapter did not follow it: it requested
no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never touches the cart or
checkout. The rules that apply to us are the `User-agent: *` group, which opens with `Allow: /` and
does not disallow `/search`. The stated preference for the agent endpoint is for the terms review
and for Phase 17.

## Unverified

- That the cheapest variant is a scarf, and what the variants of the five dropped products are.
- Whether the price guard hides products a shopper would want: the five dropped are 2020 pieces.
- Queries other than `abaya` and `kaftan` (`dress` and `gown` were never asked for).
- Pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
