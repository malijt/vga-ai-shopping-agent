# ADR 0013: One 30-second deadline for the request, and a late store costs only its own answer

- **Status:** Accepted. Decided when the pipeline was built (Phase 13); refined on 2026-10-08. Recorded here after the fact.
- **Date:** 2026-10-08
- **Sources:** `docs/02-prd.md` (30 seconds); plan sections 6 and 12.3 ("One synchronous request"), 13.2.2; `src/vga/pipeline/pipeline.py`; `src/vga/pipeline/state.py`; `src/vga/fetch/deadline.py`; `src/vga/stores/engine.py`; `CHANGELOG.md` 2026-10-08.

## Context

The business wants results in 30 seconds or less. Stores differ: some are slow, some refuse, and the
stores of one platform wait in one queue (ADR 0010). A request that waits for the slowest store either
passes 30 seconds or loses every answer.

## Options considered

1. **Wait for every store, fail at the limit.** Rejected: it loses all answers because of one slow store.
2. **A timeout per store only.** Rejected: the waits can still add up to more than 30 seconds.
3. **One deadline for the request, one task per store, and partial results (chosen).**

## Decision

- `SearchPipeline.run` runs all its steps inside one deadline: `request_deadline_s`, 30 seconds, on
  the injected clock.
- Each pair of garment and store is its own task, all started together. Every step writes what it has
  finished into the run's state as it goes.
- At the deadline, whatever is still running is cancelled, and the response is built from what had
  finished. Stores that did answer count. An item with no products gets an empty group. A warning
  says time ran out, and a store that had not answered is reported as "did not answer in time".
- If the request has not been understood by then, there is nothing to show. The shopper gets a plain
  "took too long" error.
- A store's own budget is 6 seconds times the keyword variants it may be sent (at most 2) plus one for
  robots.txt. It counts only time spent working. Time a request waits in a queue pauses it, because
  that request has not started. The request deadline never pauses: the shopper's time runs while a
  request queues.
- The Understand step gets at most 20 seconds, so two 15-second OpenAI timeouts cannot leave the
  stores no time at all.

## Consequences

- A slow, cold outfit search returns fewer results with a warning, not nothing.
- A search whose image comparison is cut short is ranked on text and price and says so.
- An item whose search did not finish is not stored for a "search again", so a re-run asks the stores
  again.
- The limit has been reached in a real search. Before ADR 0008, a two-garment outfit hit it during
  image comparison and returned what it had, with a plain warning (`CHANGELOG.md`, 2026-10-08). The
  changelog expects a cold four-garment outfit to reach it under the platform limit (ADR 0010). That
  is not measured.
- This is a deliberate departure from "retry slow work" and "push slow work to background jobs": it is
  a single synchronous request in a single-user local demo (plan 12.3).
