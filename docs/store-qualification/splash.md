# Splash qualification (2026-10-07)

**Verdict:** DROP (blocked: HTTP 403 Cloudflare managed challenge on the first request, `robots.txt`)

Scope: Splash UAE English storefront (Landmark Group). Client: `httpx` 0.28.1 via `uv run --with httpx`, User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, no redirects followed, no other headers. Run from this machine on 2026-10-07. One request was made; per the rules nothing further was requested after the 403.

## Storefront

- Base: `https://www.splashfashions.com/ae/en/` (English, UAE), confirmed by web search results listing this URL. Category pages look like `https://www.splashfashions.com/ae/en/c/women-clothing`; a search page exists at `https://www.splashfashions.com/ae/en/search` (listed by web search). None of these were fetched by me.
- Splash is the Landmark Group fast-fashion retailer. Same URL shape as Max Fashion and Centrepoint (see "Risks and fragility" for the shared-platform finding).

## robots.txt

- `GET https://www.splashfashions.com/robots.txt` -> **403**, 5528 bytes, `text/html; charset=UTF-8`, `server: cloudflare`.
- The body is Cloudflare's interstitial: `<title>Just a moment...</title>`, `<meta name="robots" content="noindex,nofollow">`, a script from `challenges.cloudflare.com`, and `cType: 'managed'` (a managed challenge that needs JavaScript in a real browser).
- Because `robots.txt` itself could not be read, no rules, crawl-delay or `Sitemap:` lines are known. Per the brief the verdict is the first block, so no further request was made.

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://www.splashfashions.com/robots.txt` | 403 (Cloudflare managed challenge) | 5528 |

No search page or product page was requested.

## Search URL template

Not verified. The site has a `/ae/en/search` page (from web search results). The query parameter was not observed. Landmark category URLs carry facet queries as `?q=:...` (for example `https://www.splashfashions.com/ae/en/c/women-clothing?q=%3A...` in search results), so a `?q={query}` form is plausible but unconfirmed.

## Data path

none (not assessed). Blocked before any page content was received.

## Extraction strategy needed

none (store dropped).

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

- Store host: `www.splashfashions.com`. Other Splash hosts seen only in web search results: `helpae.splashfashions.com` (help centre), `www2.splashfashions.com` (an older or alternate front end).
- Image CDN host: not observed.

## Price formats seen

None observed.

## Currency / tier hint

AED. Tier hint: budget (fast-fashion house brands). This is an inference from web search snippets, not an observation.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| `black blazer` | not requested (blocked) | n/a | n/a |
| `jacket` | not requested (blocked) | n/a | n/a |
| `shoes` | not requested (blocked) | n/a | n/a |

## Requests made

1 (`robots.txt`, 403).

## Sample

None (store is not GO).

## Risks and fragility

- Cloudflare returns a managed challenge to a plain, honest HTTP client. Passing it needs a real browser executing JavaScript, which is out of bounds here (no browser impersonation, no headless browser, no proxies, no retries with other headers). Dropped, not bypassed.
- Not tested from any other network, so the verdict applies to this machine and this client on 2026-10-07 only.
- Splash, Max Fashion and Centrepoint are one group on one platform: treat them as one outcome. If one is ever opened by permission from Landmark Group, the other two probably come with it, and one extractor would probably cover all three.
- Centrepoint's `robots.txt` mentions `/*/aff`, `/*/coupon` and `/*/voucher` paths, which hints at affiliate and coupon flows (not verified). If Splash is wanted later, a partner or affiliate arrangement with Landmark Group is the realistic route, not scraping (BRD decision 5, rule 6).
