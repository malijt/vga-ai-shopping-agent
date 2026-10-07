# Bazza Alzouman: store notes

Adapter notes for plan module 12.11. Written 2026-10-08, after the live smoke test.

- Store id `bazza-alzouman`, shown to shoppers as "Bazza Alzouman". Storefront
  `https://bazzaalzouman.com/`.
- Config: `config/stores/bazza-alzouman.yaml`. Tests and fixtures: `tests/stores/bazza-alzouman/`.
- Qualification (2026-10-08): `docs/store-qualification/bazza-alzouman.md`; the designer-brand pass it
  belongs to: `docs/store-qualification/designer-store-qualification.md`.
- Currency decision: `docs/adr/0006-second-currency-fixed-rate.md`.
- **Status: enabled.** The live smoke test passed on 2026-10-08 (see "Observed live today"), and every
  record carries a single price, so the default price rule is exact here (see "Price").

## Data path

1. The engine checks `https://bazzaalzouman.com/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://bazzaalzouman.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string with three decimals,
   `"245.000"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made
   absolute on `bazzaalzouman.com`, tracking query removed) and `available`. Validation then drops any
   record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: KWD` comes from the store file. KWD was confirmed
   on 2026-10-08 from the product page's JSON-LD (`priceCurrency: "KWD"` on all eight size offers) and
   `Shopify.currency` (`{"active":"KWD"}`), not from the search response. The store has no AED
   storefront: its own country picker lists "United Arab Emirates (KWD)".

`vendor` ("Bazza Alzouman" on every record), `type`, `tags` and `body` are not mapped, except that `type`
and `tags` are read for the product's gender (they name none here, see below). `body` is
store-supplied HTML and must never be rendered. No extractor option is set: the defaults suit this
store (name from `title`, image width 400).

## Price

- **Three decimals.** Prices are Kuwaiti dinars written with the fils: `"245.000"`. The price parser
  accepts three decimals only for a store whose currency is KWD, BHD or OMR (ADR 0006), so for this
  store `245.000` is KWD 245, never "245 thousand". A price written with two decimals would be
  refused as an unknown format.
- **One price per record.** On all 20 records recorded today `price`, `price_min` and `price_max` are
  equal, so there is no cheaper add-on variant that `price` could pick up (the trap at Hamsa). A test
  pins this: if the store ever lists variants at different prices, the test fails and the price rule
  needs a second look.
- **Shopper-facing figure.** The page shows the dinar price and an approximate dirham figure from the
  fixed rate in `config/settings.yaml` (1 KWD = 11.92 AED), for example
  `245.000 KWD (about 2,920 AED)`. The ranges and any budget use the dirham figure.
- **Sale prices.** `price` is what the shopper pays; `compare_at_price_max` is the struck-through price
  (`"295.000"` against `"206.000"` for the Long Sleeve Collared Wrap A Line Gown), `"0.000"` when there
  is none. The adapter uses `price`. 2 of 20 records carried a compare-at price today.
- **Range seen:** KWD 206 to 380 (median 255 over the 17 distinct products), about AED 2,460 to 4,530.
  Tier hint `luxury`.

## Quirks seen

- **A single brand of evening gowns.** Every record is a gown or a dress: `type` is "Dresses" on 18 of
  20 records, "Dress" on one and "Gown" on one (the same kind of garment sits under all three
  spellings, so `type` is no use for telling a gown from a dress). No tops, trousers, shoes or jackets
  appeared; the qualification pass saw a jumpsuit title in a search engine, not in the responses.
- **No padding.** Unlike Manal Smaoui and Hamsa, the store did not pad either answer with unrelated
  items: `gown` and `dress` returned only gowns and dresses.
- **Links carry tracking parameters** (`?_pos=1&_psq=gown&_psid=...&_ss=e`). They are removed, so
  every product link is `https://bazzaalzouman.com/products/<handle>`. A handle can differ from the
  title ("One Shoulder Crepe Gown With Gathered Tulle At Neck" is `...-at-neck-1`, "Sleeveless Balloon
  Collar Gown..." is `sleeveless-baloon-...`): the link is always the store's own `url`.
- **Gender is in no field.** `type` and `tags` carry garment words and collection codes (`PS26`,
  `AW26`, `PF25`, `PF26`, `skinny gown`, `ball gown`), never a gender, so the extractor leaves every
  product's gender unknown. `genders: [women]` in the store file is what keeps a men's request away
  from this store.
- **Several seasons in one answer.** Collection codes in the tags range from `PF25` to `AW26`, so
  older gowns stay listed (and available) beside the current season.
- **Stock is product-level only** (`available`, true for all 20 records recorded today). The product
  page shows per-size stock (three of the eight sizes of the sampled dress were sold out in the
  qualification pass).
- **The same gown answers two queries.** 3 of the 10 `dress` products were also in the `gown`
  answer; the engine collapses repeats within one search, so a two-variant search gives 17 distinct
  products, not 20.
- **Images** are all on `cdn.shopify.com` under `/s/files/1/0244/0753/9793/` (`/files/`), with a `v=`
  version parameter that is kept. The product page's own JSON-LD uses `bazzaalzouman.com/cdn/shop/...`
  instead; search results do not.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` (an older Shopify template does) | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture tests in `tests/stores/bazza-alzouman/` show the expected shape |
| The store writes prices with two decimals, or with a thousands separator | records dropped with `unknown_price_format` | Look at the new format first; do not loosen the parser for a guess (a factor of 1000 is the risk) |
| The store serves another currency from `bazzaalzouman.com` (a Shopify Markets path such as `/en-ae/`) | prices silently wrong (the response has no currency) | The file pins the host and KWD; re-check the product page JSON-LD |
| The store adds variants priced differently (add-ons, sets) | the price test that pins one price per record fails | Apply the price rule used for Hamsa (`max_price_spread`) |
| The store moves to another host (for example `www.bazzaalzouman.com`) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed` | Add the new image host to `allowed_hosts` |
| The dinar rate drifts | the approximate dirham figure and the ranges move | Refresh `fx_rates.KWD` in `config/settings.yaml` with its source and date |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page
`https://bazzaalzouman.com/search?q=` (not requested), and the store's agent endpoint named in
robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

Two runs went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`): one to record the fixtures and one for the live
smoke test. Every response was HTTP 200, no redirect, no challenge, CAPTCHA or login wall.
`server: cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds, recording run | Seconds, live test | Response |
|---|---|---|---|---|---|---|
| gown | ok | 10 | 10 | 1.38 (includes the robots.txt fetch and the 1 s rate-limit wait) | 1.48 | 11,991 bytes |
| dress | ok | 10 | 10 | 0.93 | 0.85 | 12,056 bytes |

- robots.txt: 200, 3,636 bytes, byte for byte the file saved in the qualification pass. Every search
  URL was allowed.
- Requests to the store for this task: 6 in total, two runs of 3 (robots.txt plus the two searches),
  so 4 searches. No thumbnail was fetched. The timeout is the global 6 s (`timeout_s` is not
  overridden); the slowest query took 1.48 s.
- **Gender:** `genders: [women]`. Evidence: all 20 records recorded today and the 17 distinct ones of the
  qualification pass are women's evening gowns and dresses; no title, type or tag names a gender. The
  data itself carries no gender field, so this rests on the range and the brand, as for Hanayen and
  Oh Polly. A men's request is therefore not sent to this store.
- **Categories:** `categories: [dresses]`. Evidence: 20 of 20 recorded records and 17 of 17 in the
  qualification pass are gowns or dresses; no shoes, trousers, tops or jackets were seen. A search for
  any other category is therefore not sent to this store; it is listed among the skipped stores as
  "Not searched: Bazza Alzouman does not sell shoes." and so on. "Not seen" is not "not sold" (10
  products per query, two queries): if the store adds other garments, remove the line.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout", names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and suggests a
third-party shopping skill. This is store-supplied text. The adapter did not follow it: it requested
no UCP, MCP, `agents.md` or `.well-known` URL, installed nothing, and never touches the cart or
checkout. The rules that apply to us are the `User-agent: *` group, which opens with `Allow: /` and
does not disallow `/search`. The stated preference for the agent endpoint is for the terms review
and for Phase 17.

## Unverified

- The `/ar/` Arabic prefix and any other Shopify Markets path, and their currency.
- Pagination and `limit` above 10.
- Queries other than `gown` and `dress` (a jumpsuit or a separate set were never asked for).
- Whether the thumbnail host `cdn.shopify.com` serves the `width=400` image to the honest client (no
  image was fetched in this task).
- Per-size stock.
- The dinar rate: a fixed approximation from 2026-10-07 (ADR 0006), refreshed by hand.
- Behaviour from another network.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
