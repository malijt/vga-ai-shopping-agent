# ADR 0010: Pace requests across the whole platform, and send one keyword variant per store

- **Status:** Accepted. Decided on 2026-10-08 after the first recorded acceptance run was throttled (plan A29); recorded here after the fact. It supersedes "2-3 keyword variants per store" in ADR 0001 and ADR 0003.
- **Date:** 2026-10-08
- **Sources:** plan A29; `CHANGELOG.md` 2026-10-08 (Decided, Found and Changed entries about the platform limit); `src/vga/fetch/platform.py`; `src/vga/fetch/ratelimit.py`; `src/vga/fetch/client.py`; `src/vga/stores/engine.py`; `src/vga/pipeline/planning.py`; `config/settings.yaml`.

## Context

BRD Rule 2 says about one request a second per store. All thirteen stores are Shopify storefronts.

In the first recorded acceptance run, about 30 seconds after its first search (about 39 search
requests in 3 seconds, 13 robots.txt requests and 40 thumbnails), the re-search for the gender answer
sent one request to each store at once. All thirteen answered HTTP 429 within 11 milliseconds of each
other. Thirteen shops
refusing at the same instant means the platform counts requests per client across all its shops, not
per shop.

Every store went into its 15-minute cooldown. Queries 2 to 10 returned nothing, and the run printed
"0 of 10 pass". The app obeyed its own rule (no retry, no contact during the cooldown), but the run
was not a result.

One request a second per store is not enough when every store sits on one platform: thirteen stores
at once is thirteen requests a second to that platform.

## Options considered

1. **Keep a limit per store only.** Rejected: this is what failed.
2. **Lower the per-store rate.** Rejected: it does not address a limit that is shared.
3. **Probe Shopify to find its real allowance.** Rejected: it must not be probed.
4. **One shared limit for the stores of a platform, and fewer requests (chosen).**

## Decision

- **A platform queue.** Every request to a store's own site goes through one queue shared by all the
  stores of its platform, at 2 requests a second (`rps_per_platform`), on top of 1 a second per
  store. The platform is read from the store's extraction strategy (`shopify`), so `StoreConfig` did
  not change. A store on no known platform is its own platform. Image hosts are not on the platform
  queue; they keep their own limit.
- **One keyword variant per store.** A second variant goes only to a store whose first returned fewer
  than 5 usable products (`second_variant_below`). Never a third. An outfit photo's garments get one
  each.
- **A 429 stops the platform.** A "too many requests" answer from a store's own site puts every store
  on the platform into cooldown at once, drops the requests still queued, and obeys `Retry-After`.
- **A gender answer costs no request.** Answering "Who is this for?" filters the products already
  fetched, while they are still fresh (600 seconds). See ADR 0011.
- **robots.txt is read when the app starts**, so the first search does not pay for thirteen requests.
- **The harness is gentle too.** It waits 30 seconds between queries and sends at most one link check
  every 2 seconds. A query every store turned away is "not run", and the run stops there.

## Consequences

- A thirteen-store text search is 13 search requests, down from 39. The peak rate at the start of a
  search fell from about 13 requests a second to 2.
- Searches are slower: about 6 to 6.5 seconds of store time for all thirteen, up from about 2. A cold
  four-garment outfit can reach the 30-second limit and returns what arrived (ADR 0013).
- One real search under the new limit finished with no refusal. A full acceptance run under it has
  not been made.
- Not known: whether 2 requests a second is under Shopify's allowance, and whether one variant per
  store gives enough results on every query.
- A new platform is added by naming its strategy in `KNOWN_PLATFORMS` in `src/vga/fetch/platform.py`.
