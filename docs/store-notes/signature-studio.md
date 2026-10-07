# Signature Studio: store notes

Adapter notes for plan feature 12.x.4. Written 2026-10-08, after the live smoke test.

- Store id `signature-studio`, shown to shoppers as "Signature Studio". Storefront
  `https://www.signaturestudio.ae/`.
- Config: `config/stores/signature-studio.yaml`. Tests and fixtures: `tests/stores/signature-studio/`.
- Qualification (2026-10-08): `docs/store-qualification/signature-studio.md`; the dress and modest-wear
  pass it belongs to: `docs/store-qualification/dress-store-discovery.md`.
- **Status: built, held disabled.** The live smoke test passed on 2026-10-08 (see "Observed live
  today"), but the file says `enabled: false` until the store set for the demo is decided.
- **This adapter needed one change to shared code.** The `shopify` extractor now reads the words
  `menswear` and `womenswear` as gender cues (`src/vga/stores/extractors/shopify.py`); see "Gender".

## Data path

1. The engine checks `https://www.signaturestudio.ae/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://www.signaturestudio.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string such as
   `"1838.00"` or `"554.40"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`),
   `url` (made absolute on `www.signaturestudio.ae`, tracking query removed), `available`, and the
   gender from `type` then `tags` (`gender_fields: [type, tags]`, which is also the default).
   Validation then drops any record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: AED` comes from the store file. AED was
   confirmed on 2026-10-08 from the product page's JSON-LD (`priceCurrency: "AED"`) and
   `Shopify.currency`, not from the search response.

`vendor` (the designer label), `compare_at_*` and `body` are not mapped. `body` is store-supplied
HTML and must never be rendered.

## Gender

- **`genders` is unset.** The store sells women's designer wear and men's kurta sets (10 of the 40
  qualification records, all from one label, KUNZUL CHANNAR).
- **`type` is "Clothing" on every record**, so it names no gender, and the tag `Buy Dresses` is on
  every record too. The only gender sign in any field is the tag **`Menswear`** on the men's kurta
  sets. Women's items carry no gender tag whatsoever.
- **The extractor did not read that word.** Its cue list had `man`, `men`, `mens` and so on, and
  `menswear` is a different word, so with the extractor as it was all ten men's sets would have come
  out with an unknown gender and a woman's search for a kurta set would have been shown men's kurta
  trousers. The fix is two entries in the extractor's cue table, `menswear` and `womenswear`, resolved
  by the same rules as the others (the first of `type`, `tags` that names a gender decides; a field that
  names both gives unknown). Other "-wear" words (`Formalwear`, `Swimwear`) are still not cues. No
  recorded response of the other six stores holds either word, so their results did not change. Tests:
  `tests/fetch/test_shopify_gender.py` (the word cases) and `tests/stores/signature-studio/` (the
  real men's sets).
- Result on the fixtures (28 records): 4 men's (all four men's sets in the sample), 24 unknown (the
  women's records, and the abaya-sample pieces). Unknown is not a verdict: the ranker reads the title.

## Categories

- **`categories: [dresses]`.** The 40 qualification records are designer kaftans, dresses, "dress
  saree" and Kaftaan pieces, co-ord and formal sets (some with a dupatta or trousers inside the set)
  and men's kurta-trouser sets; `type` is "Clothing" on all of them. All of these are dress-category
  garments (kurtas and sets count as dresses, BRD assumption A23); no shoes, jeans, tops, jackets or
  separately sold trousers were seen. A search for any other category is therefore not sent to this
  store, and it is listed among the skipped stores as "Not searched: Signature Studio does not sell
  shoes." and so on. "Not seen" is not "not sold" (10 products per query): if the store turns out to
  sell other garments, remove the line.

## Quirks seen

- **A multi-brand designer store.** `vendor` is the designer label and the title repeats it ("HAFSA
  MALIK - Noor Jahan", "WAJEEHA ANSARI- Kaftan"), with the label's capitals and the dash spacing
  varying. The adapter passes the whole title on. Showing the label apart from the name is a display
  choice for later (the `name_field` option cannot do it).
- **A fuzzy search.** The `abaya` word returned pret and formal pieces with names like Aysal, Maya
  and Amaya, none an abaya (qualification sample). `kaftan` returned kaftans from 7 labels (AED 419 to
  1,194 in today's answer) and `dress` returned a wedding set, formal dresses, a printed dress, "Kaftaan"
  dresses and "Dress Saree" sets. `type` and the main tag cannot separate any of these: category has
  to come from the title and text.
- **No women's kurtas for the word `kurta`.** All ten results of the qualification `kurta` query were
  men's kurta trouser sets (AED 289 to 368). A search result title elsewhere ("AMNA IQBAL- Beige floral
  kurta set") shows women's kurta sets exist; `kurta set`, `suit` and `3 piece` were not queried.
- **Titles can end with a no-break space** ("MANTO - Deedar Dress Kaftaan Beige" +
  U+00A0) **and contain double spaces** ("Midnight  mirage", "MANTO  - Mehru"). Validation trims and
  collapses them; tests pin it.
- **Prices have fractions** (AED 554.40, 1,843.34 in the qualification pass), so they look computed;
  the `price` string is still the amount shown. The plain `"1838.00"` form is the common one.
- **Few sales.** 2 of the 20 recorded records carry a pre-sale price (Noor Jahan 2,625 against 1,838,
  Pink Printed 474 against 403); the rest have `"0.00"`. The adapter uses `price`. The price band is
  steadier than at the stores on a store-wide sale.
- **Links carry tracking parameters** (`?_pos=1&_psq=dress&_psid=...&_ss=e`). They are removed, so
  every product link is `https://www.signaturestudio.ae/products/<handle>`. A handle does not always
  match the title ("HAFSA MALIK - Seraphine" is `hafsa-malik-jade-copy`).
- **Stock is product-level only** (`available`, true for all 20 records recorded today). Colour is in
  the title for some pieces ("Beige", "Maroon") and in the description for a few.
- **Images** are on `cdn.shopify.com` under `/s/files/1/0549/4394/`, as `.jpg` and `.webp`, with a `v=`
  version parameter that is kept.
- **Slow robots.txt once.** The qualification pass saw robots.txt take 3.7 s; both runs today took under
  2 s including the rate-limit wait. The global 6 s timeout covers it, with less margin than the others.
- **Price range seen:** AED 174 to 2,753 (median 589 in the qualification pass; today's answers 174 to
  2,753). Tier hint `mid_range`, with a luxury tail above AED 1,200.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (Shopify's older template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/signature-studio/` show the expected shape |
| The apex `signaturestudio.ae` becomes canonical, or the store moves host | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| A different market or currency is served from this host | prices silently wrong (the response has no currency) | The file pins the host and AED; re-check the product page JSON-LD |
| The `Menswear` tag is renamed or dropped | men's kurta sets lose their gender label | The test that pins the four men's sets fails; update the tag word or the extractor cue |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The `shopify` extractor's cue list changes | the men's sets read as unknown again | The same test fails |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Neither alternative is built: the HTML search page `https://www.signaturestudio.ae/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested; it would need a `css` or
`json_ld` extractor), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| dress | ok | 10 | 10 | 1.62 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.36 | 22,092 bytes |
| kaftan | ok | 10 | 10 | 0.97 | 1.07 | 19,180 bytes |

- robots.txt: 200, 3,656 bytes, identical to the file saved in the qualification pass. Every search URL
  was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail was fetched. The timeout is the global 6 s (`timeout_s` is not
  overridden); the slowest query took 1.62 s.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and suggests a
third-party shopping skill. This is store-supplied text. The adapter did not follow it: it requested
no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never touches the cart or
checkout. The rules that apply to us are the `User-agent: *` group, which opens with `Allow: /` and
does not disallow `/search`. The stated preference for the agent endpoint is for the terms review
and for Phase 17.

## Unverified

- The apex host `signaturestudio.ae` and where it redirects.
- Pagination and `limit` above 10.
- Women's kurta-set keywords (`kurta set`, `suit`, `3 piece`): not queried.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- Whether `Menswear` is on every men's piece of the store: it is on all 10 men's sets of the
  qualification pass (4 of them saved as fixtures) and on no women's item in the 40 records seen. No
  men's query other than `kurta` was run.
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
