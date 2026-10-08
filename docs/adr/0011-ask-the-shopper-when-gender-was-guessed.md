# ADR 0011: Ask the shopper when the gender was only guessed, and let the acceptance harness answer from the query file

- **Status:** Accepted. Decided by the user on 2026-10-08 ("ask user whether its man or woman"); recorded here after the fact. It keeps BRD Rule 8 and plan assumption A3 unchanged.
- **Date:** 2026-10-08
- **Sources:** `docs/01-business-requirements.md` (Rule 8); plan A3; `CHANGELOG.md` 2026-10-08 (Decided, and Added: "Who is this for? on the page" and "The acceptance harness answers it"); `app/components/gender_question.py`; `src/vga/pipeline/rerun.py`; `eval/harness/confirm.py`; `eval/data/queries.yaml`.

## Context

Rule 8: a gender the model only guessed is shown, not applied, until the shopper confirms it. The
guess appeared as a chip with a note, which was easy to miss. A women's outfit photo then also
returned men's shoes.

A headless acceptance run has nobody to ask. Left alone, the same women's photos would be scored with
men's shoes mixed in.

## Options considered

For the page:

1. **Apply the guess.** Rejected: it breaks Rule 8.
2. **Keep the chip and the note.** Rejected: easy to miss, and the mixed results stay.
3. **Ask a question above the results (chosen).**

For the harness:

1. **Leave the question unanswered.** Rejected: it measures a behaviour the page does not have.
2. **Apply the model's guess in the harness.** Rejected: it breaks Rule 8 in the test.
3. **Record the answer in the query file and give it as the page does (chosen).**

## Decision

**The page.** After a search with results, if some garment's gender is not stated by the shopper, the
page asks "Who is this for?" with three buttons: Women, Men and Show both.

- Women or Men searches again with that gender on every garment that is not explicit. It goes through
  the chip path: no photo is sent and OpenAI is not called. Only the gender changed, so the products
  already fetched are filtered locally and no store is asked (ADR 0010). That holds while those
  products are fresh (600 seconds); after that the stores are asked again. The question then has
  nothing left to ask and goes away.
- Show both closes the question and changes nothing.
- It is not asked when the shopper typed the gender, nor when there are no results. It is asked once
  per search.

**The harness.** A query may carry `shopper_gender` (women or men) in `eval/data/queries.yaml`.

- When some garment's gender was not stated, the harness gives the answer exactly as the page does,
  with one re-search. The results of that second search are the ones scored, labelled and link-checked.
- A gender the request stated stands, even if it differs from the recorded answer. The difference is
  reported.
- A query with no recorded answer is not re-searched. The harness never applies a guess on its own.
- The 30-second limit is checked against the first search alone, which is the wait before the shopper
  sees anything. The report shows the first search, the second and their sum.
- The frozen query file was amended once, before any acceptance run: `shopper_gender: women` was added
  to the seven photo queries, because each supplied photo shows women's clothing. No input, text or
  note was changed.

## Consequences

- The first results still show both genders until the shopper answers. The answer is a stronger signal
  than the model's guess, and it is free.
- The acceptance figures describe the app after a shopper answered "women". That is what a real
  shopper sees.
- If a photo of men's clothing is ever added, its recorded answer must be `men`.
- A recording replays offline with the extra search included.
