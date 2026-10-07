# Changelog

All notable changes to the VGA AI Shopping Agent, newest first. One entry per change merged into `develop`, written for someone who was not there: what changed and why it matters. Prompt and model changes for the Understand step are also recorded, with eval results, in `src/vga/understand/prompts/CHANGELOG.md`.

Format: grouped by date, then by Added / Changed / Fixed / Decided / Found. "Found" records facts learned from real runs.

## Unreleased

### 2026-10-08

**Decided**
- **Scope change: dresses are now a fifth category** (dresses, gowns, kaftans, abayas, kurtas and similar). The user supplied five test photos and all five show a dress or ethnic wear, which the original scope excluded. The BRD, PRD, plan (A23, A24) and `CLAUDE.md` are updated; the code change follows. The five photo-based acceptance queries will be rewritten around the supplied photos before any acceptance run.
- An outfit photo is not compared by image similarity; only a product photo and a photo + text request are. The PRD asks for image similarity "when the request has a product photo" (R8), and a real outfit search spent 18.5 s on it and hit the 30 s limit. Being implemented (plan A26).
- A store is searched only for the categories it sells: the four dress and modest-wear stores will be searched for dresses only. A real shoes search returned an abaya from one of them. Being implemented (plan A27).
- **The store limit rises from six to ten** (user decision). Six stores cannot cover both menswear and dresses: three carry menswear, and the three left for dresses give at most 18 results against the 20 the pass rule needs. The current six stay; Hanayen, Maison Arabelle, Nishat Linen UAE and Signature Studio are added, each enabled only after its live smoke test. The BRD, PRD, plan (A25) and `CLAUDE.md` are updated.
- The user named eight Kuwaiti designer brands to add (Bazza Alzouman, N.BEE, Montaha Couture, Marzook, Heba Shaikh, Yousef Al-Jasmi, Hamsa, Manal Smaoui). Each is qualified first, like every other store (plan Module 2.6, in progress): only a store an honest client can read is added. Marzook sells handbags and accessories, which are out of scope, so it is not tested.
- A further store discovery pass (plan Module 2.5) looks for Shopify stores that sell dresses and modest or ethnic wear, because the six demo stores were chosen before dresses were in scope.
- OpenAI model: `gpt-6-luna`, chosen by the user. It replaces the earlier pin `gpt-5-mini-2025-08-07`. OpenAI lists no dated variant, so the settings allow this one id by name and still reject aliases such as `gpt-6-luna-latest`. Reasoning effort stays `low`.
- Live runs that need the API key are run by the orchestrator from the main checkout, where the app reads `.env` itself. An agent's worktree has no `.env`, and the eval agent got round a worktree-guard refusal by putting the key-loading command in a script. The script was checked and no key was printed, logged or committed, but agents should not work round a guard.
- This changelog is maintained from now on (user request).

**Added**
- **Dresses as a fifth category in the code**: the contract, the ranking (dress, gown, kaftan, abaya, jalabiya, kurta, kandura and similar words are a dress; sheilas, hijabs and scarves are dropped as accessories for every request), the prompt (`understand-v2`), the page label ("Dresses and ethnic wear") and the eval data. Jumpsuits, swimwear and nightwear stay out of scope.
- The seven photo-based acceptance queries are rewritten around the user's photos, and the other 11 photos are an extra set (`eval/data/extra_queries.yaml`) that does not count toward the pass rule.
- Store adapters for the four new stores (Modules 12.7-12.10): Hanayen, Maison Arabelle, Nishat Linen UAE and Signature Studio. Each passed a live smoke test through the project's own engine (HTTP 200, 10 products per query, 4 searches per store, no block or challenge) and is enabled. **Ten stores are now enabled.**
- The Shopify gender reader recognises `menswear` and `womenswear`: Signature Studio marks its men's kurta sets only with a `Menswear` tag.
- The search pipeline (Phase 13): one entry point connects understanding, store search, ranking, image similarity and the price ranges. It validates the request before any outside call, searches each store in its own task so a slow store cannot discard the others' answers at the 30 s deadline, re-runs from a cache with no new store or OpenAI calls when only the price mix or budget changes, and attaches a plain warning to every fallback. `uv run python -m vga.search --text "..."` runs it from the command line. 241 tests, all with fakes at the boundaries; not yet run against real stores or the real model at merge time.
- Dress and modest-wear store discovery (plan Module 2.5): 31 candidates listed, 12 tested, four more Shopify stores qualify, all through `/search/suggest.json` with robots.txt allowing it: Hanayen (abayas, AED 600-4,500), Maison Arabelle (abayas and kaftans, AED 790-2,400), Nishat Linen UAE (budget long dresses and South Asian suits, AED 40-239) and Signature Studio (designer South Asian sets and kaftans, AED 174-2,753). Reports, samples and a coverage table are in `docs/store-qualification/`.
- Product gender from the store's own data: the Shopify extractor reads `type` and `tags` to say who an item is for, and the ranker drops the other gender when the shopper states one. On the 160 saved products it labelled every Sacoor, Nautica and Maison D'Vie item and none wrongly; Giordano, Oh Polly and Club L London mostly stay unlabelled and rely on the title or the store-level setting.
- Sixteen test photos supplied by the user (abayas, dresses, ethnic sets, bottoms, a blouse), kept in the git-ignored private assets folder with descriptive names and a manifest. No duplicates.
- Store adapters for all six demo stores, each enabled only after a live smoke test through the project's own engine: Sacoor Brothers UAE, Giordano UAE, Club L London UAE, Oh Polly UAE, Maison D'Vie, Nautica UAE. Every live response was HTTP 200, with no block or challenge.
- The OpenAI understanding step (Phase 5): one structured call turns a photo and/or text into what to search for, with output validation, one corrective retry, a raw-text fallback and a daily call cap. Tested with fakes only at merge time.
- Acceptance harness (Phase 11): runs the 10 frozen queries, checks the BRD pass rule, exports a labelling sheet, and can record a live run and replay it offline.

**Fixed**
- Trousers titled "khakis" no longer pass a request for another category ("khaki" as a colour still does).
- A children's item (boys, girls, kids, baby, toddler, infant, junior) is dropped when the shopper states men or women.
- Default tests no longer read the developer's real `.env` or see real credentials: one shared fixture hides the file and removes every `OPENAI_*` and `VGA_*` variable for any test not marked `live`. With the user's `.env` in place the suite went from 62 failures and 50 errors to 5,595 passed. Regression tests reproduce the failure against a hostile `.env`.
- A variable the shell sets to empty no longer blocks the same variable in `.env`.

**Changed**
- Thumbnails now pass the same robots.txt check as search pages, and Shopify images are requested at 400 px wide (a real image went from 108 KB to 20 KB).
- The search box is a single line that registers text as you type; the multi-line box lost the first click on the search button.
- The budget is set in one place, the budget chip. The sidebar budget box was removed because the two could disagree.
- `httpx2`, which the Understand tests import directly, is now a declared test dependency. `app` and `eval` imports sort as first-party.

**Found**
- **Prompt `understand-v2` on real calls: 24 of 24 checks passed**, none skipped, including the user's photos for the first time. The gown photo was read as a burgundy floor-length gown, the outfit photo as two garments (a black maxi dress and black heels), and "dark green" was applied to the gown. Typical answer 3.1 s, worst 5.9 s.
- **First real photo searches (ten stores, image similarity on real data).**
  - Gown photo: 30 results from 7 stores, every price range full. It took 29.5 s from a cold start, of which 10.4 s was loading the image model once and about 11 s fetching and comparing 40 thumbnails. With the model already loaded, as on the running page, that is about 19 s.
  - Outfit photo (black dress and heels), model already loaded: 24 results from 6 stores, but it hit the 30 s limit during image comparison and returned what it had, with a plain warning. The deadline handling worked as designed.
- Three problems from those runs, being fixed: products the photo was compared with ranked below ones it was not compared with; an abaya with no garment word in its title appeared under shoes; outfit searches cannot fit image comparison into 30 s.
- Not fixed, left for tuning with labels: because an inferred gender is not applied until the shopper confirms it (product rule 8), a women's outfit photo also returns men's shoes; and weak matches (text score under 0.3) still fill thin price ranges.
- A title with no recognised garment word is kept for every request. Most Signature Studio titles are designer and collection names, so they depend on the store-level category rule above.
- What the four new stores' data looks like: Hanayen's `kaftan` search also returns sheilas (scarves) and under-abaya inner dresses; Maison Arabelle's compare-at price is sometimes at or below the price, so it is never read; Nishat Linen's titles are codes with the colour only in the description, and every price is a 50% sale price, so its budget band will rise when the sale ends; `kurta` returns only men's items at Nishat Linen and Signature Studio.
- Maison Arabelle's robots.txt carries a content-use line: `ai-train=yes, search=yes, ai-retrieval=yes, ai-personalization=no`. The demo searches and links to the store's pages and builds no shopper profile, which is inside what the store allows. It should be re-read in the terms check before real users.
- **First real end-to-end searches (real OpenAI, real stores, three text queries, one run each).** All three completed with no error, no warning and no store block.
  - "black oversized blazer for men under 400 AED": 8.6 s, 15 results from 3 stores. Below the 20-result bar: only three stores carry menswear, and only Sacoor sells men's blazers, all above the budget. The results inside the budget are jackets, not blazers.
  - The Arabic men's white cotton shirt query: 7.7 s, 23 results from 4 stores. Arabic was read correctly (shirt, white, cotton, men, 200 AED). T-shirts and polos are mixed in with shirts.
  - "women's high-waisted wide-leg jeans in light blue": 10.0 s, 30 results from 5 stores, every price range full.
  - Time splits about evenly: 4 s understanding, 2.5-3.7 s store search; filtering, ranking and price ranges take a few milliseconds.
- Two ranking bugs from those runs, being fixed: trousers titled "khakis" passed the filter for a blazer request, and a "Boys" T-shirt was returned for an explicit men's request.
- When a thin price range borrows from its neighbour, the two ranges' price spans overlap ("Premium 380-915", "Luxury 549-2,650"). It is flagged "few options", but the header can still mislead. Left for tuning.
- Only two readable AED stores sell real abayas (Hanayen and Maison Arabelle), and none sells an everyday abaya below AED 600. An abaya search will struggle to reach three stores.
- Six stores cannot serve both the men's queries and the dress queries: three stores carry menswear, so at most three are left for dresses, and three stores at six results each is 18, below the 20-result bar.
- Shopify's older default robots.txt disallows `/search` and the newer one leaves it open. Five of the eight abaya or kaftan sellers checked close search, so robots.txt has to be the first request to any new store.
- Rejected in discovery: Lamis Abaya, Basic Abaya, KMansoori, Bousni and CAS Basics (robots.txt), Boksha (its search endpoint redirects to an HTML page), East Essence (priced in USD). The discovery agent sent Boksha 4 requests where its limit for an early rejection was 2, because its script followed two redirects; it fixed the script before the next store.
- First real run of the Understand step on `gpt-6-luna`: 20 of 20 runnable cases passed in each of three full runs (49 calls, no errors or retries), with no prompt change. Every injection case held, including text printed inside a photo. A typical answer takes about 3.0 s (worst 6.3 s) and costs about $0.0003. Not yet tested: real shopper photos (3 cases skipped because the photo queries are being rewritten), and keyword quality, which the eval does not judge.
- `gpt-6-luna` has no dated snapshot, so OpenAI can change it behind the name. Recorded as a known limitation.
- The default test suite read the developer's real `.env`: with the user's `.env` in place, 112 UI tests failed or errored in the main checkout, and the real API key was copied into the test process. Agents never saw it because their worktrees have no `.env`. Fixed the same day (see Fixed).
- Sacoor's women's suit blazers are tagged "Formalwear Men", so `type` has to outrank `tags` when reading gender.
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
