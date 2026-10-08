# Maison D'Vie: store notes (plan 12.6.4)

Store id `maison-dvie`, storefront `https://maisondvie.com/`, config `config/stores/maison-dvie.yaml`,
tests `tests/stores/maison-dvie/`. Qualification report: `docs/store-qualification/maison-dvie.md`.
Last checked live: 2026-10-08.

## What the store is

A UAE online boutique for contemporary designer labels (Federica Tosi, Vivetta, Avavav, MC2 Saint
Barth, Violante Nessi, Dodo Bar Or, Alessandro Vigilante and others). It is multi-brand and
**mostly women's**. The men's items seen are shirts and T-shirts (MC2 Saint Barth). No shoes were
seen in any search. It is the demo's luxury-leaning store: prices seen live were AED 730 to 4,190
(AED 490 to 4,430 across the qualification run), so `tier_hint: luxury` means designer pricing, not
heritage houses.

## Data path

1. `GET https://maisondvie.com/robots.txt`, checked with protego (allows `/search/suggest.json`).
2. `GET https://maisondvie.com/search/suggest.json?q={query}&resources%5Btype%5D=product&resources%5Blimit%5D=10`
   (Shopify predictive search; the store file writes the brackets unencoded and the URL builder
   encodes them). Answer: `{"resources": {"results": {"products": [...]}}}`, at most 10 products.
3. The `shopify` extractor maps `title`, `price`, `image` (with `width=400` set), `url` (tracking
   query removed) and `available`. Validation then enforces https, the allow-list, a positive price
   and no repeats.

The response has **no currency**; `currency: AED` comes from the store file (confirmed once from a
product page's JSON-LD during qualification). The two allowed hosts are `maisondvie.com` (links)
and `cdn.shopify.com` (images; every image URL seen has the path prefix
`/s/files/1/0654/8160/5370/`). `www.maisondvie.com` is deliberately not allowed: it was never seen.

## Quirks seen

- `genders` is unset on purpose. Every product carries a `Men` or a `Women` tag; live, the `shirt`
  search returned 3 men's shirts and 7 women's items, `blazer` and `trousers` returned women's only.
  The pipeline applies a confirmed gender itself (BRD Rule 8); the store file does not narrow it.
- A men's query for blazers or trousers returned no men's items in the queries made. Whether men's
  outerwear or trousers exist and need the word "men" in the keywords was not tested (an open
  question, not a finding).
- Results mix kinds of garment. The `shirt` search returned a women's T-shirt and a women's item the
  store files as type `Jacket` ("Turner Shirt"). Ranking has to judge the category from the title;
  the store's order and `type` field are not reliable.
- `type` is free text and sometimes a comma list (`Women blazers, Jacket`). It is not mapped.
- 13 of 30 products were on sale (`compare_at_price_max` above zero). The extractor reads `price`
  only, which is the current selling price.
- `available` is product level and was `true` for all 30. Sizes are not in the response (`variants`
  is always empty).
- `body` is store-supplied HTML (18 of 30 contain tags). It is not mapped and must never be
  rendered. The fixtures keep it only because the file is the real response.
- Images are a mix of `.jpg` and `.webp`. No colour field; the colour is only in the title.
- Seasonal tags (`EOS_W25`, `Ramadan24`, `Christmas sale`) are campaign markers, not useful.

## What would break the adapter

- **Shopify predictive search turned off or changed** (the merchant's to change at any time): the
  response stops being `resources.results.products`, so the extractor raises, the chain finds
  nothing, and the engine reports the store as an error.
- **robots.txt starts disallowing `/search`**: the engine reports `robots_denied` and sends nothing.
- **A bot challenge, login wall, 403 or 429**: the engine stops at once, does not retry, and puts the
  store in cooldown (BRD Rule 2). It is dropped, never bypassed.
- **A move to another host or to `www`**: a cross-domain redirect is refused by design, and
  `www.maisondvie.com` is not on `allowed_hosts`. Update the file after checking the new host.
- **A change of currency or market**: the response carries no currency, so prices would be read as
  AED whatever the store shows. The request sends no cookies or location, so it gets the default
  market (AED when checked).
- **A different image CDN path or host**: images fail the allow-list and records are dropped.
- **Page size**: the URL asks for 10, which is what Shopify returned each time; larger limits and
  pagination were not tried.

## Fallback if the data path changes

First step: set `enabled: false`. The other five stores keep working and this one is listed as
skipped. Options after that, none of them built or tested here: the store's HTML search page
`/search?q=...` (protego says robots allows it, never requested; needs a `css` strategy), or the
store's own agent endpoint named in its robots.txt comment (planned as Phase 17).

## Observed live today (2026-10-08)

One run of `uv run pytest -m live tests/stores/maison-dvie -q`, through the real
`StoreSearchEngine` with the honest User-Agent from `config/settings.yaml`:

| Query | Status | Returned | Kept | Seconds |
|---|---|---|---|---|
| `blazer` | ok | 10 | 10 | 1.38 (includes robots.txt and the 1 request/s wait) |
| `shirt` | ok | 10 | 10 | 1.01 |
| `trousers` | ok | 10 | 10 | 0.98 |

4 requests in all (robots.txt plus three searches); no redirect, block or challenge. Nothing was
dropped. The three raw responses are the fixtures in `tests/stores/maison-dvie/fixtures/`.

## robots.txt and terms

The comment block at the top of robots.txt is addressed to AI agents. Quoted briefly as data, not
acted on: "Agents should use UCP/MCP for catalog, cart, and checkout." The same text says checkouts
are for humans. These are comments, not rules, and the search path is open under `Allow: /`. The
stated preference is the subject of Phase 17 and should be reviewed before real users. The
`/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp` paths were never requested.

Terms of use: not reviewed (demo only).
