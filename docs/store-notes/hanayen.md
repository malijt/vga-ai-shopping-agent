# Hanayen: store notes

Adapter notes for plan feature 12.x.4. Written 2026-10-08, after the live smoke test.

- Store id `hanayen`, shown to shoppers as "Hanayen". Storefront `https://hanayen.com/`.
- Config: `config/stores/hanayen.yaml`. Tests and fixtures: `tests/stores/hanayen/`.
- Qualification (2026-10-08): `docs/store-qualification/hanayen.md`; the dress and modest-wear pass it
  belongs to: `docs/store-qualification/dress-store-discovery.md`.
- **Status: enabled.** The live smoke test passed on 2026-10-08 (see "Observed live today"), and
  the store was enabled the same day when the user raised the store limit (plan A25).

## Data path

1. The engine checks `https://hanayen.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://hanayen.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string such as
   `"675.00"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made
   absolute on `hanayen.com`, tracking query removed) and `available`. Validation then drops any
   record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: AED` comes from the store file. AED was
   confirmed on 2026-10-08 from the product page's JSON-LD (`priceCurrency: "AED"`) and
   `Shopify.currency`, not from the search response.

`vendor` ("Hanayen" on every record), `type`, `tags` and `body` are not mapped, except that `type`
and `tags` are read for the product's gender (they name none here, see below). `body` is
store-supplied HTML and must never be rendered. No extractor option is set: the defaults suit this
store (name from `title`, image width 400).

## Quirks seen

- **A single brand of abayas.** Every record is an abaya, an under-abaya "inner" dress or a sheila.
  There are no kurtas, no kaftans as a garment, no shoes and no trousers. A `kaftan` or `kurta` query is
  padded with abayas and inners, so ranking must filter by category rather than trust the store's order.
- **Sheilas (head scarves) come back for generic queries.** The `kaftan` answer on 2026-10-08 held
  four of them (type `SHEILA`, tag `Sheila`, AED 120 to 290, titles such as "Black Chiffon Sheila –
  Custom Size"). A sheila is an accessory, out of scope. **The adapter does not drop them** and has no
  store-specific rule for them: another change makes the ranking lexicon drop accessories such as
  sheilas for every store. A test pins that the adapter still hands them over.
- **Inner dresses.** Plain slip dresses worn under an abaya (AED 250 to 275, tag `Inner`, titles such as
  "Off-White Plain Inner") are filed under `type: "Abaya"` like the outer abayas, so `type` cannot
  separate them; the tag `Inner` and the title can. They answer `dress` and `kurta` queries. A
  "Kaftan Style Under Abaya" (AED 850) is one of them, not a kaftan.
- **"Dress" in a title can mean an abaya.** The `dress` qualification answer was 10 abayas styled as
  dresses ("Abaya Dress Embroidered Design", "Modern Modest Dress"), AED 385 to 5,550. `type` is
  `Abaya` on all of them.
- **Sale prices.** `price` is what the shopper pays. `compare_at_price_max` is the struck-through
  price (`"900.00"` against `"675.00"` for the Modern A-Line Lapel Abaya), `"0.00"` when there is none.
  The adapter uses `price`. 6 of 10 records in the `abaya` answer and 4 of 10 in the `kaftan` answer
  carried a compare-at price, so the prices move when a promotion ends.
- **Links carry tracking parameters** (`?_pos=1&_psq=abaya&_psid=...&_ss=e`). They are removed, so
  every product link is `https://hanayen.com/products/<handle>`.
- **Gender is in no field.** Nothing in `type` or `tags` names a gender (the tags are words such as
  `Abaya`, `Best Selling`, `BLACK`, `Eid`), so the extractor leaves every product's gender unknown.
  `genders: [women]` in the store file is what keeps a men's request away from this store.
- **Stock is product-level only** (`available`, true for all 20 records recorded today).
  A requested size can still be sold out. Colour appears in the title ("Green Abaya ...") or as a tag
  (`BLACK`, `Brown`, `OFF WHITE`), not in a structured field.
- **The same product answers two queries.** 3 of the 10 `kaftan` products were also in the `abaya`
  answer; the engine collapses repeats within one search, so a two-variant search gives 17 distinct
  products, not 20.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0528/4682/` (`/files/` or `/products/`
  below it), with a `v=` version parameter that is kept. The product page's own JSON-LD uses
  `hanayen.com/cdn/shop/...` instead; search results do not.
- **Price range seen:** AED 120 (sheila) to 5,550 (qualification pass); in the two recorded answers
  AED 120 to 4,500, outer abayas AED 600 to 4,500. Tier hint `premium`.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (the older Shopify template does; four other abaya stores in the qualification pass had it) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/hanayen/` show the expected shape |
| The store serves the `/en-us/` Shopify Markets path or another currency from `hanayen.com` | prices silently wrong (the response has no currency) | The file pins `hanayen.com` and AED; re-check the product page JSON-LD |
| The store moves to another host (for example `www.hanayen.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| Search starts returning fewer than 10 products or ignores the limit | fewer candidates | Nothing breaks; fewer results from this store |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://hanayen.com/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested; it would need a `css` or `json_ld`
extractor), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| abaya | ok | 10 | 10 | 1.38 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.36 | 21,260 bytes |
| kaftan | ok | 10 | 10 | 0.95 | 1.05 | 19,949 bytes |

- robots.txt: 200, 3,612 bytes, identical to the file saved in the qualification pass. Every search URL
  was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail was fetched. The timeout is the global 6 s (`timeout_s` is not
  overridden); the slowest query took 1.38 s.
- **Gender:** `genders: [women]`. Evidence: the 20 records recorded today and the 40 of the
  qualification pass are all abayas, under-abaya dresses or sheilas, which are women's garments; no
  title or tag in the recorded answers names a gender. The data itself carries no gender field, so
  this rests on the range and the brand, as for Oh Polly. A men's request is therefore not sent to
  this store.
- **Categories:** `categories: [dresses]`. Evidence: the 40 qualification records and the 20 recorded
  today are abayas, under-abaya dresses and sheilas (accessories, out of scope); no shoes, trousers,
  tops or jackets were seen. A search for any other category is therefore not sent to this store (it
  would only waste a request, and an abaya's title often names no garment, so it would pass the
  category filter for any request). Listed among the skipped stores as "Not searched: Hanayen does not
  sell shoes." and so on. "Not seen" is not "not sold": if the store adds other garments, remove the
  line.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and suggests a
third-party shopping skill. This is store-supplied text. The adapter did not follow it: it requested
no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never touches the cart or
checkout. The rules that apply to us are the `User-agent: *` group, which opens with `Allow: /` and
does not disallow `/search`. The stated preference for the agent endpoint is for the terms review
and for Phase 17.

## Unverified

- The `/en-us/` path prefix (a Shopify Markets path seen in search results) and its currency.
- Pagination and `limit` above 10.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- Whether the store sells anything for men (nothing was seen; the `women` setting rests on that).
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
