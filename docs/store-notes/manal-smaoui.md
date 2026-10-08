# Manal Smaoui: store notes

Adapter notes for plan module 12.13. Written 2026-10-08, after the live smoke test.

- Store id `manal-smaoui`, shown to shoppers as "Manal Smaoui". Storefront
  `https://manalsmaoui.com/`.
- Config: `config/stores/manal-smaoui.yaml`. Tests and fixtures: `tests/stores/manal-smaoui/`.
- Qualification (2026-10-08): `docs/store-qualification/manal-smaoui.md`; the designer-brand pass it
  belongs to: `docs/store-qualification/designer-store-qualification.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`.
- **Status: enabled.** The live smoke test passed on 2026-10-08 (see "Observed live today"), and every
  record carries a single price, so the default price rule is exact here (see "Price").

## Data path

1. The engine checks `https://manalsmaoui.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://manalsmaoui.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three decimals,
   `"85.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made absolute
   on `manalsmaoui.com`, tracking query removed) and `available`. Validation then drops any record that
   lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was confirmed on
   2026-10-08 from the product page's JSON-LD (`priceCurrency: "KWD"` on all five size offers),
   `og:price:currency` and `Shopify.currency`. A currency-converter widget on the page lists AED among
   other currencies, but that is a script-driven display tool: the server-rendered prices are KWD and
   no AED URL exists.

`vendor` ("MANAL SMAOUI" on every record), `type`, `tags` (empty on all 20 records) and `body` are not
mapped, except that `type` and `tags` are read for the product's gender (they name none). `body` is
store-supplied HTML and must never be rendered. No extractor option is set: the defaults suit this
store (name from `title`, image width 400).

## Price

- **Three decimals.** Prices are Kuwaiti dinars written with the fils: `"85.000"`. The price parser
  accepts three decimals only for a store whose currency is KWD, BHD or OMR (ADR 0006), so for this
  store `85.000` is KWD 85. A price written with two decimals would be refused as an unknown format.
- **One price per record.** On all 20 records recorded today `price`, `price_min` and `price_max` are
  equal and `variants` is an empty list, so there is no cheaper add-on variant that `price` could pick
  up (the trap at Hamsa). A test pins this: if the store ever lists variants at different prices, the
  test fails and the price rule (`max_price_spread`) needs a second look.
- **No sale today.** `compare_at_price_max` is `"0.000"` on all 20 records. The adapter uses `price`.
- **Shopper-facing figure.** The page shows the dinar price and an approximate dirham figure from the
  fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED), for example `85.000 KWD (about 1,010
  AED)`. Ranges and any budget use the dirham figure.
- **Range seen:** KWD 29 to 85 for garments, about AED 350 to 1,010 (dress 55, kaftan 85, trousers 29,
  skirts 32, blazer 35, top 29), plus a KWD 5 headband. Tier hint `mid_range`: the one set of dinar
  prices that sits in the range of the existing Nautica, Oh Polly and Sacoor Brothers.

## Quirks seen

- **`type` is a collection label, not a garment type.** "EID COLLECTION", "BLACK SETS", "BABY PINK
  SETS", "WHITE SETS", "KAFTANS". It names no category, so the category comes from the title
  ("DRESS", "KAFTAN", "PANTS", "SKIRT", "TOP", "BLAZER"). That is why the store file sets **no
  `categories`**: the store sells dresses and kaftans (dresses), a blazer (outerwear), trousers and
  skirts (bottoms) and a top (tops), so a search for any of those goes to it. A test pins that the
  ranker reads every title this store returned into the right category.
- **A headband comes back.** "HEADBANDS" (KWD 5, `type` "KAFTANS") is in both answers. It is an
  accessory, out of scope. **The adapter does not drop it** and has no store-specific rule for it: the
  ranking lexicon drops accessories such as headbands for every store. A test pins that the adapter
  still hands it over and that the ranker classifies it as out of scope.
- **The store pads its answers.** For `dress` only 2 of 10 results are dresses; for `kaftan`, 3 of 10
  are kaftans (one colour each); the rest are trousers, skirts, a top, a blazer and the headband.
  Ranking must filter by category rather than trust the store's order.
- **A small catalogue.** 13 distinct products over the two queries: the same pieces answer both words
  (7 of the 20 records were repeats, which the engine collapses). A third query would likely show
  little more.
- **Handles do not always match titles.** "THE MUSE SKIRT - BABY PINK" is
  `/products/the-muse-skirt-striped-grey`, "THE MUSE PANTS - BABY PINK" is
  `/products/the-f-w-pants-only-baby-pink` and "AICHA KAFTAN - BABY BLUE" is
  `/products/aicha-kaftan-royal-blue`. The link is always the store's own `url`, never rebuilt from
  the title; a test pins all three.
- **Titles mix upper and mixed case** ("THE BELLE DRESS - BLACK (LIMITED EDITION)", "The Ladylike
  Blazer - White"); the colour follows a dash.
- **Links carry tracking parameters** (`?_pos=1&_psq=kaftan&_psid=...&_ss=e`). They are removed, so
  every product link is `https://manalsmaoui.com/products/<handle>`.
- **Gender is in no field.** `type` and `tags` carry collection labels or nothing, never a gender, so
  the extractor leaves every product's gender unknown. `genders: [women]` in the store file is what
  keeps a men's request away from this store.
- **Stock is product-level only** (`available`, true for all 20 records). The qualification pass saw
  per-size stock on a product page (the sampled kaftan had in-stock and out-of-stock sizes).
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0682/5885/7253/` (`/files/`), with a `v=`
  version parameter that is kept. The product page's own JSON-LD image is malformed
  (`https:files/...`); search results are not.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (an older Shopify template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/manal-smaoui/` show the expected shape |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| The store adds variants priced differently (add-ons, sets) | the price test that pins one price per record fails | Apply the price rule used for Hamsa (`max_price_spread`) |
| The store serves another currency from `manalsmaoui.com` (the `/en-sa/` market path exists) | prices silently wrong (the response has no currency) | The file pins the host and KWD; re-check the product page JSON-LD |
| The store moves to another host (for example `www.manalsmaoui.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The store starts selling shoes, or men's wear | shoes or a men's request are not searched here, or men's items appear unlabelled | Edit `genders` in the store file (it rests on the range and the brand) |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page
`https://manalsmaoui.com/search?q=` (allowed by robots.txt per protego in the qualification pass,
never requested), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| dress | ok | 10 | 10 | 1.36 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.28 | 11,546 bytes |
| kaftan | ok | 10 | 10 | 0.90 | 0.97 | 11,091 bytes |

- robots.txt: 200, 3,628 bytes, byte for byte the file saved in the qualification pass. Every search
  URL was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail and no product page was fetched. The timeout is the global 6 s
  (`timeout_s` is not overridden); the slowest query took 1.36 s.
- **Gender:** `genders: [women]`. Evidence: all 13 distinct products recorded today are women's pieces
  by name and by range (kaftans, "The Belle Dress", "The Ladylike Blazer", skirts, trousers, a top, a
  headband); no title, type or tag names a gender. The data carries no gender field, so this rests on
  the range and the brand (a Kuwaiti women's ready-to-wear label), as for Hanayen and Oh Polly. A men's
  request is therefore not sent to this store.
- **Categories:** not set. Evidence: the 13 distinct products are 5 dresses and kaftans, 5 trousers and
  skirts, 1 top and 1 blazer, plus the headband; `type` is a collection label. Four of the five
  categories (dresses, bottoms, tops, outerwear) are sold, so a `categories` line listing them would
  rule out only shoes, which is "not seen" rather than "not sold" with only 13 products known. The
  store is therefore searched for every category. Add a `categories` line if a larger recording shows
  the range is narrower.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and suggests a
third-party shopping skill. This is store-supplied text. The adapter did not follow it: it requested
no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never touches the cart or
checkout. The rules that apply to us are the `User-agent: *` group, which opens with `Allow: /` and
does not disallow `/search`. The stated preference for the agent endpoint is for the terms review
and for Phase 17.

## Unverified

- The `/en-sa/` Saudi market path and its currency.
- Pagination and `limit` above 10.
- Queries other than `dress` and `kaftan` (`blazer`, `trousers` and `shoes` were never asked for, so the
  rest of the catalogue is unseen).
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
