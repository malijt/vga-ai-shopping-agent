# Backend Development Best Practices

A rule set for backend/API work. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.) so it defaults to these patterns without needing a reminder every time. Trim anything that doesn't apply to your stack.

## 1. Database & Migrations
- Always change schema through versioned migration code — never a manual `ALTER TABLE` against a live database.
- Every migration needs a reverse (`down`/rollback path), not just a forward one.
- Never edit a migration that has already run in a shared or production environment — write a new one instead.
- Keep each migration focused on one logical change; don't bundle unrelated schema changes together.
- Separate schema migrations from data seeding/backfills — run them as distinct steps.
- Add indexes for foreign keys and any column used heavily in `WHERE`, `JOIN`, or `ORDER BY`.
- Wrap multi-step migrations in a transaction where the database supports it.
- Treat destructive changes (dropping a column/table) as two deploys: stop reading/writing it in code first, drop it later once nothing depends on it.
- Run migrations as an explicit, automated step in the deploy pipeline — not a manual command someone has to remember.
- Store timestamps in UTC in the database; convert to local time only at the display layer.

## 2. API Design
- Version the API from the first endpoint (`/api/v1/...`).
- Use consistent REST conventions: nouns for resources, HTTP verbs for actions, plural resource names.
- Return one consistent error shape across every endpoint, e.g. `{ "error": { "code", "message" } }`.
- Use correct HTTP status codes — don't return `200` with the error buried in the response body.
- Validate and sanitize input at the boundary (the handler), before it reaches business logic.
- Paginate every list endpoint by default; never return an unbounded result set.
- Never leak internals to the client — no stack traces, raw DB errors, or file paths in responses.
- Make writes idempotent where possible (idempotency keys for `POST`, safe re-calls for `PUT`/`DELETE`).
- Generate or co-locate API docs (OpenAPI/Swagger) with the code so they can't silently drift out of sync.

## 3. Security
- Never commit secrets or credentials to source control — load them from environment variables or a secrets manager.
- Always use parameterized queries or an ORM's query builder — never concatenate strings into SQL.
- Hash passwords with bcrypt/argon2/scrypt. Never store plaintext, never use MD5/SHA1.
- Check authentication and authorization server-side on every protected route — never rely on the client to hide something.
- Apply least privilege to DB users, service accounts, and API tokens.
- Validate and escape all user input to guard against injection and XSS.
- Set an explicit CORS policy; don't default to allow-all origins in production.
- Rate-limit public endpoints, especially login, signup, and password reset.
- Keep dependencies patched and scan for known CVEs in CI.
- Enforce HTTPS everywhere; redirect HTTP to HTTPS.

## 4. Code Architecture
- Separate layers: routes/controllers (HTTP concerns) → services (business logic) → repositories/data access (persistence).
- Keep business logic out of controllers and out of ORM models — both stay thin.
- Use dependency injection for anything you'll want to mock in tests: DB clients, third-party API clients, clocks.
- Centralize cross-cutting concerns (auth, logging, error handling) in middleware instead of repeating them per route.

## 5. Core Design Principles
- **KISS (Keep It Simple)** — favor the simplest design that solves the actual problem; don't add abstraction, config, or patterns for requirements that don't exist yet.
- **DRY (Don't Repeat Yourself)** — extract logic that's duplicated for the same reason into one place. Don't force two things together just because they look similar today if they'll change for different reasons later — that's premature abstraction, not DRY.
- **YAGNI (You Aren't Gonna Need It)** — build for the requirement in front of you, not the one you're guessing might show up later.
- **Single Responsibility (SOLID – S)** — a function/class/module should have one reason to change. If two unrelated requirements would force edits to the same place, split it.
- **Open/Closed (SOLID – O)** — design so new behavior is added by extending (new class, new handler, new strategy) rather than editing tested, working code.
- **Liskov Substitution (SOLID – L)** — a subtype must be usable anywhere its base type is expected, without surprising the caller. Don't override a method to silently do less, or throw, where the base type wouldn't.
- **Interface Segregation (SOLID – I)** — prefer several small, specific interfaces over one large interface that forces implementers to support methods they don't need.
- **Dependency Inversion (SOLID – D)** — depend on abstractions, not concrete implementations. High-level business logic shouldn't directly import low-level details like a specific DB driver or HTTP client.

## 6. Error Handling & Logging
- Use centralized error-handling middleware instead of scattering inconsistent `try/catch` blocks.
- Log structured (JSON) logs, not free-text strings, so they're filterable in aggregation tools.
- Never log secrets, passwords, tokens, or other PII.
- Attach a request/correlation ID to every log line so one request can be traced end to end.
- Use distinct log levels (`debug`/`info`/`warn`/`error`) with a configurable threshold per environment.
- Fail loudly in development; fail safely (no internals exposed) but still logged in production — never swallow an error silently.

## 7. Testing
- Write unit tests for business logic, especially branching logic and edge cases.
- Write integration tests that hit real API routes against a dedicated test database.
- Never let tests run against dev or production data.
- Mock external services (payment gateways, email, third-party APIs) in tests.
- Run the full suite automatically in CI on every push/PR; block merges on failure.
- Prioritize coverage of critical paths (auth, payments, data integrity) over chasing a coverage percentage.

## 8. Performance & Scalability
- Cache expensive or frequently-read data (Redis/Memcached) with a clear invalidation strategy.
- Push slow work (emails, exports, image processing, reports) to background jobs/queues instead of blocking the request cycle.
- Watch for N+1 queries; use eager loading/joins where the ORM would otherwise fire one query per row.
- Use connection pooling for the database instead of opening a new connection per request.
- Set sane default limits (pagination, request size, timeouts) so no single request can exhaust resources.
- Add retries with backoff and a timeout on every outbound call to an external service.

## 9. Configuration & Secrets
- Keep all config in environment variables or a config service — never hardcoded in source.
- Commit a `.env.example` with placeholder values; keep the real `.env` gitignored.
- Keep dev/staging/prod as close to identical as possible (same DB engine/version, same runtime).
- Never point a non-production environment at real production data without anonymizing it first.

## 10. Observability & Monitoring
- Track key metrics: request latency, error rate, throughput, DB query time.
- Alert on error-rate spikes and downtime — don't rely on manually checking logs.
- Use an APM/tracing tool for visibility across services, not just single-process logs.
- Monitor DB health: connection pool saturation, slow queries, replication lag.

## 11. Deployment & CI/CD
- Automate the pipeline end to end: lint → test → build → migrate → deploy.
- Expose a health-check endpoint for load balancers/orchestrators to probe.
- Handle `SIGTERM` gracefully — finish in-flight requests before exiting.
- Aim for zero-downtime deploys and always have a tested rollback path.
- Manage infrastructure as code (Terraform/Pulumi/CloudFormation) rather than manual console changes.

## 12. Documentation & Version Control
- Keep a README that actually works: setup, run, test, and deploy instructions a new dev could follow cold.
- Write commit messages that explain *why*, not just *what*; keep PRs small and focused.
- Require code review before merging to the main branch.
- Use a secret-scanning pre-commit hook as a backstop even with good secrets hygiene.
