# AI Fashion Shopping Agent: Product Requirements Document (POC)

| | |
|---|---|
| Status | Draft v0.1, for review |
| Date | 2026-10-07 |
| Upstream | [01-business-requirements.md](01-business-requirements.md) |
| Downstream | [03-proposed-ideas.md](03-proposed-ideas.md) |

> **Technology-neutral on purpose.** This PRD states behaviour, data and acceptance. It does not pick libraries or models. Component choices belong to the research lead at Gate 1 (see [BRD §11](01-business-requirements.md)). Where the original brief named a component, the ideas file carries it as a candidate.

---

## 1. Summary

A user uploads a photo, types a request, or both. The system returns up to 60 products from 5-10 real retailers in one market. Results are ranked, split into budget / mid-range / premium tiers (and grouped by garment for outfit photos), and each links to the retailer's own product page.

**Pipeline the POC must prove:** understand, retrieve, extract, match, rank, diversify, present.

## 2. Goals and non-goals

**Goals**
- Four input modes working end to end.
- Results a human would call relevant (see §9).
- Honest scores and reasons, traceable to a score breakdown.
- Retailers added by configuration.

**Non-goals (POC)**
- Cart, checkout, accounts, history.
- Body-size estimation from photos.
- Accessories.
- More than 10 retailers.

## 3. Personas and top journeys

| Persona | Journey |
|---|---|
| **Product-photo shopper** | Uploads a photo of one item, sees similar items in three price tiers, clicks "View product" |
| **Outfit shopper** | Uploads a mirror selfie, sees results grouped by detected garment (top, outerwear, bottoms, shoes) |
| **Text shopper** | Types "black oversized blazer for men under $100", edits detected chips, sees results |
| **Refiner** | Uploads a jacket photo and types "similar but dark brown and cheaper"; photo drives look, text sets filters and changes |

## 4. User stories (acceptance in §9)

- As a shopper, I can search with a photo, text, or both, so I can describe what I want however is easiest.
- As a shopper, I can see and edit what the system understood (category, colour, gender, others), so I can fix mistakes without retyping.
- As a shopper, I can enter my size or measurements once, so results show whether my size is in stock.
- As a shopper, I see budget, mid-range and premium options with each tier's price range, so I can compare.
- As a shopper, I see when the price was last checked and a link to the retailer, so I can trust and act on it.
- As a shopper, I get a one-line reason per result that is actually true.
- As an operator, I can add a retailer with a config file, so we can scale to Phase 2.
- As an evaluator, I can re-run one script on a frozen index and get comparable metrics.

## 5. Functional requirements

### 5.1 Input and understanding

| ID | Requirement |
|---|---|
| FR-01 | Accept an image, text, or both. Validate type and size; reject unsupported input with a clear message. |
| FR-02 | Distinguish a single-product photo from an outfit/person photo. (How: automatic, or user choice, is an open question.) |
| FR-03 | For outfit photos, detect each visible garment in the four categories. Each garment becomes its own search, run in parallel, and results are grouped by garment. If detection fails, treat the whole image as one item. |
| FR-04 | Extract attributes per item: category, colour, pattern, material, style/fit, season, gender presentation. **Every attribute carries a confidence score.** |
| FR-05 | Colour from garment pixels (perceptual colour space, mapped to a fixed colour-name palette) overrides the vision model's colour when they disagree. |
| FR-06 | Parse text into a structured search spec: hard filters (price, category, gender, colour, size) and attribute overrides. If parsing fails, use the raw text as the query. |
| FR-07 | **Photo + text:** the photo supplies visual similarity; the text supplies filters and overrides. "Dark brown" replaces the photo's colour in attribute match. "Cheaper" means max price = 0.8 × the reference product's price when a reference is identified, otherwise the lower half of the candidate price range. |
| FR-08 | Show detected attributes as **editable chips**. Editing re-runs the search. Low confidence lowers that attribute's ranking weight. Gender/presentation is inferred, shown as a chip, and **never applied silently**. |
| FR-09 | Size: the user may enter known size or measurements (height, chest, waist, hip, shoe size, preferred fit). **Never infer body size from a photo.** If size matters and is unknown, ask once. |

### 5.2 Catalog (nightly, offline)

| ID | Requirement |
|---|---|
| FR-10 | Ingest each retailer nightly into the common **product record** (§7.2). Drop records missing title, price, image or URL. |
| FR-11 | Each retailer is defined by one config file plus, at most, one small class. Extraction methods are tried **cheapest first**; an LLM or browser agent is the last resort. Order in the brief: feed/API, embedded page data, CSS/XPath schema, LLM extraction, browser agent. |
| FR-12 | Respect robots.txt; no login-walled pages; no CAPTCHA solving; per-retailer rate limit in config. |
| FR-13 | Validate extracted price against the visible page price on a 5% sample (stale markup guard). |
| FR-14 | Enrich every new or changed product image once into a fixed vocabulary: category, subcategory, colour family, pattern, fit, length, collar/neckline, material appearance, season. Cross-check colour with pixel colour. Re-tag only when the image URL hash changes. Report tagging cost per 1,000 products. |
| FR-15 | Normalise: category mapped to the four, colours to the palette, sizes to **one internal scale per category** (for example chest cm for tops, EU for shoes), with per-brand tables where size charts exist. Output size confidence (high / medium / low), never a guarantee. |
| FR-16 | Index must support similarity search, keyword search and filters (market, category, in-stock, price cap) together. |
| FR-17 | Compute price-tier boundaries per category over the full indexed catalog for the market, refreshed nightly. |

### 5.3 Retrieval, ranking and shaping (online)

| ID | Requirement |
|---|---|
| FR-18 | Per item, retrieve candidates using several independent signals (visual similarity to the query crop, text or photo+text meaning, keyword match), each with the same hard filters, then merge by rank so no single signal dominates. Candidate counts and the merge method are tunable. |
| FR-19 | Score the merged candidates with a deterministic, config-driven weighted sum (each component normalised to 0-1, minus a duplicate penalty). Starting components and weights are in §6. Weights live in a config file and are tuned on the labelled set, not by hand. |
| FR-20 | An optional rerank stage on the top candidates, switchable by config. If it does not earn its place in the bake-off, the pipeline runs unchanged without it. |
| FR-21 | **Live refresh:** re-check price and stock for the shortlist (about the top 150) before display. 6 s timeout per retailer; on timeout skip and log, never block the batch. Out-of-stock items are dropped from the final list. |
| FR-22 | **Deduplicate** in this order, stopping at the first match: (1) same canonical URL or GTIN/SKU; (2) same brand + title similarity ≥ 0.9 + image similarity ≥ 0.95 → same product at a different retailer, keep the cheapest in-stock offer and list others as "also at"; (3) same brand + title ≥ 0.9 + image similarity 0.85-0.95 → colour/size variant, keep one and show swatches; (4) otherwise distinct. Thresholds are starting values to tune on 200 hand-labelled pairs. |
| FR-23 | **Price tiers** use category-aware percentiles, never fixed currency thresholds: budget 0-30th, mid-range 30-70th, premium 70-100th. If the user states a budget, budget and mid-range must be within it; premium may exceed it and is labelled "over budget". Show each tier's price range in the UI. |
| FR-24 | **Distribution** is configurable (integers summing to the total, e.g. 20/20/20). If a tier has too few candidates, refill from the nearest tier and flag it in the response. |
| FR-25 | **Diversity:** fill each tier with a relevance-vs-novelty method (starting λ = 0.7 relevance, 0.3 novelty; novelty = 1 − max image similarity to items already picked). Limits, all config: max 3 per retailer, max 2 per dedup cluster, min 4 retailers across the 60. |

### 5.4 Presentation and explanation

| ID | Requirement |
|---|---|
| FR-26 | Each result card shows: image, title, brand, retailer; price, original price and discount if present, currency; available sizes with size-fit confidence; colour (and material if known); rating and review count; match score; one-sentence reason; time price was checked; a "View product" link to the retailer. |
| FR-27 | Cards are grouped by tier, and by garment for outfit photos. |
| FR-28 | **Match score** shown as a percentage must be a **calibrated relevance probability** (fitted on the tuning queries). If calibration fails the threshold in §9, show a band (Strong / Good / Partial) instead of a number. A visual-match number, if shown, uses the same calibrated mapping, never a raw similarity. |
| FR-29 | **Reason sentence:** the LLM receives only a fact sheet built by code (top 2-3 score components and their verified values) and may add no other claim. A validator checks every sentence: each colour, size, price or attribute word must match a fact-sheet field; "within budget" requires price ≤ budget; "your size" requires size match = 1; any failure replaces the sentence with a fixed-wording template. Reasons never mention a component that scored below 0.5. |
| FR-30 | API returns, per result, the **score breakdown** so every position can be explained. |

### 5.5 Operations and quality

| ID | Requirement |
|---|---|
| FR-31 | Every LLM call is traced with latency and cost, per query. |
| FR-32 | Weights, distribution, diversity limits and per-retailer settings live in config files. |
| FR-33 | One eval script computes all metrics against a frozen index snapshot and writes a comparable report. |
| FR-34 | Degrade gracefully (table below). |

**Failure behaviour**

| Component | On failure |
|---|---|
| Intent parsing | Use raw text as the query |
| Vision / detection | Treat the whole image as one item |
| Query expansion | Use the single original query |
| A retailer's live refresh | Skip and log; never block the batch |
| Extraction (nightly) | Drop records missing title, price, image or URL |
| Ranking / tiering | Return fewer results with a reason |
| Explanation | Template text from the top two score components |

## 6. Ranking score: starting point

Weights are **starting values**, to be tuned on the labelled tuning set.

| Component | Start weight | Meaning |
|---|---|---|
| Visual similarity | 0.30 | Query crop vs product image |
| Text relevance | 0.20 | Query meaning vs product title + image, plus keyword match on title |
| Attribute match | 0.15 | Share of extracted attributes that match, weighted by confidence |
| Category match | 0.10 | 1 same, 0.5 adjacent (coat vs jacket), 0 otherwise; also a hard pre-filter |
| Size compatibility | 0.10 | 1 if size in stock; 0.5 if unknown; 0 if known and absent |
| Price fit | 0.05 | 1 inside budget, decaying to 0 at 1.5× budget |
| Quality | 0.05 | Smoothed rating × log(review count) |
| Availability | 0.05 | 1 in stock, 0 out of stock (also dropped from the final list) |

If a rerank stage is kept, its score replaces text relevance.

## 7. Data contracts (baseline interfaces)

These are the interfaces between components. The research lead may propose changes at Gate 1; once frozen, every adapter and agent must produce exactly these fields.

### 7.1 Search spec (intent + vision output)

```json
{
  "items": [{
    "category": "jacket",            "category_conf": 0.93,
    "style": ["oversized", "casual"], "color": ["beige"], "color_conf": 0.81,
    "material": ["wool"],            "pattern": "solid",
    "image_embedding_id": "q123-crop0"
  }],
  "season": "winter",
  "gender": "male", "gender_source": "inferred",
  "budget": {"currency": "USD", "max": 150},
  "size": {"label": "M", "chest_cm": 102, "source": "user"},
  "text_overrides": {"color": ["dark brown"], "price": "cheaper"},
  "distribution": {"total": 60, "budget": 20, "mid_range": 20, "premium": 20}
}
```

### 7.2 Product record (adapter output)

| Field | Type | Required |
|---|---|---|
| product_id, retailer_id, product_url, image_url | string | Yes |
| title | string | Yes |
| brand | string | If shown |
| price, currency | number, ISO code | Yes |
| original_price | number | If shown |
| category (mapped to our 4), color, material | string | Category yes |
| available_sizes | list, raw + normalised | If shown |
| rating, review_count | number | If shown |
| availability | in_stock / out_of_stock / unknown | Yes |
| gtin_or_sku | string | If shown |
| source_method | feed / jsonld / css / llm / browser | Yes |
| fetched_at, extraction_confidence | timestamp, 0-1 | Yes |

### 7.3 Distribution config

```csv
total_results,budget,mid_range,premium
60,20,20,20
60,10,30,20
60,30,20,10
```

### 7.4 Retailer adapter config (illustrative)

```yaml
retailer_id: example_store
market: US
currency: USD
method: jsonld            # feed | jsonld | css | llm | browser
search_url: https://example.com/search?q={query}
listing_selector: ...     # only for css
rate_limit_rps: 1
needs_js: false
robots_ok: true
fields_map: {...}         # retailer field -> common schema field
```

## 8. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | End-to-end latency, pre-indexed path | p50 ≤ 8 s, p95 ≤ 15 s (stretch 4 s / 8 s) |
| NFR-02 | Cost per query (LLM + infra, excluding crawl) | ≤ $0.05 (stretch ≤ $0.02) |
| NFR-03 | Hosting | One 24 GB GPU server for embeddings and detection; CPU workers for crawling |
| NFR-04 | Any selected embedding model | Embeds one image in ≤ 100 ms on the GPU server; all selected models fit together in 24 GB VRAM |
| NFR-05 | Freshness | Catalogs re-indexed nightly; price and stock re-checked live for the shortlist |
| NFR-06 | Compliance | Robots.txt honoured; no login walls; no CAPTCHA solving; component and dataset licences recorded and cleared |
| NFR-07 | Observability | Per-call trace of LLM latency and cost; per-query score breakdown |
| NFR-08 | Reproducibility | Frozen index snapshot; one eval script; pinned versions |
| NFR-09 | Privacy (**not in the original brief; for review**) | Uploaded-photo retention and face handling defined and legally approved before any real-user test |
| NFR-10 | Extensibility | New retailer = one config plus at most one small class |

## 9. Acceptance criteria

The POC is accepted only if every **Must** is met on the 50 held-out queries. Stretch values are goals, not acceptance.

| Metric | Must | Stretch |
|---|---|---|
| Precision@10 (relevant or partial), all query types | ≥ 0.70 | ≥ 0.80 |
| NDCG@20 | ≥ 0.60 | ≥ 0.70 |
| Category accuracy of top 20 | ≥ 0.90 | ≥ 0.95 |
| Colour / attribute accuracy of top 20 | ≥ 0.75 | ≥ 0.85 |
| Outfit photos: share of visible garments detected | ≥ 0.80 | ≥ 0.90 |
| Sources successfully searched per query | ≥ 5 | ≥ 8 |
| Useful products returned (where available) | ≥ 30 | 60 |
| Required metadata present (title, image, price, retailer, URL) | 100% | 100% |
| Broken URL rate | ≤ 2% | ≤ 1% |
| Duplicate rate in final list | ≤ 5% | ≤ 2% |
| Max products from one retailer | ≤ 3 per tier | config |
| End-to-end latency p50 / p95 | ≤ 8 s / ≤ 15 s | ≤ 4 s / ≤ 8 s |
| Cost per query | ≤ $0.05 | ≤ $0.02 |
| Human rating: majority of top 10 relevant | ≥ 80% of queries | ≥ 90% |

**Score and reason quality**

| Check | Must |
|---|---|
| Expected calibration error of match score (held-out, 10 bins) | ≤ 0.10, otherwise show bands |
| Reason claims that are factually true (audit of 200 random cards) | ≥ 98% |
| Reasons that name the actual top-weighted component | ≥ 95% |
| Human rating "reason makes sense for this product" | ≥ 90% |
| Validator fallback rate | Report; investigate if > 10% |

**Retailer qualification (per source, extraction benchmark)**

| Metric | Target to qualify |
|---|---|
| Required-field completeness (title, image, price, URL) | ≥ 95% |
| Optional-field completeness (sizes, colour, rating) | ≥ 60% |
| Price correct vs manual check | ≥ 98% |
| Blocked or CAPTCHA rate over 100 requests | ≤ 5% |
| Median fetch time per page | ≤ 3 s (HTTP), ≤ 8 s (browser) |
| Cost per 1,000 pages | Report; no target yet |

## 10. Evaluation plan

- **Test set:** 150 queries: 50 product-image, 25 outfit-photo, 50 text, 25 photo + text. Real user-style photos (phone shots, mirror selfies), not only catalog images.
- **Split:** 100 tuning, 50 held-out. Weights and thresholds are tuned only on the 100; the acceptance report uses only the 50.
- **Labels:** relevant (2), partial (1), not relevant (0), on the top 50 pooled results of every system variant.
- **Who labels:** humans label 50 queries (two annotators plus a tie-breaker). A multimodal LLM judge labels the rest, with a written rubric (category, colour, silhouette, price, instruction compliance). The judge is accepted only if Cohen's kappa vs humans ≥ 0.6; otherwise humans label everything.
- **Metrics:** computed with a standard IR metrics tool; paired significance tests when comparing variants.
- **Component bake-off decision rules** (carried from the brief, for the research lead to confirm or amend):
  1. A visual-embedding challenger replaces the default only if it beats it by ≥ 3 NDCG@20 points on product- and outfit-photo queries.
  2. Same ≥ 3-point rule for the multimodal-embedding role on text and photo + text queries.
  3. A reranker is kept only if it adds ≥ 3 NDCG@20 points overall and p95 latency stays within the limit.
  4. A winner must embed one image in ≤ 100 ms and all selected models must fit in 24 GB. A larger model may be measured as a quality ceiling only.
  5. If one model wins both roles, use it for both with a single vector.

## 11. Milestones, gates and deliverables

| Phase | Weeks | Content |
|---|---|---|
| Decide | 0 | Lock fixed requirements; pick 10 candidate retailers |
| Research | 1-2 | D1-D4 |
| **Gate 1** | end of week 2 | Research sign-off: 5+ sources qualify; component choices recorded with evidence |
| Build | 3-5 | Adapters for 5-10 sites; index and ranking; label 150 queries |
| Evaluate | 6 | Run eval script; human review; D5 demo |
| **Gate 2** | end of week 6 | POC accepted if all Musts are met |

| # | Deliverable | Due | Accepted when |
|---|---|---|---|
| D1 | Open-source landscape | End of week 1 | Licence file and pinned version recorded for every component under consideration |
| D2 | Model benchmark | End of week 2 | All embedding candidates compared on a public set and on our own catalog; winner per role and reranker decision recorded with numbers |
| D3 | Extraction benchmark | End of week 2 | 10 retailers scored on the qualification table; 5-10 picked |
| D4 | Architecture note | End of week 2 | Covers components, timeouts, retries, merge logic, and how each is evaluated |
| D5 | Working POC | End of week 6 | All four input modes work end to end; eval report meets every Must |

## 12. Open questions

| # | Question | Owner |
|---|---|---|
| Q1 | Target country and currency | Product owner |
| Q2 | Is input mode (product vs outfit photo) detected automatically or chosen by the user? | Research lead / product owner |
| Q3 | Does the POC need a real UI, or is the API plus a thin demo page enough? | Product owner |
| Q4 | Which languages must text queries support? | Product owner |
| Q5 | Photo privacy: retention, faces, jurisdiction | Legal |
| Q6 | Monetisation (affiliate tracking on outbound links)? | Product owner |
| Q7 | Are the starting score weights, thresholds and caps above acceptable, or should the research lead propose different starting points? | Research lead |
| Q8 | What is the fallback if no hosted LLM fits the cost limit? | Research lead |
| Q9 | Which licence terms are acceptable beyond the permissive ones (Apache-2.0, MIT, BSD)? Custom or gated licences need a named legal approver. | Legal |
