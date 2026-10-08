# Gul Ahmed UAE: store notes

Adapter notes for plan module 12.19. Written 2026-10-08, before the live smoke test; updated the same
day with the smoke test's result.

- Store id `gul-ahmed-uae`, shown to shoppers as "Gul Ahmed UAE". Storefront
  `https://uae.gulahmedshop.com/`.
- Config: `config/stores/gul-ahmed-uae.yaml`. Tests and fixtures: `tests/stores/gul-ahmed-uae/`.
- Qualification (2026-10-08): `docs/store-qualification/gul-ahmed-uae.md`; the dress and modest-wear
  discovery pass that listed it (row 13, untested there): `docs/store-qualification/dress-store-discovery.md`.
- **Status: enabled** (live smoke test passed 2026-10-08, through the project's own engine; the table
  is in "Observed live"). The file says `enabled: true`. The live test is
  `tests/stores/gul-ahmed-uae/test_gul_ahmed_uae_live.py`.
- Why it matters: the first readable source of men's shalwar kameez, and one of few for men's kurtas and
  women's kurtis. Nothing else enabled sells a men's shalwar kameez.

## Data path

1. The engine checks `https://uae.gulahmedshop.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://uae.gulahmedshop.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string such as `"53.50"`),
   `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute on
   `uae.gulahmedshop.com`, tracking query removed), `available`, and the product's gender from `type` then
   `tags` (`gender_fields: [type, tags]`, which is also the default). Validation then drops any record that
   lacks a field or has a link off `allowed_hosts`, and collapses a repeat of the same title at the same
   price.
4. The response carries **no currency**; `currency: AED` comes from the store file. The product page has
   **no JSON-LD**, so AED was confirmed on 2026-10-08 from `Shopify.currency` (`{"active":"AED","rate":"1.0"}`),
   `Shopify.country` (`"AE"`) and `"currencyCode":"AED"` on the variant prices in the page's data, not from the
   search response and not from `priceCurrency`.

`vendor` ("GulAhmed Ideas PK" on 33 of 40 records, "uae.gulahmedshop.com" on 7), `compare_at_*` and `body`
are not mapped. `body` is store-supplied HTML and must never be rendered.

## Quirks seen

- **Many different products share one title, and the app collapses them.** "UAE-Regular Fit Styling Kurta"
  at AED 53.50 is four products (handles `...kr-sty25-079`, `-084`, `-086`, `-001`; design codes in the
  description; four pictures, lite green, sky blue, beige and green). Validation treats the same
  normalised title at the same price as one product, so one of the four is shown. Counted through the real
  chain over the four saved answers: **40 records, 32 distinct products, 20 products after the app's
  rule**. The 12 that are hidden are real, different garments; "UAE-Cambric Printed Shirt" alone is
  4 products at AED 79 (plus a fifth in another spelling). This cannot be fixed in the store file: nothing
  in the title differs. A better key (for example the image address) is a change to
  `src/vga/stores/normalise.py`, which is shared code and is not part of this adapter. The 20 distinct
  products are exactly the plan's floor for the offline test; it passes at `== 20`.
- **Titles start with `UAE-`, in three spellings.** 19 products start "UAE-", 12 start "UAE- " (a space
  after the hyphen) and 1 starts "UAE -" (a space before it). The spelling changes what collapses: "UAE-
  Cambric Printed Shirt" and "UAE-Cambric Printed Shirt" at AED 79 are different normalised titles and both
  survive. 4 of 32 titles also end with a style code ("... Kurta KR-STY25-007"); the rest carry the code
  in the handle and description only.
- **How the ranker reads those titles.** `tokenize` splits at hyphens and drops the apostrophes, so the
  prefix is the word "uae" in all three spellings and a code is "kr", "sty25", "007". None is a garment,
  colour or gender word, and the overlap score counts the request's words found in the title, not the other
  way round, so the prefix and the code cost a product nothing. A shopper who typed "uae" would match every
  product of this store; nobody searches for that. Nothing in `src/` needs to change.
- **Two prices on 5 of 32 products, left alone on purpose.** `price` is the lowest variant. On
  `...embroidered-kurta-kr-emb25-028`, `...styling-kurta-kr-sty25-079`, `...styling-kurta-kr-sty25-084`
  (AED 53.50 against 89.00), `...styling-suits-sk-bsc25-111` and `...styling-waist-coat-wc-sty25-018`
  (AED 101.50 against 169.00), `price_max` is 1.66 times higher. This is not the Hamsa trap (ADR 0012, where
  the low price belonged to a head scarf). Evidence: on all five, `price_max` equals `compare_at_price_max`,
  the pre-sale price of the same garment, and `price` divided by it is 0.601, the same as on every other
  product that is on sale (18 of 32). Read plainly, some sizes are at the 40% sale price and some are still
  at the full price. The search answer lists no variants (the `variants` list is empty on all 40 records), and
  the only product page fetched (`...embroidered-suits-sk-emb25-042`, AED 113.50) has four sizes at one
  price, so the size split is **not confirmed**. What each choice does to the saved answers:

  | `max_price_spread` | Records dropped | Distinct products left |
  |---|---|---|
  | off (chosen) | 0 | 20 |
  | 1 or 1.25 | 7 of 40 (the 5 products; 3 of them reach the shopper today) | 18, under the plan's floor of 20 |
  | 1.7 or 2 | 0 | 20 |

  The cost of leaving it off: a size can cost up to 66% more than the price shown. The benefit: the
  embroidered kurta, the 53.50 kurtas and the waistcoat, which a guard of 1 would remove, stay. If a real
  add-on (a scarf, a set) ever appears as a cheap variant, add the option and change the test that pins
  the file's options. A value of 1.7 would catch a Hamsa-style add-on (their ratios were 2.7 to 4.8) and
  keep every current record; it was not set because no such add-on has been seen here and the option also
  makes every record without `price_min` and `price_max` fail closed.
- **Gender is in `type`.** `type` is "Men" on 27 of 40 records and "Women" on 13, and titles never say. Read
  first, it labels every product (over the 20 distinct products: 14 men, 6 women). The tags agree where they
  name a gender ("Men Suits", "Men Kurta", "Mens Kurta", "Men Waistcoat", "Women Co-Ords"; no
  disagreement on any record) and the women's kurti tag "Kurti" names none, so the tags alone would leave
  the 11 kurtis unlabelled. A test pins both and the filter result: a women's request drops every men's
  product, and a men's request drops every women's one.
- **`genders` is left unset** because the store sells for both (20 men's and 12 women's of 32 products).
- **A men's shalwar kameez is titled "Suits".** "Suit" is deliberately ambiguous in
  `src/vga/rank/lexicon.py` (a South Asian suit here, a men's suit at Sacoor Brothers), so the 9 "Suits" have
  no category and are kept for any request. That is right for the dresses request the store is searched
  for, and it is the reason a shoes or trousers search must not be sent here: it would let a "Suits"
  title through (ADR 0007). A test shows a shoes request keeps them.
- **A women's kurti is titled "Shirt".** The 11 women's kurtis are "Printed Shirt", "Printed Long Shirt" or
  "Printed Embellished Shirt" (tag "Kurti"), and the two-piece set is "Printed Shirt With Embroidered And Dyed
  Trouser" (read up to "With", so a shirt). The ranker reads all 12 as **tops** and drops them from a
  dresses request (`wrong_category`). They show only for a tops request. This is why the store file lists
  both `dresses` and `tops`.
- **A "kurti" search mostly finds men's kurtas.** The query `kurti` returned 7 men's kurtas and only 3
  women's "Printed Shirt" records; the query `printed shirt` returned 10 women's (9 kurtis and the set).
  The lexicon lists "kurti" as a dress word, so a "kurti" request is a dresses request, and the store then
  returns men's kurtas and women's items that the ranker drops. A better women's keyword for this store is "printed shirt" or "shirt".
- **A waistcoat comes back for "shalwar kameez".** "UAE-Regular Fit Styling Waist Coat" (AED 101.50, tag
  "Men Waistcoat", one of the two-price products) is read as outerwear and dropped from a dresses request.
  Outerwear is not in `categories`, so a men's waistcoat search is not sent here. Add `outerwear` if
  waistcoats are wanted (1 of 32 products seen).
- **Sale prices.** 18 of 32 products (23 of 40 records) are about 40% off (`price` is 60.1% of
  `compare_at_price_max`, pre-sale prices AED 69 to 189). All 18 are men's; the women's kurtis have a
  `compare_at_price_max` of `"0.00"`. The adapter uses `price`, what the shopper pays. The prices and the
  `budget` band will rise when the sale ends.
- **Colour is not a field.** It is in the picture file name ("...Color-Sky-Blue...") and in the description
  ("the sky-blue color enhances..."), so `Product.colour` is unset and a colour request cannot rank on it.
- **Some descriptions are damaged.** 7 of the 40 records (6 products) have U+FFFD replacement characters in
  `body` in the store's own response; for "UAE-Regular Fit Styling Kurta KR-STY25-007", 287 of 431
  characters. The adapter does not read `body`.
- **Links carry tracking parameters** (`?_pos=1&_psq=kurta&_psid=...&_ss=e`). They are removed, so every
  product link is `https://uae.gulahmedshop.com/products/<handle>`.
- **Stock is product-level only** (`available`, true for all 40 records).
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0652/2100/1325/`, with a `v=` version
  parameter that is kept.
- **The range is wider than the search answers show.** The saved product page's data lists women's
  "2 Piece Printed Lawn Suit" (AED 89), "3 Piece ... Suit" (AED 109, 289, 329) and similar. No search
  returned them. Their SKUs start `UAE-W-FB-`; whether they are unstitched fabric is not known.
- **Price range seen:** AED 41.50 to 149 (median 91.25). Men's 41.50 to 113.50, women's 79 to 149.
  Tier hint `budget`.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare or Shopify starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (Shopify's older template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/gul-ahmed-uae/` show the expected shape |
| The store moves host (for example to a different subdomain) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| A different market or currency is served from this host | prices silently wrong (the response has no currency, and the page has no JSON-LD to re-check) | The file pins the host and AED; re-check `Shopify.currency` on a product page |
| `type` is renamed or emptied (for example "Men" becomes "Mens Wear") | gender labels fall back to the tags, then to unknown; a women's request may show men's items | The tests that pin 14 men's and 6 women's products fail; update `gender_fields` or the label |
| A cheap add-on appears as a variant of a garment | a wrong, low price (no guard is set) | Add `max_price_spread` (see "Quirks seen") and a test |
| The title gets a design code for every product | fewer products collapse; more reach the shopper | Good news; update the test that pins 20 distinct products |
| The sale ends | prices rise by about two thirds on the men's range; the store may move from `budget` to `mid_range` | Re-check `tier_hint` |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Neither alternative is built: the HTML search page `https://uae.gulahmedshop.com/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested; it would need a `css` extractor, and the
product page has no JSON-LD to read), and the store's agent endpoint named in robots.txt (planned as
Phase 17).

## Observed live

**The live smoke test passed on 2026-10-08.** It ran through `StoreSearchEngine` between 14:35 and 14:38
local time, one store at a time with 15 s between stores, through Cloudflare WARP (see "Unverified"). Three
requests went to this store: `robots.txt` once, `shalwar kameez` and `printed shirt`. Every answer was HTTP
200, with no block or challenge.

| Query | Status | Products kept | Seconds |
|---|---|---|---|
| shalwar kameez | ok | 8 (2 collapsed as the same title and price) | 1.38 |
| printed shirt | ok | 5 (5 collapsed as the same title and price) | 0.95 |

The slowest request took 1.38 s, against the global 6 s timeout (`timeout_s` is not overridden). Response
sizes were not recorded in the live run. The kept counts match the saved answers offline (8 and 5).

The numbers below are from the qualification pass earlier the same day, sent by the orchestrator with the
qualification User-Agent (`vga-shopping-agent-demo/0.1 (store-qualification research)`), robots.txt first,
at least 1 s apart. They went through Cloudflare WARP too, because the machine's own path to Shopify timed
out that day.

| Query | Status | Products returned | Kept after validation | Seconds | Response |
|---|---|---|---|---|---|
| shalwar kameez | HTTP 200 | 10 | 8 | 0.3 | 24,242 bytes |
| kurta | HTTP 200 | 10 | 6 | 0.3 | 22,551 bytes |
| kurti | HTTP 200 | 10 | 7 | 0.2 | 23,152 bytes |
| printed shirt | HTTP 200 | 10 | 5 | not recorded | 26,256 bytes |

- robots.txt: 200, 3,648 bytes on all three fetches. Every search URL and the product page were allowed.
- Requests to the store for the qualification: 8 (robots.txt three times, four searches, one product
  page). The live test used 3 (robots.txt once, `shalwar kameez` and `printed shirt`), with the global
  6 s timeout (`timeout_s` is not overridden).
- **Gender:** `genders` unset; `gender_fields: [type, tags]` set explicitly in the store file. Evidence: `type`
  is "Men" on 27 of 40 records (20 of 32 products) and "Women" on 13 (12 products), with tags that agree.
  Both genders are sold, so the store must stay open to both.
- **Categories:** `categories: [dresses, tops]`. Evidence, by the ranker's own reading of the 32 distinct
  titles: dresses 10 (men's kurtas), tops 12 (women's "Shirt" kurtis and the set), no category 9 (men's
  "Suits"), outerwear 1 (the waistcoat). No trousers, jackets or shoes were seen. A search for any other
  category is therefore not sent to this store; it is listed among the skipped stores as "Not searched: Gul
  Ahmed UAE does not sell shoes." and so on. The options and what each costs:

  | `categories` | Effect |
  |---|---|
  | `[dresses, tops]` (chosen) | Kurtas and suits come from a dresses search, women's kurtis from a tops search. Shoes, trousers and jackets are not sent. A tops search may also return "Suits", which have no category and are kept |
  | `[dresses]` | The 12 women's products are fetched for a dresses search and then dropped by the ranker (`wrong_category`), so the store would show men's wear only |
  | unset | Every category is sent, including shoes and trousers, which the store was not seen to sell; "Suits" have no category and would pass the filter for them (ADR 0007) |

  "Not seen" is not "not sold": four queries, 10 products each, all chosen for the core range. Trousers
  (`shalwar`, `trouser`), `waistcoat`, `suit`, `lawn` and `dupatta` were never queried. If the store turns out
  to sell other garments, edit the line. The store file uses the first row of the table.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, says checkouts are for
humans and must not be completed by an agent without a buyer's approval, and suggests a third-party
shopping skill. This is store-supplied text. The adapter did not follow it: it requested no UCP, MCP,
`agents.md` or `.well-known` URL, installed nothing, and never touches the cart or checkout. The rules
that apply to us are the `User-agent: *` group, which opens with `Allow: /` and does not disallow `/search`.
The stated preference for the agent endpoint is for the terms review and for Phase 17.

## Unverified

- Behaviour from the machine's own network: every request went through Cloudflare WARP, the live smoke
  test included. The direct path to Shopify timed out from about 13:00 that day, and no store ever
  answered with a refusal.
- Response sizes in the live run (not recorded).
- Whether the two-price products are sizes at sale and full price; the variants are not in the answer.
- Women's 2 and 3 piece suits seen only on the product page, and whether they are unstitched.
- Queries other than the four: `suit`, `lawn`, `waistcoat`, `shalwar`, `trouser`, `jacket`, `shoes`.
- The HTML search page, the bare domain `gulahmedshop.com`, pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched).
- Per-size stock. Whether the sale is permanent.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
