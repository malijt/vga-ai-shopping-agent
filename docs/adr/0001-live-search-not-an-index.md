# ADR 0001: Search store pages live, do not build an index or crawl sitemaps

- **Status:** Accepted. Decided in the approved implementation plan (v2, 2026-10-07); recorded here.
- **Date:** 2026-10-07
- **Sources:** `docs/01-business-requirements.md` (scope), `docs/02-prd.md` ("Key point"), `docs/03-proposed-ideas.md` ("Main idea: search, don't crawl", "What was cut"), plan sections 1, 4 and 10.

## Context

A shopper gives a photo, text or both and expects results from several GCC fashion stores in 30 seconds or less, each linking to the store's own product page. The business scoped this as a one-day demo: nightly catalogue crawling, a vector database and more than 6 stores are out of scope (BRD).

Each store's own search page already lists 20-50 products with price, image and link. The proposed-ideas document estimates about 10-12 requests per query, taking about 3-8 seconds in parallel (an estimate, not a measurement).

## Options considered

1. **Live search of each store's search page, per request (chosen).** Visit about 5-6 search pages with the model's keywords; read the products from the response.
2. **Nightly index of whole catalogues plus a vector database.** Fast queries, but needs a crawler, storage, scheduling and a much larger volume of requests to stores. Cut in the proposed-ideas document: "not needed if we search live".
3. **Sitemap-lite index.** A lighter index built from sitemaps. Deferred; see the trigger below.
4. **Visit individual product pages** (about 60 per query). Far more requests than a search page needs, and slower. Rejected in the PRD.

## Decision

Search each enabled store's own search page live, once per request (2-3 keyword variants per store, in parallel, 6 second timeout per request, at most 6 results from any one store). Stores are configuration, one YAML file each; adding a store adds a file, not code. No index, no database, no crawler.

## Consequences

- No stored catalogue, no crawl infrastructure, no staleness: prices and links come from the store at request time. The application stays a stateless single process.
- Results depend on what a store's search returns for our keywords. Junk results are possible (plan risk R8), so each store gets fixtures, a live smoke test and fragility notes, and the ranker removes products below a minimum match score.
- Store access becomes the biggest risk (plan R1): a store that cannot be read honestly is dropped (ADR 0003). The plan sets a gate of at least 4 working stores.
- The 30 second budget covers the live requests. An outfit photo needs about 4 times the search pages (R13), handled with limits and a global deadline that returns partial results.
- Price ranges can only be computed from the candidates found for this search, not from a market-wide catalogue (ADR 0004).
- **Revisit** with a sitemap-lite index only if live search proves too slow or fragile after the demo (plan section 10).
