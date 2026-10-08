# ADR 0014: Read who a product is for from the store's own fields first, then the title

- **Status:** Accepted. Decided on 2026-10-08 while building the store adapters; refined for Signature Studio the same day. Recorded here after the fact.
- **Date:** 2026-10-08
- **Sources:** `CHANGELOG.md` 2026-10-08 (Added: "Product gender from the store's own data" and "The Shopify gender reader recognises menswear and womenswear"; Found: Sacoor's tags); `src/vga/stores/extractors/shopify.py`; `src/vga/rank/filters.py`; BRD Rule 8; `docs/store-notes/signature-studio.md`.

## Context

When a shopper states a gender, products for the other gender must not appear. Titles often name no
gender ("Nelson Pant - Black"). Several stores do say it in two fields of the search answer, `type`
and `tags`. Sacoor Brothers writes `type` as "Winter 2025 / Man / Blazer". Nautica and Maison D'Vie
tag items "Men" or "Women". Signature Studio tags its men's kurta sets "Menswear".

Sacoor also tags women's suits "Formalwear Men" while their `type` says "Woman".

## Options considered

1. **Read the title only.** Rejected: items with no gender word get through.
2. **Pool `type` and `tags` together.** Rejected: Sacoor's women's suits would name both genders and
   be left unlabelled.
3. **Read the fields in order and let the first one that names a gender decide (chosen).**
4. **Let a model read titles.** Rejected: no model reads store content.

## Decision

- The `shopify` reader sets `Product.gender` from `gender_fields`: `type` then `tags` by default, and
  `[]` turns it off.
- A field names a gender when it holds one of these words, whole and in any case: `man`, `men`, `mens`,
  `menswear`; `woman`, `women`, `womens`, `womenswear`, `ladies`; `unisex`. "Women" is never read as
  "men". "Man-made" is not a cue. Other "-wear" words ("Formalwear") are not cues.
- The first listed field that names a gender decides. Within it, "unisex" wins. A field that names both
  men and women gives unknown. A product whose fields name nothing is unknown.
- Unknown is not a verdict. The ranker then reads the title (`title_gender`).
- The ranker drops a product only when the shopper stated or confirmed a gender, and the product
  clearly names the other. It also drops children's items then. A guessed gender never filters
  (ADR 0011).

## Consequences

- On the 160 saved products, every Sacoor, Nautica and Maison D'Vie item was labelled and none wrongly.
  Giordano, Oh Polly and Club L London mostly stay unlabelled and rely on the title or the store's
  `genders` setting (ADR 0007).
- A store that renames a tag silently loses its labels. Tests pin Signature Studio's `Menswear` tag
  and Nishat Linen's `RTW Men` type.
- Women's items at Signature Studio and Nishat Linen carry no gender tag. They stay unknown.
