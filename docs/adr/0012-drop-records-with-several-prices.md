# ADR 0012: Drop a record whose variants differ in price, rather than show a wrong price

- **Status:** Accepted. Decided on 2026-10-08 while adding the Hamsa adapter; recorded here after the fact.
- **Date:** 2026-10-08
- **Sources:** `CHANGELOG.md` 2026-10-08 (Added: "A Shopify option, `max_price_spread`"; Found: "Hamsa's search price is the cheapest variant"); `src/vga/stores/extractors/shopify.py`; `config/stores/hamsa-kw.yaml`; `docs/store-notes/hamsa-kw.md`.

## Context

In Shopify's search answer, `price` is the lowest price among a product's variants. `price_min` and
`price_max` give the lowest and the highest.

Hamsa sells a head scarf as a cheap variant of the same product as an abaya. On 5 of the 10 abaya
records, `price` was KWD 20 to 95, while the abaya itself costs KWD 75 to 365. Shown as it came, an
abaya would land in the wrong price range and would pass as "within budget" when it is not.

## Options considered

1. **Take the highest price.** Right on four of the five records. Wrong on "Tonal Abaya/Scarf": its
   abaya variant is KWD 75 and its maximum KWD 95 (probably a set).
2. **Use the variant the search matched.** It was the abaya on all five. Rejected: Shopify picks it by
   matching the typed words against variant titles, so another query ("scarf") could match the cheap
   variant, and nothing in the response says which variant is the garment.
3. **Read each product page for its variants.** Rejected: one more request per product, against a
   shared limit (ADR 0010).
4. **Drop a record whose variants do not all cost the same (chosen).**
5. **Leave Hamsa out.** Rejected: it is the third store that sells abayas.

## Decision

The `shopify` strategy has an option, `max_price_spread`, off unless set. With it set, a record is
kept only when `price_max` is at most that many times `price_min`. Any other record is dropped, and so
is a record whose `price_min` or `price_max` is missing or cannot be read (it fails closed). A dropped
record is counted as `missing_price`, and the real reason is logged. Hamsa sets it to `1`, meaning all
variants cost the same. Nothing is corrected.

## Consequences

- Hamsa shows 5 of its 10 abayas and all its kaftans. The five dropped are 2020 pieces, old and
  heavily discounted, so the store loses stock that is not its current range. They are still missing.
- If Shopify stops sending `price_min` and `price_max`, every Hamsa record is dropped and the store
  returns an error. That is on purpose.
- A test pins that the shipped Hamsa file keeps the option. Without it the store must not be enabled.
- If the business wants the five back, the next step is the matched variant, tested against a
  recording of more queries.
- Bazza Alzouman and Manal Smaoui (the other dinar stores) have one price on every record seen. A
  test pins that, so a change shows up.
