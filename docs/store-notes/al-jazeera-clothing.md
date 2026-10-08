# Al Jazeera Clothing: store notes

Adapter notes for plan module 12.18. Written 2026-10-08, before the live smoke test; updated the same
day with the smoke test's result.

- Store id `al-jazeera-clothing`, shown to shoppers as "Al Jazeera Clothing". Storefront
  `https://aljazeera-clothing.com/`. A Kuwaiti label of traditional menswear, no relation to the news
  network.
- Config: `config/stores/al-jazeera-clothing.yaml`. Tests and fixtures: `tests/stores/al-jazeera-clothing/`.
  The price option lives in the shared extractor (`src/vga/stores/extractors/shopify.py`, option
  `max_price_spread`).
- Qualification (2026-10-08): `docs/store-qualification/al-jazeera-clothing.md`; the modest and ethnic
  wear pass it belongs to: `docs/store-qualification/modest-ethnic-wear-discovery.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`. Price rule:
  `docs/adr/0012-drop-records-with-several-prices.md`.
- **Status: enabled** (live smoke test passed 2026-10-08, through the project's own engine, on the
  address with `/en/` in it; the table is in "Observed live"). The file says `enabled: true`.
- **How thin this store is for the demo.** Three adult dishdashas were seen (KWD 9 each, about AED 107)
  in 30 distinct records over four queries. The other 27 records are 18 children's dishdashas and 9
  men's underwear, nightwear and multipacks. A search for a men's thobe will mostly bring back boys'
  dishdashas from here unless the ranker filters them (see "Quirks seen"). Do not count this store as a
  source of men's thobes in the demo's coverage.

## Data path

1. The engine checks `https://aljazeera-clothing.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search on the **English address**, one request per keyword
   variant:
   `https://aljazeera-clothing.com/en/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
   **The `/en/` is not decoration.** The store's default language is Arabic (`<html lang="ar" dir="rtl">`,
   `Shopify.locale = "ar"`), and the plain `/search/suggest.json` answered **HTTP 417** with the 86-byte
   body `{"status":417,"message":"Expectation Failed","description":"Unsupported buyer locale"}` three
   times (for `dishdasha`, `thobe` and `men`). The English storefront under `/en` answers normally.
   Tests pin both halves: the store file's address has `/en/`, and the 417 body is read as an error with
   no products.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three decimals,
   `"9.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute
   on `aljazeera-clothing.com`, tracking query and `variant=` removed; the path stays
   `/en/products/<handle>`), `available`, and the product's gender from `type` then `tags`
   (`gender_fields: [type, tags]`, also the default). With `max_price_spread: 1` it first drops any
   record whose variants do not all cost the same (see "The price rule"). Validation then drops any
   record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was read on
   2026-10-08 from the **home page**: `Shopify.currency` `{"active":"KWD","rate":"1.0"}`,
   `shop.paymentSettings.currencyCode` `"KWD"`, `Shopify.country` `"KW"`, and a market picker that lists
   seven markets (AU, AE, BH, KW, SA, OM, QA), every one priced in KWD. **No product page was read**, so
   there is no JSON-LD `priceCurrency` evidence (the qualification request budget ran out first).

`vendor` ("JAZEERA" on all 30 records), `compare_at_*` (`"0.000"` on all 30) and `body` are not mapped.
`body` is store-supplied HTML and must never be rendered.

## The price rule

`price` is the cheapest variant. On 9 of the 30 distinct records `price_min` differs from `price_max`:

| Record (all KWD) | `price` (= `price_min`) | `price_max` |
|---|---|---|
| Kids' Linen Dishdasha | 12 | 14 |
| Boys' Special Dishdasha with Colored Line | 12 | 14 |
| Boys' Stripes Moroccan Dishdasha | 5 | 6 |
| Boys' Beige, Dark Beige, Dark Grey and Light Grey Soft Winter Dishdasha (four records) | 6 | 7 |
| Boys' Stripes V-Neck Half Sleeve Sleeping Dishdasha | 2 | 2.25 |
| Men's 6 Pcs Cotton Half Pants Set | 6.6 | 9 |

Eight are children's, one is a men's multipack. The one ranged record that lists a variant shows what the
difference is: "Light Gray / 6 Months (18 Inch)" at KWD 12 (maximum 14), a size by age. So `price` is the
smallest size's price. For the other seven records the search answer lists no variant; that they are
sizes too is an inference. The three adult dishdashas have one price each (KWD 9), and the matched
variants that are listed read "White / M / 52" and "Gray / M / 52" at KWD 9, so the sizes carry no
surcharge.

**The rule (chosen).** `max_price_spread: 1` in the store file: a record is kept only when its variants
all cost the same, as at Hamsa (ADR 0012). The nine are dropped, never corrected, and counted as
`missing_price`. Of the 40 records in the four saved answers (30 distinct), 11 are dropped (9 distinct),
29 are valid and 21 are distinct valid products.

**Why 1 and not 1.25.** The widest spread among the eight children's records is 1.2 (KWD 5 to 6), so
`1.25` would keep all eight at their smallest size's price (the men's multipack, at 1.36, would still be
dropped). They are children's, which an adult
shopper does not want, and a price that is "from" the smallest size is not one the shopper can count on.
The cost of `1` is real but small here: 8 children's records. If the store adds a size surcharge to its
adult dishdashas, those would be dropped too (fail closed); raise the option to about 1.25 then, after
reading the real ranges.

## Gender

`genders: [men]`. Evidence, 30 distinct records over four queries: `type` is "Apparel for men" on 12 and
"Apparel for kids" on 18; no record is women's. A women's request is therefore not sent to this store.

- Boys, youths and newborns are not a gender in the contract (`women`, `men`, `unisex`), so the 18
  children's records do not fit `genders`. `men` is the adult range. How a request for a boy's
  dishdasha is read is up to the understand step and was not checked here.
- The home page's handles include three girls' dresses (a prayer dress, a daraa and a black-and-green
  dress). They are girls', not women's, and none was a search record. If women's items turn up, remove
  the line.
- "Not seen" is not "not sold": 40 records, four queries, none women's.
- How gender reaches the product: `gender_fields: [type, tags]`. "Apparel for men" names men, and the
  tags agree on all 12 ("men", "A/W men", "men new"). "Apparel for kids" and the tags "boys", "kids"
  and "A/W boys" name no gender word, so every children's product has no gender (unknown). Tests pin
  that.

## Categories

`categories: [dresses]`. The category that holds thobes, dishdashas and kanduras. Evidence: of the 12
men's records, the 3 dishdashas are the only adult garments to wear outside; the other 9 are underwear,
nightwear and multipacks (thermal sets, pyjama sets, "6 Pcs" and "12 Pcs" packs of innerwear, undershirts
and pants), all tagged "Under Garments". A search for tops, trousers, jackets or shoes is therefore not
sent to the store (it would only bring back pyjamas and undershirts), and a dresses search is.

- "Not seen" is not "not sold". The home page's handles also include a men's sandal, boys' shoes, boys'
  jackets and vests, bags and sunglasses. None was a search record, and, judging from the
  handles alone, the adult items are one pair of sandals and accessories or religious items (caps, bags,
  sunglasses, ghutras, an ihram). If a men's shoes search from this store is wanted, remove the line and
  read a live answer first.
- `type` cannot name a category here ("Apparel for men" says who, not what), so the category comes from
  the title. That is the ranker's job (see "Quirks seen").

## Quirks seen

- **The English address.** See "Data path". Without `/en/` every search is an `error` ("HTTP 417 from the
  search page"), one request, no cooldown. The engine does not treat a 417 as a block, and a test pins
  that.
- **Mostly children's.** Of the 10 records in each answer: `dishdasha` 9 children's and 1 men's,
  `thobe` 9 and 1, `winter` 8 and 2, `men` 0 and 10 (1 dishdasha). The adult share of a ten-product
  answer is small, and the 10-product cap leaves no room for more.
- **Only three adult dishdashas, all KWD 9.** "Men's Summer Dishdasha by Al Jazeera", "Men's Elegant
  Winter Dishdasha by Al Jazeera" and "Men's Winter Dishdasha by Al Jazeera". After the price rule the
  store contributes 21 distinct products to the offline test: 10 children's, 3 men's dishdashas, 8 other
  men's records. The offline test needs 20, so the margin is one product.
- **The children's filter (ranker, not this adapter).** Before "youth" and "newborn" were added to the
  children's words in `src/vga/rank/lexicon.py`, `is_childrens_title` recognised 14 of the 18 children's
  titles (those with "boys", "kids"). Three say "Youth" and one "Newborn" with no boys or kids word,
  and `type` ("Apparel for kids") names no gender, so those four passed as unknown. The two words are
  in the lexicon now, in the same branch as this store; when this note was written, with them all 18
  were recognised and no adult record was. That count was not repeated after the change was committed.
  Separately, the filter drops children's items only when the shopper stated a gender (`gender_source`
  explicit): with an inferred or no gender they stay in the results, and 10 of the 21 valid products
  are children's.
- **"Sleeping" dishdashas are nightwear.** Two children's records are named "... Sleeping Dishdasha"
  (tag `home`), and the home page's data shows two adult men's ones
  (`men-s-half-sleeve-stripes-summer-sleeping-dishdasha-by-al-jazeera`,
  `men-s-stripes-half-sleeve-v-neck-summer-sleeping-dishdasha-by-al-jazeera`). The ranker's out-of-scope
  words include "nightwear" and "sleepwear" but not "sleeping", and "dishdasha" is now in the dresses
  list, so a sleeping dishdasha ranks as a dress. None of the adult ones was a search record.
- **"Dishdasha" as a category word.** Before the lexicon change the three adult titles ("Men's Summer
  Dishdasha by Al Jazeera") named no garment word and had no category, so they were kept for every request
  without a category bonus. Now dishdasha, thawb, kandura and more are folded into "thobe" and listed
  under dresses, so they are dresses, and a thobe request also matches a dishdasha or kandura title. This
  adapter does not depend on either: `categories: [dresses]` already decides which searches reach the
  store.
- **Handles do not always match titles.** "Boys' Beige Summer Dishdasha" is
  `/en/products/beige-dishdasha-al-jazeera-for-kids-ramadan-edition-with-name-embroidery`; "Boys' Beige
  Soft Winter Dishdasha" is `boys-beige-light-winter-dishdasha-by-al-jazeera` ("Soft" against "light").
  The link is always the store's own `url`, never rebuilt from the title.
- **Links carry tracking parameters** (`?_pos=1&_psq=dishdasha&_psid=...&_ss=e`, and on 5 of 30 records
  `&variant=<id>`). They are removed, so every link is `https://aljazeera-clothing.com/en/products/<handle>`.
- **Title typography.** 27 of the 30 titles have an apostrophe: the curly right quotation mark in 20 and
  a straight one in 7; one title has a double space ("Boys'  Winter Dishdasha", collapsed by the
  adapter) and one a stray apostrophe ("Youth' Stripes V-Neck ..."). 26 of 30 titles contain "by Al
  Jazeera".
- **A name-embroidery add-on.** The home page's product data shows an option "Custom name (+5.000 KWD)".
  The search `price` is the base garment price; a personalised dishdasha costs KWD 5 more.
- **No sale prices.** `compare_at_price_*` is `"0.000"` on all 30 records; `price` is what the shopper
  pays.
- **Stock is product-level only** (`available`, true for all 30 records). Per-size stock was not read.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0960/9602/6936/` (a `files/` folder), with a
  `v=` version parameter that is kept.
- **Price range seen (30 distinct records):** KWD 2 to 18, about AED 24 to 215. Men's KWD 5 to 18
  (dishdashas KWD 9, about AED 107), children's KWD 2 to 12 (maximum variant price 14). Tier hint
  `budget`.
- **Shopper-facing figure.** The page shows the dinar price and an approximate dirham figure from the
  fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED), for example `9.000 KWD (about 110 AED)`.
  Ranges and any budget use the dirham figure.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| The store makes English its default language, so `/en/` stops answering or redirects to the apex | `error` (a redirect to a host not on the list is refused; a 404 or a non-JSON page is an unreadable answer) | Look at the home page's `hreflang` links, then change `search_url_template` (the host stays in `allowed_hosts`). A test fails first: it pins the `/en/` path |
| Shopify starts serving Arabic from the plain address (the 417 goes away) | nothing breaks: `/en/` keeps working | Leave it; the product links stay `/en/products/...`, which is the English page |
| The `/en/` prefix is dropped from the store file by mistake | `error`, "HTTP 417 from the search page", one request, no cooldown | Restore the prefix. The offline test that pins the template fails first |
| Cloudflare or Shopify starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` or `/en/search` | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/al-jazeera-clothing/` show the expected shape |
| Shopify stops sending `price_min` / `price_max` | every record is dropped (`missing_price`), the store returns an error | Fail closed on purpose: the rule cannot check, so no price is shown. Fix the extractor, do not remove the option |
| The adult dishdashas get a size surcharge | they are dropped, fewer results | Raise `max_price_spread` (for example 1.25) after reading the real ranges |
| The `max_price_spread` line is removed from the store file | children's sizes are shown at the smallest size's price | The test that pins the file's options fails. Restore the line |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| The store serves another currency from `aljazeera-clothing.com` | prices silently wrong (the response has no currency) | The file pins the host and KWD; read a product page's JSON-LD `priceCurrency` (not yet done) |
| The store moves to another host (for example `www.aljazeera-clothing.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://aljazeera-clothing.com/en/search?q=`
(robots.txt allows it; never requested) and the store's agent endpoint named in robots.txt (planned as
Phase 17).

## Observed live (2026-10-08)

**The live smoke test passed.** It ran through `StoreSearchEngine` on the `/en/` address between 14:35
and 14:38 local time, one store at a time with 15 s between stores, through Cloudflare WARP (see
"Unverified"). Three requests went to this store: `robots.txt` and two searches. Every answer was HTTP
200, with no block or challenge.

| Query | Status | Products kept | Seconds |
|---|---|---|---|
| dishdasha | ok | 7 (3 dropped, reported as `missing_price`: the price rule `max_price_spread: 1`) | 1.56 |
| thobe | ok | 8 (2 dropped the same way) | 0.89 |

The slowest request took 1.56 s, against the global 6 s timeout. The kept counts are the same as the
saved answers gave offline (7 and 8). Response sizes were not recorded in the live run.

What was seen earlier the same day is from the qualification script's requests (all HTTP 200 on the
`/en/` address, no redirect, no challenge, CAPTCHA or login wall; all through Cloudflare WARP, see the
qualification report):

| Query | Status | Records returned | Kept after the price rule and validation | Seconds | Response |
|---|---|---|---|---|---|
| dishdasha | 200 | 10 | 7 (3 dropped as `missing_price`) | 0.5 | 30,468 bytes |
| thobe | 200 | 10 | 8 (2 dropped) | 0.3 | 28,272 bytes |
| winter | 200 | 10 | 5 (5 dropped) | 0.3 | 29,920 bytes |
| men | 200 | 10 | 9 (1 dropped) | 0.5 | 26,277 bytes |
| dishdasha, thobe, men on the plain address | 417 | none | none | 0.2 | 86 bytes |

- robots.txt: 200, 3,656 bytes, the same bytes every time. Every `/en/` search URL was allowed.
- Requests to the store for this adapter: 12 in the qualification pass (4 robots.txt,
  3 refused plain-address searches, 1 home page, 4 `/en/` searches), plus 3 in the live smoke test
  (`robots.txt` and the two searches above). Four of the 12 (the three
  refused plain-address searches and the home page) were wasted by the orchestrator's script, which did
  not stop at the first 417 and fetched the home page where a product page was meant. No product page and no thumbnail was fetched.
- **Gender:** `genders: [men]`. Evidence: 12 of 30 distinct records are men's (`type` "Apparel for men"),
  18 are children's, none is women's. See "Gender".
- **Categories:** `categories: [dresses]`. Evidence: 3 of the 12 men's records are dishdashas, 9 are
  underwear and nightwear. See "Categories".

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog, cart,
and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, asks an agent that acts as a
personal shopper to recommend that its user install a third-party shopping skill, and says checkouts are
for humans. This is store-supplied text. The adapter did not follow it: it requested no UCP, MCP,
`agents.md` or `.well-known` URL, installed nothing, and never touches the cart or checkout. The rules
that apply to us are the `User-agent: *` group, which opens with `Allow: /` and does not disallow
`/search` or `/en/search`. The stated preference for the agent endpoint is for the terms review and for
Phase 17.

## Unverified

- A product page: no JSON-LD `priceCurrency`, no variant list, no check that the product page at
  `/en/products/<handle>` is in KWD. Currency rests on the home page.
- That Shopify's predictive search does not serve Arabic at all (the 417 was seen three times in one
  afternoon, on three queries, and not tried again).
- That the seven ranged records without a listed variant differ by size.
- Queries other than `dishdasha`, `thobe`, `winter` and `men` (`kandura`, `thawb`, `ghutra`, Arabic
  words and "men's dishdasha" were never asked for). A query that names men may bring more of the three
  adult dishdashas and fewer boys' ones; that was not tried.
- Women's items, and whether shoes, jackets or bags can be found by search (the home page's handles
  suggest they exist).
- Pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched).
- Per-size stock.
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.
- Behaviour from the machine's own network: from about 13:00 on 2026-10-08 its path to Shopify timed
  out on connect, and every request here went through Cloudflare WARP, the live smoke test included.
- Response sizes in the live run (not recorded).

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
