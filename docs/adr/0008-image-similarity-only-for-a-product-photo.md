# ADR 0008: Compare products with the photo for a product photo and a photo with text, not for an outfit photo

- **Status:** Accepted. Decided on 2026-10-08 after a real search (plan A26); recorded here after the fact.
- **Date:** 2026-10-08
- **Sources:** `docs/02-prd.md` (R8: image similarity "when the request has a product photo"); plan A26; `CHANGELOG.md` 2026-10-08 (Decided and Fixed: "An outfit photo no longer runs image comparison"); `src/vga/pipeline/pipeline.py` (`compares_images`); `src/vga/pipeline/state.py`.

## Context

An outfit photo shows a person in several garments. The pipeline searches once for each garment.
Comparing the photo with thumbnails means up to 40 thumbnails per garment, fetched from one shared
image host at 5 a second.

A real search with a black dress and heels (two garments) spent 18.5 seconds on thumbnails and hit
the 30-second limit. One embedding of a whole-outfit photo is also a weak likeness for the thumbnail
of one garment.

## Options considered

1. **Compare every garment's products with the whole-outfit photo.** Rejected: slow, and a weak signal.
2. **Crop each garment first, then compare.** Rejected for now: it needs a garment detector, which is
   not built and is outside the one-day demo.
3. **Compare only when the request is a product photo or a photo with text (chosen).**

## Decision

- For an outfit photo, `compares_images` is false, on a first search and on a "search again". No
  thumbnail is fetched, the photo is not embedded, no embedding is kept, and the results are ranked
  by text and price. This is not a failure, so it raises no warning. The step is recorded as `skipped`
  in the timings and is not announced to the shopper.
- A product photo and a photo with text are still compared.

## Consequences

- The same real search went from 30.3 seconds and a timeout warning to 9.4 seconds, with 24 results
  from 5 stores.
- Outfit results carry no image score. They are ranked on text and price only.
- The photo's embedding is kept only for the other two kinds of request (ADR 0005).
- The decision depends on telling an outfit photo from a product photo reliably. That is decided by
  code, not by the model's label (ADR 0009).
- **Revisit** if a garment detector is added, or if outfit results prove poor in the labelled run.
