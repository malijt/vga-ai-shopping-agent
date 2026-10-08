# Nishat Linen UAE: store notes

Adapter notes for plan feature 12.x.4. Written 2026-10-08, after the live smoke test.

- Store id `nishat-linen-uae`, shown to shoppers as "Nishat Linen UAE". Storefront
  `https://www.nishatlinenuae.com/`.
- Config: `config/stores/nishat-linen-uae.yaml`. Tests and fixtures: `tests/stores/nishat-linen-uae/`.
- Qualification (2026-10-08): `docs/store-qualification/nishat-linen-uae.md`; the dress and modest-wear
  pass it belongs to: `docs/store-qualification/dress-store-discovery.md`.
- **Status: enabled.** The live smoke test passed on 2026-10-08 (see "Observed live today"), and
  the store was enabled the same day when the user raised the store limit (plan A25).

## Data path

1. The engine checks `https://www.nishatlinenuae.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://www.nishatlinenuae.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string such as
   `"79.50"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute
   on `www.nishatlinenuae.com`, tracking query removed), `available`, and the product's gender from
   `type` then `tags` (`gender_fields: [type, tags]`, which is also the default). Validation then drops
   any record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: AED` comes from the store file. AED was
   confirmed on 2026-10-08 from the product page's JSON-LD (`priceCurrency: "AED"`) and
   `Shopify.currency`, not from the search response.

`vendor` (a season or collection label such as "Aura-Summer-2026-July", not the brand), `compare_at_*`
and `body` are not mapped. `body` is store-supplied HTML and must never be rendered.

## Quirks seen

- **Titles are a garment word plus a code** ("Printed Dress - AS26-92", "2 Piece - Embroidered Gown -
  FE26-128"). No brand, no colour, no gender word. A name-based ranker has "Printed Dress",
  "Embroidered Kaftan" and the like to work with. The `vendor` field is a season label, so `title` stays
  the name.
- **Colour is only in the description**, written "Color: Brown" inside the HTML `body`. It is not a
  field, so `Product.colour` is unset. (The fixtures cut `body` to 300 characters; the colour is inside
  that cut for the kurtas and not for the dresses.)
- **The whole range was at 50% off on 2026-10-08.** `compare_at_price_max` is exactly twice `price` on
  every one of the 28 records in the fixtures (and on 38 of 39 in the qualification pass). The adapter
  uses `price`, the sale price, so the prices and the `budget` band will rise when the sale ends.
- **The `kurta` word finds only men's kurtas.** All ten results of the `kurta` query were type
  `RTW Men` (AED 39.50 to 114.50). The women's embroidered sets are filed as Fustan, Aura and Luxury Pret
  and are not found by that word; a women's "kurta set" request needs another keyword (`suit`,
  `embroidered`, `dress`), which was not tested. Do not read an empty women's answer to `kurta` as a
  dead store.
- **Gender comes from `type` first.** Men's items have `type: "RTW Men"`, which names men, so all 10
  `kurta` results are labelled men's. Women's items have type "Fustan", "Fustaan", "Aura" or "Luxury
  Pret" (no gender word); the tag `Women` is on **some** of them (7 of 10 in the `dress` answer; the
  three without it are a printed, an embroidered and a basic dress). Those get no gender and the
  ranker reads their titles. Nothing labels a women's dress as men's. Over the 28 fixture records:
  12 women, 10 men, 6 unknown.
- **`genders` is left unset** because the store sells for both (10 of the 40 qualification records are
  men's kurtas). A men's request still reaches the store and finds the kurtas.
- **The same title can belong to two products.** "Basic Kurta - NQ26-010" appears twice in the `kurta`
  answer, at AED 39.50 (handle `nq26-028`, tagged `men-bottoms`) and AED 64.50 (handle `nq26-010`). They
  differ in link and price, so both are kept.
- **Women's long dresses, kaftans, gowns and suits.** The `dress` answer is ten long dresses (printed,
  solid, embroidered) at AED 59.50 to 129.50; the qualification `kaftan` answer is eight kaftans and
  two dresses (AED 84.50 to 239); `abaya` returns no abayas and is padded with dresses, a gown and
  2-piece suits (AED 69.50 to 164.50).
- **Links carry tracking parameters** (`?_pos=1&_psq=dress&_psid=...&_ss=e`). They are removed, so
  every product link is `https://www.nishatlinenuae.com/products/<handle>`.
- **Stock is product-level only** (`available`, true for all 20 records recorded today). Sizes are
  listed as tags (`XS`, `S`, `M`, `L`), not as stock.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0283/9766/`, with a `v=` version parameter
  that is kept. The product page's own JSON-LD uses `www.nishatlinenuae.com/cdn/shop/...` instead;
  search results do not.
- **Price range seen:** AED 39.50 to 239 (sale prices). Tier hint `budget`.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (Shopify's older template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/nishat-linen-uae/` show the expected shape |
| The apex `nishatlinenuae.com` becomes canonical, or the store moves host | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| A different market or currency is served from this host | prices silently wrong (the response has no currency) | The file pins the host and AED; re-check the product page JSON-LD |
| The `type` or `tags` convention changes (for example `RTW Men` is renamed) | men's kurtas lose their gender label, a women's request may show them | The tests that pin 10 of 10 `kurta` results as men's fail; update the store's `gender_fields` or the label |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The sale ends | prices roughly double; the store may move from `budget` to `mid_range` | Re-check `tier_hint` |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Neither alternative is built: the HTML search page `https://www.nishatlinenuae.com/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested; it would need a `css` or `json_ld`
extractor), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| dress | ok | 10 | 10 | 1.74 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.34 | 19,090 bytes |
| kurta | ok | 10 | 10 | 0.94 | 1.02 | 16,682 bytes |

- robots.txt: 200, 3,656 bytes, identical to the file saved in the qualification pass. Every search URL
  was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail was fetched. The timeout is the global 6 s (`timeout_s` is not
  overridden); the slowest query took 1.74 s.
- **Gender:** `genders` unset; `gender_fields: [type, tags]` set explicitly in the store file. Evidence:
  the `kurta` answer is 10 of 10 `RTW Men`, and the `dress` answer is 10 of 10 women's long dresses,
  7 of them tagged `Women`. Both genders are sold, so the store must stay open to both.
- **Categories:** `categories: [dresses]`. Evidence: the 40 qualification records are long dresses,
  kaftans, a gown, 2- and 3-piece suits and men's kurtas, all of them dress-category garments (kurtas
  and sets count as dresses, BRD assumption A23); no shoes, jeans, tops or jackets were seen. A search
  for any other category is therefore not sent to this store, and it is listed among the skipped
  stores as "Not searched: Nishat Linen UAE does not sell shoes." and so on. **One caveat:** the men's
  "Basic Kurta - NQ26-010" at AED 39.50 (handle `nq26-028`, tag `men-bottoms`) is a shalwar, men's
  trousers sold as part of the ready-to-wear range, and the store also lists unstitched fabric. Its
  title says kurta, so it ranks as a dress, but a men's trousers search is not sent here. If trousers
  from this store are wanted, remove the line.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and suggests a
third-party shopping skill. This is store-supplied text. The adapter did not follow it: it requested
no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never touches the cart or
checkout. The rules that apply to us are the `User-agent: *` group, which opens with `Allow: /` and
does not disallow `/search`. The stated preference for the agent endpoint is for the terms review
and for Phase 17.

## Unverified

- The apex host `nishatlinenuae.com` and where it redirects.
- Pagination and `limit` above 10.
- Women's keywords for South Asian sets (`suit`, `3 piece`, `embroidered`): not queried.
- Whether the 50% sale is permanent.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
