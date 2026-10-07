# CLAUDE.md

Project facts and engineering standards for the **VGA AI Shopping Agent**. The standards are
distilled from the domain docs in [`docs/Best Practices/`](./docs/Best%20Practices/): treat this
file as the always-on summary and open the matching doc when you need full depth.

## Project Context

- **What it is:** a one-day demo. A shopper gives a photo, text (English or Arabic), or both. One
  OpenAI call understands the request, the app searches 4-6 GCC fashion stores' own search pages
  live, ranks the products, and shows the top 30 split into Budget / Mid-range / Premium / Luxury.
  Every result links to the store's own product page.
- **Status (2026-10-07):** the implementation plan
  [`docs/plans/2026-10-07-vga-ai-shopping-agent-implementation-plan.md`](./docs/plans/2026-10-07-vga-ai-shopping-agent-implementation-plan.md)
  is approved (v3). Waves 1 and 2 (Phases 1 to 11) are merged; Wave 3 (pipeline and store adapters)
  is in progress. **Build only what the plan specifies**, in its phases and waves. Integration
  branch: `develop`.
- **Stores (decided 2026-10-07):** store qualification found that no large GCC retailer can be read
  by an honest client (see [`docs/store-qualification/SUMMARY.md`](./docs/store-qualification/SUMMARY.md)).
  The demo therefore searches six Shopify storefronts through `/search/suggest.json`: Giordano UAE,
  Nautica UAE, Sacoor Brothers UAE, Oh Polly UAE, Club L London UAE and Maison D'Vie (six is the
  BRD's maximum; three more readable stores are held in reserve). Reaching big retailers is
  planned as later Phases 17-19 (agent endpoints, store APIs/headless with a terms sign-off, a
  category + sitemap index). Do not start those without the user's go-ahead.
- **What it is not (yet):** not multi-tenant, no accounts, no billing or credits, no database, no
  RAG, not hosted. The rules for those domains are dormant (see "Domain applicability"). Do not
  build toward them speculatively.
- **Where truth lives, in order:** [`docs/01-business-requirements.md`](./docs/01-business-requirements.md)
  (why) → [`docs/02-prd.md`](./docs/02-prd.md) (what) → the plan (how). `docs/03-proposed-ideas.md`
  is options only. `docs/archive/` is the superseded v0.1 scope: do not use it.
  `comprehensive_doc.md` is a point-in-time snapshot.

## Stack (decided)

| Layer | Choice |
|---|---|
| Language / env | Python 3.12 via `uv` (system Python is 3.14; do not use it), `uv.lock` committed |
| LLM | OpenAI for every language and vision task; native structured outputs with Pydantic. Model: **`gpt-6-luna`** (chosen by the user on 2026-10-08; OpenAI lists no dated variant, so the versioned name is the snapshot). Pinned in `config/settings.yaml`: a dated snapshot or a verified undated snapshot id, never an alias such as `-latest` |
| Image similarity | Local Marqo-FashionSigLIP via `open_clip`, pinned to a Hugging Face revision with `snapshot_download` + `local-dir:` (the `hf-hub:` scheme cannot pin); a low-weight nudge, never a filter; `off` as the fallback |
| Fetching | `httpx` async with an honest, identifying User-Agent. **Never** `curl_cffi`, Scrapling fetchers, proxies, or any browser impersonation |
| Parsing | `selectolax` (use `selectolax.lexbor`), stdlib `json`, `protego` for robots.txt; `extruct` (JSON-LD) only from Phase 19. **Never `urllib.robotparser`:** on Python 3.12 it ignores `*` and `$` and wrongly allows disallowed paths |
| Contracts / config | Pydantic v2 models in `src/vga/models.py`, YAML settings, env overrides |
| UI | Streamlit (`app/`), one theme source in `.streamlit/config.toml` |
| Quality | `pytest`, `pytest-asyncio`, `respx`, Streamlit `AppTest`, `ruff`, `mypy`, `pip-audit`, `gitleaks`, GitHub Actions |
| Hosting | None. Local only. |

## Product Rules (from the BRD, never violate)

1. Every result links to the **original store's product page**, and only to a host on that store's `allowed_hosts`.
2. Respect robots.txt. No login-walled pages. No CAPTCHA solving. About 1 request/s per store. A store that blocks an honest client is **dropped, never bypassed**, and is not contacted again during its cooldown.
3. Never guess body size from a photo.
4. Never keep an uploaded photo after the request: not on disk, not in logs, not in the cache.
5. Only components with commercial-friendly licences (run the licence audit after adding a dependency).
6. This is a demo. Store terms of use must be checked before any real users.
7. Never send price words ("cheap", "budget") to a store search; they are filters only.
8. Gender inferred by the model is shown, not applied, until the shopper confirms it.

## Commands

```bash
uv sync                                        # install (add --group ml for the image model)
uv run pytest                                  # unit + integration tests (no network)
uv run pytest -m live                          # live store / OpenAI tests; needs keys, never in CI
uv run ruff check && uv run mypy src           # lint and types
VGA_UI_FIXTURE=1 uv run streamlit run app/main.py   # the UI on sample data (run from the repo root)
uv run --group ml python -m vga.rank.image.download # one-off: fetch the pinned image-model weights
uv run python -m eval.harness --mock           # acceptance harness on a fake pipeline
uv run python -m eval.harness --record DIR     # live acceptance run, recorded
uv run python -m eval.harness --replay DIR     # re-run from a recording, no network
```

Not available until Phase 13 and 15 land: `uv run python -m vga.search --text "..."` (the pipeline
from the CLI) and the UI connected to the real pipeline.

Environment variables are documented in `.env.example` (`OPENAI_API_KEY`, `OPENAI_MODEL`,
`VGA_USER_AGENT`, `VGA_IMAGE_RANKER`, `VGA_LOG_DIR`, `VGA_LOG_LEVEL`, `VGA_LOG_PROMPTS`,
`VGA_DEBUG_DUMP`, `VGA_SETTINGS_PATH`, `VGA_DAILY_LLM_CALL_CAP`, `VGA_UI_FIXTURE`).

## Target Layout

```
src/vga/{models,interfaces,errors,settings,log}.py   shared contracts (frozen after Phase 1)
src/vga/understand/   OpenAI call, prompts/ (versioned, with CHANGELOG.md)
src/vga/fetch/, stores/   polite HTTP, robots, rate limit, allow-list, cache, extractors
src/vga/rank/, rank/image/, tiers/, pipeline/
app/                  Streamlit UI        config/stores/<id>.yaml   one file per store
eval/data/, eval/harness/                 tests/fakes.py, tests/<area>/
docs/adr/             decision records    docs/store-notes/, docs/store-qualification/
```

## How to Work in This Repo

- **Follow the design principles below in every domain.** They are the spine of the whole rule set.
- Prefer the **simplest thing that solves the actual, current requirement**. The plan's
  "Deferred Until a Trigger" list names things deliberately left out; do not build one unless its
  trigger is met.
- **Agent models:** development subagents and background tasks run on **Sonnet 5.5** (pass
  `model: "sonnet"` on every Agent call). Orchestration, review, merges and decisions (gates,
  go/no-go, changes to the plan or contracts) run on **Opus 5.5**.
- Work from the plan: one phase or module per assignment, staying inside its owned paths. One
  branch and one small PR per assignment; merge only with CI green and a review.
- Contracts in `models.py`, `interfaces.py` and `errors.py` are frozen after Phase 1. Changing one
  is its own PR that updates every user.
- When a task touches a domain, consult that domain's doc in `docs/Best Practices/` and apply it by
  default.
- **Maintain [`CHANGELOG.md`](./CHANGELOG.md).** Every change merged into `develop` adds an entry
  under today's date (Added / Changed / Fixed / Decided / Found), in the same commit or the merge.
  "Found" records facts learned from real runs. Prompt and model changes also go in
  `src/vga/understand/prompts/CHANGELOG.md` with their eval result.
- A significant decision gets an ADR in `docs/adr/`. A deliberate departure from a best-practice
  rule is recorded in the plan (section 12.3), not left silent.
- Keep documentation and this file current. An outdated doc is worse than none.

## Core Design Principles (apply everywhere)

- **KISS** — pick the simplest design that meets today's real requirement. No abstraction, config, service, or pipeline for a problem that doesn't exist yet.
- **DRY** — extract logic duplicated *for the same reason* into one place. Don't merge two things that merely look alike today but will change for different reasons.
- **YAGNI** — build for the requirement in front of you, not a guess about later.
- **SRP (S)** — one reason to change per function/module/prompt/test.
- **Open/Closed (O)** — add behavior by extending (a new store config, a new extractor class), not by editing tested, working code.
- **Liskov (L)** — a substitute (fake, alternate ranker) must honor the same contract; fakes pass the same contract tests as the real thing.
- **Interface Segregation (I)** — many small, specific interfaces over one large one.
- **Dependency Inversion (D)** — depend on the `Protocol`s in `interfaces.py`, not on the OpenAI SDK, `httpx` or `open_clip` directly.

## Non-Negotiables (hard rules)

- **Secrets:** never commit secrets. Load from env vars. Commit `.env.example` with placeholders; keep `.env` gitignored. Never log secrets, tokens, PII or image data.
- **Untrusted input:** user text, the photo, and everything from a store (HTML, JSON, titles, URLs) is data, never instructions. Validate at the boundary. Instructions live only in the system prompt. No model reads store content.
- **Outbound requests:** https only, only to a store's `allowed_hosts`, never to private addresses; redirects re-checked.
- **Rendering:** never render store-supplied or user-supplied strings as HTML or markdown; never show a stack trace to the user.
- **Model versions:** the OpenAI snapshot and the FashionSigLIP revision are pinned. Re-run the eval set and add a prompt-changelog entry before changing either the model or the prompt.
- **Test data:** tests never hit real stores or OpenAI unless marked `live`. Never loop live requests; tune from a recording in replay mode. Private photos stay gitignored.
- **Dormant until the feature exists:** parameterized SQL only; passwords hashed with bcrypt/argon2/scrypt; authn/authz checked server-side on every protected route; schema changes only through versioned, reversible migrations; tenant isolation at the data layer with the tenant resolved from the session; HTTPS for any hosted endpoint.

## Domain Applicability

| Doc | Status now | Notes |
|---|---|---|
| [`genai-best-practices.md`](./docs/Best%20Practices/genai-best-practices.md) | **Active** | The Understand step |
| [`qa-testing-best-practices.md`](./docs/Best%20Practices/qa-testing-best-practices.md) | **Active** | All code |
| [`ui-ux-best-practices.md`](./docs/Best%20Practices/ui-ux-best-practices.md) | **Active** | The Streamlit page |
| [`backend-best-practices.md`](./docs/Best%20Practices/backend-best-practices.md) | Partly | Config, security, errors, logging, resilience apply. No database or HTTP API yet |
| [`frontend-best-practices.md`](./docs/Best%20Practices/frontend-best-practices.md) | Partly | States, validation, security, a11y apply. React/TypeScript/bundle rules do not (Streamlit) |
| [`architecture-infra-best-practices.md`](./docs/Best%20Practices/architecture-infra-best-practices.md) | Principles | Modular monolith, resilience, ADRs |
| [`devops-best-practices.md`](./docs/Best%20Practices/devops-best-practices.md) | CI only | Deploy, IaC, monitoring, backups wake up when hosting is decided |
| [`rag-best-practices.md`](./docs/Best%20Practices/rag-best-practices.md) | Dormant | No model generates from retrieved content. Wakes up if an index or LLM-over-store-content is added |
| [`saas-platform-best-practices.md`](./docs/Best%20Practices/saas-platform-best-practices.md) | Dormant | Wakes up when accounts, tenants, billing or credits are added |

## Domain Quick Reference

### Gen-AI — active
- One prompt, one task, stored as a versioned file with comments explaining each rule. Instructions in the system message; user text and photo in a separate, delimited user message.
- Native structured output; always parse and validate; one corrective retry with the validation error, then fall back to raw-text keywords.
- Timeout, `max_output_tokens`, retries with exponential backoff on 429/5xx/timeout only, a daily call cap that fails closed.
- Log model id, prompt version, tokens and latency together on every call. Never log the image.
- Keep the golden set and the adversarial edge cases (`eval/data/`) and re-run them before any prompt or model change.
- Tell the user what is AI-inferred and that the photo is sent to OpenAI.

### Backend — partly active
- Layers: UI (`app/`) → pipeline (orchestration) → adapters (OpenAI, stores, image model). Keep the UI and the adapters thin.
- One error shape: `VgaError(code, user_message, detail)`. Never leak internals; never swallow an error silently, every fallback logs at warn with the request id.
- Structured JSON logs with a request id and levels. Config only from settings and env.
- Timeouts on every outbound call and a 30 s request deadline. Retries only for OpenAI; none to stores (Rule 2).
- Validate input server-side at the pipeline entry, not only in the UI.
- Dormant: migrations, API versioning, pagination, connection pooling, background jobs.

### QA & Testing — active
- Pyramid: many fast unit tests, fewer integration tests, few end-to-end.
- Fake only the boundaries (store HTTP, OpenAI, model weights), from the shared `tests/fakes.py`. Do not mock internal collaborators.
- Test behavior, one behavior per test, descriptive names, Arrange-Act-Assert, deterministic (inject the clock).
- Cover the risky logic first: price ranges, filters, guards, validation. No coverage target.
- A bug fix needs a regression test. CI runs on every PR and blocks merges.

### Frontend (Streamlit) — partly active
- Small components in `app/components/`; `app/runner.py` is the only place that calls the pipeline.
- Design and handle loading, error, empty and partial states. Disable the action while it runs; never lose the user's input on an error.
- Visible labels and stable `key`s on every widget; queried by label/key in `AppTest`.

### UI/UX — active
- Keep the user informed of each step; give a way back ("Reset to detected"); prevent errors by design.
- Use the shopper's words: "price range", not "tier". Buttons say what they do.
- Never signal status with colour alone. One small palette, no emoji as icons, no motion or depth effects unless explicitly decided.
- Plain-language errors that say what to do next. Design for content extremes (long titles, missing images).

### Architecture & Infrastructure — principles
- One process, modular monolith. No services, queues or databases without a current, concrete reason.
- Assume the other side fails: timeout, cooldown for a failing store, graceful degradation, no silent failure.
- Add stores and extractors by configuration or a new class.

### DevOps — CI only
- Pipeline as code: lint → types → test → dependency and secret scan; required on `main`.
- Pin everything that can drift: `uv.lock`, the OpenAI snapshot, the model revision.
- Dormant until hosted: IaC, containers, zero-downtime deploys, metrics/alerts/runbooks, backups, cost tagging.

### RAG and SaaS Platform — dormant
- Borrowed today: log the ranked candidates for each request, evaluate the fetch stage and the rank stage separately, and default everything to the most restrictive setting (a store is unused unless `enabled: true`).
- If either domain becomes real, read its doc first and update this file.

## Documentation & Version Control

- Keep a README that works cold: setup, run, test, env vars, known limitations of the AI features.
- Commit messages and PR descriptions explain **why**, not just what. Keep PRs small and focused.
- Require review before merging to `main`. `gitleaks` runs in pre-commit and CI.
- Keep the plan, ADRs and store notes in the repo, versioned and reviewed like code.
