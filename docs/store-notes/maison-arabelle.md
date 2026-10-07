# Maison Arabelle: store notes

Adapter notes for plan feature 12.x.4. Written 2026-10-08, after the live smoke test.

- Store id `maison-arabelle`, shown to shoppers as "Maison Arabelle". Storefront
  `https://maisonarabelle.com/`.
- Config: `config/stores/maison-arabelle.yaml`. Tests and fixtures: `tests/stores/maison-arabelle/`.
- Qualification (2026-10-08): `docs/store-qualification/maison-arabelle.md`; the dress and modest-wear
  pass it belongs to: `docs/store-qualification/dress-store-discovery.md`.
- **Status: built, held disabled.** The live smoke test passed on 2026-10-08 (see "Observed live
  today"), but the file says `enabled: false` until the store set for the demo is decided.

## Data path

1. The engine checks `https://maisonarabelle.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://maisonarabelle.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string such as
   `"1800.00"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made
   absolute on `maisonarabelle.com`, tracking query removed) and `available`. Validation then drops
   any record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: AED` comes from the store file. AED was
   confirmed on 2026-10-08 from the product page's JSON-LD (`priceCurrency: "AED"`) and
   `Shopify.currency`, not from the search response.

`vendor`, `type`, `tags`, `compare_at_price_*` and `body` are not mapped; `type` and `tags` are read
only for the product's gender (they name none here). `body` is store-supplied HTML and must never be
rendered. No extractor option is set: the defaults suit this store.

## Quirks seen

- **A single luxury house with one garment family.** Every record is a kaftan, an abaya or a
  one-piece dress in the same collection (`type: "Kaftans and Abayas"` on all 28 records in the
  fixtures). There are no kurtas, shoes or trousers: a `kurta` query returned 9 kaftans and an abaya in
  the qualification pass. Ranking must filter by category rather than trust the store's order.
- **`compare_at_price_max` is unreliable. Never read it as a discount.** In the `dress` answer of
  2026-10-08, MARWA WHITE has `price` 1040.00 with compare-at 890.00, SHAMAA has 980.00 with 790.00, and
  SHIMMER has 1600.00 with 1600.00: a struck-through price at or below the price. The other 17 records
  in the two recordings have `"0.00"`. The adapter uses `price` and never reads the compare-at field,
  so a test pins that the three pieces keep their `price`.
- **Many titles are only a name.** MARWA WHITE, SHIMMER, SHAMAA, MAYRA BLACK, BADER LINEN NAVY BLUE and
  CHARLOTTE BLUSH PINK say neither kaftan nor abaya, and `type` is identical on every record, so the
  garment kind has to come from the ranker's reading of the title and text. Titles are upper case and
  can carry the store's own typos ("LARA GRAY EMBROIREDED ABAYA"); the adapter passes them on as
  written.
- **A named abaya can be a three-piece set.** The description of the Lara grey abaya says the set holds
  an open abaya, an inner dress and a matching sheila. The search record has one price, which is the
  price of the whole set.
- **`vendor` is spelled two ways** ("MAISON ARABELLE" and "Maison Arabelle", mixed within one answer).
  It is not mapped; the shopper sees the name from the store file.
- **`tags` are empty on most records** (`["OUR CURATED PICKS"]` on a few). Nothing in `type` or `tags`
  names a gender, so the extractor leaves every product's gender unknown and `genders: [women]` in the
  store file does the work.
- **Links carry tracking parameters** (`?_pos=1&_psq=dress&_psid=...&_ss=e`). They are removed, so
  every product link is `https://maisonarabelle.com/products/<handle>`.
- **Stock is product-level only** (`available`, true for all 20 records recorded today). A requested
  size can still be sold out. Colour is in the title for most pieces and in the description as
  "Colour: ..." for some.
- **The same product answers two queries.** Two abayas (Lara grey, Charlotte off-white) were in both the
  `dress` and the `abaya` answer; the engine collapses repeats within one search, so a two-variant
  search gives 18 distinct products, not 20 (the qualification pass saw 32 distinct handles in 40
  records over four queries).
- **Images** are on `cdn.shopify.com` under `/s/files/1/0747/8444/`, both `.jpg` and `.png`, with a `v=`
  version parameter that is kept. A search result for this domain once had a non-Shopify shape
  (`/en/item/zarina-orx0353mh8`, title "ZARINA-Maison Arabelle Trading LLC") in the qualification pass; it
  never appeared in the suggest answers and was not requested.
- **Descriptions contain pasted markup** (long utility class names inside a `<section>` tag in one
  record, apparently copied from a web app). They are cut to 300 characters in the fixtures and are
  never rendered.
- **Price range seen:** AED 790 to 2,400 (dress answer 790 to 1,800, abaya answer 1,200 to 2,400).
  Tier hint `luxury`.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| The owner edits the hand-written robots.txt to `Disallow: /search` (it is a custom file, not Shopify's default) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/maison-arabelle/` show the expected shape |
| The store moves to another host (for example `www.maisonarabelle.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| A different market or currency is served from `maisonarabelle.com` | prices silently wrong (the response has no currency) | The file pins the host and AED; re-check the product page JSON-LD |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| Search starts returning fewer than 10 products or ignores the limit | fewer candidates | Nothing breaks; fewer results from this store |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Neither alternative is built: the HTML search page `https://maisonarabelle.com/search?q=`
(allowed by robots.txt per protego on 2026-10-08, never requested; it would need a `css` or
`json_ld` extractor).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| dress | ok | 10 | 10 | 1.76 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.55 | 26,700 bytes |
| abaya | ok | 10 | 10 | 0.82 | 0.84 | 44,964 bytes |

- robots.txt: 200, 445 bytes, identical to the file saved in the qualification pass. Every search URL
  was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail was fetched. The timeout is the global 6 s (`timeout_s` is not
  overridden); the slowest query took 1.76 s.
- **Gender:** `genders: [women]`. Evidence: the 20 records recorded today and the 40 of the
  qualification pass are all kaftans, abayas or one-piece dresses from one women's atelier; no title
  or tag names a gender. The data carries no gender field, so this rests on the range and the brand.
  A men's request is therefore not sent to this store.

## robots.txt (data, not acted on)

A 445-byte hand-written file, not Shopify's default. The `*` group closes `/admin`, `/cart`,
`/orders`, `/checkouts/`, `/checkout`, `/cgi-bin`, `/wp-admin` and `/wp-login.php` and then says
`Allow: /`; `/search/suggest.json` is therefore allowed (protego). Named groups for GPTBot, ClaudeBot,
PerplexityBot and Google-Extended each allow everything; our User-Agent is not one of them. The file has
no comment block addressed to AI agents and the adapter requested no agent, UCP or MCP URL. It ends with
a `Content-Signal` line: `ai-train=yes, search=yes, ai-retrieval=yes, ai-personalization=no`. That is a
statement about AI use of the content, not an Allow or Disallow rule, and it took no part in the
robots decision. For the terms review: the demo shows the store's own listing live and does not train on
it, which falls under "search" and "ai-retrieval"; whether tailoring a result list to a shopper's photo
counts as "ai-personalization" is a question for that review, not something this note decides.

## Unverified

- Pagination and `limit` above 10; the `www` host; the `/en/item/` path form.
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- Whether the store sells anything for men (nothing was seen; the `women` setting rests on that).
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
