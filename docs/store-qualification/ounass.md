# Ounass qualification (2026-10-07)

**Verdict:** DROP (blocked): the very first request, `robots.txt`, returned HTTP 403 with a Cloudflare "Just a moment..." challenge page to the honest client. Re-checked once as instructed; nothing further was requested.

## Storefront

- UAE storefront: `https://www.ounass.ae/` (host confirmed live: Cloudflare answered for it).
- Luxury multi-brand fashion retailer (Al Tayer group). Tier and positioning are from public descriptions found with WebSearch, not observed on the site.
- The related `nisnass.com` redirects (301) to `https://www.ounass.com/`, so it is the same business and is not a separate candidate.

## robots.txt

- Status: **403**, 5,523 bytes, `content-type: text/html; charset=UTF-8`, `server: cloudflare`.
- The body is a Cloudflare challenge page, not a robots file: `<title>Just a moment...</title>`, `<meta name="robots" content="noindex,nofollow">`, and a content-security-policy that allows scripts from `https://challenges.cloudflare.com`. The saved body contains the markers `just a moment` and `challenge-platform`.
- No rules could be read, so there are no rules to quote and no parser was run (the protego check does not apply because there is no robots.txt body). Crawl-delay: unknown. Sitemap lines: none readable.
- Per BRD Rule 2 (first 403 or JavaScript challenge means stop), no search page, category page, sitemap or product page was requested.

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.ounass.ae/robots.txt` | 403 | 5523 | 1.94 s | Cloudflare challenge page, HTTP/1.1, no redirect |

Request sent with exactly `User-Agent: vga-shopping-agent-demo/0.1 (store-qualification research)` and no other custom header. No retry, no header change.

## Search URL template

Not determined. The search path was never requested because the site blocked the honest client at `robots.txt`.

## Data path

`none`. Evidence: the only response received is the Cloudflare JavaScript challenge page (no product data, no robots rules).

## Extraction strategy needed

None (store dropped). Nothing for Phase 6 to build for this store.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | not checked | blocked before any product page |
| price | not checked | blocked |
| currency | not checked | blocked |
| image URL | not checked | blocked |
| product URL | not checked | blocked |
| in stock | not checked | blocked |
| colour | not checked | blocked |

## Hosts

- Observed: `www.ounass.ae` (storefront host that answered), `challenges.cloudflare.com` (referenced by the challenge page; not a store host and never an `allowed_hosts` candidate).
- Image CDN: not observed.
- Not a candidate for `allowed_hosts` because the store is dropped.

## Price formats seen

None (no product data received).

## Currency / tier hint

luxury (from public descriptions of the store, not observed). Expected currency AED on the `.ae` storefront, unverified.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| (none) | not requested | n/a | 0 |

## Requests made

1 (`robots.txt`).

## Sample

None (not a GO store).

## Risks and fragility

- The block is a Cloudflare managed challenge; it applies to our honest, non-browser client. Per the project rules it is not worked around (no browser impersonation, no proxy, no headless browser, no `curl_cffi`).
- Not tested: whether the block depends on the network. If the user's network gets a different result, re-run from there with the same honest client; do not treat that as a reason to change headers.
- Ounass is the main luxury candidate on the shortlist, so dropping it leaves the "at least 1 luxury-leaning" gate to other stores (see `luxury-for-you.md`).
