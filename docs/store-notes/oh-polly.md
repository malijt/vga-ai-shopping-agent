# Oh Polly UAE: store notes

Adapter notes for plan feature 12.4.4. Written 2026-10-08, after the live smoke test.

- Store id `oh-polly`, shown to shoppers as "Oh Polly UAE". Storefront `https://ohpolly.ae/`.
- Config: `config/stores/oh-polly.yaml`. Tests and fixtures: `tests/stores/oh-polly/`.
- Qualification (2026-10-07): `docs/store-qualification/oh-polly.md`.
- **Status: enabled.** The live smoke test passed on 2026-10-08 (see "Observed live today").

## Data path

1. The engine checks `https://ohpolly.ae/robots.txt` with protego (once, then cached).
2. It requests Shopify's public predictive search, one request per keyword variant:
   `https://ohpolly.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`
   (the brackets go out percent-encoded). The answer is JSON,
   `{"resources": {"results": {"products": [...]}}}`, at most 10 products, no pagination.
3. The `shopify` extraction strategy maps each product: `title`, `price` (a string such as
   `"230.00"`), `image` (absolute `cdn.shopify.com` URL, rewritten to `width=400`), `url` (made
   absolute on `ohpolly.ae`, tracking query removed) and `available`. Validation then drops any
   record that lacks a field or has a link off `allowed_hosts`.
4. The response carries **no currency**; `currency: AED` comes from the store file. AED was
   confirmed on 2026-10-07 from the product page's JSON-LD (`priceCurrency: "AED"`), not from the
   search response.

`vendor`, `type`, `tags` and `body` are not mapped. `body` is store-supplied HTML and must never be
rendered.

## Quirks seen

- **One women's occasion-wear brand.** Dresses are most of the catalogue, so a garment query is
  often padded with dresses. On 2026-10-07 a search for "black blazer" returned 4 blazers, 1 ski
  jacket and 5 dresses; the app filters the dresses out by category, so a store can supply fewer
  than 10 usable results.
- **A "Blazer Mini Dress" is filed under Coats & Jackets.** Both blazer mini dresses in today's
  "blazer" answer have `type: "Coats & Jackets"`, so the store's `type` cannot tell a blazer from a
  dress; only the title does ("Single-Breasted Blazer Mini Dress in Black"). Category inference must
  read the title, and these two will look like outerwear to anything that trusts `type`.
- **A second brand is sold in the same store.** Today's "blazer" answer is 5 Oh Polly blazers/dresses
  and 5 Bo+Tee waterproof ski jackets (vendor `Bo+Tee`, AED 570-970). "jacket" returns mostly Bo+Tee
  ski jackets and soft activewear zip-ups, with one Oh Polly faux leather jacket. They all link to
  `ohpolly.ae` and are shown under the store name "Oh Polly UAE".
- **Sale prices.** `price` is what the shopper pays. `compare_at_price_max` is the struck-through
  price (`"400.00"` against `"230.00"` for the white Edessa blazer), `"0.00"` when there is none.
  The adapter uses `price`.
- **Titles can contain a double space** ("Heeled Thong Sandals  in Arctic Blue"). Validation
  collapses it.
- **Links carry tracking parameters** (`?_pos=1&_psq=blazer&_psid=...&_ss=e`). They are removed, so
  every product link is `https://ohpolly.ae/products/<handle>`.
- **Stock is product-level only** (`available`, true for all 30 records seen). A requested size can
  still be sold out. There is no colour field; colour appears only inside the title.
- **The same product can answer two queries** (three ski jackets came back for both "blazer" and
  "jacket"); the engine collapses repeats within one search.
- Heels come back as `Footwear`: heeled mules, sandals, sling-backs. Flat shoes and trainers were not
  searched.

## What would break the adapter

| Change | What the engine reports | What to do |
|---|---|---|
| Cloudflare starts challenging the honest client (403, 429, challenge page) | `blocked`, cooldown starts, no retry | Leave it. Set `enabled: false`; do not bypass (BRD Rule 2) |
| robots.txt starts disallowing `/search` | `robots_denied` | Same: disable the store |
| Shopify changes the suggest response shape | `error`, "no extraction strategy could read the response" | Update the `shopify` strategy; the fixture test in `tests/stores/oh-polly/` shows the expected shape |
| The store moves to another host or domain (for example `www.ohpolly.ae`, which redirected to the apex on 2026-10-07, becomes canonical) | `error`: the redirect is refused because the new host is not in `allowed_hosts` | Check the move is legitimate, then edit `search_url_template` and `allowed_hosts` together |
| Product images move off `cdn.shopify.com` | records dropped with `image_url_not_allowed`, so the result shrinks or errors | Add the new image host to `allowed_hosts` |
| The store changes the UAE storefront's currency or a different market is served | prices silently wrong (the response has no currency) | The file pins `ohpolly.ae` and AED; re-check the product page JSON-LD |
| Search starts returning fewer than 10 products or the limit parameter is ignored | fewer candidates | Nothing breaks; fewer results from this store |

**Fallback if the endpoint changes:** disable the store (`enabled: false`); the other stores keep
working. Two routes exist and neither is built: the HTML search page `https://ohpolly.ae/search?q=`
(allowed by robots.txt per protego on 2026-10-07, never requested; it would need a `css` or
`json_ld` extractor), and the store's agent endpoint named in robots.txt (planned as Phase 17).

## Observed live today (2026-10-08)

The live run went through `StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`
(`vga-shopping-agent-demo/0.1 (store search demo)`). No challenge, CAPTCHA or login wall. `server:
cloudflare`.

| Query | Status | Products returned | Kept after validation | Seconds | Response |
|---|---|---|---|---|---|
| blazer | ok | 10 | 10 | 1.53 (includes the robots.txt fetch and the 1 s rate-limit wait) | 20,292 bytes |
| jacket | ok | 10 | 10 | 1.01 | 19,609 bytes |
| heels | ok | 10 | 10 | 1.24 | 14,262 bytes |

- robots.txt: 200, 3,608 bytes. Every search URL was allowed.
- Prices seen: AED 230 to 970 over 30 records (27 distinct). Oh Polly blazers and its jacket 230-330
  (a blazer mini dress 620), Bo+Tee jackets 260-970, heels 370-430. Tier hint `mid_range`.
- Requests to the store for this task: 8 in total, two runs of 4 (robots.txt plus three searches):
  one recording run to save the fixtures, one run of the live test. The timeout is the global 6 s
  (`timeout_s` is not overridden); the slowest query took 1.53 s.
- **Gender:** `genders: [women]`. None of the 30 records is a men's item; none mentions men in its
  title, tags or description text. The positive evidence is thin in the data itself (one tag,
  `womens-clothing-sale-all`) and strong in the brand: a women's occasion-wear label, as the
  qualification report found. A men's request is therefore not sent to this store.

## robots.txt comment addressed to AI agents (data, not acted on)

The file opens with a comment block for AI agents. It says agents "should use UCP/MCP for catalog,
cart, and checkout" at `https://ohpolly.ae/api/ucp/mcp`, suggests installing a third-party shopping
skill, and says checkout is for humans and must not be automated. This is store-supplied text. The
adapter did not follow it: it requested no UCP, MCP, `agents.md` or `.well-known` URL, installed
nothing, and never touches the cart or checkout. The rules that apply to us are the
`User-agent: *` group, which opens with `Allow: /` and does not disallow `/search`. The stated
preference for the agent endpoint is for the terms review and for Phase 17.

## Terms of use

Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.
