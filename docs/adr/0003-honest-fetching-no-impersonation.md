# ADR 0003: Fetch honestly, never impersonate a browser, drop blocking stores

- **Status:** Accepted. Decided in the approved implementation plan (v2, 2026-10-07) and BRD Rule 2; recorded here. One later change, marked below.
- **Date:** 2026-10-07
- **Sources:** `docs/01-business-requirements.md` (Rule 2, Rule 6), plan sections 2, 3, 6 (Phases 2, 6, 14), 10, 12.3 and assumptions A5, A9; risks R1, R3, R8, R9, R18.

## Context

BRD Rule 2 is not negotiable: respect robots.txt, no login-walled pages, no CAPTCHA solving, about 1 request per second per store. A store that blocks an honest client must be dropped.

Store access is the biggest risk (plan R1). Checked from the build machine on 2026-10-07: 6thStreet's `robots.txt` loads and has no search restriction; Ounass and Styli returned 403 to automated clients; Namshi and Noon timed out. A public Noon scraper needs browser TLS-fingerprint impersonation "to bypass bot detection", which signals that Noon will block an honest client.

## Options considered

1. **Plain `httpx` with an honest, identifying User-Agent (chosen).**
2. **`curl_cffi` or Scrapling** (browser TLS-fingerprint impersonation, anti-bot bypass). Rejected: evasion conflicts with Rule 2 and with "drop blocking stores". The anti-ban and proxy modules of the self-healing scraper are rejected for the same reason; only its extraction-cascade idea is borrowed.
3. **Proxies or rotating identities.** Rejected for the same reason.
4. **A headless browser for stores that need JavaScript.** Deferred. Assumption A9: a store that needs JavaScript is dropped. Trigger to reconsider: a must-have store only works with JavaScript and its terms allow it.
5. **Let a model read store HTML.** Deferred. It would put untrusted store content in front of a model, which needs its own injection hardening first. Trigger: fewer than 4 stores qualify with deterministic extractors.

## Decision

- Fetch with async `httpx`, an identifying `User-Agent` (`VGA_USER_AGENT`), **https only**, a response size cap, at most 3 redirects, a 6 second timeout.
- **Every outgoing URL** (search page, thumbnail, link check) must resolve to a host on that store's `allowed_hosts`, re-checked after every redirect; private, loopback and link-local addresses are refused. Product links and image URLs shown to the shopper must be https and on the same list.
- **Respect robots.txt**, fetched and cached per host with RFC 9309 behaviour (4xx means allowed; 5xx or unreachable means disallowed). *Change recorded 2026-10-07:* matching uses **`protego`**, not the standard library's `urllib.robotparser` named in plan feature 6.2.1, because `urllib.robotparser` ignores the `*` and `$` wildcards and wrongly allows paths such as `Disallow: /*/search?`.
- **About 1 request per second per store.** Thumbnails come from image CDN hosts at up to 5 requests per second per host, at most 10 per store (assumption A5), so they do not blow the time budget (R3).
- **Block detection:** a 403, 429 or CAPTCHA/challenge marker marks the store `blocked`. There is no retry and no workaround. The store is skipped for `store_cooldown_s` (default 900 seconds) and reported as `cooldown` on the next query.
- **No retries to stores or image hosts.** This is a deliberate departure from the usual "retry with backoff" rule (plan 12.3): politeness and the 30 second deadline come first, and 2-3 keyword variants already give redundancy. Retries exist for OpenAI only.
- **Qualify before adapting.** Phase 2 checks each store's robots.txt, reachability and data path from the user's network before any adapter is written. Stores are disabled (`enabled: false`) until their live smoke test passes.

## Consequences

- Fewer stores will work than were shortlisted. The plan sets a gate of at least 4 working stores (target 5) including at least 1 luxury-leaning, because the cap of 6 results per store means 3 stores can give at most 18 results, below the 20 required (R2). If the gate fails, the decision goes back to the user; the answer is never to bypass.
- The fetch engine stays small and auditable, and its guards (block policy, request budget, host and link safety) are tested against the real engine in Phase 14.
- Every store's terms of use still need checking before any real users (BRD Rule 6, R9). Fixtures and recordings of real store responses are kept trimmed in a private repository (R10).

## Update (2026-10-08): what the build changed

The decision stands and was tested harder than expected. The text above is kept as written.

- **Rates.** Besides 1 request a second per store, every store on one platform shares a queue of
  2 requests a second (ADR 0010). The first acceptance run showed why: all thirteen stores answered
  HTTP 429 within 11 milliseconds of each other. Thumbnails: at most 40 per search, at most 10 per
  store, 5 a second per image host.
- **Keyword variants.** "2-3 keyword variants already give redundancy" no longer holds. One variant,
  and a second only for a thin answer (ADR 0010).
- **What counts as a block.** A 401, 403 or 429, a redirect to a login page, or a bot-challenge page.
  A 429 from a store's own site also stops every store on the platform, drops the requests still
  queued, and obeys a `Retry-After` (capped at 24 hours). The cooldown starts only after a block. A
  store that only errors or times out is skipped for that search and asked again on the next one.
- **Redirects.** A redirect to another registered domain stops the request. The robots.txt of a
  redirect's target is read before the redirect is followed, for search pages and thumbnails.
- **robots.txt.** Read for every store when the app starts. An unreadable file means "everything
  disallowed" and is remembered for the cooldown period, not for a day. A `Crawl-delay` can only slow
  the store down. Thumbnails pass the same check as search pages.
- **No cookies, no proxies.** The client rejects every cookie and ignores proxy settings in the
  environment. The settings refuse a User-Agent that looks like a browser.
- **Addresses.** An IP address in any notation, a local host name, a port other than 443 and
  credentials in a URL are refused. A listed host name whose DNS record points at a private address
  is not caught (noted in `src/vga/fetch/allowlist.py`).
- **Qualification outcome.** Of 34 sites checked on 2026-10-07, 3 were readable. After the Shopify
  discovery pass, thirteen Shopify storefronts are enabled. Nothing was bypassed to get there.
- **Still open.** No store's terms of use have been reviewed (`docs/store-notes/SUMMARY.md`). Whether
  2 requests a second is under Shopify's allowance is not known.
