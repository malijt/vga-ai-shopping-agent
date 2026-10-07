# PRD: AI Fashion Shopping Agent (1-day demo)

Status: Draft v0.2, simplified · 2026-10-07 · Upstream: [01-business-requirements.md](01-business-requirements.md)

This file says what the demo does. It does not pick libraries; see [03-proposed-ideas.md](03-proposed-ideas.md).

## How it works

```
photo and/or text
      │
1. Understand   one LLM call → what to look for (category, colour, style, gender, budget, search keywords)
      │
2. Search       visit each store's SEARCH page in parallel → product cards (title, price, image, link)
      │
3. Rank         score every product against the request
      │
4. Show         top 30 split into Budget / Mid / Premium / Luxury by your % mix, max 6 per store, link to store page
```

**Key point:** we visit about 5-6 store **search pages**, not 60 product pages. A search page already lists 20-50 products with price, image and link.

## Inputs

| Input | What happens |
|---|---|
| Product photo | LLM describes the item; search by keywords; rank by image similarity too |
| Outfit photo | LLM lists each garment (top, outerwear, bottoms, shoes); one search per garment; results grouped by garment |
| Text | LLM turns it (English or Arabic) into English search keywords and filters |
| Photo + text | Photo gives the look; text gives filters and changes ("dark brown", "cheaper", "under 300 AED") |

## Requirements

| # | Requirement |
|---|---|
| R1 | Accept an image, text, or both. Reject other input with a clear message. |
| R2 | One LLM call returns structured JSON: per item, category, colour, style, material, gender, plus budget and 2-3 English search keyword variants. |
| R3 | Show what the system understood as **editable chips** (category, colour, gender, budget). Editing re-runs the search. Gender is never applied silently. |
| R4 | Each store is one small config entry: country, search URL template, how to read products, rate limit. Adding a store = adding config. |
| R5 | Search all stores in parallel. **6 s timeout per request**; a slow or blocked store is skipped and logged, never blocks the rest. |
| R6 | Every product has: title, price, currency, image URL, product URL, store. Drop products missing any of these. |
| R7 | Keep only products matching hard filters (category, budget if given, in stock if the card says so). |
| R8 | Rank by a simple score: how well the title/attributes match the request, plus image similarity when the request has a product photo, plus price fit. Weights in one config file. |
| R9 | Show at most 6 results per store so one store cannot take over. |
| R10 | Each result card: image, title, store, price + currency, colour if known, short reason, "View product" link. |
| R11 | The reason sentence may only use facts the code knows (colour matched, within budget, store). If unsure, show a plain template. |
| R12 | Log time per step and per store, so we can see where the seconds go. |
| R13 | Split the final list into 4 price ranges: Budget, Mid-range, Premium, Luxury (see "Price ranges and the final list"). |
| R14 | The share of each range is a setting (`tier_mix`, percentages that sum to 100). |
| R15 | Inside each range, show the best-matching products first. |
| R16 | Show each range's real price span and result count in the UI, for example "Budget · 45-139 AED · 8 results". |

## Settings (one config file)

`country` (default UAE), `stores`, `results` (30), `max_per_store` (6), `timeout_s` (6), `rps_per_store` (1), `tier_mix` (25/25/25/25), ranking weights.

## Price ranges and the final list

**Two separate knobs:** where the range borders sit, and how many results come from each range.

**1. Range borders (proposed default).** After the search, take all candidates for one garment category and sort by price. Cut at the quartiles: cheapest 25% = Budget, next 25% = Mid-range, next 25% = Premium, top 25% = Luxury. The borders adjust to what the stores actually sell, so a t-shirt search and a coat search get different price ranges. The UI shows the real span of each range.

**2. Mix (how many results per range).** Percentages in `tier_mix`; counts use rounding that always sums to the total (ties go to the cheaper range).

| Preset | Budget / Mid / Premium / Luxury | Results out of 30 |
|---|---|---|
| Even (default) | 25 / 25 / 25 / 25 | 8 / 8 / 7 / 7 |
| Value first | 40 / 30 / 20 / 10 | 12 / 9 / 6 / 3 |
| Luxury first | 10 / 20 / 30 / 40 | 3 / 6 / 9 / 12 |

**Rules**
- Fill each range with its best-matching products, max 6 per store overall.
- If a range has too few products, fill the gap from the nearest range and flag "few options in this range". Never fill with products below the minimum match score; return fewer instead.
- If the user gives a budget: Budget and Mid-range must be within it. Premium and Luxury may go over and are labelled "over budget".
- Outfit photo: each garment gets its own list with the same mix (default 12 results per garment).

**Example (illustration only, jacket search in UAE)**

| Range | Share | Price span found | Results |
|---|---|---|---|
| Budget | 25% | 45-139 AED | 8 |
| Mid-range | 25% | 140-299 AED | 8 |
| Premium | 25% | 300-699 AED | 7 |
| Luxury | 25% | 700-2,400 AED | 7 |

**Limit:** borders come from this search's candidates, not the whole market. If no luxury store is among the working stores, "Luxury" only means "most expensive found". The UI price span makes that visible.

## If something fails

| What fails | What happens |
|---|---|
| LLM call | Use the raw text as the search keywords |
| One store | Skip it, log it, show results from the others |
| All stores | Show "no results right now" with the reason |
| Image similarity | Rank by text/attribute match only |

## Time (estimate, not measured)

| Step | Expected |
|---|---|
| Understand (LLM) | 1-3 s |
| Search 5-6 stores in parallel | 3-8 s |
| Rank (incl. image similarity on about 30-50 thumbnails) | 2-8 s |
| Price ranges and mix | under 0.1 s |
| **Total** | **about 10-20 s** (limit for the demo: 30 s) |

An outfit photo with 4 garments needs about 4× the search pages: about 6-10 s for the search step (formula estimate, not simulated).

## Acceptance test (10 queries)

| Type | Count | Example |
|---|---|---|
| Product photo | 3 | A phone photo of a jacket |
| Outfit photo | 2 | A mirror selfie |
| Text | 3 | "black oversized blazer for men under 400 AED"; one in Arabic |
| Photo + text | 2 | Jacket photo + "similar but dark brown and cheaper" |

**Pass:** for most of the 10 queries: ≥ 20 results, from ≥ 3 stores, ≤ 30 s, all links open the right product page, and a person marks ≥ 7 of the top 10 as good matches (same category, close colour/style), and each price range is within 1 result of its target count (or flagged "few options"). Record the results in a short table, plus every failure.

## Open questions

1. Is input type (product vs outfit photo) detected automatically? Proposed: yes, the LLM decides.
2. Arabic text only for the LLM step, with English store search. Is that enough?
3. Show price in each store's currency only? (Proposed: yes, UAE first so AED.)
4. Is the even 25/25/25/25 default mix right, and are quartile borders from this search acceptable, or do you want fixed AED bands per category?
