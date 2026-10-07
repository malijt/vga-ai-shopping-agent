# Changelog

All notable changes to the VGA AI Shopping Agent, newest first. One entry per change merged into `develop`, written for someone who was not there: what changed and why it matters. Prompt and model changes for the Understand step are also recorded, with eval results, in `src/vga/understand/prompts/CHANGELOG.md`.

Format: grouped by date, then by Added / Changed / Fixed / Decided / Found. "Found" records facts learned from real runs.

## Unreleased

### 2026-10-08

**Decided**
- **Scope change: dresses are now a fifth category** (dresses, gowns, kaftans, abayas, kurtas and similar). The user supplied five test photos and all five show a dress or ethnic wear, which the original scope excluded. The BRD, PRD, plan (A23, A24) and `CLAUDE.md` are updated; the code change follows. The five photo-based acceptance queries will be rewritten around the supplied photos before any acceptance run.
- **Three Kuwaiti designer stores will be added, and the app gets a second currency** (user decision). Of the eight brands the user named, four can be read; the user chose the three that price in dinar: Bazza Alzouman, Hamsa and Manal Smaoui. A result will show the dinar price plus an approximate AED figure from a fixed rate, and price ranges and budgets use the AED figure. The store limit becomes 13. Currency support is being built first; the adapters follow (plan A28).
- An outfit photo is not compared by image similarity; only a product photo and a photo + text request are. The PRD asks for image similarity "when the request has a product photo" (R8), and a real outfit search spent 18.5 s on it and hit the 30 s limit. Being implemented (plan A26).
- A store is searched only for the categories it sells: the four dress and modest-wear stores will be searched for dresses only. A real shoes search returned an abaya from one of them. Being implemented (plan A27).
- **The store limit rises from six to ten** (user decision). Six stores cannot cover both menswear and dresses: three carry menswear, and the three left for dresses give at most 18 results against the 20 the pass rule needs. The current six stay; Hanayen, Maison Arabelle, Nishat Linen UAE and Signature Studio are added, each enabled only after its live smoke test. The BRD, PRD, plan (A25) and `CLAUDE.md` are updated.
- The user named eight Kuwaiti designer brands to add (Bazza Alzouman, N.BEE, Montaha Couture, Marzook, Heba Shaikh, Yousef Al-Jasmi, Hamsa, Manal Smaoui). Each is qualified first, like every other store (plan Module 2.6, in progress): only a store an honest client can read is added. Marzook sells handbags and accessories, which are out of scope, so it is not tested.
- A further store discovery pass (plan Module 2.5) looks for Shopify stores that sell dresses and modest or ethnic wear, because the six demo stores were chosen before dresses were in scope.
- OpenAI model: `gpt-6-luna`, chosen by the user. It replaces the earlier pin `gpt-5-mini-2025-08-07`. OpenAI lists no dated variant, so the settings allow this one id by name and still reject aliases such as `gpt-6-luna-latest`. Reasoning effort stays `low`.
- Live runs that need the API key are run by the orchestrator from the main checkout, where the app reads `.env` itself. An agent's worktree has no `.env`, and the eval agent got round a worktree-guard refusal by putting the key-loading command in a script. The script was checked and no key was printed, logged or committed, but agents should not work round a guard.
- This changelog is maintained from now on (user request).

**Added**
- **Currency support for dinar stores (plan A28, ADR 0006).** A product keeps the store's own price; a result in another currency also carries an approximate AED figure from a fixed rate, 1 KWD = 11.92 AED (Central Bank of Kuwait's dollar rate on 2026-10-07 with the dirham's fixed peg; the UAE central bank's own table agrees within 0.5%). Price ranges, budgets, the over-budget flag and the reason sentence use the AED figure. A three-decimal price is accepted only for a three-decimal currency. Stores in Kuwait can be searched while the home market stays the UAE. A currency with no rate is never converted. An AED-only search behaves exactly as before.
- **The acceptance harness runs the real pipeline.** `--record` with `--wiring eval.harness.real:real_wiring` records a live run and `--replay` re-runs it with no network and no model call. The image model is loaded before the first timed query and its load time is reported separately. Links are checked through the project's own polite fetch engine. The 11 extra photos run as a separate set whose report says it is not the acceptance result. The labelling sheet now names the photo, the garment, the price and the price range on each row. A recording holds the model's answer, the stores' products and image scores, and no photo.
- **Photo privacy audit (Module 14.2) and `docs/privacy.md`.** 135 tests run whole requests through the real pipeline and look for any trace of the photo in five places: files written, every log call, memory afterwards, every outgoing request, and the answer. It covers product, outfit and photo + text requests, both debug switches on and off, and failed requests. Nothing is kept. 23 deliberately planted leaks prove the audit can fail. The privacy note says in plain language what leaves the machine and what must be reviewed before real users.
- **Store-access guards (Module 14.1):** 198 tests through the real pipeline and the real fetch engine, with only store HTTP, the model and the clock faked. A 403, 429, challenge, CAPTCHA or login redirect gets exactly one request, no retry and a cooldown; eight kinds of robots.txt rule are honoured and an unreadable robots.txt means no search; requests to a store are at least 1 s apart, including for a four-garment outfit; 25 kinds of hostile product and image link lead to no request and no such link in the answer; no price word or budget number reaches a store URL; a store that is not enabled gets no request at all. The agent broke each guard in turn to check its tests catch it.
- **The page runs the real search pipeline (Phase 15).** One pipeline per process; the image model loads once when the page opens, with a plain "Getting ready" note; searching again from the chips or the price mix makes no new OpenAI call, and a mix-only change makes no store request either; the photo is dropped after a search and the uploader is reset; warnings, skipped stores with their reasons, token usage and plain errors are shown; a missing API key is named when the page opens. A failed search keeps the photo so the shopper can retry.
- **Prompt-injection guards (Module 14.3):** 390 tests through the real pipeline, with only OpenAI, store HTTP, the image model and the clock faked. A model that obeys injected text still cannot put a link, markup, a control character or an invented category into a store search or the answer; no store text ever reaches the model, including on a re-run; hostile store titles come out as plain text; off-host, look-alike-host and private-address links are dropped and never requested.
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
- **All ten findings from the guard audits:**
  - robots.txt is read for a redirect target before the redirect is followed, for search pages and thumbnails. A store that redirects every search now costs about twice the wait per keyword; a store that does not is unchanged.
  - A store's page requests share one request-a-second limit across all of its own hosts; the shared image host keeps its own limit.
  - A product link must be on the store's own site. A link to the shared image host is dropped. None of the ten stores is affected.
  - A store host that just refused a search is not asked for thumbnails during its cooldown.
  - A budget is kept only when the shopper typed a number, in digits or in words, in English or Arabic. A price printed in a photo no longer becomes the budget.
  - An edit such as "cheaper" or a colour change is kept only when the shopper's typed words ask for it.
  - More price words are kept out of store searches: plurals, "markdown", "half price", "70% off" and similar phrases, and more Arabic sale words. "Off-white", "off-shoulder" and "100% cotton" are untouched.
  - The photo sent to OpenAI is rebuilt from its pixels alone, so a comment or any other hidden field cannot travel with it.
- **An outfit photo no longer runs image comparison** (plan A26). The same real search, a black dress with heels, went from 30.3 s and a timeout warning to 9.4 s, with 24 results from 5 stores.
- **A product the photo was not compared with no longer outranks one that was.** Only the top 40 candidates get an image score; the rest are now totalled with the average image score of that search, so being compared is no longer a penalty.
- **A store is searched only for the categories it sells** (plan A27, a new optional `categories` field on a store config). Hanayen, Maison Arabelle, Nishat Linen UAE and Signature Studio are searched for dresses only. The abaya that had appeared under shoes is gone, and those stores get no request at all for a shoes or jeans search.
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
- **Live Understand eval after the validation changes: 23 of 24 passed.** The one failure is not from those changes: the real model labelled the single-gown photo an outfit photo this time and a product photo last time. The kind of request will be decided by the code from facts (photo or not, text or not, number of garments) and not by the model's label; being fixed. Typical answer 2.2 s, worst 4.7 s.
- Still possible after the fixes: a shopper who types a budget in words next to a sign with another price could get the sign's price if the model obeys it; price words outside the list (coupon, voucher, outlet) still reach a store search; a sign can still sway colour or style when the typed text is silent on them.
- **One privacy gap, fixed the same day (see Fixed):** a comment stored inside a JPEG, or a PNG text field named "comment", is sent to OpenAI with the photo. Location data, camera details, colour profiles and every other hidden field are stripped; this was the one that got through.
- The privacy audit cannot see: files written by non-Python code, the image model's internals (read, not run), or how a running Streamlit page stores an upload. Whether this OpenAI account has zero data retention is not verified; it is an account setting the owner must request from OpenAI.
- Four gaps in the fetch engine from the store-access guards, being fixed. The main one: when a store redirects a search to another of its hosts (for example to `www.`), that host's robots.txt was not read. Also: the one-request-a-second limit was per host and not per store; a product link was accepted on the shared image host; and a store host that had just refused a search could still be asked for thumbnails (not reachable with today's stores, which all use a shared image host).
- Cooldown wording corrected: the code, the plan and ADR 0003 cool a store down only after a block. Two comments said "blocked or failed". A store that only errors or times out is skipped for that search and asked again on the next.
- **Manual pass on the real page in a browser (plan 15.1.4), one real search:** "black embroidered abaya for women" returned 30 results in about 13 s with every price range full and abayas from both abaya stores; the progress steps showed as it ran. Keyboard only: typing enables the search button, Tab reaches it and Enter runs the search. No sideways scrolling at 375, 768 and 1280 px wide. All 30 images have a text alternative; all 30 links go to the stores' own hosts and open in a new tab.
  - To fix: every card says "Colour: not listed" while its title and its reason sentence name the colour.
  - To tune: an abaya request fills the Budget range with black mini dresses, because no store sells a cheap abaya and a dress of another type still counts as a match.
  - Not checked: a screen reader, and colour contrast beyond the documented theme values.
- Three weaknesses from the injection guards, being fixed: a price printed in a photo could become the shopper's budget when the typed text had no number; an edit such as "cheaper" printed in a photo was applied; and the price-word list missed "discounts", "sales", "markdown" and "70 percent off", so they reached a store search. Whether the real model obeys such text is untested beyond the live eval's seven injection cases, which it resisted.
- Not verified on the page: two browser sessions searching at the same moment, and whether Streamlit's own file store releases an uploaded photo when the uploader is reset (the page itself holds no bytes).
- **The eight designer brands the user named (plan Module 2.6).** Four can be read by an honest client, all Shopify with robots.txt allowing search: Bazza Alzouman (evening gowns, KWD 206-380), Hamsa (abayas and kaftans, garments KWD 55-365), Manal Smaoui (kaftans, dresses and sets, KWD 5-85) and Heba Shaikh (premium essentials, GBP 35-950, one dress style). **None prices in AED**, and the code is AED-only today: the price parser rejects a three-decimal dinar price and the price ranges keep one currency. Adding any of them needs a currency decision first; none is added yet.
  - Not readable: N.BEE has no online store of its own (Instagram only); Montaha Couture's site has an invalid security certificate, which the client will not bypass; Yousef Al-Jasmi's site has no robots.txt and redirects to an unrelated domain, which was not followed. Marzook was not tested (handbags and accessories are out of scope).
  - Hamsa would be a third abaya store, but its listed price is often the cheapest variant (a scarf at KWD 20-35) and not the abaya, so it needs adapter work.
  - 20 requests in total to 6 sites, none over the limit, no block or challenge.
- **Prompt `understand-v2` on real calls: 24 of 24 checks passed**, none skipped, including the user's photos for the first time. The gown photo was read as a burgundy floor-length gown, the outfit photo as two garments (a black maxi dress and black heels), and "dark green" was applied to the gown. Typical answer 3.1 s, worst 5.9 s.
- **First real photo searches (ten stores, image similarity on real data).**
  - Gown photo: 30 results from 7 stores, every price range full. It took 29.5 s from a cold start, of which 10.4 s was loading the image model once and about 11 s fetching and comparing 40 thumbnails. With the model already loaded, as on the running page, that is about 19 s.
  - Outfit photo (black dress and heels), model already loaded: 24 results from 6 stores, but it hit the 30 s limit during image comparison and returned what it had, with a plain warning. The deadline handling worked as designed.
- Three problems from those runs, fixed the same day (see Fixed): products the photo was compared with ranked below ones it was not compared with; an abaya with no garment word in its title appeared under shoes; outfit searches cannot fit image comparison into 30 s.
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
