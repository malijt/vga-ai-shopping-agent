# 6thStreet qualification (2026-10-07)

**Verdict:** DROP (no readable data: the search page is a client-rendered React shell; the store has also moved to `en-ae.aivi.com`)

robots.txt does not block us on either host, and nothing blocked or challenged our client. The reason for DROP is that the server returns the same empty application shell for every URL, so a plain HTTP client never receives a product. This is a "no data path" drop, not a "blocked" drop.

## Storefront

- 6thStreet (Apparel Group) was rebranded to **AIVI** in 2026. `https://en-ae.6thstreet.com/search?q=black%20blazer` answers `301` with a redirect to `https://en-ae.aivi.com/search?q=black%20blazer` (observed today). The page title is "Shop Online @ AIVI.com for Men, Women & Kids across GCC".
- Current UAE English storefront: **`https://en-ae.aivi.com/`**. The old host `en-ae.6thstreet.com` still answers `robots.txt` with 200 but redirects search to the new host.
- Rebrand corroboration (web search, not fetched from the store): Apparel Group press and Khaleej Times coverage of the AIVI launch (Aug 2026), and an App Store listing titled "AIVI - Previously 6thStreet".
- The redirect crosses domains, so the new host's own `robots.txt` was fetched and checked before any request to it (see below). The qualification script does not follow cross-domain redirects; it stops and asks for a re-run on the new base URL.

## robots.txt

Parser: **Protego 0.7.0** (the `qualify_store.py` script; `urllib.robotparser` was not used for any decision). The first live fetches were made before the script was switched to Protego, so the decisions below were re-checked offline with Protego against the saved bodies and against the exact URLs requested. No new request was needed.

`https://en-ae.aivi.com/robots.txt` (200, 894 bytes, one `User-agent: *` group, no crawl-delay):

```
User-agent: *
Disallow: /my-account/
Disallow: /cart$
Disallow: /cart/
Disallow: /checkout$
Disallow: /checkout/
Disallow: /sales/order/history/
Disallow: /storecredit/
Disallow: /catalogsearch/
Disallow: /viewall/
Disallow: /*?*dFR
Disallow: /*?*hFR
Disallow: /*?*nR
Disallow: /*?*idx=
Disallow: /*?*facetFilters=
Disallow: /*?*utm_
Disallow: /*?*gclid=
```

- Rules that bear on the search path: none matches `/search?q=...`. The only "search" rule is `Disallow: /catalogsearch/` (a legacy Magento path, not the one the app uses). The `/*?*` rules block facet, tracking and index parameters, not `q=`.
- Protego, exact URLs: `https://en-ae.aivi.com/search?q=black%20blazer` ALLOWED, `...?q=jacket` ALLOWED, `...?q=shoes` ALLOWED, the product page URL ALLOWED. Control checks: `/catalogsearch/result/?q=x` DISALLOWED, `/search?q=x&utm_source=a` DISALLOWED.
- Crawl-delay: none. Sitemap lines: 12 (`ar-` and `en-` for ae, bh, kw, om, qa, sa on `aivi.com`), for example `https://en-ae.aivi.com/sitemap.xml`. Not fetched.
- Old host `https://en-ae.6thstreet.com/robots.txt` (200, 805 bytes): `User-agent: *` disallows `/my-account/`, `/cart$`, `/checkout`, `/sales/order/history/`, `/storecredit/info`; AhrefsBot and AhrefsSiteAudit are allowed; no crawl-delay, same 12 sitemaps on `6thstreet.com`. Protego: `/search?q=black%20blazer` ALLOWED. This confirms the earlier finding that there is no search restriction.

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://en-ae.6thstreet.com/robots.txt` | 200 | 805 |
| 2 | `https://en-ae.6thstreet.com/robots.txt` (second script run) | 200 | 805 |
| 3 | `https://en-ae.6thstreet.com/search?q=black%20blazer` | 301 to `https://en-ae.aivi.com/search?q=black%20blazer` | 148 |
| 4 | `https://en-ae.aivi.com/robots.txt` | 200 | 894 |
| 5 | `https://en-ae.aivi.com/search?q=black%20blazer` | 200 | 57,522 |
| 6 | `https://en-ae.aivi.com/robots.txt` (second script run) | 200 | 894 |
| 7 | `https://en-ae.aivi.com/search?q=jacket` | 200 | 57,522 |
| 8 | `https://en-ae.aivi.com/search?q=shoes` | 200 | 57,522 |
| 9 | `https://en-ae.aivi.com/ig5901905310209-brown-inglot-amc-brow-liner-gel-20-brown-for-female9999.html` (product page) | 200 | 57,522 |

No 403, 429, CAPTCHA, login wall or challenge page was seen. Latency: search pages 1.1 to 1.6 s; `aivi.com/robots.txt` was slow (4.3 s and 7.6 s) while the old host answered in 1.3 to 1.5 s. A 6 s per-phase timeout is tight for the first request.

## Search URL template

`https://en-ae.aivi.com/search?q={query}` (query percent-encoded, spaces as `%20`).

Caveat: this is the path the old host redirected to, and the server returns 200 for it, but because the server answers every path with the same shell, the response does not prove the template is the one the application's own search box uses.

## Data path

**none** for a plain HTTP client.

Evidence:
- All four responses (three searches and the product page) are **byte-identical** (57,522 bytes, SHA-1 `59564a3f52142ba74fdaaaf38784e8c08004671d`). The server returns one create-react-app shell for any path, including a product page, so HTTP status codes carry no information.
- The shell contains `<div id="root">` with only a spinner, `<noscript>You need to enable JavaScript to run this app.</noscript>`, and two bundle `<script src>` tags (`/static/js/114.*.chunk.js`, `/static/js/main.*.chunk.js`).
- Zero `application/ld+json` blocks, no `__NEXT_DATA__`, no `<script type="application/json">`, no product-card markup. The only inline state is `window.contentConfiguration={}` and `window.storeList=["default"]`.
- The head's resource hints show where the browser gets its data: an Algolia host (`02X7U6O3SI-dsn.algolia.net`), `catalog.6thstreet.com`, `mobilecdn.6thstreet.com`, `config.aivi.com` and `media.6media.me`. Web search results also say 6thStreet search runs on Algolia. **None of these was requested.** They are outside the permitted request list (robots, search pages, one product page), and calling a store's front-end search backend with its embedded key is not "reading a public page".

## Extraction strategy needed

**None available.** No strategy in plan module 6.4 (`store_json`, `embedded_json`, `json_ld`, `css`, `shopify`) works on this response, because the response contains no data.

If the business still wants this store, the only route would be `store_json` against the store's own backend API (Algolia or `catalog.6thstreet.com`). That would need a decision from the business, ideally an agreement with Apparel Group for an API or product feed. It was not tested, and it is not a legitimate "honest client" path today.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | no | not in any response |
| price | no | not in any response |
| currency | no | not in any response |
| image URL | no | not in any response |
| product URL | no | not in any response |
| in stock | no | not in any response |
| colour | no | not in any response |

## Hosts

Candidates for `allowed_hosts` (only if the store were ever enabled):
- Store: `en-ae.aivi.com` (current). `en-ae.6thstreet.com` is the legacy host that redirects; do not allow-list it unless product links still use it.
- Image CDN: `media.6media.me` is the only image-looking host in the page, as a `preconnect` hint. **Not verified**: no product image was ever seen.
- Seen in the page but not store hosts and not to be allow-listed: `02X7U6O3SI-dsn.algolia.net`, `catalog.6thstreet.com`, `mobilecdn.6thstreet.com`, `config.aivi.com`.

## Price formats seen

None. No response contained a price.

## Currency / tier hint

Currency: AED expected for the UAE storefront (not observed). Tier hint: **mid** (budget-to-mid). This comes from press coverage listing brands such as Tommy Hilfiger, Charles & Keith, ALDO, Steve Madden, Skechers, Levi's, GUESS, LC Waikiki and Boohoo, not from observed prices.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| black blazer | `https://en-ae.aivi.com/search?q=black%20blazer` (after a 301 from `en-ae.6thstreet.com`) | 200 | 0 |
| jacket | `https://en-ae.aivi.com/search?q=jacket` | 200 | 0 |
| shoes | `https://en-ae.aivi.com/search?q=shoes` | 200 | 0 |

Product page check: 1 page fetched, 200, same shell, 0 JSON-LD `Product` nodes. The URL was a beauty item (an Inglot brow liner) because it was the only product URL that web search returned and no search page gave one. The result would be the same for a fashion item, since the server returns the identical shell for any path.

## Requests made

9 in total: 3 to `en-ae.6thstreet.com` and 6 to `en-ae.aivi.com`, counted as one store against the limit of 12. Rate: at least 1 s between requests.

## Sample

`docs/store-qualification/samples/6thstreet/`:
- `search-shell.trimmed.html` (about 2 KB): the shell with the head's resource hints, root div and script tags. Usable as a negative fixture ("an extractor returns nothing for this").
- `robots.en-ae.aivi.com.txt` and `robots.en-ae.6thstreet.com.txt`: the complete robots files.

## Risks and fragility

- **Client-side rendering is the blocker.** Reading this store would need a JavaScript engine, which project rules exclude, or its undocumented backend, which needs a business decision.
- **Brand and host migration.** The domain changed from `6thstreet.com` to `aivi.com` in 2026. Backend hosts still carry the old name (`catalog.6thstreet.com`), so more changes are likely.
- **Backend dependence.** A search backed by Algolia with a front-end key is not a public API. Using the key would be a terms-of-use question to settle with the store before any use.
- Slow `robots.txt` on `aivi.com` (4 to 8 s) would trip the 6 s client timeout.
- Legacy and current hosts share one robots layout; `/catalogsearch/` is blocked on both.
- Terms of use were not read (Rule 6).
