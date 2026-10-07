# Store Qualification Summary (Phase 2 gate)

Date: 2026-10-07 · Written by the orchestrator from the 12 reports in this folder and the candidate list in the Module 2.3 hand-back. All checks ran from one machine with the honest client `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first, at most 1 request/s, stopping at the first block.

## Gate result: FAILED

The plan requires **at least 4 readable stores (target 5), including at least 1 luxury-leaning**. Result: **3 readable, of which 2 are firm and 1 is conditional.** The luxury requirement is met only by the conditional one.

34 sites were checked. 3 can be read by an honest client.

| Outcome | Count | Sites |
|---|---|---|
| Readable (GO) | 3 | Luxury For You (conditional), Oh Polly UAE, Club L London UAE |
| Blocked by a bot challenge (HTTP 403/429) | 9 | Splash, Max Fashion, Centrepoint, Ounass, Styli, Brands For Less, VAO Concept Store, H&M UAE, Mango |
| Search disallowed in robots.txt | 14 | Noon, Level Shoes, Namshi (malformed rule, read as intended), Bloomingdale's UAE, VogaCloset, Trendyol, THAT Concept Store, Etoile La Boutique, Harvey Nichols, Farfetch, Net-a-Porter, PrettyLittleThing UAE, Next UAE, The Luxury Closet (provisional) |
| No product data in the page (JavaScript-only) | 1 | 6thStreet, now `aivi.com` |
| Not a separate store, or a parked domain | 4 | Sivvi (redirects to Namshi), Nisnass (redirects to Ounass), Boutique 1, SAAF |
| Undetermined or not assessed | 3 | Revolve (timeout), Glam Moda (TLS failure), Mytheresa (search path unknown) |

## The 12 stores with full reports

| Store | Verdict | Reason | Strategy | Tier hint | Report |
|---|---|---|---|---|---|
| Oh Polly UAE | **GO** | Shopify `/search/suggest.json`, allowed by robots.txt | `shopify` | mid (AED 170-970 seen) | [oh-polly.md](oh-polly.md) |
| Club L London UAE | **GO** | Same | `shopify` | premium (AED 199-1,499 seen) | [club-l-london.md](club-l-london.md) |
| Luxury For You | **GO (conditional)** | Server-rendered search cards, allowed by robots.txt | `css` | luxury | [luxury-for-you.md](luxury-for-you.md) |
| 6thStreet / AIVI | DROP | Empty JavaScript shell; products load from Algolia in the browser | none | mid | [6thstreet.md](6thstreet.md) |
| Namshi | DROP | `Disallow: ?q=` (malformed, read as the intended block on search) | none | budget-mid | [namshi.md](namshi.md) |
| Noon | DROP | robots.txt disallows `/*/search$`, `/*/search?`, `/*/search/` for `*` | none | mid | [noon.md](noon.md) |
| Level Shoes | DROP | robots.txt disallows `*/catalogsearch/` | none | premium-luxury | [level-shoes.md](level-shoes.md) |
| Splash | DROP | Cloudflare challenge on robots.txt | none | budget | [splash.md](splash.md) |
| Max Fashion | DROP | Cloudflare challenge on robots.txt | none | budget | [max-fashion.md](max-fashion.md) |
| Centrepoint | DROP | robots.txt loads; product page returns a Cloudflare challenge | none | mid | [centrepoint.md](centrepoint.md) |
| Ounass | DROP | Cloudflare challenge on robots.txt | none | luxury | [ounass.md](ounass.md) |
| Styli | DROP | Cloudflare challenge on robots.txt | none | budget-mid | [styli.md](styli.md) |

## Why the 3 readable stores are not enough for the demo as specified

1. **No menswear in two of them.** Oh Polly and Club L London are single-brand, women-only stores. Acceptance queries q06 and q07 are for men, so they can get results from at most one store, and the pass rule needs at least 3 stores.
2. **Narrow, partly out-of-scope assortment.** Club L London's results are mostly dresses, which are not one of the four categories. Its search for "black blazer" returned 1 blazer and 9 dresses.
3. **Shopify's endpoint returns at most 10 products per call.**
4. **Luxury For You is slow and its price is ambiguous.** Each search page is about 2.7 MB and took 7 to 15 s, above the PRD's 6 s per-request timeout (R5). Each card shows two prices, a struck-through one and a lower "member" one; which a non-member pays is unverified.
5. **None is one of the large GCC multi-brand retailers** the BRD has in mind. Every one of those is blocked, disallows search, or serves no data to an honest client.

## What this means

The plan's core idea, "visit each store's search page", does not work for the major GCC retailers under Rule 2. This is not a tooling problem: internal search pages are disallowed or challenged almost everywhere. The stores that are open are small Shopify storefronts and one luxury e-tailer.

## Options (a business decision; nothing below is decided)

| # | Option | What it gives | Cost and risk |
|---|---|---|---|
| A | **More Shopify storefronts.** A second discovery pass for GCC Shopify fashion stores that sell menswear and the four categories and whose robots.txt leaves `/search/suggest.json` open | Stays inside every current rule. One `shopify` extractor serves every such store | Stores are small and often single-brand; 10 products per call; the demo is "GCC boutiques", not "Namshi and Noon" |
| B | **Stores' official AI-agent endpoints.** The two Shopify stores' robots.txt comments tell AI agents to use the store's own endpoint (`/api/ucp/mcp`) for catalogue search. Not requested or tested yet | A route the store itself offers to agents; possibly more products and a currency field | Unknown until researched; a new client to build; terms still to read |
| C | **Use a store's own search API or a headless browser** for big stores, for example 6thStreet's Algolia search or rendering the JavaScript page | Reaches large multi-brand retailers | Uses a key issued to the store's website, or automation the store may not permit. Needs the business to accept the terms-of-use risk per store. Does not help where robots.txt disallows search or a challenge blocks us |
| D | **Category pages and sitemaps instead of search pages.** robots.txt usually allows these | Works for stores that only disallow search (Noon, Level Shoes, Namshi and others) | Needs an index and many page visits: more than one day, and it reverses ADR 0001 |
| E | **Feeds, affiliate programmes or partnerships** with the large retailers | The durable answer for real users. Noon's robots.txt already lets several named AI agents reach search, which suggests openness | Slow; outside a one-day demo |

Recommendation: **A now, and research B alongside it**, so the demo can run today within the rules. Treat C, D and E as decisions for the business after it sees this result. Re-test the undetermined stores from another network.

## Notes for Phase 6 if we proceed with the readable stores

- Strategies actually needed: `shopify` (2 stores) and `css` (1 store). No readable store needs `store_json`, `json_ld` or `embedded_json`.
- Shopify search responses carry **no currency**; pin `currency: AED` in the store config (confirmed only from the product page's JSON-LD).
- Luxury For You: response-size cap of at least 3 MB; a per-store timeout above 6 s or it will always be skipped; one keyword variant only; strip the bidi marks U+2066-U+2069 from prices; link from the card `href`, not the JSON-LD `offers.url`; decide which of the two prices to show.
- `selectolax` 1.0.0: use `selectolax.lexbor.LexborHTMLParser`; `selectolax.parser` fails to import.
- robots.txt: use `protego`, check the full URL with its query string, and read a malformed rule (a value that starts with neither `/` nor `*`) as if it began with `*`. Reject an HTML page served in place of robots.txt.
- A store can change domain (6thStreet now redirects to `aivi.com`): a cross-domain redirect must stop the request, as the allow-list already requires.
- Rank by category, not by the store's own order: store search pads results with off-category items.

## Not verified

Terms of use for every store. Behaviour from any other network. What a non-member pays at Luxury For You. Pagination and Shopify limits above 10. The UCP/MCP endpoints (never requested). Tier hints for dropped stores (from public descriptions, not observed prices).
