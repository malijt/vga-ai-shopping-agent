# Max Fashion qualification (2026-10-07)

**Verdict:** DROP (blocked: HTTP 403 Cloudflare managed challenge on the first request, `robots.txt`)

Scope: Max Fashion UAE English storefront (Landmark Group). Client: `httpx` 0.28.1 via `uv run --with httpx`, User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, no redirects followed, no other headers. Run from this machine on 2026-10-07. One request was made; per the rules nothing further was requested after the 403.

## Storefront

- Base: `https://www.maxfashion.com/ae/en/` (English, UAE), confirmed by web search results listing this URL. Category pages look like `https://www.maxfashion.com/ae/en/c/women` and `https://www.maxfashion.com/ae/en/c/mxwomen-shoes`. None were fetched by me.
- Max is the Landmark Group value-fashion retailer. Same URL shape as Splash and Centrepoint (see the shared-platform finding below and in `centrepoint.md`).

## robots.txt

- `GET https://www.maxfashion.com/robots.txt` -> **403**, 5502 bytes, `text/html; charset=UTF-8`, `server: cloudflare`.
- The body is Cloudflare's interstitial: `<title>Just a moment...</title>`, `<meta name="robots" content="noindex,nofollow">`, a script from `challenges.cloudflare.com`, and `cType: 'managed'`.
- Because `robots.txt` itself could not be read, no rules, crawl-delay or `Sitemap:` lines are known. No further request was made.

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://www.maxfashion.com/robots.txt` | 403 (Cloudflare managed challenge) | 5502 |

No search page or product page was requested.

## Search URL template

Not observed. Web search results did not return a Max search URL. Landmark's shared URL shape suggests `/ae/en/search` with a `q` parameter, but this is unconfirmed.

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

- Store host: `www.maxfashion.com`. `www2.maxfashion.com` also appears in web search results (an alternate front end).
- Image CDN host: not observed.

## Price formats seen

None observed.

## Currency / tier hint

AED. Tier hint: budget (value-fashion retailer). This is an inference from web search snippets, not an observation.

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

- Same behaviour as Splash: Cloudflare returns a managed challenge to a plain, honest HTTP client. Dropped, not bypassed. No browser impersonation, headless browser, proxy or retry with other headers was tried.
- Not tested from any other network; the verdict applies to this machine and this client on 2026-10-07 only.
- Shared-platform finding: Splash, Max and Centrepoint (all Landmark Group) share the same URL scheme (`/ae/en/`, `/c/<category>`, `/p/<product>`, `/department/<x>`), the same Cloudflare front, and the same style of challenge. Treat them as one outcome.
