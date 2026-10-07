# Proposed Ideas (not decisions): 1-day demo

Status: Draft v0.2, simplified · 2026-10-07 · The research person decides what to use and what to drop.

Upstream: [01-business-requirements.md](01-business-requirements.md), [02-prd.md](02-prd.md). Full earlier research is in `archive/` and in `../../reports/` (desk research from 2026-10-07, nothing was run; re-check licences before use).

## Main idea: search, don't crawl

Do **not** index whole stores and do **not** visit 60 product pages. Visit each store's **search results page** with the LLM's keywords. One page gives 20-50 products with price, image and link. That is about 10-12 requests total, about 3-8 s in parallel (estimate).

## Options per step

| Step | Simple default (proposed) | Other options |
|---|---|---|
| Understand | One multimodal LLM call with structured JSON output | Two calls (intent, then keyword expansion) |
| Fetch | `curl_cffi` or `httpx`, parallel with `asyncio`, 1 request/s per store | Crawl4AI or Playwright only for stores that need JavaScript |
| Read products | Per store, first thing that works: (1) the JSON the site's own search uses, (2) schema.org JSON-LD on the page, (3) CSS selectors, (4) headless browser | Shopify stores often expose `/products.json` or `/search/suggest.json` |
| Rank (text) | Keyword and attribute match of title vs request | Small text embedding model |
| Rank (image) | FashionSigLIP embeddings: query photo vs product thumbnails, top 30-50 only | A multimodal LLM looks at the photo plus top 20 thumbnails and picks the best (check cost and speed) |
| Outfit photo | LLM lists garments and searches each; rank by text match | Grounding DINO crop per garment, then image similarity (more work, better) |
| Photo + text | Photo → look; text → filters and changes | Embed photo and instruction together |
| Price ranges | Quartiles of this search's candidate prices per garment category, then pick the best matches per range by the `tier_mix` percentages | Fixed AED bands per category in config; tag known luxury stores (for example Ounass) as Luxury |
| UI | Streamlit page with chips and four price-range sections | FastAPI endpoint plus any front end |
| Runs on | A laptop or one GPU box | |

## Store shortlist (unverified)

Names are common GCC fashion sites. Whether each can be read cleanly, and whether it allows it, is **not checked**. Do that in hour 1.

| Store | Check first |
|---|---|
| Namshi | Own search API? Blocks bots? |
| Noon (fashion) | Same |
| 6thStreet | Same |
| Ounass | Same |
| Styli | Same |
| Level Shoes | Shoes only |
| Splash / Max Fashion / Centrepoint | Same |
| H&M, ASOS, Amazon | Often strict bot protection; try only if time |

Per store: look at `robots.txt`, then the browser's network tab to see how its search loads data. Drop any store that needs login, CAPTCHA or aggressive tricks.

## Day plan (about 8 hours, 1-2 people)

| Hours | Do |
|---|---|
| 0-1 | Pick country and 5-6 stores; check robots.txt; find the easiest data path for each |
| 1-4 | One fetcher per store returning the product record. **Timebox 45 min per store; drop it if stuck. Need at least 3 working.** |
| 4-5 | Understand step: LLM prompt and JSON schema |
| 5-6.5 | Ranking: text match first, image similarity second, then price ranges and mix |
| 6.5-7.5 | Endpoint plus simple page with chips |
| 7.5-8 | Run the 10 acceptance queries; write down results and failures |

## What was cut, and why

| Cut | Reason |
|---|---|
| Nightly index and vector database | Not needed if we search live |
| Score calibration, dedup, diversity algorithms | Nice, not needed to prove "find best match". Price ranges stay in: a few lines of code |
| Reranker model, benchmarks, bake-offs | A day is not enough to compare models; start with FashionSigLIP |
| Size matching | Needs per-brand size tables; user size is not in the demo |
| Metrics tooling and tracing platform | Log timings to a file; eyeball 10 queries |

## Risks

| Risk | What to do |
|---|---|
| Stores block automated requests | Drop the store; never bypass CAPTCHA; use the others |
| A store needs JavaScript | Use a headless browser for that store only; it is slower |
| Search page keywords return junk | Try 2-3 keyword variants per store; lower the match threshold |
| Store pages change | Fine for a demo; note which parsers are fragile |
| Terms of use | Demo only; check each store's terms before real users |
| 1 day is tight | Three working stores is enough to pass |
| No luxury store works, so the Luxury range is thin or only "most expensive found" | Include at least one luxury-leaning store in the shortlist; show the real price span; flag thin ranges |
| Search keywords bias the price pool (for example "cheap" in the query) | Do not pass price words to the stores; use them only as filters |

## If the demo works (not phases, just a list)

Add more stores, a cached catalog for speed, fixed price bands from the whole market, size matching, better outfit detection, measured quality numbers.

## Decisions for the research person

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Which 4-6 stores | | |
| 2 | LLM and API key | | |
| 3 | Image ranking: FashionSigLIP or multimodal LLM | | |
| 4 | Outfit photos: LLM list or crop detector | | |
| 5 | UI: Streamlit or other | | |
| 6 | Price range borders: quartiles of this search or fixed AED bands; default mix | | |
