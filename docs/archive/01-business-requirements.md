# AI Fashion Shopping Agent: High-Level Business Requirements

| | |
|---|---|
| Status | Draft v0.1, for review |
| Date | 2026-10-07 |
| Audience | Product owner, legal, engineering, research lead |
| Companion docs | [02-prd.md](02-prd.md) (what to build), [03-proposed-ideas.md](03-proposed-ideas.md) (options, not decisions) |

> **How to read this set.** This file says *why* and *within what limits*. The PRD says *what the product must do*. The ideas file lists *possible ways to build it*. Nothing about technology is final: the research lead decides, with evidence, at Gate 1 (end of week 2).

---

## 1. Purpose

Prove, in 6 weeks, that one pipeline can turn a **photo, a text request, or both** into a **ranked, price-tiered list of real products** from 5-10 real retailers in one market, each linking to the retailer's own product page.

The POC exists to answer a go/no-go question: *is this good enough, cheap enough and legally clean enough to scale to 20-30 retailers (Phase 2) and 50-60+ (Phase 3)?*

## 2. Problem

- A shopper who sees an outfit they like, or can describe one, must search retailer by retailer. Each site has different search, filters, naming and sizing.
- Keyword search misses visual intent ("this jacket, but dark brown"). Image-only tools ignore budget, size and availability.
- Comparing price and fit across retailers is slow, so shoppers give up or overpay.

## 3. Business objectives

| # | Objective | How we know |
|---|---|---|
| O1 | Prove the end-to-end flow: understand, retrieve, extract, match, rank, diversify, present | All four input modes work and meet the "Must" thresholds in the PRD |
| O2 | Prove retailer access is viable in the chosen market | At least 5 retailers qualify in the extraction benchmark; otherwise stop at Gate 1 |
| O3 | Prove unit economics | LLM spend ≤ $0.05 per query; runs on one 24 GB GPU server plus CPU workers |
| O4 | Build a base that scales by configuration | A new retailer is one config file plus, at most, one small class |
| O5 | Give decision-makers evidence, not opinions | One eval script on a frozen index produces every reported number |

## 4. Stakeholders and roles

| Role | Responsibility |
|---|---|
| Product owner | Names the market and currency at kickoff; approves scope; owns the go/no-go at Gate 2 |
| Legal | Approves retailer access rules, dataset use, and every component licence before it ships |
| Research lead | Decides technology choices from evidence (see §11); owns deliverables D1-D4 |
| ML engineer | Vision, embeddings, ranking, evaluation |
| Backend engineer | Retailer adapters, indexing, API, infra |
| Annotators (2, plus a tie-breaker) | Label 50 queries; calibrate the automated judge (about 1 person-day each) |
| Retailers (external) | Not stakeholders in the POC, but their terms and robots.txt bind us |

## 5. Target users and needs (high level)

| User | Need |
|---|---|
| Shopper with a product photo | "Find this item, or very close, at real shops" |
| Shopper with an outfit or mirror photo | "Find every piece of this look, grouped by piece" |
| Shopper with only words | "Black oversized blazer for men under $100" |
| Shopper refining a photo | "Like this, but dark brown and cheaper" |
| All shoppers | Trust the result: current price, real stock, honest reason, easy click-through to buy |

## 6. Scope

**In scope**
- Four input modes: product photo, outfit/person photo, text, photo + text.
- Categories: tops, outerwear, bottoms, footwear.
- 5-10 real retailers in **one country and one currency**.
- Up to 60 results, split into budget / mid-range / premium tiers.
- Result cards that link to the original retailer product page.

**Out of scope for the POC**
- Add-to-cart and checkout.
- Estimating body size from photos (never done, by policy).
- Accessories.
- User accounts and history.
- More than 10 retailers.

## 7. Business requirements

| ID | Requirement | Priority |
|---|---|---|
| BR-01 | User flow is discover, compare, redirect. Every result's URL points to the **original retailer's** product page. | Must |
| BR-02 | All four input modes work end to end. | Must |
| BR-03 | Return up to 60 results, split into three price tiers with a configurable ratio (for example 20/20/20, 10/30/20, 30/20/10). | Must |
| BR-04 | One market and one currency, named by the product owner at kickoff. | Must |
| BR-05 | Results come from 5-10 real retailers; at least 5 are searched successfully per query. | Must |
| BR-06 | Show how fresh price and stock are. Re-check them live for the shortlist before display. | Must |
| BR-07 | Explanations and scores must be honest: a reason sentence may only state facts the system verified, and a match percentage must be calibrated or shown as a band. | Must |
| BR-08 | The user stays in control: detected attributes are visible and editable; gender or presentation is never applied silently; body size is only what the user enters. | Must |
| BR-09 | Respect retailer access rules: feeds and APIs first, robots.txt honoured, no login-walled pages, no CAPTCHA solving. | Must |
| BR-10 | Every software component and model is licensed for commercial use, with the licence and pinned version recorded. Evaluation-only datasets are never used to train a shipped model. | Must |
| BR-11 | Cost: ≤ $0.05 LLM spend per query. Hosting: one GPU server with 24 GB VRAM plus CPU workers. | Must |
| BR-12 | Adding a retailer needs only a config file plus, at most, one small class, with no change to ranking or agents. | Must |
| BR-13 | All reported metrics come from one script against a frozen index snapshot, so runs are comparable over time. | Must |
| BR-14 | Delivered in 6 weeks by one ML engineer and one backend engineer, with a go/no-go at Gate 1 after week 2. | Must |
| BR-15 | Every ranked result can be traced to a score breakdown. | Should |

## 8. Constraints

- **Time and team:** 6 weeks, two engineers.
- **Hardware:** one 24 GB GPU server for embeddings and detection; CPU workers for crawling.
- **Cost:** ≤ $0.05 per query for LLM spend (stretch ≤ $0.02).
- **Legal:** retailer terms, robots.txt, dataset licences and component licences all bind us (see BR-09, BR-10).
- **Principle carried from the original brief:** the LLM understands the request and writes explanations; code and embedding models decide what is shown and in what order. The research lead may challenge this at Gate 1 with a written reason.

## 9. Success criteria (business level)

The POC is accepted at **Gate 2 (end of week 6)** only if every "Must" threshold in the [PRD §9](02-prd.md) is met on the held-out test set. Headline targets:

- Precision@10 (relevant or partial) ≥ 0.70, NDCG@20 ≥ 0.60.
- 100% of results carry title, image, price, retailer and URL; broken-URL rate ≤ 2%.
- ≥ 30 useful products returned where available; ≥ 5 sources searched per query.
- p50 / p95 latency ≤ 8 s / 15 s on the pre-indexed path; cost ≤ $0.05 per query.
- A majority of the top 10 judged relevant for ≥ 80% of queries.

## 10. Phasing

| Phase | Retailers | Gate |
|---|---|---|
| Phase 1 (this POC) | 5-10, one market | Gate 1 after week 2 (research sign-off); Gate 2 after week 6 (acceptance) |
| Phase 2 | 20-30 | Only after Gate 2 |
| Phase 3 | 50-60+ | Only after Phase 2 |

**Gate 1 can stop the project** if fewer than 5 retailers can be extracted reliably in the chosen market. The fallback is to choose a different market or add affiliate feeds before building.

## 11. How technology decisions are made

The original brief fixed a stack. **That is relaxed for this document set.**

- The research lead decides which components to use, and which to drop, based on measured results on our own catalog and queries.
- Public benchmarks are sanity checks only. Our own crawled catalog and the 150 test queries decide.
- Any choice needs: a recorded licence and pinned version, a measured result, and a written reason. Gate 1 signs off the set.
- [03-proposed-ideas.md](03-proposed-ideas.md) lists candidates and evidence gathered so far. It is input to that decision, not the decision.

## 12. Assumptions

- A single market can supply at least 5 retailers with extractable data.
- A hosted multimodal LLM with structured output is available and its cost fits the budget.
- Real user-style photos (phone shots, mirror selfies) can be collected or sourced for the test set.
- Retailers' public product data can be used for discovery and redirect under their terms. **Legal must confirm.**

## 13. Dependencies and handover checklist

- [ ] Product owner names the market and currency
- [ ] Legal approves retailer access rules, evaluation-only use of any restricted dataset, and any custom-licence model
- [ ] GPU server and LLM API key provisioned; cost alerts set
- [ ] Two annotators booked to label 50 queries and calibrate the judge
- [ ] Repo created with config files for weights, distribution and diversity limits

## 14. Risks

| Risk | Impact | Required mitigation |
|---|---|---|
| Retailers block crawlers or rate-limit | Fewer than 5 usable sources | Qualify retailers in week 1; prefer feeds and APIs; cache; per-retailer rate limits |
| Fewer than 5 retailers qualify | Project cannot proceed | Stop at Gate 1; change market or add affiliate feeds |
| Live crawling too slow | Latency misses | Index nightly; live calls only refresh price and stock for the shortlist |
| Vision mislabels category or colour | Wrong results | Confidence on every attribute; editable chips; category re-checked against user text |
| Price or stock changes after indexing | Broken trust | Refresh before display; show "price checked at" time |
| Public benchmarks mislead model choice | Wrong models | Decide on our own catalog |
| Licence problems in a component, model or dataset | Cannot ship commercially | Licence register from week 1; legal review before use |
| Uploaded photos may contain people (faces) | Privacy exposure | See open item on photo handling in §15 |

## 15. Open items for the business

1. **Target country and currency** (the only open input in the original brief).
2. **Monetisation model**, if any (affiliate links, referral fees). Not in the brief; it affects which retailer programmes we can join and how links are tracked.
3. **Privacy of uploaded photos:** retention period, whether faces are processed or stored, and the legal regime of the chosen country. Not in the brief; added here for review.
4. **Languages** the POC must support in text queries.
5. **Retailer shortlist** and who approaches each affiliate programme.
6. **Who approves a custom-licence component** (legal contact and turnaround).
