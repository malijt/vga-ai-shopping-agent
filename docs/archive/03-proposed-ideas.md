# AI Fashion Shopping Agent: Proposed Ideas (Not Decisions)

| | |
|---|---|
| Status | Draft v0.1, **input for the research lead** |
| Date | 2026-10-07 |
| Upstream | [01-business-requirements.md](01-business-requirements.md), [02-prd.md](02-prd.md) |
| Evidence source | Preliminary desk research on 2026-10-07: `reports/Open source fashion shopping agent bases.md` and four notes under `research_notes/Open source fashion shopping agent bases/` (in the parent `shopping-agent` folder) |

> **Nothing here is decided.** Each card lists options, what the preliminary research found, and a suggested way to decide. The research lead picks, drops or replaces any of it, and records the decision in card X (the decision table at the end) with evidence.
>
> **Caveat on evidence.** Stars, licences, dates and model facts were gathered by desk research on 2026-10-07 from repos, model cards and package pages. Nothing was run or tested. Re-verify each one on day 1 (deliverable D1) before relying on it. Licence readings are technical notes, not legal advice.

---

## 0. Headline from the preliminary research

- **No open-source project is a good fork for the whole POC.** About 50 repos were looked at. The closest on features (a photo-to-similar-products repo with outfit detection) and the closest on stack (a hybrid-search plus LangGraph repo) both had **no licence file**. Another had conflicting licence terms. The permissively licensed ones were demo- or notebook-shaped.
- **No repo found** does multi-retailer ingestion, price-tiering, or links to real retailer pages. That half is custom work under any approach.
- **Most of the brief's planned components are permissively licensed** (Apache-2.0, MIT, BSD), so "assemble from libraries and models" looks feasible. The risk sits in tempting shortcuts, not in the plan.

---

## How to use each card

**Need** → **Options** → **What we know so far** → **Suggested way to decide** → **Decision** (blank, researcher fills it in).

---

## A. Build approach: fork, assemble, or hybrid

- **Need:** reach a working POC in 6 weeks with a clean licence position.
- **Options:**
  1. Fork one existing repo and extend it.
  2. Assemble from libraries and models (new thin skeleton).
  3. Assemble, but borrow *ideas* from unlicensed repos and re-implement them.
  4. Ask the authors of unlicensed repos for a written licence and fork only if granted.
- **What we know so far:**
  - Unlicensed, closest on features: `TanyaChan516/fashion-visual-search` (all four input modes, Grounding DINO + SAM2, eval harness; static 10k-image catalog; photo+text only re-ranks the image's nearest neighbours).
  - Unlicensed, closest on stack: `EternalSol1tude/multimodal-fashion-rag` (Qdrant dense + sparse with RRF, cross-encoder, LangGraph, FastAPI, tests; text-first, no detection).
  - Conflicting licence: NVIDIA `retail-shopping-assistant` (badge says Apache-2.0, LICENSE file says NVIDIA terms; demo-only catalog).
  - Permissive but weak: `haticebaydemir/ai-fashion-assistant-v2` (MIT, notebook-shaped), `yainage90/fashion-visual-search` (MIT, stale; training-data provenance concerns).
  - Marqo's open-source engine is marked deprecated in its README.
  - Estimated saving even from a granted licence: a few days of demo flow; the 6-week risk is the retailer layer, which no repo contains. (This estimate is an inference, not measured.)
- **Suggested way to decide:** send licence requests on day 1 (cheap, no downside); plan as if no reply; revisit at Gate 1.
- **Decision:** ☐

## B. Orchestration

- **Need:** a fixed pipeline with parallel work per garment and per retailer group, retries, partial results.
- **Options:** (1) LangGraph library (fixed graph, `Send` fan-out, checkpointers); (2) plain async Python with Pydantic models and a small runner; (3) another workflow engine.
- **What we know so far:**
  - LangGraph is MIT. No LangGraph shopping template has real adoption; start from the official project template or the library plus your own FastAPI app.
  - Two MIT FastAPI + LangGraph templates are worth *borrowing infrastructure patterns from* (settings, Postgres checkpointer, Docker, Langfuse wiring in one of them), but both are chat-shaped.
  - Avoid `langgraph-api` (Elastic-2.0) and LangServe (custom licence, archived).
  - The graph is a **fixed pipeline**, so a framework is optional. Whether LangGraph's checkpoints and fan-out justify the dependency is a real question.
- **Suggested way to decide:** build the skeleton both ways in half a day each, or decide on whether you need checkpoint-based retries.
- **Decision:** ☐

## C. Visual-similarity embeddings ("find this exact look")

- **Candidates:**

| Model | Notes from preliminary research |
|---|---|
| Marqo-FashionSigLIP | Apache-2.0, ~203M params, image and text in one space. Its card says the newer FashionSigLIP-2 is **on request only**. |
| GR-Lite | Image-only (cannot embed text queries). Card says Apache-2.0, but its DINOv3 base has a custom, gated licence; **chain unresolved**. 65.71% on LookBench per the paper. |
| MODA (HopitAI) | MIT/Apache-2.0, built on FashionSigLIP, ~203M. Benchmark gains are self-reported; could not confirm it is the "MODA" the brief means. |
| marqo-ecommerce-embeddings | Weights Apache-2.0; its GitHub repo has no licence. |
| FashionCLIP 2.0, OpenCLIP, SigLIP 2 | Baselines. |

- **Suggested way to decide:** the brief's rule (challenger must beat the default by ≥ 3 NDCG@20 on product- and outfit-photo queries), measured on our own catalog. Do not mix numbers across benchmark harnesses (two different LookBench figures appeared for similar Marqo models).
- **Decision:** ☐

## D. Multimodal query embeddings (text, photo + text)

- **Question to settle first:** do we need a second embedding model at all? A single fashion model with a text tower may be enough; if one model wins both roles, use one vector.
- **Candidates:**

| Model | Notes |
|---|---|
| EmbeddingGemma 2 | Apache-2.0, 740M params, 768-d, text/image/video/audio. **Not** the small text-only v1 (v1 is `gemma`-licensed, gated). Its self-reported image score is far below Qwen3-VL's. |
| Qwen3-VL-Embedding 2B / 8B | Apache-2.0, mixed image+text input, instruction-aware, released 2026-01-07. 8B as a "quality ceiling" measurement. |
| WeMM-Embedding (2B/4B/9B) | HF licence tag is `other`; LICENSE text says Apache-2.0 "except third-party components listed below" with no visible list. **Licence unresolved.** |
| Marqo-FashionSigLIP text tower | Free, already in the visual space. |
| Gemini Embedding 2 | Hosted reference only. |

- **Suggested way to decide:** brief's rule on text and photo + text queries on our own catalog; get legal sign-off on any model with ambiguous terms before it enters a shortlist.
- **Decision:** ☐

## E. Vector store and hybrid search

- **Need:** several vectors per product, keyword search, filters, rank-merge in one call.
- **Options:** Qdrant; Vespa (heavier, more samples); OpenSearch or Milvus (Apache-2.0, RRF support).
- **What we know so far:**
  - Qdrant (Apache-2.0) natively offers rank fusion (RRF, DBSF), a formula-based rescore (price decay, rating, stock gate), MMR, group-by and positive/negative "recommend" queries. That absorbs part of the scoring work.
  - **Detail to verify:** Qdrant's RRF constant defaults to a small value; the classic k = 60 maps to a different parameter value. The brief says k = 60.
  - **Detail to verify:** Qdrant's MMR appears to attach to a single nearest-neighbour query, not to the fused hybrid score. If so, diversity must be done in application code.
  - Avoid as base: Elasticsearch (AGPL/SSPL/ELv2), Typesense (GPL-3.0). Weaviate has mixed terms.
  - Qdrant's own e-commerce demo is close in shape (dense + BM25 + RRF + formula rescore + LLM-judge eval) but **has no licence file** and is text-only; use as a design reference or ask for a licence.
  - Copyable (Apache-2.0): the Qdrant `examples` repo, including a fusion-methods notebook that already uses ranx.
- **Suggested way to decide:** hybrid must beat the best single signal on our own labelled set (Qdrant's own guide notes fusion lost to the best single retriever on 1 of 5 datasets).
- **Decision:** ☐

## F. Photo + text composition ("like this, but dark brown and cheaper")

- **Idea:** split the text into **hard filters** (price, colour, category) and **soft semantic edits**; do not rely on embedding arithmetic alone.
- **Options for the soft part:**
  1. Weighted sum of photo embedding and edit-text embedding in one space.
  2. Feed photo + instruction together into a multimodal embedder.
  3. A VLM rewrites a target description with the edit applied, then embed that.
  4. Positive and negative example queries ("like A, not B") using the vector DB's recommend feature.
- **What we know so far:**
  - Published composed-image-retrieval repos are not good adoptions: two are CC BY-NC, three have no licence, two permissive ones pin old frameworks and score about 28-33% Recall@10 on FashionIQ.
  - A 2026 audit paper reports that strong generalist embedders reach only about 15.8-33.2% Recall@10 on FashionIQ, and that 32% of FashionIQ queries can be solved from one modality alone. Treat any quoted number as hard to compare.
  - No source gives a ready recipe for fashion; this is research-grade everywhere.
- **Suggested way to decide:** build our own small (photo, edit, accepted-targets) set first; try options 1-3 as ablation switches.
- **Decision:** ☐

## G. Reranker (optional)

- **Candidates:** Qwen3-VL-Reranker 2B / 8B (Apache-2.0, released 2026-01-07).
- **What we know so far:** the model card gives no VRAM figure (weights alone are about 4.3 GB for 2B and 17.5 GB for 8B by rough arithmetic); in Qwen's own table the 2B reranker scores slightly **below** the 2B embedder on image retrieval; no fashion evaluation exists. Other rerankers found: jina-reranker-m0 (non-commercial), an NVIDIA reranker (custom licence, terms not read).
- **Suggested way to decide:** the brief's week-2 rule (keep only if ≥ +3 NDCG@20 and latency fits). It is fine to drop it.
- **Decision:** ☐

## H. Garment detection and masks

- **Need:** find tops, outerwear, bottoms and footwear in outfit photos reliably.
- **Candidates:**

| Option | Notes |
|---|---|
| Grounding DINO (via the maintained transformers port) | Apache-2.0. Upstream repo untouched since 2024-08-12. A 2023 paper proposes fixes for missed or false clothing detections (from a search summary only; no numbers retrieved). |
| Fashion-specific DETR detector (`yainage90`) | Labels top / outer / bottom / shoes etc.; MIT label, but trained on ModaNet (non-commercial annotations) and Fashionpedia. **Legal effect on weights unresolved.** |
| SAM 2.1 | Apache-2.0, box-prompted masks. |
| SAM 3 | Custom, gated licence (flow-down terms, indemnity, termination clause, Meta may amend). Needs legal review before any use. |
| Florence-2 | MIT. |
| RF-DETR / D-FINE / RT-DETR | Permissive detector families if a trained detector is wanted. |
| Avoid | Ultralytics YOLO (AGPL-3.0), YOLO-World (GPL-3.0). |

- **Open design choices:** fully automatic detection versus a human box-review step (one repo uses human review; the brief wants automatic); how to treat dresses, jumpsuits, left/right shoes.
- **Suggested way to decide:** pilot on 30-50 real outfit photos; measure garment recall against the Must (≥ 0.80).
- **Decision:** ☐

## I. Colour extraction

- **Idea:** masked pixels, k-means in CIELAB, map to a curated palette of about 30-60 fashion colour names; run the same code on catalog images so query and catalog share one vocabulary.
- **What we know so far:** no library does this end to end. `scikit-image` (BSD-3) provides the colour-space maths; palette seeds exist (XKCD names CC0; `meodai/color-names` MIT). About 50 lines of code. The palette is the real work.
- **Decision:** ☐

## J. Nightly catalog tagging with a vision-language model (VLM)

- **Need:** a fixed attribute vocabulary on every product image, at low cost.
- **Options:** hosted multimodal LLM; self-hosted open VLM on the GPU box (serve with a batch inference server using constrained JSON).
- **Open VLM candidates (all Apache-2.0 per their cards):** Qwen3-VL (2B-32B), Qwen3.5 / 3.6, Gemma 4, SmolVLM2, InternVL3.5-8B. Avoid Qwen2.5-VL-3B (research licence) and Gemma 3 (custom, gated).
- **What we know so far:** no open fashion-attribute tagger or VLM fashion benchmark found.
- **Suggested way to decide:** bake-off on a 200-500 item human-labelled set; compare accuracy and cost per 1,000 products, including hosted vs self-hosted.
- **Decision:** ☐

## K. Retailer data acquisition

- **Idea (from the brief):** cheapest method first, per retailer, in a config-driven cascade: (1) feed / API, (2) embedded page data, (3) CSS/XPath schema, (4) LLM extraction used once to *write* a reusable schema, (5) browser agent only for click-gated sites.
- **Tools mentioned:** Crawl4AI, extruct, curl_cffi, Playwright, browser-use, Scrapy, Crawlee. Check each tool's licence and maintenance.
- **What we know so far:**
  - Crawl4AI is Apache-2.0 **plus an attribution requirement**; its robots.txt check defaults to off. Scrapy's robots obeying also defaults to off in core settings. A compliance layer is therefore ours to write.
  - extruct's latest PyPI release is old (2024-11) while fixes sit on the main branch; pin a commit.
  - Anti-bot: curl_cffi, then normal Playwright. Retailers behind challenge pages should go via an affiliate feed or be dropped (the brief forbids CAPTCHA solving).
  - Avoid: Firecrawl core (AGPL-3.0), nodriver and zendriver (AGPL-3.0), undetected-chromedriver (GPL-3.0). Scrapling's stealth fetcher conflicts with the no-CAPTCHA rule.
  - Feed sources that exist: Awin product feeds (JSON Lines), CJ GraphQL product search, Impact catalogs, Rakuten product search, Shopify `/products.json` (one store checked) and Shopify's global catalog for Shopify merchants. **No open-source client for product feeds was found; write one small downloader per network.** Google's Content API for Shopping was sunset on 2026-08-18; the Google feed *format* remains a common standard.
  - Which networks exist depends on the target country.
- **Suggested way to decide:** the brief's extraction benchmark (10 retailers, 20 product pages and 3 search pages each) is the decision tool. Programme and retailer terms were **not** reviewed in the preliminary research.
- **Decision:** ☐

## L. Schema, taxonomy and sizes

- **Reusable:** Zyte `Product` field vocabulary (BSD-3, no confidence or provenance fields), Shopify `product-taxonomy` (MIT) as a category backbone, `price-parser` (BSD-3), the `recipe-scrapers` layout idea ("generic parser first, site override second").
- **Custom:** canonical record with `extraction_confidence` and `source_method`; taxonomy-node to 4-category map; **per-brand size-chart normalisation** (no open library or maintained table found); a GTIN check-digit validator (a few lines; `python-stdnum` is LGPL).
- **Decision:** ☐

## M. Cross-retailer matching and dedup

- **Idea:** tiered, per the brief: exact keys (URL, GTIN, brand + MPN), then fuzzy title match, then image similarity.
- **What we know so far:** RapidFuzz (MIT) is active; Splink (MIT) active; `dedupe` and `recordlinkage` look stale; `imagededup` (Apache-2.0) and `SemHash` (MIT) for images.
- **Suggested way to decide:** tune thresholds on the 200 hand-labelled pairs from the brief.
- **Decision:** ☐

## N. Score calibration and honest explanations

- **Idea:** calibrate with isotonic regression (e.g. scikit-learn, BSD-3) on the tuning set; show bands if ECE fails; reasons come from a code-built fact sheet and are checked by a validator.
- **What we know so far:** no off-the-shelf validator checks every claim against a fact sheet; write a deterministic fact-id check. Optional second line: a hallucination-detection model (HHEM-2.1-open Apache-2.0, LettuceDetect MIT). Avoid Patronus Lynx (non-commercial); Bespoke-MiniCheck licence unverified.
- **Decision:** ☐

## O. Price tiers and diversity

- **Idea:** percentile tiers computed per category over the full indexed catalog (a few lines of NumPy/pandas); diversity by relevance-vs-novelty selection with retailer and cluster caps.
- **What we know so far:** no library worth adopting for tiers. MMR exists in the vector DB and in a LangChain helper, but see the Qdrant caveat in card E.
- **Decision:** ☐

## P. LLM choice and structured output

- **Idea:** one hosted multimodal LLM with structured output for three online steps (intent, query expansion, batched explanation) and two offline jobs.
- **Options for structured output:** the orchestrator's built-in structured output; Instructor (MIT, validation retries); Pydantic AI (MIT); Outlines (Apache-2.0).
- **Open:** a per-query cost model for the three online calls against the $0.05 cap; whether query expansion earns its call.
- **Decision:** ☐

## Q. Interface (UI)

- **Need:** chips, three tiers, grouping by garment, outbound links.
- **Options:** Streamlit (Apache-2.0; pills widget supports multi-select chips; quickest); Next.js + shadcn/ui (MIT; production path); thin demo page over the API.
- **What we know so far:** no reusable shop-the-look UI exists. Search-UI kits (InstantSearch etc.) are index-centric and fit poorly with a pre-ranked, pre-grouped API response.
- **Decision:** ☐

## R. Evaluation and tracing

- **Evaluation:**
  - ranx (MIT) for metrics and significance tests; last release 2025-08-07, so test it against your Python/NumPy versions.
  - Marqo's `eval.py` (Apache-2.0, 7 datasets); HopitAI's `Moda` benchmark folder (MIT, self-published).
  - LLM-judge prompt ideas from published e-commerce work; no mature permissive package.
  - Build a human recall set: a judge only sees what was returned.
- **Tracing:** Langfuse core is MIT; the `ee/` folders are a separate licence (RBAC, SCIM, audit logs, data masking, retention). Self-hosting needs Postgres, ClickHouse, Redis and S3. Managed cloud is an option (pricing not researched). Whether tracing propagates through parallel fan-out branches was **not tested**.
- **Decision:** ☐

## S. Sequencing

- **Idea:** start the **retailer and catalog layer first**; it is the biggest gap and the biggest Gate 1 risk. Build an eval set for each unproven piece (retailer extraction, photo+text, outfit decomposition) before tuning anything.
- **Rough plan (inference, not sourced):**

| Week | Focus |
|---|---|
| Day 1 | Licence requests; pick country; classify candidate retailers (Shopify / affiliate / crawl-only) |
| 1 | Skeleton, vector DB, tracing, licence register; start the eval set |
| 1-3 | Retailer adapters, canonical model, compliance layer, nightly job |
| 2-3 | Embeddings, hybrid retrieval, weights from config; ablation switch per stage |
| 3-4 | Detection, masks, colour; pilot on outfit photos |
| 4 | Photo+text, tagging |
| 5 | Tiers, dedup, diversity, optional rerank, UI |
| 6 | Eval run, judge calibration, hardening, cut list |

- **Decision:** ☐

## T. Development data before real crawls

| Dataset | Preliminary licence reading |
|---|---|
| DeepFashion | Non-commercial research (verified on the official page) |
| DeepFashion2 | No licence file; terms unverified; evaluation only |
| H&M (Kaggle), Fashion-Gen | Non-commercial per secondary sources |
| Amazon Reviews 2023 | HF card states no licence |
| Marqo-GS-10M, fashion200k | Apache-2.0 declared on HF cards |
| Fashionpedia | CC-BY-4.0 on HF card (images follow source-platform terms) |
| Kaggle Fashion Product Images | MIT, declared by uploader |

Uploader labels may not clear the rights to underlying retailer images, and none has live prices or stock. Use for development and evaluation only, never in shipped features.

## U. Reference-only repos (do not copy code until licensed)

| Repo | Problem | Idea worth taking |
|---|---|---|
| `TanyaChan516/fashion-visual-search` | No licence | Detect, review, segment, embed, rerank flow; eval design |
| `EternalSol1tude/multimodal-fashion-rag` | No licence | Dense + sparse + RRF + cross-encoder layout; tests and observability scaffolding |
| `qdrant-labs/demo-ecommerce-search` | No licence; text-only | Formula weights, LLM relevance judge, "embed title plus category" lesson |
| NVIDIA `retail-shopping-assistant` | Conflicting licences; demo-only catalog | Planner graph shape; price-filter refinement behaviour |
| `qdrant/demo-hnm`, `qdrant/demo-food-discovery` | No licence | Positive / negative image queries |
| Several Streamlit / shop-the-look repos | No licence | Small UI and flow ideas |
| CIR repos (LDRE, OSrCIR, SPRC) | No licence | Method ideas only |

## V. Licence red flags to check before adopting anything

| Flag | Why |
|---|---|
| Ultralytics YOLO (AGPL-3.0), YOLO-World (GPL-3.0), Firecrawl core (AGPL-3.0), nodriver / zendriver (AGPL-3.0), undetected-chromedriver (GPL-3.0), Elasticsearch (AGPL/SSPL/ELv2), Typesense (GPL-3.0) | Copyleft or source-available terms in a hosted product |
| SAM 3 (custom gated), GR-Lite's DINOv3 base (custom gated), NVIDIA models (custom), Qwen2.5-VL-3B (research licence), Gemma 3 (custom) | Custom or gated terms need a named legal approver |
| jina-reranker-m0, SEARLE, LinCIR, Patronus Lynx | CC BY-NC (non-commercial) |
| ModaNet-trained weights | Annotations are non-commercial; effect on derived weights unresolved |
| Crawl4AI | Apache-2.0 plus attribution notice |
| Langfuse `ee/` | Separate enterprise licence |
| `langgraph-api` (Elastic-2.0), LangServe (custom), Meilisearch (MIT + BUSL parts), RF-DETR "Plus" models | Hidden non-OSI terms behind familiar names |
| Research-only datasets (see card T) | Never train or ship on them |

Keep a one-page **licence register** from week 1: component, version, licence text link, who approved, date.

## W. Parking lot (post-POC, not scope)

- Learn weights from real click-through instead of hand labels.
- Use live search at query time for long-tail retailers.
- Outfit completion ("what goes with this").
- Return-rate or fit feedback loop for size confidence.
- Affiliate monetisation and outbound-link analytics.

## X. Decisions the research lead must make at Gate 1

| # | Decision | Needs evidence from | Decision | Reason | Date |
|---|---|---|---|---|---|
| 1 | Fork vs assemble (card A) | Licence replies, effort comparison | | | |
| 2 | Orchestrator (B) | Skeleton comparison | | | |
| 3 | Visual embedding model (C) | D2 bake-off | | | |
| 4 | One embedding model or two; which (D) | D2 bake-off | | | |
| 5 | Vector store (E) | Hybrid vs single-signal results | | | |
| 6 | Photo+text composition method (F) | Own composed-query set | | | |
| 7 | Keep or drop the reranker (G) | D2 bake-off | | | |
| 8 | Detector and masking approach (H) | Outfit pilot | | | |
| 9 | Tagging model and hosting (J) | Labelled bake-off, cost per 1,000 | | | |
| 10 | Retailers and extraction methods (K) | D3 extraction benchmark | | | |
| 11 | LLM and structured-output approach (P) | Per-query cost model | | | |
| 12 | UI approach (Q) | Product owner answer on demo needs | | | |
| 13 | Which licences are acceptable (V) | Legal | | | |
