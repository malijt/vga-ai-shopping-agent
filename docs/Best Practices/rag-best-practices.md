# RAG Best Practices & Architecture Selection Guide

A focused reference on Retrieval-Augmented Generation: the practices that make retrieval reliable, the major architectural variants in production use, and a decision guide for picking between them. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.). Complements `genai-best-practices.md`'s RAG section with full depth.

---

## Part 1: RAG Best Practices

### 1. Chunking & Ingestion
- Start with simple fixed-size or recursive chunking (roughly 200–500 tokens) before reaching for anything more complex — measure failures before adding sophistication.
- Chunk on natural boundaries (paragraphs, sections, headings), not blind character counts, so you don't split a thought mid-sentence.
- Add chunk-level context — a short note on what the chunk is and how it relates to the source document — before embedding it. This "contextual retrieval" step is one of the highest-leverage upgrades to retrieval accuracy for a modest cost increase.
- Skip chunking entirely for short, self-contained documents (FAQs, tickets, product listings) — splitting small documents can hurt retrieval more than it helps.
- Keep chunk overlap small and deliberate; overlap should recover boundary information, not double your index size by default.
- Preserve source metadata on every chunk (title, section, URL, last-updated date, permissions) — you'll need it for filtering, citation, and access control, not just similarity search.

### 2. Embedding & Indexing
- Choose an embedding model evaluated on retrieval tasks close to your domain — legal, code, and medical text embed differently than general prose, so the most popular general-purpose model isn't automatically the right one.
- Fine-tune or adapt the embedding model on real query-document pairs once you have production traffic; a domain-adapted model closes most of the gap that would otherwise require hybrid search.
- Treat "rebuild the index" as a versioned, automated, reversible operation, not a manual one-off script.
- Re-embed and fully re-index when you change embedding models — vectors from two different models are not comparable in the same index.

### 3. Retrieval
- Use hybrid search (dense embeddings + sparse/BM25 keyword search) whenever queries include IDs, product codes, names, or rare technical terms that embeddings tend to blur together — fuse the two ranked lists with Reciprocal Rank Fusion rather than a hand-tuned weighted average.
- Add a reranker (cross-encoder) as a second pass when precision in the top-5 results is the bottleneck. Retrieval and reranking solve different problems — recall vs. precision — so don't expect one step to do both.
- Retrieve a wider candidate set than you need and let reranking narrow it, rather than trying to nail the perfect top-k on the first pass.
- Log retrieved chunks alongside every generated answer in production. When a query fails, compare what dense vs. sparse retrieval each returned — it tells you whether the failure is a vocabulary mismatch or a genuine relevance problem.

### 4. Context Assembly & Generation
- Clearly delimit retrieved context from instructions in the prompt (e.g., dedicated tags or a labeled block) so the model doesn't confuse retrieved data for commands.
- Keep retrieved context relevant and minimal — dumping every marginally-related chunk in raises cost and latency and increases the chance the model latches onto the wrong passage.
- Preserve original document order among retrieved chunks where narrative coherence matters, instead of always sorting purely by similarity score.
- Require citations back to source chunks in the generated answer so claims can be checked against retrieved material instead of just trusted.
- Give the model an explicit "insufficient information" path so it says so rather than filling gaps from parametric memory when retrieval comes up short.

### 5. Security & Access Control
- Treat retrieval-time access control as a hard requirement, not an add-on — vector databases don't enforce permissions on their own.
- Enforce access control at the retrieval layer itself (filter before the similarity search runs), not by discarding unauthorized results afterward in the application layer. Post-hoc filtering wastes compute and is a thin defense against bugs or prompt injection.
- Tag every chunk with the same access metadata (classification, owner, permitted roles) the source system enforces, and keep it in sync as source permissions change.
- Watch for indirect exfiltration: a user without access to a document can sometimes reconstruct its contents through a series of narrow, seemingly unrelated questions — this needs monitoring, not just chunk-level filtering.
- Treat all retrieved content as untrusted input to the model, same as any other external data — a document already inside your own knowledge base can still carry an injected instruction if more than one party can write to it.

### 6. Evaluation & Monitoring
- Evaluate retrieval and generation separately. A bad answer built on good context is a prompt/generation problem; a good answer that got lucky on bad context is a retrieval problem waiting to fail elsewhere.
- Use an eval framework (RAGAS or equivalent) that scores context precision, context recall, faithfulness, and answer relevancy as four distinct numbers, not one blended score.
- Build a golden dataset of real questions with known-correct answers and known-relevant source chunks; re-run it on every change to chunking, embeddings, retrieval, or prompts.
- Track faithfulness — whether the answer is actually grounded in the retrieved context — as your primary hallucination signal; it catches failures that a "the answer sounded right" review misses.
- Monitor in production, not just at eval time: retrieval latency, empty-result rate, and user feedback (thumbs down, escalations) surface regressions offline evals can miss.

---

## Part 2: Types of RAG

### Foundational Paradigms
- **Naive RAG** — The baseline pipeline: embed the query, retrieve the top-k most similar chunks, stuff them into the prompt, generate. Cheap and simple, but retrieval is single-shot with no quality check — if the wrong chunks come back, the model confidently answers from them anyway.
- **Advanced RAG** — Naive RAG plus pre-retrieval and post-retrieval optimization: query rewriting/expansion before search, reranking and filtering after. Same retrieve-then-generate shape, with quality gates added around it.
- **Modular RAG** — Breaks the pipeline into independent, swappable components (retriever, reranker, router, fusion step) that can be built and upgraded separately rather than as one monolithic chain. Less a distinct "type" than the engineering pattern most production systems converge on.

### Retrieval Strategy Variants
- **Hybrid Search RAG** — Combines dense vector search (semantic/paraphrase matching) with sparse keyword search like BM25 (exact term matching), fusing both ranked lists — typically with Reciprocal Rank Fusion. Fixes pure dense retrieval's blind spot on exact IDs, codes, names, and rare technical terms.
- **HyDE (Hypothetical Document Embeddings)** — Instead of embedding the raw user query, the model first generates a hypothetical answer, and that hypothetical answer is embedded and used for retrieval. Helps when user vocabulary doesn't match document vocabulary.
- **RAG-Fusion (Multi-Query RAG)** — Generates several reworded variants of the user's query, retrieves for each in parallel, then fuses and re-ranks the combined results. Improves recall on ambiguous or underspecified queries at the cost of multiple retrieval calls per question.
- **GraphRAG** — Builds a knowledge graph (entities, relationships, claims) from your documents, detects communities of related entities, and generates summaries at each level. Supports entity-centric "local search" and broad, corpus-wide "global search" via community summaries. Strong for multi-hop reasoning and thematic questions flat chunk retrieval can't synthesize; meaningfully more expensive to build and maintain than a vector index.

### Adaptive & Agentic Variants
- **Agentic RAG** — An LLM-driven agent decides when to retrieve, reformulates queries, chooses between multiple tools/sources, evaluates what came back, and loops until it has enough evidence, rather than retrieving once and stopping. Best for complex, multi-part questions that need exploration; costs more calls and latency per answer than any single-shot pattern.
- **Corrective RAG (CRAG)** — Adds an explicit evaluator that grades retrieved documents for relevance; when the grade is low, it triggers a corrective action (query rewrite, broader search, or fallback to web search) instead of generating from weak context.
- **Self-RAG** — The model itself is trained/prompted to decide when retrieval is needed and to critique its own generation against retrieved evidence, re-retrieving if it judges its answer poorly supported. Similar goal to Corrective RAG, but the judgment lives inside the model's own generation process rather than an external grader.
- **Adaptive RAG** — Routes each incoming query to a different retrieval strategy based on its complexity: a simple factual question might skip retrieval entirely, a straightforward one uses single-shot retrieval, a complex one gets routed to multi-step or agentic retrieval.
- **Multi-Hop / Iterative RAG** — Performs retrieval in multiple rounds, where the result of one step informs the query for the next, to chain together facts spread across separate documents.

### Specialized
- **Multimodal RAG** — Extends retrieval and generation across images, audio, video, and tables rather than text alone, using modality-specific embedding models and retrievers. Needed when critical knowledge lives outside text — diagrams, scans, product photos — and grounding requires the non-text evidence directly.

### Alternative Pattern
- **Cache-Augmented Generation (CAG) / Long-Context, No Retrieval** — Skips retrieval entirely: preload the entire bounded knowledge source into the model's long context window, optionally precomputing and caching the KV state, and let the model reason over everything at once. Works well when the corpus is small and stable; retrieval wins once the corpus is large, changes often, or the cost/latency of processing full context on every call becomes the bottleneck.

---

## Part 3: Which Type to Use, When

| Your situation | Use | Why |
|---|---|---|
| Prototyping, or a simple factual Q&A use case | Naive RAG | Fastest to build; validate the concept before adding complexity |
| Right document exists but the wrong chunk keeps coming back | Advanced RAG (query rewriting + reranking) | Adds quality gates without changing the overall shape |
| Queries include IDs, product codes, names, or rare technical terms | Hybrid Search RAG | Dense embeddings alone blur exact-match terms; BM25 catches them |
| User vocabulary differs from your documents' vocabulary | HyDE | Hypothetical-answer embeddings bridge the gap |
| Queries are ambiguous or phrased very differently by different users | RAG-Fusion (Multi-Query) | Multiple query variants improve recall over one fixed phrasing |
| Questions require synthesizing themes or relationships across the whole corpus | GraphRAG | Community summaries and graph traversal handle "global" sensemaking that flat retrieval can't |
| Questions require chaining facts across multiple separate documents | Multi-Hop RAG, or GraphRAG | Multi-hop RAG for ad hoc chains; GraphRAG if the corpus benefits from a persistent graph |
| System needs to self-correct when retrieval quality is poor | Corrective RAG (CRAG) | Explicit evaluator catches and routes around weak retrieval |
| Want self-correction without standing up a separate evaluator | Self-RAG | Model-internal reflection instead of an external grading step |
| Query complexity varies a lot across your traffic | Adaptive RAG | Routes cheap queries to cheap paths, complex ones to expensive paths |
| Task genuinely needs exploration, multiple tools, or open-ended reasoning | Agentic RAG | Iterative retrieval plus tool use for questions no single pass resolves |
| Critical knowledge lives in images, diagrams, audio, or video | Multimodal RAG | Text-only retrieval can't ground answers in non-text evidence |
| Knowledge base is small (fits comfortably in context) and rarely changes | Cache-Augmented Generation | Simpler architecture, no retrieval errors, skips indexing overhead for a small stable corpus |
| Enterprise data with per-user or per-role access restrictions | Any of the above, plus document-level access control at the retrieval layer | RAG type is orthogonal to this — access control must be enforced regardless of pattern |

These aren't mutually exclusive — a mature production system commonly layers several at once (e.g., hybrid search + reranking, wrapped in an agentic loop, with adaptive routing deciding which queries need the full loop at all). Start from the simplest pattern that could work, measure where it actually fails against your eval set, and add exactly the layer that fixes that failure.
