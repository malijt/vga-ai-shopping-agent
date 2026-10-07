# Styli qualification (2026-10-07)

**Verdict:** DROP (blocked): the very first request, `robots.txt`, returned HTTP 403 with a Cloudflare "Just a moment..." challenge page to the honest client. Re-checked once as instructed; nothing further was requested.

## Storefront

- Brand name: Styli. The storefront domain is **`stylishop.com`**, not `styli.com`. UAE English storefront: `https://stylishop.com/ae/en/` (confirmed by WebSearch results restricted to `stylishop.com`, for example `https://stylishop.com/ae/en/list/women/clothing/dresses`; that is search-engine evidence, not a request from our client).
- Landmark Group's e-commerce-only fashion brand (public descriptions). Fast fashion, men, women, kids, plus footwear and accessories.
- The apex host `stylishop.com` was tested. The `www.stylishop.com` variant was not tried because the first 403 means stop.

## robots.txt

- Status: **403**, 5,519 bytes, `content-type: text/html; charset=UTF-8`, `server: cloudflare`.
- The body is the Cloudflare challenge page (saved body has the markers `just a moment` and `challenge-platform`), not a robots file.
- No rules could be read, so there are no rules to quote and no parser was run. Crawl-delay: unknown. Sitemap lines: none readable.
- Per BRD Rule 2, no search page, category page, sitemap or product page was requested.

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://stylishop.com/robots.txt` | 403 | 5519 | 2.35 s | Cloudflare challenge page, HTTP/1.1, no redirect |

Request sent with exactly `User-Agent: vga-shopping-agent-demo/0.1 (store-qualification research)` and no other custom header. No retry, no header change.

## Search URL template

Not determined. The search path was never requested because the site blocked the honest client at `robots.txt`.

## Data path

`none`. Evidence: the only response received is the Cloudflare JavaScript challenge page.

## Extraction strategy needed

None (store dropped).

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

- Observed: `stylishop.com` (storefront host that answered), `challenges.cloudflare.com` (referenced by the challenge page; not a store host).
- Image CDN: not observed.
- Not a candidate for `allowed_hosts` because the store is dropped.

## Price formats seen

None (no product data received).

## Currency / tier hint

budget to mid (from public descriptions of the store, not observed). Expected currency AED on the `/ae/en/` storefront, unverified.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| (none) | not requested | n/a | 0 |

## Requests made

1 (`robots.txt`).

## Sample

None (not a GO store).

## Risks and fragility

- Same Cloudflare challenge page as Ounass, Brands For Less, VAO Concept Store and H&M UAE, all seen on 2026-10-07 in this module: several GCC fashion retailers block non-browser clients at `robots.txt`. Not worked around, per the project rules.
- Not tested: whether the result differs on the user's network. If re-tested there, use the same honest client unchanged.
