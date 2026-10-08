# VGA AI Shopping Agent

A demo that lets a shopper search many fashion stores at once. You give it a **photo, a few words (English or Arabic), or both**. It works out what you are after, asks 19 stores in the UAE and Kuwait through their own search, ranks what comes back, and shows the best 30 products in four **price ranges**: Budget, Mid-range, Premium and Luxury. Every result links to the product page on the store's own website.

> **Status (2026-10-08).** The demo is built and runs end to end: the Streamlit page, the search pipeline, 19 store adapters, the guard tests and the acceptance harness are all in place. **The recorded acceptance run and the labelling of its results are still to come, so there is no pass or fail verdict yet.** See [Acceptance result](#acceptance-result).

If you have never seen this project, read in this order: this README, then [business requirements](docs/01-business-requirements.md) (why), the [PRD](docs/02-prd.md) (what), and the [implementation plan](docs/plans/2026-10-07-vga-ai-shopping-agent-implementation-plan.md) (how). Engineering rules for people and AI agents working in the repo are in [CLAUDE.md](CLAUDE.md).

## Contents

1. [What it is, and what it is not](#what-it-is-and-what-it-is-not)
2. [Set it up](#set-it-up-from-a-fresh-clone)
3. [Using the page](#using-the-page)
4. [Tests](#tests)
5. [Settings reference](#settings-reference)
6. [Behaving towards the stores](#behaving-towards-the-stores)
7. [The acceptance harness](#the-acceptance-harness)
8. [Known limitations and failure modes](#known-limitations-and-failure-modes-of-the-ai-features)
9. [Accepted gaps, and what must happen before real users](#accepted-gaps-and-what-must-happen-before-real-users)
10. [Acceptance result](#acceptance-result)
11. [How the code is organised, CI and licences](#how-the-code-is-organised)
12. [Where to read more](#where-to-read-more)

## What it is, and what it is not

**What it does**

- Takes a product photo, an outfit photo, text, or a photo plus text ("like this but dark brown, under 300 AED").
- Makes **one call to OpenAI** to understand the request (garment, colour, style, who it is for, budget, search words). Arabic is translated into English search words.
- Searches the stores **live**, at the moment you press the button. Nothing is crawled in advance and there is no catalogue or database.
- Ranks the products by how well the title matches, how close the picture is to your photo (when you gave one), and how well the price fits.
- Shows the top 30 results (12 per garment for an outfit photo), split into four price ranges by a mix you choose, with at most 6 results from any one store.

**The five garment categories:** tops, outerwear, bottoms, shoes, and **dresses and ethnic wear** (dresses, gowns, kaftans, abayas, jalabiyas, daraas, burqas, kurtas and similar one-piece or ethnic garments, and the men's robe sold as a thobe, dishdasha or kandura; added 2026-10-08). Accessories (bags, belts, jewellery, scarves, sheilas and hijabs), jumpsuits, swimwear and nightwear are out of scope.

**The 19 stores.** All are small or mid-sized online shops built on Shopify (a hosted shop platform), and all are read through the same public search address, `/search/suggest.json`, which each store's `robots.txt` leaves open. `robots.txt` is the file where a website says which pages automated tools may visit. The large GCC retailers could not be read by an honest client: of 34 sites checked, nine sit behind a bot challenge, fourteen forbid search in `robots.txt`, and one serves an empty page ([details](docs/store-qualification/SUMMARY.md)). They were dropped, not worked around.

| Store | Market and currency | Sells (as configured) | Searched for |
|---|---|---|---|
| Giordano UAE | UAE, AED | everyone | all five categories |
| Nautica UAE | UAE, AED | everyone | all five |
| Sacoor Brothers UAE | UAE, AED | everyone | all five |
| Oh Polly UAE | UAE, AED | women | all five |
| Club L London UAE | UAE, AED | women | all five |
| Maison D'Vie | UAE, AED | everyone | all five |
| Hanayen | UAE, AED | women | dresses only |
| Maison Arabelle | UAE, AED | women | dresses only |
| Nishat Linen UAE | UAE, AED | everyone (women's wear, men's kurtas) | dresses only |
| Signature Studio | UAE, AED | everyone (women's wear, men's kurta sets) | dresses only |
| Gul Ahmed UAE | UAE, AED | everyone (men's shalwar kameez and kurtas, women's kurtis) | dresses and tops |
| Bazza Alzouman | Kuwait, KWD | women | dresses only |
| Hamsa | Kuwait, KWD | women | dresses only |
| Manal Smaoui | Kuwait, KWD | women | all five |
| Daraat | Kuwait, KWD | women | dresses only |
| Shadow | Kuwait, KWD | women | dresses only |
| Her Highness Q8 | Kuwait, KWD | women | dresses only |
| Veil Essentials | Kuwait, KWD | women | dresses only |
| Al Jazeera Clothing | Kuwait, KWD | men | dresses only |

A store is only asked for what it sells: a search for shoes is never sent to Hanayen, and a men's search is never sent to a women-only store. Eleven of the stores are in the UAE (prices in AED) and eight in Kuwait (prices in KWD). The Kuwaiti stores price in dinars (KWD); the page shows the dinar price and an approximate dirham (AED) figure, and the price ranges and budgets go by the dirham figure ([ADR 0006](docs/adr/0006-second-currency-fixed-rate.md)). To add a store, follow [How to add a store](docs/how-to-add-a-store.md).

**What it is not**

- Not a shop: no cart, checkout or accounts.
- Not multi-user: no logins, no billing, no database, nothing hosted. It runs on one computer.
- Not a guess at your size: body size is never guessed from a photo.
- Not a copy of the stores' catalogues: results come from each store at the time of the search, and the shopper pays the store's own price on the store's own site.
- Not ready for real shoppers. This is a demo. See [Accepted gaps](#accepted-gaps-and-what-must-happen-before-real-users).

## Set it up from a fresh clone

### Prerequisites

- `git` and [`uv`](https://docs.astral.sh/uv/getting-started/installation/), the Python project manager. Any recent version works (CI uses 0.12.9).
- You do **not** need Python installed. The project pins **Python 3.12** (see `.python-version`); `uv` fetches it. Do not use a newer system Python.
- For real searches only: an **OpenAI API key**, and an internet connection that is allowed to reach the stores. Tests and the sample-data page need neither.
- The commands below are written for macOS and Linux shells. Windows was not tried.

### 1. Install

```bash
git clone <this repository> && cd vga-ai-shopping-agent
uv sync
```

`uv sync` installs Python 3.12, the runtime and the development tools (a few minutes the first time). Run every later command from the repository root.

### 2. Check that it works

```bash
uv run pytest
```

This needs no network and no key. At the time of writing it takes about three to four minutes and ends with about `8,800 passed, 13 skipped, 46 deselected` (the exact count grows with the code). The skips are expected: nine need the image-model packages (step 4) and four are contract checks that do not apply to every image ranker. The 46 deselected tests are the `live` ones (see [Tests](#tests)). The other gates that CI also runs:

```bash
uv run ruff check        # lint, including security rules
uv run mypy src          # types
```

### 3. See the page on sample data (no key, no network)

```bash
VGA_UI_FIXTURE=1 uv run streamlit run app/main.py --server.address localhost
```

Streamlit prints the address (usually `http://localhost:8501`). The page shows a fixed example response and says so ("Sample mode ..."): what you type does not change it and no store is searched. Stop it with Ctrl+C. You can instead put `VGA_UI_FIXTURE=1` in `.env` (step 5).

`--server.address localhost` keeps the page reachable from this computer only. Without it, Streamlit listens on every network interface and prints a "Network URL" and an "External URL", so anyone on your network who knows the address could use the page and spend your OpenAI allowance. Use the flag whenever you run the page.

### 4. The image model (optional, about 1 GB)

Photo searches compare store pictures with your photo using a small local model, Marqo-FashionSigLIP, so that a result that *looks* like your photo ranks higher. It is a gentle nudge on the ranking, never a filter. It is optional: without it, photo searches still work and are ranked on text and price alone, and the page says so.

```bash
uv sync --group ml
uv run --group ml python -m vga.rank.image.download
```

The first command installs `torch` and `open_clip` (the `ml` dependency group). The second downloads the weights (about 816 MB) once into the Hugging Face cache; it is safe to run twice. The weights are pinned to one exact revision, `siglip_revision` in `config/settings.yaml`. After installing the `ml` group, remember that a plain `uv sync` removes any package outside the groups you name (checked), so it would take `torch` out again: run `uv sync --group ml` instead. A plain `uv run` leaves installed packages alone (checked). To switch image comparison off, set `VGA_IMAGE_RANKER=off`.

### 5. Your `.env` file

```bash
cp .env.example .env
```

Then open `.env` and replace the placeholder `OPENAI_API_KEY=sk-your-key-here` with your real key. `.env` is git-ignored: never commit it. Everything else in the file is optional; every variable is listed under [Settings reference](#settings-reference). A real environment variable beats `.env`, and `.env` beats `config/settings.yaml`. Tests never read your `.env`.

### 6. Run the page for real searches

```bash
uv run streamlit run app/main.py --server.address localhost
```

Opening the page in this mode already contacts the stores: it reads each store's `robots.txt` once (19 requests) and loads the image model, showing "Getting ready" while it does. A missing API key or model name is reported on the page. Settings are read when the page starts: after editing `config/settings.yaml` or a store file, restart the page. The OpenAI model is `gpt-6-luna`; each search sends one request to OpenAI (two at most if the first answer must be corrected), and the page shows the tokens used.

### 7. Search from the command line

```bash
uv run python -m vga.search --text "black oversized blazer for men under 400 AED"
uv run python -m vga.search --image photo.jpg --text "same but dark brown and cheaper"
uv run python -m vga.search --text "white sneakers" --budget 300
```

It prints the full response as JSON (results, skipped stores with reasons, warnings, timings, tokens). Add `-v` to also print the log lines. The photo is read into memory and never written anywhere. Exit status: 0 done, 1 the search could not be done (the reason is printed), 2 a mistake in the command line. These make real requests to OpenAI and the stores: see [Behaving towards the stores](#behaving-towards-the-stores) first.

### Other commands

```bash
uv run python scripts/licence_audit.py             # dependency licences -> rewrites docs/licences.md
uv run python scripts/licence_audit.py --offline   # same, installed packages only, no lookups
uv run pip-audit                                   # known-vulnerability scan (needs internet)
uv run pre-commit install                          # once: run ruff and the secret scan before each commit
```

## Using the page

1. Add a photo (PNG, JPG or WebP, up to 8 MB), type up to 2,000 characters, or both, and press **Search stores**. The page shows each step as it runs.
2. **Detected by AI** shows what the AI understood as editable chips: garment type, colour, who it is for, budget. Change them and press **Apply changes and search again**, or **Reset to detected**. Changing chips searches again without a new OpenAI call.
3. If the request does not say who the garment is for, the page asks **Who is this for?** (Women, Men, Show both). A gender the AI only guessed is *shown, never applied* until you answer. Women or Men searches again with no OpenAI call and no new store requests.
4. The sidebar offers the **share of results in each price range** (see [Price-mix presets](#price-mix-presets)). Changing it re-sorts the results already found. The stores are asked again only when those results are more than 10 minutes old.
5. Results are grouped by price range. Each header shows the real price span and count, for example "Budget · 45-139 AED · 8 results". A card shows the picture, title, store, price, a one-sentence reason and a **View product** link that opens the store's own page. Flags are written in words: "Over your budget", "Few options in this range".
6. Skipped stores, warnings and token usage are listed under the results. Errors are written in plain words; a failed search keeps your photo so you can retry.

The page tells you what is AI-inferred and that the photo is sent to OpenAI. After a search the page drops the photo and clears the upload box; what it keeps for chip edits is a list of numbers describing the photo (its "embedding"), not the picture. Details in [docs/privacy.md](docs/privacy.md).

## Tests

```bash
uv run pytest                 # the complete suite: no network, no key, about 4 minutes
uv run pytest -m critical     # the critical suite, the one CI runs: about 140 tests, under a minute
uv run pytest tests/guards    # only the three guard suites (757 tests, about 40 seconds)
uv run pytest -m live tests/stores/hanayen   # ONE store's live smoke test (real requests)
```

**What CI runs, and what it does not.** CI minutes cost money, so CI no longer runs the complete suite (about 8,450 tests). On every pull request, and on every push to `main`, the `test` job runs ruff, mypy and the **critical suite**: the few tests whose failure would mean a broken rule (store access, links and hosts, price words, photo privacy, untrusted text, secrets and errors, a guessed gender) or a broken demo (contracts, understanding, store data, ranking, price ranges, the pipeline, the page, the acceptance harness). A push to a branch that has an open pull request starts no run of its own, so each commit is checked once. **A green CI does not mean the complete suite passes. Run the complete suite on your machine before a push or a merge.** The three commands:

```bash
uv run pytest -m critical     # 1. what CI runs
uv run pytest                 # 2. the complete suite, before every push or merge
# 3. the complete suite on GitHub, when you want CI to do it: Actions > CI > Run workflow,
#    then set "full_suite" to true (nothing is scheduled)
```

To have git run the complete suite before each push, install the opt-in hook once with `uv run pre-commit install --hook-type pre-push` (about 4 minutes per push; `git push --no-verify` skips it for one push).

**The critical list.** The critical tests are named in one reviewable file, [`tests/critical_suite.txt`](tests/critical_suite.txt): one pytest node id per line, under fifteen headings that say what each group protects. `tests/conftest.py` gives every test the list names the `critical` marker, so no test file carries a decorator for it. To add a test, find its id (`uv run pytest --collect-only -q tests/path/test_file.py`), add the line under the heading it protects and run `uv run pytest -m critical -q`. Prefer a test that runs the real pipeline to a narrow unit test, and one case of a parametrised table to the whole table. Never list a `live` test. `tests/foundation/test_critical_suite.py` is itself critical and fails when the list rots: an entry that names no test (a renamed test or a changed case id), a critical test that is also marked `live` (`-m critical` replaces the `-m 'not live'` of the default run, so a live one would reach the network), a heading with no test, or a count over its ceiling (150, raised on purpose in that file).

**What the default suite covers.** Many fast unit tests (price ranges and rounding, filters, scores, price parsing, validation, word lists), contract tests that make sure each fake behaves like the real thing, integration tests that run the *real* pipeline, fetch engine, extractors, ranker and price-range shaper with only the three outside boundaries faked (store HTTP, OpenAI, the image model) from `tests/fakes.py`, and Streamlit `AppTest` tests of the page. Each store has an offline test over real recorded answers. Default tests never read your real `.env` or see your credentials: `tests/conftest.py` points the loader away from `.env` and removes every `OPENAI_*` and `VGA_*` variable from the environment for any test not marked `live` (a test that needs one sets it itself). There is no coverage percentage target; the risky logic comes first. A bug fix needs a test that fails without it.

**What `live` means.** Tests marked `live` talk to the real stores or the real OpenAI API. They need keys, cost money or make real store requests, and **never run in CI**. The default run skips them (`-m 'not live'`). There are 46: one smoke test per store (Sacoor Brothers has four), and 24 cases of the Understand eval (`uv run pytest -m live tests/understand`, which calls OpenAI and writes `eval/results/understand-live.md`). Do not run `-m live` wholesale: that sends requests to all 19 stores in a row. Run one store at a time, once, and never in a loop. Tune from a recording instead (see [replay](#the-acceptance-harness)).

**The guard suites (`tests/guards/`).** Three suites prove the project's rules against the real pipeline: `scraping` (a 403, 429, challenge or login page gets exactly one request and a cooldown; `robots.txt` is honoured; requests stay under the rate limits; hostile links lead to no request; price words never reach a store), `privacy` (whole requests are run while watching files, logs, memory, outgoing requests and the answer for any trace of the photo, and 23 planted leaks prove the audit can fail), and `injection` (a model that obeys instructions hidden in the request or in store text still cannot put a link, markup or an invented category into a search or an answer). Changing the fetch engine, the pipeline or the Understand step without these passing is not acceptable.

**Changing the model or the prompt.** The OpenAI model and the image-model revision are pinned. Before changing either, or the prompt, re-run the Understand eval and add an entry to `src/vga/understand/prompts/CHANGELOG.md` with the result.

## Settings reference

### `config/settings.yaml`

The shipped values are the defaults you get. A bad value stops start-up with a message naming the field (for example, `tier_mix` must sum to 100). Unknown keys are rejected. Environment variables listed in the next table override the matching key.

| Key | What it does | Shipped value |
|---|---|---|
| **Search** | | |
| `country` | Home market (ISO country code). Enabled stores in it are searched | `AE` |
| `extra_store_countries` | More countries whose enabled stores are also searched (the Kuwaiti stores need `KW`). The code default is none | `[KW]` |
| `stores` | Store ids to use. Empty means every enabled store in the countries above | `[]` |
| `results` | Results for a normal request (1 to 100) | `30` |
| `max_per_store` | No store may supply more than this many results (1 to 50) | `6` |
| `outfit_results_per_garment` | Results per garment for an outfit photo (1 to 50) | `12` |
| `request_deadline_s` | Ceiling for one whole search. At the deadline you get what has been ranked so far, with a warning (up to 120) | `30` |
| `max_image_bytes` | Largest photo accepted, in bytes. The upload box has its own 8 MB limit in `.streamlit/config.toml`, kept in step by a test | `8000000` |
| **Fetching** | | |
| `timeout_s` | Time allowed for one store request, in seconds. A store file may override it | `6` |
| `rps_per_store` | Requests a second to one store. Keep it at 1 or lower: a test fails if the shipped settings or a store file ask for more | `1` |
| `rps_per_platform` | Requests a second to *all* stores on one platform together. All 19 are Shopify, and Shopify counts per client address, not per shop | `2` |
| `rps_images_per_host` | Picture downloads a second from one image server | `5` |
| `second_variant_below` | A store is sent a garment's second search-word variant only if its first returned fewer usable products than this. Never a third. `0` means never a second | `5` |
| `store_cache_ttl_s` | Identical store searches within this many seconds are answered from memory | `600` |
| `store_cooldown_s` | A store that turned a request away is left alone for this many seconds (more if it said how long) | `900` |
| `max_response_bytes` | Size cap for one HTTP response. A store file may override it | `2000000` |
| **Currencies** | | |
| `base_currency` | The currency prices, budgets and price ranges are compared in | `AED` |
| `fx_rates` | Fixed, approximate rates into `base_currency`. `KWD: 11.92` means 1 dinar is 11.92 dirhams. A currency with no rate is never converted and is left out of the price ranges. There is no live rate call. The comment in the file records the source and date; refresh it before any real use | `{KWD: 11.92}` |
| **Price ranges and ranking** | | |
| `tier_mix` | Percent of results per price range (budget, mid_range, premium, luxury). Must sum to 100. The page's sidebar can override it per search | `25/25/25/25` |
| `ranking_weights` | The three parts of the match score: `text`, `image`, `price`. They are normalised, so they need not sum to 1. With no image score, the image weight is dropped | `0.5 / 0.3 / 0.2` |
| `min_match_score` | A product scoring below this (0 to 1) is never shown, even to fill a thin range | `0.2` |
| `neutral_price_score` | The price-fit score when the shopper gave no budget (0 to 1) | `0.5` |
| **Models** | | |
| `image_ranker` | `siglip` (local model; needs the `ml` group and the weights, else it falls back to `off` with a warning) or `off`. The code default is `off`; only the shipped file turns the model on | `siglip` |
| `siglip_revision` | The exact 40-character Hugging Face commit of the image model. Changing it means re-running the spike's quality check | `c56244cc94f92419e8369fa71efdaf403b124ce8` |
| `siglip_cos_lo`, `siglip_cos_hi` | Turn an image similarity into a 0-1 score: at or below `lo` is 0, at or above `hi` is 1. `lo` must be below `hi` | `0.45`, `0.90` |
| `openai_model` | The OpenAI model for the Understand step. Must be a dated snapshot id or the one named undated id verified for it (OpenAI lists no dated variant of `gpt-6-luna`; the source and date are in the file's comment). Aliases such as `...-latest` are rejected | `gpt-6-luna` |
| `daily_llm_call_cap` | The most OpenAI calls per day. At the cap no call is made and the page says so. The count lives in the running process: it resets at midnight UTC and when the page restarts | `200` |
| **Logging and debugging** | | |
| `user_agent` | The name sent to stores. Must be honest and identifying; anything that looks like a browser is rejected | `vga-shopping-agent-demo/0.1 (store search demo)` |
| `log_dir` | Folder for the JSON-lines log `vga.jsonl` (git-ignored). Never holds the photo | `logs` |
| `log_level` | `DEBUG`, `INFO`, `WARNING` or `ERROR` | `INFO` |
| `log_prompts` | `true` also logs the typed text and what the AI read, never the photo. Debugging only | `false` |
| `debug_dump` | `true` writes every search's ranked candidates to `logs/candidates-<request id>.jsonl`. Debugging only | `false` |
| `ui_fixture` | `true` runs the page on the sample response | `false` |

### Environment variables (`.env.example`)

Copy `.env.example` to `.env` (git-ignored). An empty value counts as "not set". Never commit a real key.

| Variable | Meaning | Default |
|---|---|---|
| `OPENAI_API_KEY` | Your OpenAI key. Needed for real searches only. Read by the OpenAI client directly: it is never a setting and never logged | none |
| `OPENAI_MODEL` | Overrides `openai_model` | the YAML value |
| `VGA_USER_AGENT` | Overrides `user_agent` | as in the YAML |
| `VGA_IMAGE_RANKER` | `siglip` or `off`. Left commented out in `.env.example` so a copied file does not switch the model off | the YAML value |
| `VGA_LOG_DIR` | Overrides `log_dir` | `logs` |
| `VGA_LOG_LEVEL` | Overrides `log_level` | `INFO` |
| `VGA_LOG_PROMPTS` | `1` logs typed text and what the AI read (never the photo) | `0` |
| `VGA_DEBUG_DUMP` | `1` writes each search's candidate list to a file in `VGA_LOG_DIR` | `0` |
| `VGA_SETTINGS_PATH` | Path to another settings file | `config/settings.yaml` |
| `VGA_DAILY_LLM_CALL_CAP` | Overrides `daily_llm_call_cap` | `200` |
| `VGA_UI_FIXTURE` | `1` runs the page on sample data | `0` |

Keep `VGA_LOG_PROMPTS` and `VGA_DEBUG_DUMP` off outside debugging: both pile up on disk with no limit and no deletion, and the first records what people asked for. Never switch on debug logging for the whole Python process: the picture library then writes photo metadata to the log ([docs/privacy.md](docs/privacy.md)).

### Price-mix presets

The price mix says how many of the 30 results come from each price range. The ranges themselves are *relative*: the four borders are the quartiles of the prices found for this search, so a T-shirt search and a coat search get different ranges. The page's sidebar offers three presets; the default for the app is `tier_mix` in the settings file.

| Preset | Budget / Mid-range / Premium / Luxury | Results out of 30 | What it does |
|---|---|---|---|
| Even (default) | 25 / 25 / 25 / 25 | 8 / 8 / 7 / 7 | An even spread across the prices found |
| Value first | 40 / 30 / 20 / 10 | 12 / 9 / 6 / 3 | Favours cheaper products. Also used automatically when you ask for something "cheaper" without giving a budget; the page says so |
| Luxury first | 10 / 20 / 30 / 40 | 3 / 6 / 9 / 12 | Favours the dearest products |

Counts are rounded so they always add up to the total, with ties going to the cheaper range. If a range has too few products it borrows from the range next to it and is flagged "Few options in this range"; if nothing good enough is left it shows fewer results, never padding with weak matches. If you give a budget, Budget and Mid-range stay within it, and Premium and Luxury may go over and are labelled "Over your budget". For an outfit photo, each garment gets its own list with the same mix.

### Store files

Each store is one file in `config/stores/`, and a store is **off unless it says `enabled: true`**. The keys, with examples, are explained in [How to add a store](docs/how-to-add-a-store.md).

## Behaving towards the stores

The stores are real businesses, and this app is a guest on their websites. The rules are product rules (never broken) and the code enforces them, but you can still be rude by how you run it.

**What the app does on its own**

- Sends an honest, identifying name (`vga-shopping-agent-demo/0.1 (store search demo)`), never a browser's, and never any personal detail. No cookies, no login, no proxy, no pretending to be a browser.
- Reads each store's `robots.txt` first and does not visit what it forbids. If a store later forbids search, the store is skipped, not worked around.
- Sends about **1 request a second to each store** and **2 a second to all Shopify stores together**, because the shared platform limits a client address across all its shops. The first recorded acceptance run was throttled when it sent more: all 13 stores answered "too many requests" within 11 milliseconds of each other.
- Sends **one search-word variant per store**, and a second only to a store whose first came back with fewer than 5 products. A text search that reaches all 19 stores is about 19 search requests. A store is searched only for the categories and genders its file allows, so most searches reach fewer than 19. A photo search also downloads up to 40 product thumbnails from the stores' image servers, politely paced.
- **Never retries** a store request. It does not repeat a request that failed.
- Stops at the first refusal: a 403, a 429, a challenge page or a login page. A 429 from one Shopify store stops every Shopify store, drops the requests still waiting, and honours the `Retry-After` time if the store gave one.

**What "X was skipped because it turned down a recent request" means.** A store (or the whole Shopify platform) refused a request earlier, and the app is leaving it alone for the cooldown, 15 minutes by default (`store_cooldown_s`, longer if the store asked for longer). Nothing you click shortens it. **What to do:**

1. Stop searching. Wait **at least 15 minutes** (longer if the page or log says so).
2. Then try **one** search. Do not retry in a loop, and do not search again "just to see".
3. Do **not** restart the app to clear it. The app forgets its cooldown when it restarts, but the platform does not forget you: a restart would ask again at once.
4. Do not change network, use a VPN or alter the name the app sends. The project never works round a refusal. If it keeps happening, send fewer searches; never raise `rps_per_store` or `rps_per_platform`.

Other skip messages: "did not answer in time" and "its results could not be read" do not start a cooldown (that store is just skipped for this search); "asks automated tools not to search it" means the store's `robots.txt` now forbids search and it stays skipped until that changes.

**Do not run two things against the stores at once.** The app, a live acceptance run, `pytest -m live`, the command-line search and the qualification script all share one internet address and so one platform allowance, but each process only knows its own traffic. Two together can break the limit that either keeps on its own. Run one, let it finish, then run the next.

**Never loop live requests.** Tune ranking from a recording in replay mode, which sends nothing. A live run is for measuring, not for experimenting.

**Keep the laptop awake for a long run.** A full live acceptance run takes about 19 minutes (estimated when 13 stores were enabled; not repeated with 19). If the computer sleeps (a closed lid does it), the run stops, times become meaningless, and the app's cooldowns no longer match real time. An earlier build agent seemed to stall for hours this way. Plug in, keep the lid open, and on a Mac you can stop idle sleep for the length of one command:

```bash
caffeinate -i uv run --group ml python -m eval.harness --record eval/results/run-1/recording --wiring eval.harness.real:real_wiring
```

## The acceptance harness

The harness runs the 10 frozen acceptance queries (`eval/data/queries.yaml`: 3 product photos, 2 outfit photos, 3 text, 2 photo plus text; one is Arabic) headless, measures them against the pass rule below, and leaves only the human judgement of "is this a good match?" to a person.

**The pass rule** (from the PRD, with "most" read as at least 7 of the 10): a query passes if it returns at least 20 results from at least 3 stores, the first search takes 30 seconds or less, every link opens the right product page, a person marks at least 7 of the top 10 as good matches (rules in `eval/data/rubric.md`), and each price range is within one result of its target or flagged "few options". For an outfit photo, the 20 results count for the whole query, every garment needs at least one result, and the other checks run per garment ([plan A20](docs/plans/2026-10-07-vga-ai-shopping-agent-implementation-plan.md)).

**A mock run** uses a fake pipeline: no network, no key, no photos. It proves the harness works and measures nothing about the app.

```bash
uv run python -m eval.harness --mock
```

**A live recorded run** uses the real pipeline and records what OpenAI and the stores return, so the run can be replayed later without the network. It needs your OpenAI key (step 5 above), ideally the image model (step 4; without it photo queries are ranked on text and price only and the report says so), and the **five private acceptance photos**. The photos are not in the repository (they are git-ignored); copy them into `eval/data/assets/private/` with the exact names listed in [`eval/data/ASSETS.md`](eval/data/ASSETS.md). It sends real requests to all 19 stores, waits 30 seconds between queries (`--pause`) and one link check at most every 2 seconds (`--link-interval`), and takes about 19 minutes (estimated when 13 stores were enabled; not repeated with 19). Read [Behaving towards the stores](#behaving-towards-the-stores) first and keep the laptop awake.

```bash
uv run --group ml python -m eval.harness --record eval/results/run-1/recording --wiring eval.harness.real:real_wiring
```

If a query finds every store turned away or in cooldown, it is recorded as **not run** (neither a pass nor a fail), the run stops there, and the verdict reads INCOMPLETE. The harness prints which queries did not run and the exact command to finish them.

**The extra-photo set** is the other 11 supplied photos (`eval/data/extra_queries.yaml`). It runs the same way with `--queries`, goes to its own `extras-N` folder, and its report says it is not the acceptance result: it has no verdict and does not count towards the 7 of 10.

```bash
uv run --group ml python -m eval.harness --record eval/results/extras-1/recording --queries eval/data/extra_queries.yaml --wiring eval.harness.real:real_wiring
```

**Finishing a stopped run.** Wait at least 15 minutes after the stop, then run only the missing queries into the same folder and recording. Queries that already have a result are not sent again.

```bash
uv run --group ml python -m eval.harness --record eval/results/run-1/recording --only q03,q07 --wiring eval.harness.real:real_wiring
```

**A replay** re-runs the real pipeline offline from a recording: zero network, zero OpenAI calls, no image model needed. Use it to tune weights and thresholds without contacting the stores. It cannot check links (that needs the network). Replay times are the recorded live times.

```bash
uv run python -m eval.harness --replay eval/results/run-1/recording --wiring eval.harness.real:real_wiring
```

**Scoring a filled labelling sheet.** Every run writes `labels.csv` with one row per result in the top 10 of each garment. Open it, open the photo named in the `photo` column, and fill only the `label` column: `1` for a good match, `0` for not good, nothing else (the rubric explains how to judge). Then rebuild the report with the labels:

```bash
uv run python -m eval.harness --rescore eval/results/run-1 --labels eval/results/run-1/labels.csv
```

The harness checks every row against the run that produced the sheet and lists all problems together. The earlier report is kept as `results.bak-N.md`; a sheet that already holds labels is never overwritten (a new blank one is written as `labels.new.csv`).

**Where results land.** `eval/results/run-N/` for live acceptance runs (`run.json`, `results.md`, `labels.csv`, `responses/`, and the `recording/` folder when you put it there), `eval/results/extras-N/` for the extra set, and `eval/results/mock/` and `eval/results/replay/` for the offline runs. A live run's folder is never overwritten unless you pass `--overwrite`. **Results are git-ignored**: only a human-written `SUMMARY.md` inside a results folder is committed, so keep a run's summary there if you want it in the repository.

## Known limitations and failure modes of the AI features

These come from real runs, not guesses. "Not verified" means exactly that.

**The AI can misread a photo or a request**

- Colour, style, material and category are the model's reading of your photo or words. They are shown as editable chips labelled "Detected by AI" so you can correct them. Matching is AI-assisted and can be wrong; the page says so.
- `gpt-6-luna` has **no dated snapshot**, so OpenAI can change the model behind its name. The app pins what it can: the name, the prompt version and reasoning effort (`low`).
- The model's own label for the kind of request is not stable (it called a single-gown photo an outfit photo on one run and a product photo on another). So the code decides the kind from facts: a photo with one garment is a product photo, two or more an outfit photo, typed text alongside a photo is photo plus text.
- Live checks of the Understand step (24 cases, including the supplied photos and seven injection attempts) passed 24 of 24, then 23 of 24 on a re-run with no prompt change (the label flip above), then 24 of 24 once the code took over that decision. A typical answer takes about 2 to 3 seconds. A few runs are a small sample, and the check does not judge the quality of the search words.
- Text printed inside a photo is treated as data, and every injection case in the live check held. Still possible: a shopper who types a budget in words next to a sign showing another price could get the sign's price if the model obeys it; price words outside the filter list (coupon, voucher, outlet) can reach a store search; a sign in a photo can sway colour or style when your typed words are silent on them.
- **Arabic** is translated into English search words; translation quality varies. The translated chips can be corrected. The prompt spells out four Arabic garment words (abaya, dress, kaftan, jalabiya); other words rely on the model. Arabic was checked end to end on one real search (a men's white cotton shirt, read correctly) and in the Understand eval cases, nowhere else.
- **Faces in outfit photos are not blurred.** The photo goes to OpenAI as it is (after the camera details, GPS, colour profile and any comment are removed and the picture is shrunk to at most 1024 pixels).
- The model reads the photo; it does not guess your body size, and the app never uses one.

**Who it is for (gender)**

- A gender the AI only guessed is shown but **not applied** until you confirm it (product rule 8). When it is not stated, the page asks "Who is this for?". Until you answer, results for everyone are shown: a women's outfit photo then also returns men's shoes. Answering Women or Men fixes it, with no new OpenAI call.
- Stores say who a product is for in different places (`type` for Sacoor Brothers, tags for Nautica and Maison D'Vie, a "Menswear" tag at Signature Studio) or not at all (Giordano, Oh Polly and Club L London mostly give nothing). Where the store says nothing, the ranker reads the title, and women-only stores are marked in their config. A product with no clue can be shown for either.

**Thin spots in store coverage (the biggest risk)**

- **The 19 stores are boutiques and brands, not the big GCC retailers**, which an honest client cannot read. Results depend on what these shops sell, so some requests come back thin. The recorded acceptance run may fail its own pass rule on those queries even when nothing is broken, and the verdict will say so.
- **Menswear is the thinnest.** Giordano, Nautica and Sacoor Brothers carry it (not every category each), and Maison D'Vie only shirts and T-shirts. A real search for a black oversized men's blazer under 400 AED returned 15 results from 3 stores, below the 20-result bar: only Sacoor sells men's blazers, and all are over that budget.
- **Men's ethnic wear.** The stores added on 2026-10-08 fill most of this: Gul Ahmed UAE sells men's shalwar kameez (titled "Suits") and kurtas, Nishat Linen UAE and Signature Studio sell kurtas, and Al Jazeera Clothing sells dishdashas. **Adult men's thobes are still thin:** three men's dishdashas, all KWD 9 (about AED 107), were seen at one store, Al Jazeera Clothing, and most of what that store returns for a thobe search is boys' dishdashas. The ranker drops children's items only when you have stated or confirmed who the search is for.
- **Abayas:** Hanayen, Maison Arabelle, Hamsa, Shadow and Veil Essentials sell them. Before 2026-10-08 none sold an everyday abaya below about AED 600. Now Veil Essentials' abayas start near AED 142 (KWD 11.9 to 26) and Shadow's near AED 465 (6 of the 20 seen were under AED 600), so an abaya search can fill its Budget range with abayas; that has not been checked on a real search. Hamsa shows only about half of its abayas (see the price trap below).
- **Burqas and kurtis.** Nothing is sold as a burqa; the nearest are Veil Essentials' jilbabs and khimars. The ranker counts "burqa" as a dress but leaves "khimar" out (it can be a garment or a head covering, and the owner has yet to decide), so single khimars are kept and can show beside abayas. Women's kurtis are sold by Gul Ahmed UAE but titled "Shirt", so the ranker reads them as tops: they appear for a tops search and not a dresses one, and a "kurti" search there mostly returns men's kurtas ("printed shirt" finds the women's).
- **Other holes.** Heels come from Oh Polly and Club L London only. Skinny jeans and satin blouses were never searched in any store. `kurta` returns only men's items at Nishat Linen UAE and Signature Studio (women's kurta words were not tried). A "kaftan" search at Hanayen also returns sheilas (head scarves, dropped by the ranker as accessories) and plain under-abaya dresses (kept, because they are dresses). A "kaftan" or "dress" search at Shadow returns sheilas and caps, and no kaftan or dress.
- **Repeated and unreliable data.** Giordano repeats one title under several listings, so only 4 to 6 distinct products survive a search. Nishat Linen UAE shows 50% sale prices, so its place in the Budget range will move when the sale ends. Maison Arabelle's "was" price is unreliable, so it is never read. At Club L London shorter search words worked better ("blazer" beat "black blazer"). Gul Ahmed UAE gives different garments the same title, and the app collapses the same title at the same price: its four saved answers held 32 distinct products and 20 are left after that rule.
- **Price traps.** Hamsa's search price is the cheapest variant of a product, which on half its abayas is a head scarf. Those records are dropped rather than shown at a wrong price. Al Jazeera Clothing has the same rule for children's sizes: in the live test 3 of 10 records for `dishdasha` and 2 of 10 for `thobe` were dropped this way. Gul Ahmed UAE has two prices on 5 of 32 products and no such rule (some sizes may be at the sale price and some at the full price; not confirmed), so a size there can cost up to 66% more than the price shown.
- **A store can disappear at any time.** Shopify, or the shop, can close its search address or change its `robots.txt`. The store is then skipped, with a plain warning, and the others carry on. Eighteen of the 19 stores' `robots.txt` files (all but Maison Arabelle's) also carry a comment telling AI agents to use the store's own agent endpoint; the app treats it as data and does not use it (it is the subject of a later phase).
- Not verified: behaviour from any other internet connection; paging beyond 10 results per search (Shopify returns at most 10 products per call). The six stores added on 2026-10-08 (Daraat, Shadow, Her Highness Q8, Veil Essentials, Al Jazeera Clothing and Gul Ahmed UAE) were only ever reached through Cloudflare WARP, because the machine's own path to several Shopify addresses timed out on connect from about 13:00 that day; behaviour from the machine's own network is untested, and whether the time-outs were a routing fault is not known.

**The approximate dinar conversion**

- A Kuwaiti price is converted at a **fixed** rate, 1 KWD = 11.92 AED (Central Bank of Kuwait's dollar rate on 2026-10-07, with the dirham's fixed peg). The dinar moves against an undisclosed basket of currencies, so a rate read today is good to about 1% and drifts after that. The page shows "about" figures, rounded to the nearest 10 dirhams from 100 up. Price ranges, the budget check and the "over budget" flag go by that figure; what you actually pay is the store's own dinar price.
- A currency with no rate is never converted, and its products are left out of the price ranges. There is no live rate.
- The rate must be refreshed by hand, with its source and date, before any real use.

**Price ranges are relative**

- The borders are quartiles of this search's candidates, not market price bands. If the stores that answered are cheap or few, "Luxury" only means "the most expensive found" (the page says so when no luxury store was searched). With few products, borders can overlap (for example "Premium 380-915" next to "Luxury 549-2,650") because a thin range borrows from its neighbour. It is flagged "Few options in this range", but the header can still mislead.
- Weak matches (a text score under 0.3) can still fill a thin range. Tuning is left to the recorded run.

**Speed and the request limit**

- Each search first waits for OpenAI (about 2 to 5 seconds), then for the stores. Because every store request passes through a shared queue of 2 a second, store time for 13 stores was about 6 to 6.5 seconds, up from about 2 before the platform limit. With all 19 stores it is about 9.5 seconds by the same arithmetic (19 search requests at 2 a second); that is not measured yet. A store is searched only for the categories and genders its file allows, so most searches reach fewer than 19. Measured with 13 stores: "navy linen shirt for men" took 8.4 seconds and returned 23 results from 4 stores; "black abaya for women" 4.8 seconds and 30 results from 8 stores; "black embroidered abaya for women" about 13 seconds on the page.
- Photo searches add image comparison. Before the platform limit, a gown photo took about 19 seconds with the model already loaded, and 29.5 seconds from a cold start (10.4 seconds of that was loading the model). The page loads the model once when it opens. An outfit photo no longer runs image comparison (a whole-person photo is a weak likeness for one garment).
- A cold four-garment outfit search can reach the 30-second limit; the app then returns what had arrived, with a warning.
- Not known: whether 2 requests a second is under Shopify's allowance (it must not be probed), and whether one keyword variant per store gives enough results on every query.

**What was never verified**

- A recorded acceptance run with human labels: none exists yet.
- A screen reader, and colour contrast beyond the theme's documented values. (A keyboard-only pass worked; there was no sideways scrolling at 375, 768 or 1280 px wide.)
- Two browser sessions searching at the same moment, and whether Streamlit releases an uploaded photo from its own file store when the upload box is cleared (the page itself holds no photo).
- Whether this OpenAI account has zero data retention, and whether a photo's embedding can be turned back into a picture.
- Each store's terms of use. None has been read.

## Accepted gaps, and what must happen before real users

Accepted for this demo, on purpose: no load test beyond the 30-second budget measured by the harness; no automated accessibility checks (a manual pass instead); no usability test with real shoppers (a person labels the results); no production monitoring, hosting, containers or backups. The app runs on one computer.

**Before real shoppers use it, all of these are needed:**

1. **Terms of use, store by store.** Product rule 6: someone must read each of the 19 stores' terms and any affiliate rules. Nothing has been reviewed. Re-read Maison Arabelle's content-use line in `robots.txt` (`ai-train=yes, search=yes, ai-retrieval=yes, ai-personalization=no`), and the agent-endpoint comment that 18 of the 19 stores carry. The per-store checklist is in [`docs/store-notes/SUMMARY.md`](docs/store-notes/SUMMARY.md): it lists what is still owed for each store and leaves a blank "Checked by / date" line. Each store's note in `docs/store-notes/` also has a "Terms of use" entry that says "not reviewed".
2. **A privacy review.** UAE data protection law (Federal Decree-Law No. 45 of 2021) and, if people in Europe use it, GDPR. A photo of a person is probably personal data. The page's wording about the photo, a way to delete data on request, and photos of other people (children in particular) need a decision. See [docs/privacy.md](docs/privacy.md).
3. **Zero data retention at OpenAI.** The app asks OpenAI not to store a request, but OpenAI may still keep it for up to 30 days unless the account has "zero data retention". That is an arrangement the account owner must request from OpenAI. It has not been verified for this account. Reword the page's "not stored by us" notice once this is decided.
4. **The fixed exchange rate.** Refresh `fx_rates` in `config/settings.yaml` with a dated source, or replace it with a rate source you trust.
5. **Hosting.** Today there is no login and the daily OpenAI cap lives in one process. Hosting needs access control, TLS, a cap that survives restarts, and a check of the privacy points above. A Linux GPU machine would also pull NVIDIA packages whose licences are still marked "needs review" in `docs/licences.md`.
6. **Pin check.** `gpt-6-luna` can change behind its name. Re-run the Understand eval before relying on results.

## Acceptance result

> **TO BE FILLED IN BY THE ORCHESTRATOR. Not yet run.**
>
> The first recorded run (2026-10-08) was throttled by the stores' shared platform and is **not a result** (the folder is kept locally as `eval/results/run-1-throttled`, which is git-ignored; the app obeyed its own rule and stopped). The paced run, its human labelling and the verdict against the pass rule are still to come. Until this section is filled in, nothing in this repository claims that the demo passes or fails.
>
> Fill in here: date and commit; the model and prompt version; the per-query table (results, stores, first-search time, links, good matches in the top 10, price-range check); every failure with its cause (store, ranking, model or price range); the verdict (pass, fail or incomplete) and what failed; where the run folder is.

## How the code is organised

```
src/vga/models.py, interfaces.py, errors.py   shared contracts (change only in their own PR)
src/vga/settings.py, log.py, money.py         validated settings; JSON logs; currency conversion
src/vga/search.py                             the command-line search
src/vga/understand/   the one OpenAI call and its versioned prompt (prompts/, with a CHANGELOG)
src/vga/fetch/        the only code that talks to a store: robots.txt, rate limits, allow-list, cooldown
src/vga/stores/       store files loader, the search engine, the Shopify reader, price parsing
src/vga/rank/         text and price ranking; rank/image/ is the local image model
src/vga/tiers/        price ranges and the mix
src/vga/pipeline/     orchestration: the single entry point from request to response
app/                  the Streamlit page (runner.py is the only place that calls the pipeline)
eval/harness/         the acceptance harness      eval/data/   queries, rubric, photos' list
config/               settings.yaml and stores/<id>.yaml, one file per store
tests/                fakes.py, factories.py and one folder per area (guards/, stores/, ...)
docs/                 requirements, PRD, plan, ADRs, privacy note, store notes and qualification
```

Layers: the page calls the pipeline; the pipeline calls the OpenAI step, the store engine and the rankers; each outside system sits behind a small interface in `src/vga/interfaces.py`, so tests can swap in fakes. Untrusted text (what you type, the photo, and everything a store sends) is data and never instructions. No model ever reads store content. Store titles and links are never shown as HTML or markdown.

**Continuous integration.** `.github/workflows/ci.yml` runs three jobs on every pull request and on pushes to `main`: `test` (ruff, mypy and the critical suite, `pytest -m critical`; the complete suite runs locally, or in CI by hand with "Run workflow" and `full_suite`), `pip-audit` (every locked dependency, including the `ml` group) and `gitleaks` (a secret scan of the whole history). If gitleaks flags something that is not a secret, such as a made-up value in a test, add that finding's fingerprint (gitleaks prints it) to `.gitleaksignore` with a comment saying why; do not loosen the rules in `.gitleaks.toml`. To run the same scan locally: `gitleaks git --redact .` (install with `brew install gitleaks`). The plan records (risk R23) that the workflow had not yet run on GitHub when it was written; watch the first run. **A one-time manual step for the repository owner:** in GitHub, protect `main` (Settings, Branches) and require the checks `test`, `pip-audit` and `gitleaks` plus a review before merging. That cannot be done from the code.

**Licences.** Only components with commercial-friendly licences are allowed. After adding a dependency, run `uv run python scripts/licence_audit.py`; it rewrites [docs/licences.md](docs/licences.md) and flags copyleft, proprietary and unknown licences for a decision.

## Where to read more

- [Business requirements](docs/01-business-requirements.md), [PRD](docs/02-prd.md) and the [implementation plan](docs/plans/2026-10-07-vga-ai-shopping-agent-implementation-plan.md) (phases, assumptions A1 to A30, risks, the list of things deliberately left out).
- Decision records in [docs/adr/](docs/adr/): 0001 live search not an index, 0002 OpenAI and FashionSigLIP, 0003 honest fetching, 0004 weighted score and quartile price ranges, 0005 photo lifetime, 0006 second currency at a fixed rate. Some pre-date later changes (the platform-wide request limit, the model choice); the changelog and the plan hold the current numbers.
- [Privacy note](docs/privacy.md): what leaves the computer, what is kept, what is removed from the photo. It was written against the command line; where it says the page is not yet connected to the real search, that is out of date.
- Store files and notes: [How to add a store](docs/how-to-add-a-store.md), [store notes](docs/store-notes/) (one per store: data path, quirks, what would break it), [store qualification](docs/store-qualification/SUMMARY.md) (how each store was checked and the stores that were dropped).
- [CHANGELOG.md](CHANGELOG.md): what changed and what real runs showed, newest first; the prompt and model history is in `src/vga/understand/prompts/CHANGELOG.md`.
- [CLAUDE.md](CLAUDE.md) and `docs/Best Practices/`: the rules for working in the repo.
