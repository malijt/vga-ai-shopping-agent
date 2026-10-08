# ADR 0007: Search a store only for the categories and genders it sells

- **Status:** Accepted. The gender half was decided when Wave 2 was launched (plan section 6, "Store gender"). The category half was decided on 2026-10-08 after a real search (plan A27). Recorded here after the fact.
- **Date:** 2026-10-08
- **Sources:** plan section 6 ("Store gender") and A27; `CHANGELOG.md` 2026-10-08 (Decided and Fixed: "A store is searched only for the categories it sells"); `src/vga/models.py` (`StoreConfig.genders`, `StoreConfig.categories`, `sells_for_gender`, `sells_category`); `src/vga/pipeline/planning.py` (`stores_for_item`); `src/vga/pipeline/reports.py`; `config/stores/*.yaml`.

## Context

Store search pads its answers. A real search for shoes returned an abaya from a dress and modest-wear
store. The abaya's title names no garment, and a product whose category cannot be read is kept for
every request, so the category filter let it through.

Many of the stores that can be read are single-brand boutiques: women-only, or dresses only. Sending
them a request they cannot answer also wastes a request, and every request to a store on the shared
platform counts against its limit (ADR 0010).

## Options considered

1. **Rely on the category filter alone.** Rejected: it cannot catch a title with no garment word.
2. **Special rules in code for each such store.** Rejected: adding a store must add a file, not code
   (Open/Closed).
3. **Say in the store's file what it sells, and do not ask it for anything else (chosen).**

## Decision

- `StoreConfig` has two optional lists: `genders` and `categories`. Unset means "all, or not known".
- Before a garment is searched, `stores_for_item` leaves out every store that does not sell its
  category, and every store that does not sell for its gender. Only a gender the shopper stated or
  confirmed counts (BRD Rule 8). A guessed gender excludes no store.
- A store left out gets no request. The response lists it as skipped with a plain reason, for
  example "Not searched: Hanayen does not sell shoes." When no store sells a category at all, a
  warning says so.
- The shipped files: six stores are `categories: [dresses]` (Hanayen, Maison Arabelle, Nishat Linen
  UAE, Signature Studio, Bazza Alzouman, Hamsa). Seven are `genders: [women]` (Oh Polly, Club L
  London, Hanayen, Maison Arabelle, Bazza Alzouman, Hamsa, Manal Smaoui). Where a store sells several
  families (Manal Smaoui) the list is left unset.

## Consequences

- The abaya under "shoes" is gone, and those stores get no request for a shoes or jeans search.
- The lists are written from the records seen, and "not seen" is not "not sold". A store that adds a
  new line is missed until its file is edited. Each store note says what the list rests on.
- One known edge: Nishat Linen UAE sells a men's shalwar titled "Basic Kurta". It ranks as a dress,
  and a men's trousers search is not sent to the store (`docs/store-notes/nishat-linen-uae.md`).
- This does not replace the category filter. Both run.
