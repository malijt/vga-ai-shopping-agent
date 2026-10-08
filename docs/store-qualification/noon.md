# Noon qualification (2026-10-07)

**Verdict:** DROP (robots: the search path is disallowed for `User-agent: *`)

Scope: Noon UAE English storefront, fashion section. Client: `httpx` 0.28.1 via `uv run --with httpx`, User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, no redirects followed, no other headers. Run from this machine on 2026-10-07. Only `robots.txt` was requested; nothing further was requested from Noon after it showed the search path is disallowed.

## Storefront

- Base: `https://www.noon.com/uae-en/` (English, UAE). Fashion section: `https://www.noon.com/uae-en/fashion/` (for example `https://www.noon.com/uae-en/fashion/men-31225/`). Confirmed by web search results listing these URLs; I did not fetch them.
- Product URL shape (from web search results, not fetched): `https://www.noon.com/uae-en/<slug>/<SKU>/p/`, for example `https://www.noon.com/uae-en/black-regular-fit-stretch-blazer-for-women/Z5FC684D4BFBFDB092659Z/p/`.
- Noon is a multi-seller marketplace (many brands and third-party sellers in one catalogue).

## robots.txt

- `GET https://www.noon.com/robots.txt` -> 200, 3614 bytes, `text/plain`, `server: istio-envoy`. (The timeout seen earlier today did not reproduce in this session.)
- Rules for `User-agent: *` that matter here (verbatim):
  ```
  Disallow: /*/search$
  Disallow: /*/search?
  Disallow: /*/search/
  ```
  Also disallowed for `*`: `/_svc/`, `/_vs/`, `/_serverFn/`, cart, checkout, wishlist, `account_mobile`, `buynow`, `oauth/authorize`, digital-card and gift-card transaction paths.
- Our User-Agent matches only the `*` group. The groups for `GPTBot`, `ChatGPT-User`, `ClaudeBot` and `PerplexityBot` do not disallow search and end with `Allow: /`. Those groups do not apply to us and we must not present ourselves as those agents. Noon fully disallows `BadBot`, `YandexBot`, `PetalBot`, `Bytespider`, `Baiduspider`, `Amazonbot`, `GoogleOther`.
- `Crawl-delay`: none.
- `Sitemap:` lines: `https://www.noon.com/sitemap-index.xml`, `https://www.noon.com/blog-sitemap.xml` (not fetched).
- Evaluation (offline, RFC 9309 wildcard matching on the file I fetched): `/uae-en/search/?q=black%20blazer` -> disallowed by `/*/search/`; `/uae-en/search?q=black%20blazer` -> disallowed by `/*/search?`; `/uae-en/search` -> disallowed by `/*/search$`; `/uae-en/fashion/men-31225/` -> allowed.
- **Tooling finding for the plan (module 6.2.1):** Python 3.12.14's `urllib.robotparser` (the project's pinned runtime) does not implement `*` or `$` wildcards. Run on this exact file it returned `can_fetch(...) == True` for `/uae-en/search/?q=black%20blazer`, which is wrong. Python 3.14.7's stdlib returned `False` (correct). A 3.12 robots checker needs its own wildcard-aware matcher (or a library that implements RFC 9309). The same gap affects the Level Shoes and Centrepoint rules (see their reports).

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://www.noon.com/robots.txt` | 200 | 3614 |

No search page, product page or category page was requested.

## Search URL template

`https://www.noon.com/uae-en/search/?q={query}` is the commonly used form, but I did not observe it (not requested, and web search did not return a search URL). Every `/<locale>/search` form is covered by the three disallow rules above, so the exact form does not change the verdict.

## Data path

none (not assessed). The search path is disallowed, so no search page was requested and no data path was tested. Whether category or product pages carry JSON-LD or embedded JSON was not checked.

## Extraction strategy needed

none (store dropped). If Noon is ever re-opened by permission, the likely candidate is `embedded_json`, but that is unverified and no evidence was gathered.

## Fields available

Not assessed (no page body was fetched).

| Field | Available |
|---|---|
| title | not assessed |
| price | not assessed |
| currency | not assessed (AED expected) |
| image URL | not assessed |
| product URL | not assessed |
| in stock | not assessed |
| colour | not assessed |

## Hosts

- Store host: `www.noon.com`.
- Image CDN host: not observed. Do not add Noon to any `allowed_hosts` list.

## Price formats seen

None observed.

## Currency / tier hint

AED. Tier hint: mid (broad marketplace across budget to premium). This is an inference from web search snippets, not an observation.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| `black blazer` | not requested (disallowed by robots) | n/a | n/a |
| `jacket` | not requested (disallowed by robots) | n/a | n/a |
| `shoes` | not requested (disallowed by robots) | n/a | n/a |

## Requests made

1 (`robots.txt`).

## Sample

None (store is not GO).

## Risks and fragility

- The block is a policy decision published in `robots.txt`, not a technical block, so it will not go away by changing the client. Category and product pages are not disallowed for `*`, but this product searches by keyword and cannot work from category pages without a separate design.
- Options outside this module: ask Noon for permission or a partner or affiliate feed (BRD decision 5, money plan). Do not use the `ClaudeBot`/`GPTBot` carve-outs: they are for those operators' own agents.
- Earlier today Noon timed out from this machine; this run it answered at once. Treat reachability as variable, but it no longer matters for the verdict.
- Python 3.12 stdlib robots parsing would wrongly allow this store (see the tooling finding above). Phase 6 must not rely on it.
