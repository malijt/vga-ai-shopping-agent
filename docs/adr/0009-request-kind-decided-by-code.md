# ADR 0009: The code decides the kind of request, not the model's label

- **Status:** Accepted. Decided on 2026-10-08 after a live eval failure; recorded here after the fact.
- **Date:** 2026-10-08
- **Sources:** `CHANGELOG.md` 2026-10-08 (Found: "Live Understand eval after the validation changes: 23 of 24 passed"; Fixed: "The kind of request is decided by the code"); `src/vga/understand/prompts/CHANGELOG.md` (understand-v2 entry); `src/vga/understand/input_type.py`; `src/vga/understand/validation.py` (`_derive_input_type`); `src/vga/understand/fallback.py`.

## Context

The model's answer carries an `input_type` label: text, product photo, outfit photo or photo and text.
The kind of request matters downstream. Only an outfit photo skips image comparison (ADR 0008) and
gets 12 results per garment instead of 30.

On 2026-10-08 the real model labelled the same single-gown photo a product photo in one run and an
outfit photo in the next. Had the label been trusted, a flip would have silently taken image
comparison and results away from the shopper.

## Options considered

1. **Trust the model's label.** Rejected: it is not stable.
2. **Tighten the prompt.** Rejected: a prompt cannot make a model deterministic, and every prompt
   change needs a new version and a new eval.
3. **Work it out from facts the code already knows (chosen).**

## Decision

`derive_input_type` is the one place that decides:

- no photo: `text`;
- a photo and typed text: `photo_text`;
- a photo only, one garment: `product_photo`;
- a photo only, two or more garments: `outfit_photo`.

Validation ignores the model's label. A label that disagrees is not an error and does not cause a
retry. It is noted at debug level so a flipping model can be seen in the log. The raw-words fallback
uses the same function, so the two paths cannot drift apart.

## Consequences

- The live eval went from 23 of 24 to 24 of 24, with a typical answer of 1.9 seconds and a worst of
  3.0.
- The model still decides how many garments a photo holds. That count is what separates a product
  photo from an outfit photo, so a wrong count is still a wrong kind of request.
- `input_type` is still in the answer schema and the prompt, but nothing reads it. Removing it is a
  prompt change, with a new version and an eval, and is left for the next version.
