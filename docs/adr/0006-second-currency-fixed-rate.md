# ADR 0006: A second currency, converted at a fixed rate for comparison only

- **Status:** Accepted. Decided by the user on 2026-10-08; recorded here.
- **Date:** 2026-10-08
- **Sources:** `docs/01-business-requirements.md` ("In scope"), `docs/02-prd.md` (open question 3), plan section 11 (A28), `docs/store-qualification/designer-store-qualification.md`, `config/settings.yaml`.

## Context

The demo was AED-only: every enabled store prices in AED, the price parser accepted two-decimal amounts only, and the price ranges kept one currency.

The user named eight Kuwaiti designer brands to add. Four can be read by an honest client; three of them price in Kuwaiti dinar (Bazza Alzouman, Hamsa, Manal Smaoui). The BRD says a result shows "price in the store's currency". Price ranges and a budget need one common unit to compare prices.

## Options considered

1. **Leave the dinar stores out.** Simple, but the user asked for them, and Hamsa is the third store that sells abayas.
2. **Show the dinar price only and keep the stores out of the price ranges.** Results would have no price range and a budget could not apply to them.
3. **Convert at a live exchange rate.** One more outside service, a new failure mode, and prices that move between two runs of the same search.
4. **Keep the store's own price and add an approximate AED figure from a fixed rate in configuration (chosen).**

## Decision

- A product keeps **its own price and currency**, exactly as the store gave them.
- The settings hold a base currency (`base_currency: AED`) and a table of fixed rates (`fx_rates`). The dinar rate is 1 KWD = 11.92 AED, from the Central Bank of Kuwait's dollar rate on 2026-10-07 and the dirham's fixed peg to the dollar; the source and date sit beside the number.
- A result carries the **approximate AED figure** (`base_price`) only when its currency is not AED. The page shows both, for example `245.000 KWD (about 2,920 AED)`. The "about" figure is rounded to the nearest 10 AED from 100 AED up, because a fixed rate is good to about 1%.
- **Price ranges, the budget check, the over-budget flag and the reason sentence all use the AED figure.** Range headers are in AED.
- A currency with no rate is **never converted**: its products get no budget claim and are left out of the price ranges, with a plain warning. The app does not guess a rate.
- A three-decimal amount such as `260.000` is a price **only** for a store whose currency has three decimals (KWD, BHD, OMR). For an AED store the same text is still rejected, because there it more likely hides a thousands separator.
- The home market stays the UAE (`country: AE`). Stores of other listed countries (`extra_store_countries: [KW]`) are searched too, and a store is still unused unless `enabled: true`.
- There is **no live exchange-rate call**.

## Consequences

- The three dinar stores can sit in the same price ranges as the AED stores, and a budget in AED applies to them.
- The AED figure is approximate. The rate drifts (the dinar is pegged to an undisclosed basket), so it must be refreshed before any real use; the configuration says so.
- A shopper who buys pays the store's own price in dinar; the AED figure is a guide, and the page labels it "about".
- A store in pounds or dollars is not carried until a rate for it is added on purpose (Heba Shaikh, in GBP, is held in reserve for that reason).

## Update (2026-10-08): what the build changed

The decision is built as written. The text above is kept. Three things were added or learned.

- **Where the AED figure lives.** The price-range shaper writes it onto the shown product as
  `ScoredProduct.base_price`, and only when the product's currency is not AED. The page and the
  command line convert nothing. The page adds one sentence above the results saying that ranges and
  the budget go by the AED figure. A range holding a converted product has its span widened to whole
  AED, so a header does not claim cents from an approximate rate.
- **A price trap in one dinar store.** Hamsa's search price is the cheapest variant, which was a
  scarf's on half its abayas. Those records are dropped, not corrected (ADR 0012).
- **Still to do before real use.** The rate is a fixed approximation from 2026-10-07. It drifts and
  must be refreshed by hand, with its source and date, before anyone relies on it.
- **Still true.** The three dinar stores are enabled (Bazza Alzouman, Hamsa, Manal Smaoui). Heba
  Shaikh (GBP) is still in reserve and needs a rate before it can be added.
