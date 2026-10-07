# ADR 0004: Rank with a weighted score; cut price ranges at quartiles of this search

- **Status:** Accepted. Decided in the approved implementation plan (v2, 2026-10-07), following PRD R8 and "Price ranges and the final list"; recorded here.
- **Date:** 2026-10-07
- **Sources:** `docs/02-prd.md` (R8, R13-R16, "Price ranges and the final list"), `docs/03-proposed-ideas.md` (Price ranges row), plan sections 4, 7 (Phases 7 and 9), 10, 11 (A4, A7), 12.3; risk R12.

## Context

Two related choices shape the final list.

**Ranking.** PRD R8 asks for "a simple score": how well the title and attributes match the request, plus image similarity when the request has a product photo, plus price fit, with "weights in one config file". The backend best-practice document suggests rank fusion for combining retrieval signals.

**Price ranges.** The final list of 30 is split into Budget, Mid-range, Premium and Luxury by a configurable percentage mix (R13, R14). Two knobs are separate: where the range borders sit, and how many results come from each range.

## Options considered

Ranking:

1. **Weighted sum of the three scores, weights in settings (chosen).**
2. **Rank fusion.** Rejected for now because PRD R8 requires the weights in one config file. Deferred; see the trigger below.

Range borders:

1. **Quartiles of the candidate prices for this search, per garment category (chosen).** Cheapest 25% is Budget, then Mid-range, Premium, and the top 25% is Luxury. The borders adjust to what the stores sell, so a t-shirt search and a coat search get different ranges.
2. **Fixed AED bands per category in configuration.** An option in the proposed-ideas document; needs market knowledge we do not have for the demo.
3. **Tag known luxury stores as Luxury.** Also listed in the proposed-ideas document; ties the label to a store rather than to the price.

## Decision

- **Score:** `total` is a weighted sum of `text`, `image` and `price` scores, each between 0 and 1, with the weights in `ranking_weights` in `config/settings.yaml`. When there is no image score (no photo, or the image ranker is off or failed), the image weight is dropped and the remaining weights are renormalised. Products below `min_match_score` are removed and never used to fill a thin range.
- **Price fit:** within budget scores 1 and decays above it; with no budget the score is a neutral value from settings. The budget is a flag, not a hard drop: over-budget items are kept and marked `over_budget` (assumption A4).
- **Ranges:** quartile borders per garment category, computed over all category-matching candidates, including over-budget ones (A4). Within each range the best-matching products come first, with at most `max_per_store` results per store across the list.
- **Counts:** the mix in `tier_mix` (default 25/25/25/25) becomes counts by largest-remainder rounding that always sums to the total, ties going to the cheaper range. The presets are Even 25/25/25/25 (8/8/7/7 of 30), Value first 40/30/20/10 (12/9/6/3) and Luxury first 10/20/30/40 (3/6/9/12). A request that asks for "cheaper" without giving a budget switches to Value first (A7).
- **Thin ranges:** fill gaps from the nearest range and flag `few_options`; if nothing above the minimum score remains, return fewer results. If a budget is given, Budget and Mid-range stay within it; Premium and Luxury may exceed it and are labelled over budget.
- **Honesty about the borders:** each range shows its real price span and result count, for example "Budget · 45-139 AED · 8 results". If no enabled store is luxury-leaning, `relative_range` is flagged on Luxury, because it then only means "most expensive found".

## Consequences

- All tuning lives in one settings file, and the weights are tuned against a recorded run, never per query (plan 16.3.1).
- The score is easy to explain and to test, but the weights may prove unstable across queries. **Revisit** with rank fusion only if weight tuning proves unstable across queries (plan section 10).
- Quartiles are relative to this search's candidates, not the whole market (risk R12). On a small or single-store pool they are not very meaningful, which is why the real span, the `few_options` flag and the `relative_range` flag are shown.
- The PRD's open question 4 (quartiles versus fixed AED bands, and whether the even mix is the right default) is answered here only as the default; fixed bands remain possible if the business asks.
