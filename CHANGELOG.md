# Changelog

All notable changes to the VGA AI Shopping Agent, newest first. One entry per change merged into `develop`, written for someone who was not there: what changed and why it matters. Prompt and model changes for the Understand step are also recorded, with eval results, in `src/vga/understand/prompts/CHANGELOG.md`.

Format: grouped by date, then by Added / Changed / Fixed / Decided / Found. "Found" records facts learned from real runs.

## Unreleased

### 2026-10-08

**Decided**
- **Scope change: dresses are now a fifth category** (dresses, gowns, kaftans, abayas, kurtas and similar). The user supplied five test photos and all five show a dress or ethnic wear, which the original scope excluded. The BRD, PRD, plan (A23, A24) and `CLAUDE.md` are updated; the code change follows. The five photo-based acceptance queries will be rewritten around the supplied photos before any acceptance run.
- A further store discovery pass (plan Module 2.5) looks for Shopify stores that sell dresses and modest or ethnic wear, because the six demo stores were chosen before dresses were in scope.
- OpenAI model: `gpt-6-luna`, chosen by the user. It replaces the earlier pin `gpt-5-mini-2025-08-07`. The switch and the first real run of the Understand step are in progress.
- This changelog is maintained from now on (user request).

**Added**
- Store adapters for all six demo stores, each enabled only after a live smoke test through the project's own engine: Sacoor Brothers UAE, Giordano UAE, Club L London UAE, Oh Polly UAE, Maison D'Vie, Nautica UAE. Every live response was HTTP 200, with no block or challenge.
- The OpenAI understanding step (Phase 5): one structured call turns a photo and/or text into what to search for, with output validation, one corrective retry, a raw-text fallback and a daily call cap. Tested with fakes only at merge time.
- Acceptance harness (Phase 11): runs the 10 frozen queries, checks the BRD pass rule, exports a labelling sheet, and can record a live run and replay it offline.

**Changed**
- Thumbnails now pass the same robots.txt check as search pages, and Shopify images are requested at 400 px wide (a real image went from 108 KB to 20 KB).
- The search box is a single line that registers text as you type; the multi-line box lost the first click on the search button.
- The budget is set in one place, the budget chip. The sidebar budget box was removed because the two could disagree.
- `httpx2`, which the Understand tests import directly, is now a declared test dependency. `app` and `eval` imports sort as first-party.

**Found**
- Nautica UAE sells women's clothing as well as men's. The qualification pass had seen only women's accessories.
- Giordano UAE repeats one title under several listings, so only 4 to 6 distinct products survive per search.
- Sacoor Brothers, Nautica and Maison D'Vie keep gender in `type` or `tags`, not always in the title, so a stated gender could let the other gender's items through. A fix is in progress.
- Short garment keywords ("blazer") return cleaner results than longer ones ("black blazer") at Club L London.

### 2026-10-07

**Decided**
- Stack: OpenAI for understanding, local Marqo-FashionSigLIP for image similarity, plain `httpx` fetching, Streamlit UI, Python 3.12 with `uv`.
- Honest fetching only: no browser impersonation, proxies or CAPTCHA handling. A store that blocks is dropped.
- Store route: after the first qualification pass failed (3 of 34 sites readable, no large GCC retailer among them), the user chose the easiest route, Shopify storefronts. The other three routes are planned as Phases 17-19.
- Demo store set of six (the BRD's maximum): Giordano UAE, Nautica UAE, Sacoor Brothers UAE, Oh Polly UAE, Club L London UAE, Maison D'Vie. Reserves: The Bear House UAE, Good Times, Luxury For You.
- Agent models: development on Sonnet 5.5, orchestration and decisions on Opus 5.5.
- A thin price range borrows only from the range next to it and otherwise shows fewer results.

**Added**
- Implementation plan (16 demo phases, 3 later phases), project `CLAUDE.md`, best-practice reference docs, and the codebase snapshot.
- Project skeleton, shared typed contracts, fakes and contract tests, structured logging, settings, CI workflow, pre-commit, licence audit, five decision records (Phase 1).
- Store qualification: 12 full reports, then 6 more Shopify stores, a reusable qualification script, and a summary with the gate result (Phase 2).
- FashionSigLIP spike with measured speed and quality (Phase 3) and the image ranker built on it (Phase 8).
- Frozen acceptance set: 10 queries, 17 edge cases, a labelling rubric and a results template (Phase 4).
- Fetch engine: https only, per-store host allow-list, robots.txt, 1 request/s, no retries, cooldown after a block, Shopify extractor, result cache (Phase 6).
- Ranking: category filter, text and price scoring, reason sentence (Phase 7).
- Price-range shaper: quartile borders, mix counts, per-store cap, budget rule (Phase 9).
- Streamlit page built on sample data: input, chips, price-range sections, cards, all error and empty states (Phase 10).
- Contract additions as findings arrived: image-score range, response size cap, per-store size and variant limits, store genders, re-run requests, shared photo size limit.

**Fixed**
- robots.txt parsing: Python 3.12's `urllib.robotparser` ignores `*` and `$` and reported disallowed search paths as allowed. Replaced with `protego`, and malformed rules are read conservatively.
- `.env.example` silently switched image ranking off for anyone who copied it.
- Repo-wide lint failures after the first merges.

**Found**
- No large GCC retailer can be read by an honest client: 9 sites are behind a bot challenge, 14 disallow search in robots.txt, and 6thStreet (now `aivi.com`) serves an empty JavaScript shell.
- FashionSigLIP scores 40 thumbnails in about 0.6 s on this Mac's GPU and 1.1 s on CPU, but is weak at telling categories apart, so it nudges ranking and never filters.
- Two early manual sitemap checks by the orchestrator sent the user's email address in a User-Agent header to 6thStreet. Every request since uses a neutral User-Agent with no personal data.
