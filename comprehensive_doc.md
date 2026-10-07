# VGA AI Shopping Agent: Comprehensive Documentation

Generated: 2026-10-07 · Source: repository at commit `c504a06` (branch `main`)

> **Read this first: the repository contains no application code.**
> It holds six Markdown files: the 1-day-demo business requirements, PRD and proposed-ideas (v0.2) plus their longer v0.1 predecessors in `docs/archive/`. There is no backend, frontend, database, config, dependency manifest, Dockerfile or CI.
>
> This document therefore describes the **specified** system. Every statement carries one of these tags:
>
> | Tag | Meaning |
> |---|---|
> | **[SPEC]** | Stated in `docs/01-business-requirements.md` or `docs/02-prd.md` (the requirements). |
> | **[IDEA]** | A non-binding option in `docs/03-proposed-ideas.md`. Nothing there is decided. |
> | **[DERIVED]** | Inferred by this document from the spec (for example the schema). Not in the repo. |
> | **[ABSENT]** | Does not exist anywhere in the repo or the spec. |

---

## 1. System Overview

**Purpose [SPEC].** A shopper gives a **photo, text, or both**. The system searches several **GCC online fashion stores** (UAE first) and returns the **best-matching products**, each linking to the store's own product page. It is a **one-day demo**, not a product.

**Primary features [SPEC]**

| Feature | Detail |
|---|---|
| Inputs | Product photo, outfit photo, text (English or Arabic), photo + text ("like this but dark brown, under 300 AED"). |
| Categories | Tops, outerwear, bottoms, shoes. Accessories are out of scope. |
| Stores | 4-6 GCC fashion sites, each one a small config entry. Not yet chosen. |
| Understanding | One multimodal LLM call returns structured JSON (category, colour, style, material, gender, budget, 2-3 English search keyword variants). |
| Editable chips | The UI shows what the system understood; editing a chip re-runs the search. Gender is never applied silently. |
| Live search | Visits each store's **search results page** in parallel (about 5-6 pages, not 60 product pages). No catalog crawl or index. |
| Ranking | Score = text/attribute match + image similarity (when the request has a product photo) + price fit. Weights in one config file. |
| Price ranges | Final top 30 split into **Budget / Mid-range / Premium / Luxury** by a configurable percentage mix (default 25/25/25/25). Each range shows its real price span and count. |
| Result card | Image, title, store, price + currency, colour if known, a short factual reason, "View product" link. Max 6 results per store. |

**Non-negotiable rules [SPEC].** Every result links to the original store page · respect robots.txt, no login walls, no CAPTCHA solving, about 1 request/s per store · never guess body size from a photo · do not keep uploaded photos after the request · only commercially licensed components · demo only; store terms of use must be checked before real users.

**Out of scope [SPEC].** Cart/checkout, accounts, accessories, size guessing, nightly crawling, score calibration, duplicate merging, more than 6 stores.

**Demo success criterion [SPEC].** On 10 test queries: at least 20 results from at least 3 stores in 30 s or less, with working links; a person judges 7 or more of the top 10 as good matches on most queries; each price range within 1 result of its target (or flagged as thin).

---

## 2. System Flow

### 2.1 Process flow [SPEC]

```
photo and/or text
      │
1. UNDERSTAND   one LLM call → structured intent JSON
      │         (on LLM failure: raw text becomes the keywords)
2. SEARCH       per store, in parallel, 6 s timeout, ~1 req/s
      │         → product cards (title, price, currency, image URL, product URL, store)
      │         (slow/blocked store: skipped and logged)
3. FILTER       drop incomplete cards (R6); keep only hard-filter matches (R7)
      │
4. RANK         score = text/attribute match + image similarity + price fit
      │         (image similarity failure: text/attribute score only)
5. SHAPE        quartile price borders → tier mix → per-store cap → top 30
      │
6. SHOW         four price-range sections with chips and result cards
```

### 2.2 Data flow [SPEC + DERIVED]

| Stage | Input | Output | Notes |
|---|---|---|---|
| Intake | Image bytes and/or text | Validated request | Anything else is rejected with a clear message (R1). Photo is held only for the request, never stored (Rule 4). |
| Understand | Image + text | `UnderstandResult` JSON | Product vs outfit photo is decided by the LLM (open question 1). Arabic is translated to English keywords by the LLM (open question 2). |
| Fetch | Keyword variants per store/garment | Raw HTML or JSON per store | Outfit photo = one search per garment, so about 4x the pages (about 6-10 s estimated). Price words ("cheap") must not be sent to stores; they are filters only. |
| Extract | Raw store response | `Product` records | Per store, first method that works: (1) the site's own search JSON, (2) schema.org JSON-LD, (3) CSS selectors, (4) headless browser **[IDEA]**. |
| Filter | `Product[]` | Filtered `Product[]` | Category, budget if given, in-stock if the card says so. |
| Rank | `Product[]` + request | Scored products | Image similarity runs only on the top 30-50 thumbnails **[IDEA: FashionSigLIP embeddings]**. |
| Shape | Scored products | Four tiers | Quartile borders per garment category over this search's candidates; counts from `tier_mix` with rounding that sums to the total (ties go to the cheaper range). |
| Respond | Tiers | UI payload | Per tier: real price span, result count, flags. |
| Log | Timings | Log file | Time per step and per store (R12). |

### 2.3 Price-range logic [SPEC]

1. **Borders.** Sort candidates for one garment category by price; cut at quartiles (cheapest 25% = Budget, then Mid-range, Premium, top 25% = Luxury).
2. **Counts.** `tier_mix` percentages of the 30 results. Default 25/25/25/25 gives 8/8/7/7; value-first 40/30/20/10 gives 12/9/6/3; luxury-first 10/20/30/40 gives 3/6/9/12.
3. **Fill.** Best matches first inside each range, max 6 per store overall. A thin range is filled from the nearest range and flagged "few options in this range". Products below the minimum match score are never used as filler; fewer results are returned instead.
4. **Budget.** If the user gives a budget, Budget and Mid-range must be within it. Premium and Luxury may exceed it and are labelled "over budget".
5. **Outfit photo.** Each garment gets its own list with the same mix (default 12 results per garment).

### 2.4 Failure handling [SPEC]

| Failure | Behaviour |
|---|---|
| LLM call | Use the raw text as search keywords. |
| One store | Skip, log, show the others. |
| All stores | "No results right now" with the reason. |
| Image similarity | Rank by text/attribute match only. |

### 2.5 Latency budget [SPEC, estimates, not measured]

| Step | Expected |
|---|---|
| Understand (LLM) | 1-3 s |
| Search 5-6 stores in parallel | 3-8 s |
| Rank incl. image similarity on 30-50 thumbnails | 2-8 s |
| Price ranges and mix | under 0.1 s |
| **Total** | **about 10-20 s**; demo limit 30 s |

---

## 3. User Flow

A typical journey **[SPEC + DERIVED]**:

1. **Enter.** The shopper opens the page (a simple web page is enough for the demo; no login, no account).
2. **Provide input.** Uploads a product photo or outfit photo, types text (English or Arabic), or both, for example "similar but dark brown and cheaper".
3. **Submit.** Invalid input (not an image, not text) is rejected with a clear message.
4. **Wait.** Roughly 10-20 s (limit 30 s) while the system understands, searches and ranks.
5. **Review understanding.** Editable chips show category, colour, gender and budget. For an outfit photo there is one group per detected garment.
6. **Correct (optional).** Editing a chip (for example setting gender or lowering the budget) re-runs the search. Gender stays unset until the shopper chooses it.
7. **Browse.** Four sections: Budget, Mid-range, Premium, Luxury. Each header shows its real price span and result count (for example "Budget · 45-139 AED · 8 results") and any flag ("few options in this range", "over budget").
8. **Inspect.** Each card shows image, title, store, price + currency, colour if known and a short reason.
9. **Exit.** Clicks "View product" and lands on the store's own product page. All buying happens there; the system has no cart or checkout.

Photos are discarded when the request ends.

---

## 4. Architecture

**Style [SPEC/IDEA]:** a stateless, synchronous-per-request pipeline. No database, no vector store, no queue, no background crawler. It runs on a laptop or one GPU box.

### 4.1 Components (planned)

| # | Component | Responsibility | Candidate tech **[IDEA]** |
|---|---|---|---|
| 1 | Presentation | Upload/text form, chips, four price-range sections, result cards | Streamlit (or FastAPI + any front end) |
| 2 | Request handler | Validate input (R1), orchestrate pipeline, enforce 30 s budget | Python `asyncio`, optional FastAPI endpoint |
| 3 | Understand service | One multimodal LLM call to structured JSON | Hosted multimodal LLM with structured output (provider not chosen) |
| 4 | Store registry | One config entry per store: country, search URL template, extraction method, rate limit | Config file (YAML/JSON/TOML not chosen) |
| 5 | Fetchers | Parallel, rate-limited, 6 s timeout HTTP fetch per store | `curl_cffi` or `httpx`; Playwright/Crawl4AI only where JavaScript is required |
| 6 | Extractors | Turn a store response into `Product` records | Store JSON, JSON-LD, CSS selectors, headless browser |
| 7 | Filter | Drop incomplete products; apply hard filters | Plain code |
| 8 | Ranker | Text/attribute match, image similarity, price fit; weights in config | Keyword/attribute match; FashionSigLIP embeddings (top 30-50 only) |
| 9 | Tier shaper | Quartile borders, mix counts, per-store cap, flags | Plain code |
| 10 | Settings | `country`, `stores`, `results`, `max_per_store`, `timeout_s`, `rps_per_store`, `tier_mix`, ranking weights | One config file |
| 11 | Logging | Timing per step and per store | Log file |

### 4.2 Interaction diagram

```
 Shopper ──photo/text──▶ UI ──▶ Request handler ──▶ Understand (LLM API) ──▶ intent JSON
                                      │
                                      ├──▶ Fetcher × N stores (parallel, 6 s, 1 rps)
                                      │         └─▶ Extractor ──▶ Product[]
                                      ├──▶ Filter ──▶ Ranker (+ image embeddings) ──▶ Tier shaper
                                      └──▶ UI ◀── four price-range sections (links go to store sites)
                           Settings ──▶ all components        Logger ◀── all steps
```

### 4.3 External dependencies

| Dependency | Direction | Risk |
|---|---|---|
| Hosted multimodal LLM API | Outbound, per request | Key not chosen. The uploaded photo leaves the machine to this provider. |
| 4-6 GCC fashion store sites | Outbound, per request | May block bots; terms of use unchecked; pages can change. |
| Image-embedding model weights | Local | Licence read from desk research only, never tested. |

---

## 5. Folder Structure

### 5.1 Actual (this repository)

```
vga-ai-shopping-agent/
├── .git/                          # git history (one commit: c504a06)
├── docs/
│   ├── 01-business-requirements.md   # WHY: goal, scope, rules, success criteria, business decisions (v0.2)
│   ├── 02-prd.md                     # WHAT: pipeline, requirements R1-R16, settings, price ranges, acceptance test (v0.2)
│   ├── 03-proposed-ideas.md          # HOW (options only): tech options, store shortlist, day plan, risks (v0.2)
│   └── archive/                      # Earlier, longer v0.1 versions of the same three files (6-week POC scope), superseded
│       ├── 01-business-requirements.md
│       ├── 02-prd.md
│       └── 03-proposed-ideas.md
└── comprehensive_doc.md           # this file
```

There is no `src/`, `backend/`, `frontend/`, `tests/`, `config/`, `docker/`, `.github/`, `README.md`, `.gitignore`, `.env*` or dependency manifest.

Reading order: `01` (why) → `02` (what) → `03` (how). The v0.1 files in `archive/` describe a different, larger scope (vector DB, nightly indexing, benchmarks, 10-retailer extraction) and should not be treated as current.

### 5.2 Implied layout **[DERIVED, not in the repo]**

Given the 1-day plan, a minimal implementation would likely look like:

```
app/                 # UI (Streamlit page) or API entrypoint
pipeline/            # understand.py, fetch.py, extract.py, filter.py, rank.py, tiers.py
stores/              # one config entry per store (R4)
config/settings.*    # country, results, max_per_store, timeout_s, rps_per_store, tier_mix, weights
logs/                # timing logs (R12)
tests/acceptance/    # the 10 acceptance queries and results table
```

---

## 6. Backend Overview

**Status: [ABSENT]. Nothing is implemented.** The spec and ideas define what it should do.

**Technologies [IDEA, undecided].**
- Language: Python is implied by every named library (`curl_cffi`, `httpx`, `asyncio`, Streamlit, FashionSigLIP) but is **not stated** as a decision.
- HTTP: `curl_cffi` or `httpx` with `asyncio`; headless browser (Playwright/Crawl4AI) only for stores that need JavaScript.
- LLM: any hosted multimodal LLM with structured (JSON) output. Provider and key undecided (business decision #3).
- Image ranking: Marqo-FashionSigLIP embeddings (about 203M params, Apache-2.0 per unverified desk research) or a multimodal LLM that compares the photo with the top ~20 thumbnails.
- Outfit photos: the LLM lists garments and one search runs per garment. Grounding DINO crops are an optional later upgrade.
- Optional serving: a FastAPI endpoint.

**Principal modules [SPEC, mapped to requirements].**

| Module | Requirements | Behaviour |
|---|---|---|
| Intake | R1 | Accept image, text or both; reject the rest. |
| Understand | R2, R3 | One LLM call; structured JSON; 2-3 English keyword variants; outputs feed the chips. |
| Store config | R4 | Adding a store means adding config: country, search URL template, extraction method, rate limit. |
| Fetch | R5, R12 | Parallel, 6 s timeout per request, about 1 request/s per store; failures skipped and logged. |
| Extract/Validate | R6 | Each product needs title, price, currency, image URL, product URL, store; drop products missing any. |
| Filter | R7 | Category, budget if given, in stock if the card says so. |
| Rank | R8, R9, R11 | Weighted score; max 6 per store; reason sentence uses only facts the code knows, else a plain template. |
| Tier shaper | R13-R16 | Quartile borders; `tier_mix` counts; fill and flag rules; real price span per range. |

**Request handling [DERIVED].** One request runs the whole pipeline within a 30 s demo limit. Store fetches run concurrently with a 6 s per-request timeout. A failure in any one store, in the LLM or in image similarity degrades the result instead of failing the request (see 2.4). There are no sessions, accounts or stored state; a chip edit re-runs the full pipeline.

**Store candidates [IDEA, unverified].** Namshi, Noon (fashion), 6thStreet, Ounass (luxury-leaning), Styli, Level Shoes (shoes only), Splash/Max Fashion/Centrepoint; H&M/ASOS/Amazon only if time (strict bot protection). Day plan: check `robots.txt` and the browser network tab first; timebox 45 minutes per store; at least 3 must work.

**API surface [ABSENT].** No endpoints are specified. Business decision #4 says a simple web page is enough.

---

## 7. Frontend Overview

**Status: [ABSENT]. Nothing is implemented.**

**Framework [IDEA].** A Streamlit page with chips and four price-range sections. Alternative: a FastAPI endpoint plus any front end. Business decision #4 defaults to "a simple web page is enough".

**Components [SPEC/DERIVED]**

| Component | Purpose |
|---|---|
| Input panel | Image upload and text box (English/Arabic); submit. Error message for invalid input (R1). |
| Understanding chips | Editable category, colour, gender and budget chips; editing re-runs the search (R3). Gender is shown, never silently applied. |
| Garment groups | For an outfit photo, one group per garment, each with its own tiers. |
| Price-range section | One of Budget / Mid-range / Premium / Luxury. Header shows price span and count (R16) and flags such as "few options in this range" or "over budget". |
| Result card | Image, title, store, price + currency, colour if known, short reason, "View product" link to the store page (R10, R11). |
| Status/empty state | Progress while waiting; "no results right now" with the reason when all stores fail. |

**Major workflows.** Submit input → view chips and tiers → edit a chip → re-run → click through to the store.

**Constraints.** Prices are shown in each store's own currency (AED first). No cart, accounts or checkout.

---

## 8. Schema

**There is no database or persisted schema [ABSENT].** The demo is stateless; uploaded photos are not retained (Rule 4), and a nightly index/vector database was explicitly cut. The structures below are the **in-memory data contracts [DERIVED]** from requirements R2, R4, R6, R10, R12-R16 and the Settings section. Field names are illustrative.

```jsonc
// Settings: one config file [SPEC: Settings]
{
  "country": "UAE",
  "stores": ["<store_id>", "..."],        // 4-6, not yet chosen
  "results": 30,
  "max_per_store": 6,
  "timeout_s": 6,
  "rps_per_store": 1,
  "tier_mix": { "budget": 25, "mid": 25, "premium": 25, "luxury": 25 },   // must sum to 100
  "ranking_weights": { "text_match": 0.0, "image_similarity": 0.0, "price_fit": 0.0 }  // values not specified
}

// StoreConfig: one entry per store [SPEC R4]
{
  "id": "string",
  "country": "UAE",
  "search_url_template": "https://…/search?q={query}",
  "extraction": "store_json | json_ld | css | headless",   // [IDEA] order, cheapest first
  "selectors_or_mapping": { },
  "rps": 1,
  "timeout_s": 6
}

// UnderstandResult: the single LLM output [SPEC R2, R3]
{
  "input_type": "product_photo | outfit_photo | text | photo_text",   // LLM decides
  "items": [
    {
      "category": "tops | outerwear | bottoms | shoes",
      "colour": "string | null",
      "style": "string | null",
      "material": "string | null",
      "gender": "men | women | unisex | null",       // null until the shopper confirms
      "search_keywords": ["en variant 1", "en variant 2", "en variant 3"]
    }
  ],
  "budget": { "max": 300, "currency": "AED" }         // nullable
}

// Product: parsed from a store [SPEC R6]; drop the record if any required field is missing
{
  "title": "string",             // required
  "price": 0.0,                  // required
  "currency": "AED",             // required
  "image_url": "string",         // required
  "product_url": "string",       // required: store's own product page (Rule 1)
  "store": "string",             // required
  "colour": "string | null",     // optional
  "in_stock": "bool | null"      // optional, only if the card shows it
}

// ScoredProduct [SPEC R8, R9, R11]
{
  "product": { },
  "scores": { "text_match": 0.0, "image_similarity": "0.0 | null", "price_fit": 0.0, "total": 0.0 },
  "tier": "budget | mid | premium | luxury",
  "reason": "string",            // only facts the code knows, else a plain template
  "flags": ["over_budget"]
}

// Response [SPEC R13-R16]
{
  "understood": { },             // UnderstandResult, rendered as editable chips
  "groups": [                    // one per garment for an outfit photo, otherwise one
    {
      "category": "string",
      "tiers": [
        {
          "name": "Budget | Mid-range | Premium | Luxury",
          "price_min": 45, "price_max": 139, "currency": "AED",
          "target_count": 8, "count": 8,
          "flags": ["few_options"],
          "results": [ ]         // ScoredProduct[], best match first
        }
      ]
    }
  ],
  "stores_used": ["..."], "stores_skipped": [{ "store": "...", "reason": "timeout" }]
}

// Log record [SPEC R12]
{ "request_id": "string", "step": "understand | fetch | extract | rank | shape", "store": "string | null", "duration_ms": 0, "status": "ok | timeout | blocked | error" }
```

**Notes**
- `tier_mix` counts use rounding that always sums to the total; ties go to the cheaper range.
- Tier borders are computed from the current search's candidates per garment category; they are not a stored table.
- No user, session, order or payment entity exists.

---

## 9. Essentials Checklist

Everything needed to understand or run the system. "Status" reflects the repo today.

### 9.1 To understand it
- [x] Read `docs/01-business-requirements.md` → `02-prd.md` → `03-proposed-ideas.md`.
- [x] Ignore `docs/archive/` except for history (v0.1, a different, larger scope).

### 9.2 To run it

| Item | Status | Detail |
|---|---|---|
| Source code | **Missing** | Nothing to run. |
| Language/runtime and version | **Undecided** | Python implied, not stated. |
| Dependency manifest | **Missing** | No `requirements.txt`, `pyproject.toml`, `package.json` or lockfile. |
| HTTP client | Undecided **[IDEA]** | `curl_cffi` or `httpx` + `asyncio`. |
| Headless browser | Conditional **[IDEA]** | Playwright/Crawl4AI only for JavaScript-only stores. |
| UI framework | Undecided **[IDEA]** | Streamlit (default) or FastAPI + any front end. |
| Multimodal LLM + API key | **Undecided** (business decision #3) | Any hosted multimodal LLM with structured output. |
| Environment variables | **None defined** | A key for the chosen LLM provider will be needed. See 9.3. |
| Image-embedding model | Undecided **[IDEA]** | Marqo-FashionSigLIP (about 203M params). Licence unverified. CPU vs GPU not decided; spec says "a laptop or one GPU box". |
| Store selection (4-6) | **Undecided** (decision #2) | Unverified shortlist only. At least 3 working stores needed; see blocker B3 for why 4 are effectively required. |
| Per-store extractor config | **Missing** | Each store needs search URL template, extraction method and rate limit. |
| Config file | **Missing** | Must hold the Settings from section 8. |
| Network access | Required | Outbound HTTPS to the LLM API and the store sites. |
| Logging location | **Undecided** | A log file for per-step/per-store timings (R12). |
| Test assets | **Missing** | 10 acceptance queries: 3 product photos, 2 outfit photos, 3 text (one Arabic), 2 photo + text. |
| Pre-real-user legal check | Required later | Each store's terms of use and affiliate programme (Rule 6). |

### 9.3 Environment variables **[DERIVED, proposed names, none exist]**

| Variable | Purpose |
|---|---|
| `LLM_API_KEY` (or the provider's own name) | Credential for the chosen multimodal LLM. Never commit it. |
| `LLM_MODEL` | Model identifier. |
| `STORES_CONFIG` / `SETTINGS_PATH` | Location of store and settings config, if not fixed in code. |

No `.env.example` and no `.gitignore` exist yet; add both before the first secret is created.

---

## 10. Deployments Checklist

**Deployment platform: [ABSENT].** No cloud provider, container image, CI/CD pipeline, infrastructure-as-code or hosting decision exists. The only runtime statement is "Runs on: a laptop or one GPU box" **[IDEA]**. The business asks only for a demo web page (decision #4). So today "deployment" means running locally; there is nothing to deploy.

If the demo is later hosted, this is what the spec implies **[DERIVED, recommendation]**:

| Area | Requirement |
|---|---|
| Packaging | A container or process running the pipeline and UI. Needs a dependency manifest and, if a headless browser is used, its browser binaries. |
| Compute | CPU may suffice for text-only ranking. Image embeddings of 30-50 thumbnails inside the 2-8 s budget may need a GPU (not measured). |
| Secrets | LLM API key in the platform's secret store, not in the repo. |
| Egress | Stores may block datacenter IP ranges that a laptop or home IP would not hit. Test from the target host before relying on it. Never bypass blocking or CAPTCHA (Rule 2). |
| Timeouts | Any proxy or platform request limit must be at least 30 s (demo limit), or the UI must stream progress. |
| Rate limiting | Honour about 1 request/s per store, including across concurrent users. |
| Storage | No persistent volume needed. Uploaded photos must be discarded after the request (Rule 4): memory or temp files removed at request end. |
| Observability | Per-step and per-store timing log (R12). Ship it somewhere readable. |
| Privacy | The photo is sent to the third-party LLM provider. Confirm that provider's retention terms. Rule 4 only covers our side. |
| Access control | No accounts exist. Anyone with the URL can spend LLM credit. Restrict access (IP allow-list, shared password or platform auth). |
| Licensing | Confirm every model and library licence is commercial-friendly (Rule 5). |
| CI/CD | None. Not needed for a one-day demo. |

---

## 11. Payment Integration & Credit Token System

**Not implemented and not specified. Both are explicitly or implicitly out of scope.**

| Question | Answer |
|---|---|
| Payment provider (Stripe, etc.) | **[ABSENT]**. None. |
| Cart / checkout | Out of scope **[SPEC: BRD "Out of scope"]**. Purchases happen on the store's own site via the product link. |
| Accounts / authentication | Out of scope **[SPEC]**. There is no user identity to attach a balance to. |
| Credit or token balance | **[ABSENT]**. No credits, wallet, quota, plans or ledger in any document or schema. |
| Monetization | Affiliate links are "not in this demo" **[SPEC: BRD decision #5]**. Rule 6 says someone must check each store's terms and any affiliate programme before real users. |
| Usage metering / rate limiting | **[ABSENT]**. Only the outbound limit of about 1 request/s per store exists. |

The only "tokens" in the picture are the hosted LLM's input/output tokens. They are a **cost to the demo operator**, not a user-facing currency, and the spec has no budget cap or per-user limit for them.

**If monetization is added later [DERIVED, not a plan]:** it would need user identity first, then a per-request credit charge at the Understand step (the only paid external call) and, if affiliate revenue is pursued, link-rewriting at the "View product" step. That conflicts with Rule 1 (every result links to the original store page) unless the affiliate URL still lands on that page. Resolve with the business before building.

---

## Appendix: Blockers and Gaps Review

### Blockers (prevent the app from running)

| # | Blocker | Why it blocks |
|---|---|---|
| B1 | **No source code in the repo** | There is no application to install, run or deploy. All sections above describe a specification. |
| B2 | **Core decisions are blank** | The decision tables in `01` (#2 stores, #3 LLM + key) and `03` (all 6 rows) are unanswered. No store, LLM provider, image-ranking approach, outfit approach or UI is chosen. |
| B3 | **Acceptance criteria are arithmetically inconsistent** | R9 caps results at 6 per store. The pass criterion needs at least 20 results from at least 3 stores, but 3 stores x 6 = 18 < 20. The demo needs **at least 4 working stores** to pass, and 5 to fill 30. The "Three working stores is enough to pass" advice in `03` contradicts this. |
| B4 | **No LLM credentials** | The Understand step cannot run without an API key for an undecided provider. |
| B5 | **No verified store access** | None of the shortlisted stores has been checked for robots.txt, bot blocking or a usable search data path. Any of them can be unreachable or off-limits. |

### Gaps and risks (do not block a start, but need an answer)

| # | Gap | Note |
|---|---|---|
| G1 | No runtime version, dependency manifest, config file, `.gitignore`, `.env.example` or README | Nothing to set up from. Add before the first secret exists. |
| G2 | Outfit-photo result count conflicts with the cap | 12 results per garment x 4 garments = 48 results, but the overall target is 30. State whether 30 applies per garment or per request. |
| G3 | Ranking weights and the "minimum match score" threshold have no values | The PRD says "weights in one config file" and "minimum match score" without numbers. |
| G4 | Photo privacy | Rule 4 (no retention) covers this system only. The photo goes to a third-party LLM. |
| G5 | No access control | No accounts means anyone with the URL can consume LLM credit. |
| G6 | Licence evidence is desk research only | Model and library licences in `03` were never tested; re-verify before use. |
| G7 | Broken cross-reference | `03-proposed-ideas.md` points to `../../reports/` for the full research. That folder is not in this repo (or its parent). |
| G8 | Two doc generations coexist | `docs/archive/` (v0.1, 6-week POC, vector DB, Qdrant, LangGraph) conflicts in scope with v0.2. Keep it clearly marked as superseded. |
| G9 | Cloud-host blocking | Stores that work from a laptop may block datacenter IPs. Test from the real host. |
| G10 | Open product questions | Auto-detect product vs outfit photo; is English-only store search enough for Arabic; AED-only display; default 25/25/25/25 mix and quartile vs fixed AED borders (PRD "Open questions" 1-4). |

**Bottom line:** the next step is not deployment. It is to resolve B2-B5 (pick at least 4-5 stores and check each, choose the LLM and key), then implement the pipeline in the order given in the day plan in `docs/03-proposed-ideas.md`.
