# Business Requirements: AI Fashion Shopping Agent (1-day demo)

Status: Draft v0.2, simplified · 2026-10-07 · Replaces the long v0.1 (kept in `archive/`)

Read in order: this file (why) → [02-prd.md](02-prd.md) (what) → [03-proposed-ideas.md](03-proposed-ideas.md) (how, options only).

## Goal

One phase, one day. A shopper gives a **photo, text, or both**. The system visits several **GCC online fashion stores** and returns the **best-matching products**. Each result links to the store's own product page.

## Why

Shoppers search store by store. We want one search across stores that understands a photo or a short description.

## Who

A shopper in the GCC. Text can be English or Arabic.

## In scope

- Inputs: product photo, outfit photo, text, photo + text ("like this but dark brown, under 300 AED").
- Categories: tops, outerwear, bottoms, shoes, **and dresses** (dresses, gowns, kaftans, abayas, kurtas and similar one-piece or ethnic garments). Dresses were added on 2026-10-08 by the business: every test photo it supplied shows a dress or ethnic wear.
- Up to 10 GCC stores, **UAE sites first**. The limit was 6 until 2026-10-08, when the business raised it: with dresses in scope, six stores cannot cover both menswear and dresses.
- Top 30 results, with price in the store's currency and a link to the store's product page.
- **Final list split by price into 4 ranges: Budget, Mid-range, Premium, Luxury, with a percentage mix** (for example 25 / 25 / 25 / 25, or value-first 40 / 30 / 20 / 10). The mix is a setting.
- Optional budget filter.

## Out of scope

Cart and checkout, accounts, accessories, guessing body size from photos, nightly catalog crawling, score calibration, duplicate merging, more than 10 stores.

## Rules (not negotiable)

1. Every result links to the **original store's product page**.
2. Respect robots.txt. No login-walled pages. No CAPTCHA solving. Low request rate (about 1 per second per store).
3. Never guess body size from a photo.
4. Do not keep uploaded photos after the request.
5. Use only components with commercial-friendly licences.
6. This is a **demo**. Before real users, someone checks each store's terms of use and any affiliate programme.

## Success (demo passes if)

On 10 test queries, the system returns **at least 20 results from at least 3 stores in 30 seconds or less, with working links**, and a person judges **7 or more of the top 10 as good matches on most queries**. The final list also follows the price mix: each range is within 1 result of its target, or flagged as thin. Exact test in the PRD.

## Decisions needed from the business

| # | Question | Default if no answer |
|---|---|---|
| 1 | Which country first? | UAE |
| 2 | Which stores (up to 10)? | Shortlist in the ideas file (unverified); pick the ones that work in the first hour |
| 3 | Which LLM and API key? | Any hosted multimodal LLM with structured output |
| 4 | Is a simple web page enough for the demo? | Yes |
| 5 | Money plan (affiliate links)? | Not in this demo |
| 6 | Default price mix? | Even: 25% Budget / 25% Mid-range / 25% Premium / 25% Luxury |
