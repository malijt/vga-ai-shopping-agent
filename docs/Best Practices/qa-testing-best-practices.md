# QA / Testing Best Practices

A rule set for QA and testing work — test strategy, unit/integration/E2E testing, test data, and quality practices. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.) so it defaults to these patterns without needing a reminder every time. Trim anything that doesn't apply to your stack or test framework.

## 1. Test Strategy & the Test Pyramid
- Follow the test pyramid: many fast unit tests, fewer integration tests, and a small number of E2E tests covering critical journeys.
- Never invert the pyramid into an "ice cream cone" — a suite dominated by slow, flaky E2E tests instead of fast unit tests is expensive to run and painful to maintain.
- Match the test type to what you're actually verifying: business logic → unit tests, component interaction → integration tests, full user journeys → E2E tests.
- Decide test strategy before writing tests ad hoc — know what layer should catch each class of bug, so the same behavior isn't redundantly tested (or missed) at every layer.
- Write tests alongside the code they cover, not as an afterthought once a feature is "done."

## 2. Unit Testing
- Test behavior and outputs, not internal implementation details — a passing test shouldn't break just because you refactored the internals without changing behavior.
- Keep one behavior under test per test case; if a test needs "and" to describe what it verifies, split it.
- Use descriptive test names that state the expected behavior (e.g., `returns 404 when the user does not exist`), not vague ones like `test1`.
- Structure tests consistently (Arrange-Act-Assert or Given-When-Then) so any test is easy to read at a glance.
- Keep tests independent — no shared mutable state and no dependency on run order; any test should pass in isolation or in any order.
- Mock or stub external dependencies (DB, network, filesystem, time, randomness) so unit tests stay fast and deterministic.
- Keep unit tests fast (milliseconds each) so the full suite can run on every save without discouraging developers from running it.

## 3. Integration Testing
- Test real interactions between components (database, cache, message queue, internal services) rather than mocking every collaborator.
- Use ephemeral test databases or containers instead of a shared, long-lived test database that accumulates state and cross-test pollution.
- Run integration tests against the same schema/migrations used in production, not a hand-maintained parallel schema that can drift.
- Isolate each test's data (transactions rolled back after each test, or a fresh database per run) so tests can't leak state into each other.
- Keep integration tests focused on the boundary being tested — don't quietly let one turn into a full E2E test.

## 4. End-to-End (E2E) Testing
- Reserve E2E tests for critical user journeys (login, checkout, core workflows) — not every possible path through the app.
- Use stable selectors (`data-testid`, ARIA roles) instead of brittle CSS classes or exact text that changes with every copy edit.
- Keep the E2E suite small and reliable; a flaky E2E suite that gets rerun until it passes trains the team to stop trusting it.
- Run E2E tests against an environment that mirrors production configuration, not a stripped-down test-only setup that hides real bugs.
- Quarantine (don't silently ignore) a flaky E2E test immediately, and fix or remove it on a deadline — a known-flaky test left in the main suite corrodes trust in every other result.

## 5. Test Data Management
- Use factories or builders to generate test data instead of duplicating hardcoded fixtures across dozens of test files.
- Give each test its own data rather than relying on shared global fixtures that other tests might mutate.
- Never test against real production data without anonymization — treat test environments with the same data-privacy discipline as any other non-production environment.
- Seed test databases to a known, deterministic state before each run so failures are reproducible.
- Version-control test fixtures and factories the same as application code, and update them when the schema changes.

## 6. Mocking & Test Doubles
- Know the difference between a mock, stub, fake, and spy, and use the narrowest one that does the job — most tests need a stub, not a mock.
- Mock at architectural boundaries (external APIs, payment providers, email) rather than mocking internal collaborators wherever you can use the real thing instead.
- Avoid over-mocking — a test that mocks every collaborator is really testing your mocks, not your code, and breaks on every refactor even when behavior didn't change.
- Prefer verifying observable outcomes (return value, state change, resulting API call) over asserting an internal method was called a specific number of times.
- Keep fakes/mocks for third-party services in one shared place, not reimplemented slightly differently in every test file.

## 7. Core Design Principles
- **KISS (Keep It Simple)** — write the simplest test that actually proves the behavior; don't build elaborate test infrastructure a plain assertion would cover.
- **DRY (Don't Repeat Yourself)** — extract shared setup into helpers/fixtures, but don't abstract so much that a failing test requires archaeology to see what it actually checks.
- **YAGNI (You Aren't Gonna Need It)** — don't build a custom test framework, DSL, or abstraction layer before repeated pain proves you need one.
- **Single Responsibility (SOLID – S)** — each test verifies one behavior; each test helper does one thing, so a failure points at exactly what broke.
- **Open/Closed (SOLID – O)** — design test helpers/fixtures so new test cases can extend or parameterize them rather than requiring edits to shared setup every time.
- **Liskov Substitution (SOLID – L)** — a fake/test double should honor the same contract as the real dependency, so swapping one in doesn't require special-casing the test.
- **Interface Segregation (SOLID – I)** — keep test utilities and fixtures narrow and purpose-specific rather than one giant shared "test helpers" file everything imports.
- **Dependency Inversion (SOLID – D)** — design production code so dependencies can be injected/swapped for tests, instead of writing tests that fight the code's hardcoded dependencies.

## 8. CI Integration & Test Automation
- Run the full automated suite on every push/PR and block merges on failure — a red pipeline should stop a merge, not just add a warning.
- Keep CI test runtime fast: parallelize suites, split slow tests, and run the fastest/most valuable tests first.
- Run tests in a clean, reproducible environment (containerized CI runners) so "works on my machine" can't hide in the pipeline too.
- Track flaky tests explicitly and fix or quarantine them within a defined window — an ignored flaky test is a rehearsal for ignoring a real failure.
- Publish test results and trends somewhere visible (pass rate, duration, flaky-test list) so testing health is visible, not just enforced silently in CI.

## 9. Test Coverage & Quality
- Don't chase 100% coverage as a goal in itself — prioritize coverage of critical, complex, or high-risk logic (auth, payments, data integrity) over trivial code.
- Treat coverage percentage as a diagnostic signal, not a target metric — high coverage with weak assertions catches nothing and just looks good on a dashboard.
- Review test code with the same rigor as production code — tests have bugs too, and a bad test can hide a real one.
- Write a regression test for every bug fix, so the same bug can't silently reappear later.
- Delete or rewrite tests that no longer verify anything meaningful instead of leaving them as dead weight that slows the suite down.

## 10. Non-Functional Testing
- Load- or performance-test critical paths before major releases or expected traffic changes, not just after the first slowdown in production.
- Run security testing (SAST/DAST, dependency and secret scanning) as part of the standard pipeline, not a separate pre-launch checklist.
- Include accessibility testing (automated linting plus manual screen-reader checks) for user-facing features, not just visual review.
- Test resilience deliberately — fault injection or chaos testing for systems where an unhandled dependency failure would be costly.

## 11. Bug Tracking & Regression Testing
- File bugs with clear reproduction steps, expected vs. actual behavior, and environment details — a bug report without repro steps is a guess, not a report.
- Triage by severity and user impact, not by recency or who's loudest — a critical data-loss bug outranks a cosmetic one regardless of filing order.
- Link every bug to the test (new or existing) that should have caught it, so the same class of bug gets systematically harder to reintroduce.
- Close the feedback loop: a bug isn't done when it's fixed, it's done when there's a test guarding against it coming back.

## 12. Exploratory & Manual Testing
- Use structured exploratory testing (a charter: what area, what risk, what time-box) rather than unstructured, unrepeatable poking around.
- Reserve exploratory testing for what automation is bad at: new features, edge cases nobody anticipated, and overall "does this feel right" judgment.
- Feed anything found during exploratory testing back into the automated suite so it's covered going forward, not just fixed once.
- Don't treat manual testing as a substitute for automated regression coverage — use it to complement, not replace, the pyramid.

## 13. Documentation & Reporting
- Write a lightweight test plan for significant features (what's covered, what's explicitly out of scope, what risk that leaves) before building starts.
- Keep test reports and dashboards visible to the whole team, not buried in a CI log only QA looks at.
- Document known gaps and accepted risks explicitly instead of leaving them as silent, undocumented holes in coverage.
- Keep testing documentation (how to run tests locally, how test environments are set up) as current as the README for the app itself.
