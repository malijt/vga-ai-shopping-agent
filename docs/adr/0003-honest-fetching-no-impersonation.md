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
