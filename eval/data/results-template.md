# Acceptance results: run N

Copy this file to `eval/results/run-N/results.md` and fill it in. The harness (plan 11.3.1) fills the
automatic columns; a person fills `good@10` using [`rubric.md`](rubric.md). Do not edit the queries
or the rubric between runs; if one had to change, say why under "Notes".

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Run | N (live, recorded / replay) |
| Model snapshot | |
| Prompt version | |
| Stores working | |
| Price-range mix | 25 / 25 / 25 / 25 (even) |

## Results

Pass rule (PRD): at least 20 results, from at least 3 stores, 30 s or less, all links open the right
product page, at least 7 of the top 10 good, and each price range within 1 result of its target
count or flagged "few options". Fill each cell with the number or `n/N`.

| Query | Results | Stores | Seconds | Links ok | good@10 | Price ranges ok |
|---|---|---|---|---|---|---|
| q01_product_jacket | | | | | | |
| q02_product_sneakers | | | | | | |
| q03_product_jeans | | | | | | |
| q04_outfit_casual | | | | | | |
| q05_outfit_layered | | | | | | |
| q06_text_blazer_budget | | | | | | |
| q07_text_arabic_shirt | | | | | | |
| q08_text_wide_leg_jeans | | | | | | |
| q09_photo_text_jacket_brown | | | | | | |
| q10_photo_text_jeans_black | | | | | | |

How to fill the columns:

- **Results**: number of results shown. Outfit photos: the number per garment, such as `12 / 12 / 11`.
- **Stores**: number of different stores among the results.
- **Seconds**: total time from search to results.
- **Links ok**: working links over total, such as `30/30`.
- **good@10**: good matches among the top 10, such as `8/10`. Outfit photos: one figure per garment,
  such as `8 / 7 / 6`; the query counts as the lowest of them.
- **Price ranges ok**: `yes`, or `no` with the range and the gap. A range flagged "few options"
  counts as ok.

A query passes only if every column meets the pass rule. **Overall verdict:** `__ of 10` queries
pass (list their ids: ...). The demo passes if at least 7 of 10 pass (the rule in `rubric.md`).
Verdict: PASS / FAIL.

## Failures

List **every** failed criterion, one row per failure, none left out. A query that fails two
criteria has two rows. Cause is one of: store, ranking, LLM, price range.

| Query | Criterion failed | Cause (store / ranking / LLM / price range) | Evidence |
|---|---|---|---|
| | | | |

Evidence is something a reader can check: the per-store counts or status, the product titles and
ranks that were wrong, the saved model output, or the price span and counts of the range.

## Notes

Anything that changed since the previous run (model, prompt version, store set, settings), and any
change to the queries or rubric with the reason.
