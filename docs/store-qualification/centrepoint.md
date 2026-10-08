# Centrepoint qualification (2026-10-07)

**Verdict:** DROP (blocked: HTTP 403 Cloudflare challenge on a public product page; `robots.txt` itself loaded)

Scope: Centrepoint UAE English storefront (Landmark Group). Client: `httpx` 0.28.1 via `uv run --with httpx`, User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, no redirects followed, no other headers. Run from this machine on 2026-10-07. Two requests were made (`robots.txt`, then one product page). The product page returned 403, so per the rules nothing further was requested and no search page was fetched.

## Storefront

- Base: `https://www.centrepointstores.com/ae/en/` (English, UAE), confirmed by web search results. A search page exists at `https://www.centrepointstores.com/ae/en/search/` (listed by web search; the indexed copy shows "No results found", so it is the empty search page). Category pages: `https://www.centrepointstores.com/ae/en/c/women-clothing-coatsandjackets`. Product pages: `https://www.centrepointstores.com/ae/en/buy-<slug>/p/<code>`.
- Centrepoint is the Landmark Group department-store format (Splash is one of its brands). It sells fashion plus electronics, home and kids, so a search needs a fashion filter.

## robots.txt

- `GET https://www.centrepointstores.com/robots.txt` -> 200, 1507 bytes, `text/plain`, `server: cloudflare`.
- Rules for `User-agent: *` (verbatim, the relevant ones):
  ```
  Disallow: /*/cart
  Disallow: /*/checkout
  Disallow: /*/my-account
  Disallow: /*/coupon
  Disallow: /*/voucher
  Disallow: /*/aff
  # URL parameters blocking for SEO
  Disallow: /*?q=
  Disallow: /*?country
  Disallow: /*&price=
  Disallow: /*&range=
  Disallow: /*manufacturerName
  ```
  Also `Allow: /ads.txt`, `Allow: /app-ads.txt`. Named groups `MJ12bot`, `EtaoSpider`, `CazoodleBot`, `dotbot/1.0`, `Gigabot` are fully disallowed. There is a `Host: www.centrepointstores.com` line.
- `Crawl-delay`: none.
- `Sitemap:` lines: 12 index files, one per country and language, including `https://www.centrepointstores.com/ae/en/sitemapindex.xml` (not fetched).
- Search-path relevance (offline RFC 9309 wildcard evaluation): `/ae/en/search/` -> allowed; `/ae/en/search/?q=black%20blazer` -> **disallowed** by `/*?q=`; `/ae/en/search/?text=black%20blazer` -> allowed (no rule). I did not observe which parameter the site's own search form uses. On the Landmark platform `q` is the facet-query parameter (Splash category URLs in web search results carry `?q=:...`), so the site's own search probably uses `?q=` and would be disallowed. This is unverified. I did not try another parameter name to get around the rule.
- **Tooling finding:** Python 3.12.14's `urllib.robotparser` ignores the `*` wildcard and reports `/ae/en/search/?q=black%20blazer` as allowed (wrong). Python 3.14.7's stdlib reports it disallowed. See `noon.md` for the module 6.2.1 consequence.

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://www.centrepointstores.com/robots.txt` | 200 | 1507 |
| 2 | `https://www.centrepointstores.com/ae/en/buy-women-hooded-jacket/p/4423807` | **403** (Cloudflare challenge) | 5668 |

The 403 body is Cloudflare's interstitial: `<title>Just a moment...</title>`, script from `challenges.cloudflare.com`, `cType: 'non-interactive'` (a JavaScript challenge). This is the first 403, so the run stopped there.

Note the order: the product page was requested as the only way to learn the site's real search template without guessing (the brief allows one product page). A search page was therefore never requested. Whether the search page is also challenged is unknown.

## Search URL template

Not verified. Best guess from the shared Landmark platform: `https://www.centrepointstores.com/ae/en/search/?q={query}`, which `Disallow: /*?q=` would block. Unconfirmed either way.

## Data path

none (not assessed). The only page body received was the challenge page.

## Extraction strategy needed

none (store dropped).

## Fields available

Not assessed (no product data was received).

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

- Store host: `www.centrepointstores.com`.
- Image CDN host: not observed.

## Price formats seen

None observed.

## Currency / tier hint

AED. Tier hint: mid (department-store format with branded and house-brand lines, discounts "up to 70% off" in page titles). Inference from web search snippets, not an observation.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| `black blazer` | not requested (blocked on the preceding product-page request) | n/a | n/a |
| `jacket` | not requested (blocked) | n/a | n/a |
| `shoes` | not requested (blocked) | n/a | n/a |

## Requests made

2 (`robots.txt` 200; one product page 403).

## Sample

None (store is not GO).

## Risks and fragility

- A public product page gets a Cloudflare JavaScript challenge while `robots.txt` is served: the bot rule is applied per path or per request, so even a store that publishes a readable `robots.txt` can still block the honest client. Dropped, not bypassed.
- Not tested from any other network; verdict applies to this machine and this client on 2026-10-07 only.
- Even if the challenge were absent, the likely search form (`?q=`) is disallowed by `robots.txt` (unverified).
- Shared-platform finding: Splash, Max and Centrepoint share the Landmark Group URL scheme (`/ae/en/`, `/c/<category>`, `/p/<product>`, `/department/<x>`, `/search`), Cloudflare in front, and the same Cloudflare challenge style (managed on Splash/Max `robots.txt`, non-interactive on a Centrepoint product page). Facet queries use `?q=:relevance:...`, which looks like SAP Commerce (Hybris). That platform guess is an inference from URL shapes only; I did not see page source.
