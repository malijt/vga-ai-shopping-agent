# ADR 0015: CI runs a critical suite; the complete test suite runs locally

- **Status:** Accepted. Decided by the user on 2026-10-08; recorded here.
- **Date:** 2026-10-08
- **Sources:** `CHANGELOG.md` 2026-10-08 (Decided: "CI runs a critical suite, not the whole test suite"), plan section 12.3, `.github/workflows/ci.yml`, `tests/critical_suite.txt`, `tests/foundation/test_critical_suite.py`.

## Context

The complete test suite has about 8,450 tests and takes three to four minutes. CI ran all of it on
every pull request and on every push to `main` and `develop`. A push to `develop` with a pull request
open ran every job twice, once for the push and once for the pull request. CI minutes cost money, and
the owner asked for CI to run only what is genuinely important.

The project's own standard (`docs/Best Practices/qa-testing-best-practices.md`, and `CLAUDE.md`)
says CI runs the tests on every pull request and blocks merges. Running a subset is a deliberate
departure from that.

## Options considered

1. **Keep running everything.** Safest, and the most expensive.
2. **Run nothing in CI but lint and types.** Cheapest, but a broken product rule could reach `main`
   unnoticed.
3. **Run a small, named set of tests whose failure would mean a broken rule or a broken demo, and
   run the complete suite locally (chosen).**

## Decision

- CI's `test` job runs `ruff`, `mypy` and **`pytest -m critical`**: 143 tests, about 20 seconds.
  The `pip-audit` and `gitleaks` jobs are unchanged.
- **What counts as critical** is one of two things. A product rule would be broken: store access
  (robots.txt, no retry after a refusal, the request limit, the honest User-Agent), links only to
  the store's own site, price words never sent to a store, no trace of the photo after a search,
  injected text kept harmless, secrets kept out of logs, and a guessed gender never applied without
  an answer. Or the demo would not work: the pipeline contract, understanding a request, reading
  store data, the ranking filters, the price ranges, one search end to end, the page, and one run of
  the acceptance harness.
- **One list names the tests:** `tests/critical_suite.txt`, one pytest node id per line under fifteen
  headings. A hook in `tests/conftest.py` gives each listed test the `critical` marker. No test file
  carries a decorator for it.
- **The list cannot rot silently.** `tests/foundation/test_critical_suite.py`, itself critical, fails
  if a listed test no longer exists, if a critical test is also marked `live`, if a heading has no
  test, or if the count drifts outside a narrow band (so growing the list is a deliberate edit).
- **Each commit is checked once:** on pull requests, and on pushes to `main`.
- **The complete suite is `uv run pytest`, run locally** before a push or a merge. An opt-in
  pre-push hook runs it automatically (`uv run pre-commit install --hook-type pre-push`).
- **The complete suite can still run in CI by hand:** Actions, CI, Run workflow, `full_suite`.
  Nothing is scheduled.
- Tests marked `live` never run in CI, as before.

## Consequences

- A CI run of the tests takes about 20 seconds where it took three to four minutes, and half as many
  runs happen.
- **A regression outside the 143 tests is not caught by CI.** It is caught only if someone runs the
  complete suite locally, or asks CI for the full run. A green check on a pull request therefore
  means "no product rule is broken and the core path works", not "everything passes".
- The critical list is thin in places by design: for example it covers one kind of store refusal and
  two robots.txt shapes, where the complete suite covers them all.
- A new product rule, or a new way the demo could silently stop working, needs a line in
  `tests/critical_suite.txt`. A test that is merely useful does not.
- The manual full run appears in GitHub only once the workflow is on the default branch.
