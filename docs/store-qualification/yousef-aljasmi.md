# Yousef Al-Jasmi qualification (2026-10-08)

**Verdict:** DROP. No working official online store was found. The domain a web-search answer named as his official site, `yousefaljasmi.com`, has no `robots.txt` (404) and its home page now answers with a 301 redirect to an unrelated domain (`https://poltekkeskrui.org/`), which was not followed. A second domain, `yousefaljasmi.net`, shows a WooCommerce "Store" in search results but is unverified and looks untrustworthy; it was not contacted.

## Storefront

- Brand: Yousef Al-Jasmi (Yousef Aljasmi), Kuwaiti designer of couture gowns for international celebrities; opened a first store in Kuwait in 2007 per press results.
- **Which domain is his, and how that is known.** A web search for his official website returned an answer naming `www.yousefaljasmi.com`, alongside his Instagram account (`@yousef_aljasmi`) and a Facebook page; pages indexed under that domain were titled "About — Yousef Aljasmi", "Celebrities — Yousef Aljasmi" and "short dresses — Yousef Aljasmi", which reads as a lookbook rather than a shop. No product, price or cart page was seen on `.com`.
- `yousefaljasmi.net`: search results titled "ALjasmi - welcome to Yousef Aljasmi Store" and `/product-category/haute-couture-dresses/` with prices of USD 3,500 per dress (WooCommerce URL shape, search-engine text). The same domain also returned pages called "Anna akana dating" and "Meetup norwich", which are not fashion content and are typical of a hijacked or spam-filled site. No third-party source seen links to it as his shop. Not contacted, and not treated as his store.
- A resale marketplace (The Luxury Closet) lists his pieces. That is a stockist/marketplace, not the brand's own store, and out of scope for this pass.

## robots.txt

- `https://yousefaljasmi.com/robots.txt`: **404** (1,795 bytes, an HTML "Page Not Found" page served through Cloudflare). A missing robots.txt means no rules (RFC 9309); protego treats everything as allowed. The home page was therefore allowed to be requested.

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://yousefaljasmi.com/robots.txt` | 404 | 1795 | 0.9 s | HTML 404 page, no rules |
| 2 | `https://yousefaljasmi.com/` | 301 | 601 | 0.6 s | `Location: https://poltekkeskrui.org/` (a different, unrelated domain); not followed |

No challenge page, CAPTCHA or login wall. The redirect leaves the brand's domain for a domain with its own `robots.txt` and no connection to the brand, so by the project's rule it is a stop, not a hop to follow. Response headers other than `Location` were not recorded.

## Search URL template, data path, extraction strategy, fields, hosts, price formats

Not applicable: no store was reached. `.com` has no search page that was seen, and the `.net` shop was not contacted.

## Currency / tier hint

Not observed. The only price seen is a search-engine snippet for `.net` (USD 3,500 per haute couture dress), which is unverified. Tier would be luxury.

## Requests made

2 (robots.txt, home page). One 404 and one 301; no redirect followed.

## Sample

None (nothing usable was fetched).

## Risks and fragility

- The `.com` domain currently redirects to an unrelated domain. That may be a lapsed domain, a parking redirect or a hijack; any of these makes the domain unfit for use as a source.
- The `.net` look-alike carries spam pages; sending shoppers to it would breach product rule 1 (links only to the brand's own store).
- If the business knows of a current official shop (an Instagram link, a different domain), it can be tested from scratch.
- Not tested: any store page, robots.txt of any other domain, terms of use.
