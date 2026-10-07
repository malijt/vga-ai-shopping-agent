# Understand prompt changelog

Every change to the prompt file or to the OpenAI model is recorded here, in the same commit, with
the eval result that justified it (CLAUDE.md, Non-Negotiables: re-run the eval set and add an entry
before changing either). The prompt version and the model id are a matched pair: a result is only
comparable with another that used the same pair.

How to run the eval: `OPENAI_API_KEY=... OPENAI_MODEL=<dated snapshot> uv run pytest -m live
tests/understand` runs the 6 golden inputs and all 17 cases of `eval/data/edge_cases.yaml` and
writes `eval/results/understand-live.md`. Paste its pass/fail counts below.

## understand-v1: 2026-10-07 (initial prompt)

- **Prompt:** `understand-v1.md`. One job (describe the clothes in a shopper's request); the user
  message is data, never instructions; a `verdict` so the model can say "nothing to shop for";
  four categories; 2-3 English keywords with no price or gender words; gender `explicit` only when
  the shopper's text says so; budget from the text only; edits kept apart from the item.
- **Model:** none is pinned in `config/settings.yaml` yet (`openai_model: null`). The snapshot found
  in OpenAI's model documentation is `gpt-5-mini-2025-08-07` (a newer, dearer alternative is
  `gpt-5.4-mini-2026-03-17`). The orchestrator pins the one to use. The code refuses to start
  without a dated snapshot.
- **Call settings:** reasoning effort `low`, `max_output_tokens` 3000 (reasoning tokens count
  against it), `store=false`, 15 s timeout, at most 2 calls per request.
- **Eval score: NOT RUN.** No `OPENAI_API_KEY` was available when this prompt was written, so
  neither the live golden run nor the live edge-case run has happened. The six golden fixtures in
  `tests/understand/golden/` are hand-written, not recorded.
- **What was checked offline** (`uv run pytest tests/understand`, no network): the real OpenAI SDK
  driven against a fake HTTP server; all 17 edge cases with a scripted well-behaved model, with a
  model that is down, and with a model that obeys the injected text or the text printed in the
  photo; the 6 hand-written golden outputs.
- **Reason:** first version.
- **Next step:** run the live eval once with a key, paste the counts here, and fix the prompt
  (bumping to `understand-v2`) for any case that fails.

## Known limitations and failure modes

Kept here so that nobody has to rediscover them (genai best practice 13).

- **Validation cannot judge meaning.** It stops links, control characters, foreign categories,
  guessed genders, price words, a copied prompt and an invented price. It cannot tell that a model
  which obeyed an injection and still answered `ok` with a plausible garment gave the wrong
  garment. Only the live eval shows that, and the prompt rules are the defence.
- **A mixed request drops what is out of scope.** "A black jacket and a handbag" searches the
  jacket only, without telling the shopper about the handbag.
- **The fallback reads a short word list.** When the model path fails, the category of a text
  request comes from about 80 English and Arabic garment words. A garment not on the list (for
  example "kurta") ends in the plain "describe an item" message, not in a search. The fallback
  keywords are the shopper's own words: Arabic stays Arabic, and a price limit is not applied.
- **Hoodies and cardigans are `tops`, blazers are `outerwear`.** A fixed choice so the same garment
  lands in the same category every run; the shopper can change the category chip.
- **Gender words are a list.** "Explicit" is downgraded to "inferred" unless the text contains a
  gender word from the English or Arabic list; a stated gender in an unlisted word is shown as an
  unconfirmed chip instead of being applied.
- **The photo is sent to OpenAI** (resized, metadata removed, with `store=false`). The app must say
  so before upload (plan 10.1.2).
