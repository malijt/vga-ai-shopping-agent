# Gen-AI Application Best Practices

A rule set for building features on top of generative AI / LLMs — chat features, agents, RAG pipelines, tool-using assistants. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.) so it defaults to these patterns without needing a reminder every time. Trim anything that doesn't apply to your use case.

## 1. Prompt Design & Engineering
- Write explicit, unambiguous system prompts; don't rely on the model to infer intent from a vague instruction.
- Structurally separate the system prompt (instructions) from user/data input — never concatenate untrusted content directly into the instruction block.
- Use few-shot examples for tasks with a specific format or style you need reproduced consistently.
- Ask for step-by-step reasoning on complex tasks, but keep the final answer format explicit and separate from the reasoning.
- Version and store prompts like code, in the repo, not hardcoded inline and scattered across files.
- Keep one prompt responsible for one task; don't overload a single prompt with unrelated instructions "just in case."
- Test prompt changes against a fixed set of examples before shipping, not just a single manual check.

## 2. Security & Prompt Injection
- Treat all external content fed to the model (web pages, documents, emails, tool outputs, RAG results) as untrusted input, not as instructions.
- Never let user-supplied text override system-level instructions; validate and sanitize before including it in a prompt.
- Give the model the minimum tool access and permissions needed for the task — least privilege applies to AI agents too.
- Require explicit confirmation before an agent takes an irreversible action (sending a message, deleting data, making a payment).
- Validate and sanitize any AI-generated output before executing it — never run generated code/SQL/shell commands without review.
- Watch for indirect prompt injection: instructions hidden inside a document, webpage, or API response the model reads.
- Don't put secrets or credentials in prompts that might be logged, cached, or sent to a third-party provider.

## 3. Tool Use & Function Calling
- Give each tool a single, clear responsibility and a precise description — vague tool descriptions cause the model to call the wrong one.
- Validate tool inputs before executing them, exactly as you would for any other untrusted input.
- Return structured, predictable errors from tools so the model can react intelligently instead of retrying blindly.
- Log every tool call and its result for debugging and audit purposes.
- Cap the number of tool-call iterations/steps an agent can take to avoid runaway loops.
- Design tools to be idempotent where possible, since a model may retry a call after an ambiguous failure.

## 4. Structured Output & Validation
- Don't trust that model output is valid JSON/schema-conformant — always parse and validate it before using it downstream.
- Prefer native structured-output/function-calling features over asking the model to "output JSON" in free text.
- Feed validation errors back to the model for a corrective retry rather than failing silently on malformed output.
- Keep output schemas as narrow as the task needs — a smaller, well-defined schema is easier for the model to satisfy reliably.

## 5. RAG (Retrieval-Augmented Generation)
- Chunk documents at a size that preserves meaning (not mid-sentence) and fits comfortably inside the context budget.
- Re-rank or filter retrieved chunks for relevance before sending them to the model — don't just dump the top-k results in.
- Include source citations/attribution in the response so a person can verify claims against the retrieved material.
- Evaluate retrieval quality separately from generation quality — a good answer built on bad context is still a fragile system.
- Keep retrieved context clearly delimited from instructions in the prompt so the model doesn't confuse data for commands.
- Set an explicit "not found" path — the model should say it doesn't know rather than fabricating an answer when retrieval comes up empty.

## 6. Reliability & Error Handling
- Set an explicit timeout on every model call; don't let a hung request block the user indefinitely.
- Retry transient failures (rate limits, 5xx errors) with exponential backoff, not immediately or infinitely.
- Have a fallback path (cached response, simpler model, static message) for when the primary model/provider is unavailable.
- Never let a model failure crash the whole request — degrade to an error message or reduced functionality instead.
- Handle partial/streamed responses that cut off mid-generation without corrupting downstream parsing.

## 7. Cost, Latency & Token Management
- Track token usage and cost per request/feature so spend is visible, not discovered at the end of the month.
- Cache responses (exact-match or semantic) for repeated or similar queries instead of regenerating from scratch.
- Route simple tasks to smaller/cheaper models and reserve the most capable model for tasks that actually need it.
- Trim conversation history/context to what's relevant instead of always sending the full history on every call.
- Stream tokens to the user instead of waiting for the full completion, especially for longer responses.
- Set max-token limits appropriate to the task so a runaway generation doesn't burn budget or time.

## 8. Model & Version Management
- Pin the exact model version in production config; don't silently ride a "latest" alias that can change behavior overnight.
- Re-run your eval suite before upgrading a model version, even a minor one — behavior can shift in subtle ways.
- Keep an abstraction layer between your app and the model provider so switching models/providers doesn't mean rewriting every call site.
- Track which prompt version was used with which model version together — they're a matched pair, not independent variables.

## 9. Core Design Principles
- **KISS (Keep It Simple)** — use the simplest prompt/chain that reliably does the job; don't reach for an agent or multi-step pipeline when a single well-crafted prompt will do.
- **DRY (Don't Repeat Yourself)** — factor shared instructions (tone, format, safety rules) into a common prompt fragment reused across features instead of copy-pasting them.
- **YAGNI (You Aren't Gonna Need It)** — don't wire up tool access, memory, or multi-agent orchestration that the current feature doesn't actually require.
- **Single Responsibility (SOLID – S)** — give each prompt/agent one job; a "do everything" mega-prompt is harder to debug and more prone to drift.
- **Open/Closed (SOLID – O)** — design prompts/pipelines so new capabilities are added via new tools or prompt sections, not by rewriting the whole instruction set each time.
- **Liskov Substitution (SOLID – L)** — if you swap one model or tool implementation for another behind the same interface, the calling code shouldn't need to change.
- **Interface Segregation (SOLID – I)** — expose narrow, specific tools rather than one giant "do anything" tool the model has to reason about.
- **Dependency Inversion (SOLID – D)** — code that orchestrates AI calls should depend on an abstraction (a model/provider interface), not a specific vendor SDK wired in directly everywhere.

## 10. Evaluation, Testing & Monitoring
- Build a golden/eval dataset of representative inputs and expected outputs to test prompt or model changes against before shipping.
- Include adversarial and edge-case examples in evals, not just the happy path.
- A/B test meaningful prompt or model changes in production rather than assuming an improvement from a few manual tries.
- Monitor output quality continuously (user feedback, thumbs up/down, escalation rate) — quality regressions here are silent, not exceptions that throw.
- Watch for behavior drift after a provider-side model update, since the same prompt can produce different results over time.
- Log prompts and completions (with privacy safeguards) so failures can actually be debugged after the fact.

## 11. Human Oversight & Safety
- Keep a human in the loop for high-stakes or irreversible actions (financial transactions, deleting data, sending communications on someone's behalf).
- Clearly disclose AI-generated content to end users where it matters for trust or compliance.
- Add guardrails/content filtering for user-facing generation, especially in open-ended or adversarial-input contexts.
- Give users an easy way to flag bad output, and route that feedback somewhere it actually gets reviewed.
- Design for graceful uncertainty — a model that isn't sure should say so rather than confidently guessing.

## 12. Data Privacy & Compliance
- Know what data leaves your system when you call a third-party model API, and whether that provider trains on or retains it.
- Redact or avoid sending PII/sensitive data to external APIs unless it's necessary and covered by a proper data processing agreement.
- Understand and follow the regulations relevant to your domain (HIPAA, GDPR, etc.) before sending regulated data to any AI system.
- Apply the same access controls to AI-accessible data as you would to any other system that can read or act on it.

## 13. Documentation & Version Control
- Version-control prompts alongside the code that uses them, not in a separate untracked doc.
- Document why a prompt is worded the way it is, especially non-obvious constraints — future editors will otherwise "simplify" away a fix for a bug they can't see.
- Document known limitations and failure modes of each AI feature so other developers and support teams know what to expect.
- Keep a changelog of prompt/model changes tied to eval results, so regressions can be traced to a specific change.
