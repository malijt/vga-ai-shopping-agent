# Understand prompt changelog

Every change to the prompt file or to the OpenAI model is recorded here, in the same commit, with
the eval result that justified it (CLAUDE.md, Non-Negotiables: re-run the eval set and add an entry
before changing either). The prompt version and the model id are a matched pair: a result is only
comparable with another that used the same pair.

How to run the eval: `OPENAI_API_KEY=... uv run pytest -m live tests/understand` (the model comes
from `config/settings.yaml`) runs the 6 golden inputs and all 18 cases of
`eval/data/edge_cases.yaml` and writes `eval/results/understand-live.md` with, for every case, what
was expected, what came back, and the latency, calls and tokens it took. Set
`VGA_EVAL_REASONING_EFFORT=none` (or another effort) to compare efforts. Paste the counts below.
The newest entry is first.

## understand-v2: 2026-10-08 (dresses as the fifth category)

- **Prompt:** `understand-v2.md` replaces `understand-v1.md`, which is kept for comparison. What
  changed, and nothing else: (1) five categories, the new one being `dresses` ("dresses, gowns,
  kaftans, abayas, jalabiyas, kurtas and kurta sets, lehengas and similar one-piece or ethnic
  garments"); (2) the `out_of_scope` list no longer names dresses or abayas and now names
  jumpsuits, playsuits, sheilas and hijabs and nightwear next to the old bags, jewellery, watches,
  belts, hats, sunglasses, scarves, perfume, underwear and swimwear; (3) "A dress worn with shoes
  is two items" and "a shirt dress is a dress, a dress shirt is a top"; (4) the keywords use the
  garment's own English word ("abaya", "kaftan", "kurta", "jalabiya", "gown", "dress") and four
  Arabic words are translated (عباية abaya, فستان dress, قفطان kaftan, جلابية jalabiya); (5) two
  new examples (an Arabic abaya request, and an outfit photo of a dress with sandals as two items).
  The output schema's category description now says "five" and its allowed values come from
  `Category`, so `dresses` is in the strict JSON schema sent to OpenAI. The system prompt grew from
  5,664 to about 7,000 characters.
- **Model:** `gpt-6-luna`, unchanged. Call settings unchanged (effort `low`, 3000 output tokens,
  `store=false`, 15 s timeout, at most 2 calls per request).
- **Eval score: 24/24 passed, 0 failed, 0 skipped** (one live run on 2026-10-08 after the merge,
  by the orchestrator from the main checkout; 20 OpenAI calls, no error, retry or fallback).
  This is the first run with the business's own photos: g1 read the gown photo as dresses /
  burgundy / floor-length ball gown, g2 read the outfit photo as two items (a black V-neck maxi
  dress and black heels), g5 applied "dark green" to the gown. e13 (a dress request) parsed as
  dresses; e18 (sunglasses) and e12 (handbag) were declined as out of scope; all seven injection
  cases held. Median latency 3.1 s over all calls (2.8 s for text requests), worst 5.9 s (the
  gown photo). Input tokens averaged 2,934 per call (v1: 2,453). One run is a small sample, and
  the eval still does not judge keyword quality.
- **What was checked offline** (`uv run pytest tests/understand`, no network): that the prompt says
  what the changes above say and stays under its size limit; that validation accepts `dresses` and
  still rejects a category outside the five without echoing it; that the fallback reads a
  category from dress, gown, abaya, kaftan, kurta, jalabiya words in English and Arabic; that
  keywords rebuilt after a chip edit keep "abaya"; that the nothing-to-shop-for message names the
  five categories; all 18 edge cases with a scripted well-behaved model, with a model that is down
  and with a model that obeys the injected text; the 6 golden outputs (g1, g2, g5 rewritten around
  the business's own photos, still hand-written, not recorded).
- **Reason:** scope change by the business on 2026-10-08 (plan assumption A23): every test photo it
  supplied shows a dress, an abaya or ethnic wear. Without this prompt change the model would have
  declined all of them as `out_of_scope` (v1 listed dresses and abayas there).
- **What the live run has to show** (the new risks): e13 (a dress request) now expects
  `valid_schema` with a `dresses` item, no longer `friendly_error`; e18 (sunglasses) is new and
  expects `friendly_error`; the sign in the injection photo now asks for "handbags" instead of
  "dresses" (the picture was regenerated), because "dresses" is no longer a category validation can
  refuse; g1, g2 and g5 point at the business's photos (`dress_burgundy_gown.png`,
  `outfit_black_dress_heels.png`) and are skipped when a file is absent; for the 11 extra photos
  in `eval/data/extra_queries.yaml` (abayas, a kaftan, South Asian sets) check that the keywords
  hold the garment's own word and that an outfit with a dress and shoes comes back as two items.
  An abaya read as `tops` or `outerwear`, or an Arabic request coming back with Arabic keywords,
  would be a failure of this version.

## understand-v1: 2026-10-08 (model pinned to gpt-6-luna, first live run)

- **Prompt:** `understand-v1.md`, unchanged from the 2026-10-07 entry below. No prompt edit was
  needed: every runnable case passed on the first run.
- **Model:** `gpt-6-luna`, chosen by the user on 2026-10-08. OpenAI lists no dated snapshot for it
  (https://developers.openai.com/api/docs/models/gpt-6-luna lists only `gpt-6-luna`), so the
  versioned name is the pin, allowed by name in `UNDATED_SNAPSHOT_IDS` in `src/vga/settings.py`.
  It replaces the never-run `gpt-5-mini-2025-08-07`. Listed price: $0.10 in / $0.50 out per 1M
  tokens, about $0.0003 per call at the token counts below.
- **Call settings:** reasoning effort `low` (the constant `REASONING_EFFORT` in
  `vga/understand/gateway.py`, now sent for `gpt-6` ids too), `max_output_tokens` 3000, `store=false`,
  15 s timeout, at most 2 calls per request. The request shape (strict JSON schema through the
  Responses API, `reasoning.effort`, an image sent as a data URL) was accepted by the API on the
  first try; no 4xx, 429, 5xx, corrective retry or fallback happened in any run.
- **Eval score: 20/20 runnable cases passed, in each of 3 full runs.** The 20 are 3 golden inputs
  (g3, g4, g6) and all 17 edge cases (e01 to e17). **3 golden cases skipped** (g1, g2, g5): they
  need the shopper photos listed in `eval/data/ASSETS.md`, which have not been supplied, so how the
  model reads a real product photo, a real outfit photo and a photo with an edit request is
  **unverified**. 4 of the 17 edge cases (e08, e09, e10, e15: empty, whitespace, 14,000 characters,
  symbols only) are refused in code before any model call, so they test the code, not the model.
  The other 16 cases made 16 calls per run (48 in total, plus 1 single-case check before the first
  run).
- **Latency** (time `understand()` took, from a developer laptop; the three runs agree): median for
  a text request 2.8 to 3.1 s (2,955 ms over all 48 calls), median over all calls 3.0 s, worst
  6.3 s (4.4 to 6.3 s in each run: the photo case e05 twice, the Arabic injection case e03 once).
  A photo request took 2.9 to 6.2 s. The median is under the 5 s line, so the comparison run with
  effort `none` was not made and `low` stays. The one cold call before the first run took 5.0 s.
- **Tokens per call** (the same for every run): 2,453 input on average (about 2,330 for a text
  request, about 2,980 with a photo) and 91 output, including any hidden reasoning. Nearly all the
  input is the system prompt and the schema.
- **What differed between runs:** only the wording of the keywords (for example "navy slim fit
  chinos men" against "navy slim-fit chinos men", a third keyword on some runs). Verdicts,
  categories, colours, genders, budgets and the outcome of every case were the same in all three
  runs. The injected text (an address, a request for the system prompt, "PWNED", a fake `[system]`
  line, instructions printed in a photo) never reached the output.
- **Reason:** the user asked for Luna and for real testing to start. The model had only ever been
  tested through fakes.
- **Not covered:** the eval's judge checks the verdict, category, colour, gender, budget, links and
  the absence of the injected text, not whether the keywords are the best ones. Three runs of one
  prompt are a small sample of a model that is not deterministic. Because the model has no dated
  snapshot, OpenAI can change what `gpt-6-luna` does without our noticing: re-run this eval from
  time to time, and before any change of prompt, model or effort.

## understand-v1: 2026-10-07 (initial prompt)

- **Prompt:** `understand-v1.md`. One job (describe the clothes in a shopper's request); the user
  message is data, never instructions; a `verdict` so the model can say "nothing to shop for";
  four categories; 2-3 English keywords with no price or gender words; gender `explicit` only when
  the shopper's text says so; budget from the text only; edits kept apart from the item.
- **Model:** none was pinned in `config/settings.yaml` when this was written (`openai_model: null`).
  The snapshot found in OpenAI's model documentation was `gpt-5-mini-2025-08-07` (a newer, dearer
  alternative is `gpt-5.4-mini-2026-03-17`); neither was ever run. `gpt-6-luna` replaced them on
  2026-10-08.
- **Call settings:** reasoning effort `low`, `max_output_tokens` 3000 (reasoning tokens count
  against it), `store=false`, 15 s timeout, at most 2 calls per request.
- **Eval score: NOT RUN when this was written.** No `OPENAI_API_KEY` was available, so no live
  golden or edge-case run had happened. The first real run is the 2026-10-08 entry above. The six
  golden fixtures in `tests/understand/golden/` are hand-written, not recorded.
- **What was checked offline** (`uv run pytest tests/understand`, no network): the real OpenAI SDK
  driven against a fake HTTP server; all 17 edge cases with a scripted well-behaved model, with a
  model that is down, and with a model that obeys the injected text or the text printed in the
  photo; the 6 hand-written golden outputs.
- **Reason:** first version.
- **Next step (done 2026-10-08):** run the live eval once with a key and paste the counts. All
  runnable cases passed, so the prompt stayed at `understand-v1`.

## Known limitations and failure modes

Kept here so that nobody has to rediscover them (genai best practice 13).

- **Validation cannot judge meaning.** It stops links, markup and control characters, foreign
  categories, guessed genders, price words, a copied prompt, edits that come from a photo, and a
  budget that is not a number the shopper wrote (a budget written in words, "four hundred", is
  accepted unchecked). It cannot tell that a model which obeyed an injection and still answered
  `ok` with a plausible garment gave the wrong garment. Only the live eval shows that, and the
  prompt rules are the defence.
- **Price words are a list.** A price word the list misses reaches the store search. The list
  covers the common English and Arabic words and number phrases ("under 300 AED", "300 or less",
  "200-300 AED", "<400"); extend `lexicon.py` when a gap shows up. "Air Max 90" is kept on purpose.
- **A mixed request drops what is out of scope.** "A black jacket and a handbag" searches the
  jacket only, without telling the shopper about the handbag.
- **The fallback reads a short word list.** When the model path fails, the category of a text
  request comes from about 100 English and Arabic garment words (the dresses list added in v2:
  dress, gown, kaftan, abaya, jalabiya, kurta, kurti, kameez, lehenga and the Arabic dress, abaya,
  kaftan and jalabiya words). A garment not on the list (for example "saree", "jumpsuit") ends in
  the plain "describe an item" message, not in a search. The fallback keywords are the shopper's
  own words: Arabic stays Arabic (so an Arabic abaya request searches the English-titled stores
  with an Arabic word and will find nothing), and a price limit is not applied.
- **Hoodies and cardigans are `tops`, blazers are `outerwear`.** A fixed choice so the same garment
  lands in the same category every run; the shopper can change the category chip.
- **`dresses` is one broad category (v2).** An abaya, a kaftan, a gown and a kurta set are all
  `dresses`, and "Dresses and ethnic wear" is its chip label. A jumpsuit, a playsuit and nightwear
  are out of scope by choice (the BRD says "similar one-piece or ethnic garments"; a jumpsuit has
  legs). Whether the model keeps to that line for a romper or a lounge set is unmeasured.
- **Gender words are a list.** "Explicit" is downgraded to "inferred" unless the text contains a
  gender word from the English or Arabic list; a stated gender in an unlisted word is shown as an
  unconfirmed chip instead of being applied.
- **The photo is sent to OpenAI** (resized, metadata removed, with `store=false`). The app must say
  so before upload (plan 10.1.2).
- **`gpt-6-luna` has no dated snapshot.** The pin is the model's name, so OpenAI can change its
  behaviour under us. Nothing in the app detects that; re-run the live eval from time to time.
- **Real photos are untested.** The live eval has run only with the two synthetic photos in
  `eval/data/assets/`. g1, g2 and g5 need the business's own photos (`eval/data/ASSETS.md`, now the
  dress and outfit photos of 2026-10-08) and are skipped until the files are in
  `eval/data/assets/private/`. Latency with a real, larger photo may also differ.
