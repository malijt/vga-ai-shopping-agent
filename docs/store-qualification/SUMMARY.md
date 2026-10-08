# Store Qualification Summary (Phase 2 gate)

Date: 2026-10-07 · Written by the orchestrator from the 12 reports in this folder and the candidate list in the Module 2.3 hand-back. All checks ran from one machine with the honest client `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first, at most 1 request/s, stopping at the first block.

## Gate result: PASSED after the second pass

The plan requires **at least 4 readable stores (target 5), including at least 1 luxury-leaning**.

- **First pass (Modules 2.1-2.3): failed.** 34 sites checked, 3 readable, none of them a large GCC retailer. The user then chose route A: more Shopify storefronts.
- **Second pass (Module 2.4): passed.** 8 more Shopify storefronts tested, 6 readable. Total: **9 readable stores (8 firm, 1 conditional), 2 of them luxury-leaning.** See "Update: Module 2.4" at the end of this file and [shopify-discovery.md](shopify-discovery.md).

The rest of this section records the first pass, which is why the route changed.

34 sites were checked in the first pass. 3 can be read by an honest client.

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

## Update: Module 2.4 (Shopify discovery, 2026-10-07)

Eight more candidates were tested with the same rules; six are readable, all through Shopify's `/search/suggest.json`, all priced in AED. Two were dropped because robots.txt disallows `/search`. Fifteen further candidates were listed but not tested (the pass stopped at six).

### The demo store set (6, the BRD's maximum)

Chosen by the orchestrator for the widest cover of gender, category and price. The BRD lets the team pick the stores that work.

| Store | Sells | Categories seen | Price seen (AED) | Tier hint | Report |
|---|---|---|---|---|---|
| Giordano UAE | men, unisex (women's not seen in results) | tops, outerwear, bottoms, shoes | 39.50-199.50 | budget | [giordano-uae.md](giordano-uae.md) |
| Nautica UAE | men and women (corrected on 2026-10-08: a live "women dress" search returned women's shirts, trousers and tops; the first pass had seen only women's accessories) | tops, outerwear, bottoms | 59-239 | mid | [nautica-uae.md](nautica-uae.md) |
| Sacoor Brothers UAE | men, some women | tops, outerwear (blazers), shoes | 195-1,495 | premium | [sacoor-brothers-uae.md](sacoor-brothers-uae.md) |
| Oh Polly UAE | women | outerwear, shoes | 170-970 | mid | [oh-polly.md](oh-polly.md) |
| Club L London UAE | women | outerwear, shoes, 1 top (dresses dominate and are filtered out) | 199-1,499 | premium | [club-l-london.md](club-l-london.md) |
| Maison D'Vie | women; men's shirts and T-shirts | tops, outerwear, bottoms | 490-4,430 | luxury | [maison-dvie.md](maison-dvie.md) |

### Readable but held in reserve

| Store | Why not in the six | Report |
|---|---|---|
| The Bear House UAE | Menswear at budget prices, no shoes; a fourth men's store was traded for a second women's store. First choice if a men's query falls short | [bear-house-uae.md](bear-house-uae.md) |
| Good Times | Streetwear, mostly T-shirts | [good-times.md](good-times.md) |
| Luxury For You | The only store with men's and women's luxury across categories, but each page took 7-15 s and its price is ambiguous. Needs the `css` extractor | [luxury-for-you.md](luxury-for-you.md) |

### What the coverage table says about the test queries

- A men's shirt under AED 200 (like q07): four readable stores return one. The 3-store rule looks reachable.
- A men's blazer under AED 400 (like q06): only Sacoor Brothers returned men's blazers, at AED 695-795, over the budget. Other stores return men's jackets, which are the same category (outerwear), so "20 results from 3 stores" may still be met. But "7 good matches in the top 10" probably is not: the rubric treats a different garment type as a miss, and the cap of 6 results per store means at most 6 real blazers can be shown. Expect q06 to fail on match quality, and report it honestly.
- Women's bottoms (like q08, wide-leg jeans): only Maison D'Vie showed women's bottoms. Not tested directly. A likely gap.
- Shoes: Giordano and Sacoor (men, unisex), Oh Polly and Club L (women's heels and boots). Sneakers for women are a likely gap.

These were generic queries, not the acceptance queries themselves.

### Notes for Phases 6 and 12 from this pass

- The Bear House keeps a style code in `title` and the product name in `vendor`: the `shopify` extractor needs a per-store name field.
- Giordano repeats one title under several handles: collapse same title and price within a store.
- Sacoor's `type` and Nautica's `tags` carry gender and category; titles mostly do too.
- Giordano, Nautica and The Bear House were entirely on sale when tested, so the prices seen are sale prices.
- All six new stores' robots.txt files carry the same comment telling AI agents to prefer the store's UCP/MCP endpoint. It was recorded as data and not acted on. It is the subject of Phase 17.

## Live adapter results (Phase 12, 2026-10-08)

All six demo stores passed a live smoke test through the project's own engine (robots.txt first, honest User-Agent, 1 request/s) and are enabled. Every response was HTTP 200; no block, challenge or robots denial. Details are in `docs/store-notes/<store>.md`.

| Store | Queries | Products kept per query | Seconds per query | Requests used (cap 10) |
|---|---|---|---|---|
| Sacoor Brothers UAE | men shirt, black blazer, shoes | 8, 8, 9 | 1.0-1.4 | 7 |
| Giordano UAE | men shirt, jacket, shoes | 4, 6, 4 | 1.0-1.4 | 4 |
| Nautica UAE | men shirt, jacket, trousers | 10, 10, 8 | 0.8-1.5 | 9 |
| Oh Polly UAE | blazer, jacket, heels | 10, 10, 10 | 1.0-1.5 | 8 |
| Club L London UAE | blazer, jacket, heels | 10, 10, 10 | 0.8-2.0 | 8 |
| Maison D'Vie | blazer, shirt, trousers | 10, 10, 10 | 1.0-1.4 | 4 |

What the live runs showed:

- Shopify returns at most 10 records per search, and repeated titles collapse, so a store yields 4 to 10 products per keyword. Giordano yields the fewest.
- Short garment keywords ("blazer") returned cleaner results than longer ones ("black blazer") at Club L London.
- Sacoor, Nautica and Maison D'Vie sell both men's and women's items and keep the gender in `type` or `tags`, not always in the title.
- Oh Polly and Club L London are women-only and are configured so.
- Not exercised live: thumbnail downloads from the Shopify CDN, women's queries at Giordano, paging beyond 10 results.

## Update: Module 2.5 and the ten-store limit (2026-10-08)

Dresses, abayas, kaftans and kurtas came into scope on 2026-10-08, and the six demo stores were chosen before that. A further discovery pass ([dress-store-discovery.md](dress-store-discovery.md)) listed 31 candidates, tested 12 and qualified four, all Shopify `/search/suggest.json` with robots.txt allowing it:

| Store | Sells | Price seen (AED) | Tier hint | Report |
|---|---|---|---|---|
| Hanayen | abayas (10 of 10 real abayas for `abaya`), modest dresses | 600-4,500 for abayas | premium | [hanayen.md](hanayen.md) |
| Maison Arabelle | abayas, kaftans | 790-2,400 | luxury | [maison-arabelle.md](maison-arabelle.md) |
| Nishat Linen UAE | long dresses, South Asian suits, men's kurtas | 40-239 (sale prices) | budget | [nishat-linen-uae.md](nishat-linen-uae.md) |
| Signature Studio | designer South Asian sets, kaftans, men's kurta sets | 174-2,753 | mid | [signature-studio.md](signature-studio.md) |

**Decision (user, 2026-10-08): the store limit rises from six to ten.** Six stores cannot serve both menswear and dresses: only three carry menswear, which leaves three for dresses, and three stores at six results each give 18 against a pass rule of 20. The demo keeps the six above and adds these four, each enabled only after its live smoke test passes (plan assumption A25, Modules 12.7-12.10).

Still thin after the change:
- Only Hanayen and Maison Arabelle sell real abayas, so an abaya search may not reach three stores. No readable AED store sells an everyday abaya below AED 600.
- `kurta` returns only men's items at Nishat Linen and Signature Studio; women's kurta keywords were not tried.
- Heels come only from Oh Polly and Club L London. Skinny jeans and satin blouses were not searched anywhere.

Not tested in this pass and worth a look if coverage stays thin: Gul Ahmed UAE (South Asian), Al Boushiya and Elilhaam (evening gowns), Shaira and four other luxury modest-wear stores, Steve Madden Middle East (heels).

## Update: Module 2.6, the designer brands the user named (2026-10-08)

The user named eight Kuwaiti designer brands. Full record: [designer-store-qualification.md](designer-store-qualification.md).

| Brand | Verdict | Currency | Price seen | Report |
|---|---|---|---|---|
| Bazza Alzouman | readable (Shopify) | KWD | 206-380 | [bazza-alzouman.md](bazza-alzouman.md) |
| Hamsa | readable (Shopify) | KWD | garments 55-365 | [hamsa-kw.md](hamsa-kw.md) |
| Manal Smaoui | readable (Shopify) | KWD | 5-85 | [manal-smaoui.md](manal-smaoui.md) |
| Heba Shaikh | readable (Shopify) | GBP | 35-950 | [heba-shaikh.md](heba-shaikh.md) |
| N.BEE | no online store of its own (Instagram only) | | | |
| Montaha Couture | not readable: invalid security certificate | | | [montaha-couture.md](montaha-couture.md) |
| Yousef Al-Jasmi | not readable: no robots.txt, home page redirects to an unrelated domain | | | [yousef-aljasmi.md](yousef-aljasmi.md) |
| Marzook | not tested: handbags and accessories are out of scope | | | |

**Decision (user, 2026-10-08): add the three dinar stores.** Each result shows the dinar price plus an approximate AED figure from a fixed rate; price ranges and budgets use the AED figure (plan assumption A28). Heba Shaikh is a reserve. The store limit becomes 13.

What it adds: evening gowns (Bazza Alzouman), a third abaya store (Hamsa) and mid-priced kaftans and sets (Manal Smaoui). What it does not add: an abaya below about AED 600, or anything in the budget range.

## Update: Module 2.7, modest and ethnic wear, Kuwait first (2026-10-08)

The user asked for more stores, naming the garments the demo must find: abayas, kaftans, burqas and kurtis for women; thobes, kurtas and shalwar kameez for men. Full record: [modest-ethnic-wear-discovery.md](modest-ethnic-wear-discovery.md). Nineteen candidates were listed, sixteen contacted (86 requests).

| Store | Verdict | Currency | Price seen | Sells | Report |
|---|---|---|---|---|---|
| Daraat | readable (Shopify) | KWD | 8-29 | kaftans, summer dresses | [daraat.md](daraat.md) |
| Shadow | readable (Shopify) | KWD | abayas 39-180 | abayas | [shadow-kw.md](shadow-kw.md) |
| Her Highness Q8 | readable (Shopify) | KWD | 28.5-85 | daraas, kaftans, dresses | [her-highness-q8.md](her-highness-q8.md) |
| Veil Essentials | readable (Shopify) | KWD | 7.55-33.5 | jilbabs, abayas, khimars | [veil-essentials-kw.md](veil-essentials-kw.md) |
| Al Jazeera Clothing | readable (Shopify, `/en/` path only), thin | KWD | men's dishdasha 9 | dishdashas, mostly boys' | [al-jazeera-clothing.md](al-jazeera-clothing.md) |
| Gul Ahmed UAE | readable (Shopify) | AED | 41.50-149 | men's shalwar kameez and kurtas, women's kurtis | [gul-ahmed-uae.md](gul-ahmed-uae.md) |
| Ambrose Abayas | readable, but WooCommerce: needs a reader that is not built | KWD (two decimals) | 35-50 | abayas | discovery record |
| Empress Clothing, Seerat Ethnic, My Little Jubba, YallaWorld | readable (Shopify), reserve: not Gulf stores | USD, INR, GBP, GBP | | salwar kameez sets, kurta sets, thobe sets | discovery record |
| Yuehlia, Riva Fashion | not readable: HTTP 403 | | | | discovery record |
| AlMubarkiya, Karaz Online | not usable live: robots.txt asks for 240 s and 30 s between requests | | | | discovery record |
| Sara Arabia | undetermined: search address not known | | | | discovery record |

**Decision (user, 2026-10-08): the store limit rises to 19 and work on stores that are not on Shopify is opened.** The six readable Gulf stores are added, each enabled only after its live smoke test (plan assumption A30, Modules 12.14-12.19). Ambrose Abayas follows on its own branch once its reader exists.

What it adds: the first abaya below AED 600 (Veil Essentials, about AED 142-310), a Kuwaiti abaya label (Shadow), budget kaftans (Daraat), daraas (Her Highness Q8), men's shalwar kameez, kurtas and women's kurtis (Gul Ahmed UAE), and men's dishdashas (Al Jazeera Clothing). Still thin: adult men's thobes (three seen), and anything sold as a burqa.

**Network note.** The Shopify requests of this pass went through Cloudflare WARP, which the user switched on after the machine's own network timed out connecting to Shopify (a time-out, never a refusal). The reasoning and what is not known are in the discovery record and in the plan, section 12.3.

## Not verified

Terms of use for every store. Behaviour from any other network. What a non-member pays at Luxury For You. Pagination and Shopify limits above 10. The UCP/MCP endpoints (never requested). Tier hints for dropped stores (from public descriptions, not observed prices).
