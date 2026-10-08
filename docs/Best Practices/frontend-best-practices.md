# Frontend Development Best Practices

A rule set for frontend/UI work. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.) so it defaults to these patterns without needing a reminder every time. Framework-agnostic — trim or adapt anything that doesn't match your stack (React/Vue/Angular/Svelte, etc.).

## 1. Component Architecture & Code Organization
- Keep components small and focused on one concern; if a component needs a table of contents to describe it, split it.
- Separate presentational (markup/UI) components from container components that manage state and data fetching.
- Co-locate a component's file, styles, and tests in one folder instead of splitting by file type across the project.
- Favor composition (children, slots, render props) over deeply nested configuration props.
- Keep components pure where possible — same props in, same output out, no hidden side effects.
- Avoid prop drilling more than 2–3 levels deep; reach for context or a state library instead.
- Name components and files consistently and predictably (e.g., `PascalCase` matching the filename).

## 2. State Management
- Keep state as local as possible; lift it up only when more than one component actually needs it.
- Treat fetched server data as the source of truth — don't copy it into local state and let the two drift apart.
- Avoid putting everything in global state; transient UI state (open/closed, hover, input drafts) belongs in the component that owns it.
- Treat state as immutable — create a new object/array on update, never mutate in place.
- Derive values from existing state/props instead of storing redundant computed state that can go out of sync.
- Normalize collections by ID in global state instead of nesting deeply, to avoid update bugs.

## 3. Data Fetching & API Integration
- Centralize API calls in one layer (hooks/services) instead of calling `fetch` directly inside components.
- Handle loading, error, and empty states explicitly for every async operation — don't assume the happy path.
- Cancel or ignore stale requests when a component unmounts or inputs change, to avoid race conditions overwriting newer data.
- Cache and dedupe requests for the same data (React Query/SWR or equivalent) instead of refetching on every render.
- Never put secrets or private API keys in frontend code — anything shipped to the browser is public.
- Retry transient network failures with backoff, and surface a clear message once retries are exhausted.

## 4. Styling & CSS
- Use a consistent design system or token set (spacing, color, typography scale) instead of one-off magic values.
- Scope styles to the component (CSS Modules, CSS-in-JS, or a utility framework) to avoid global class-name collisions.
- Design mobile-first; add complexity for larger breakpoints, not the reverse.
- Avoid `!important` and deeply nested selectors — they're a sign the specificity model has broken down.
- Use relative units (`rem`, `%`, `clamp()`) for type and spacing instead of hardcoded pixels where things should scale.
- Keep one source of truth for theme values so a design change happens in one place, not fifty.

## 5. Accessibility (a11y)
- Use semantic HTML elements (`button`, `nav`, `header`, `label`) before reaching for `div`/`span` plus ARIA.
- Every interactive element must be reachable and operable by keyboard alone (tab order, Enter/Space activation).
- Every image needs meaningful `alt` text, or an explicitly empty `alt=""` if purely decorative.
- Every form input needs a linked, visible label — not just a placeholder.
- Manage focus explicitly for modals and route changes (trap focus in a modal, return it on close).
- Meet color contrast minimums (WCAG AA) for text against its background.
- Test with automated a11y linting (axe, eslint-plugin-jsx-a11y) and not just a visual check.

## 6. Forms & Validation
- Validate on the client for immediate feedback, but always re-validate on the server — client validation is a UX layer, not a security boundary.
- Show errors next to the field they belong to, not just in a generic banner.
- Use correct input types/attributes (`type="email"`, `inputmode`, `autocomplete`) so mobile keyboards and autofill work.
- Disable the submit button (or show a pending state) during submission to prevent duplicate submits.
- Preserve user input on validation failure — never clear the form because of an error.
- Mark required fields in a way that isn't color-only, for accessibility.

## 7. Security
- Never render raw user-generated content as HTML; sanitize first if you must (avoid `dangerouslySetInnerHTML`/`v-html` on untrusted input).
- Store sensitive tokens in httpOnly cookies rather than `localStorage` where possible — anything in `localStorage` is readable by any script on the page.
- Validate and allow-list redirect targets — never redirect straight to a URL taken from user input or query params.
- Keep dependencies patched; a vulnerable npm package ships straight to every user's browser.
- Set a Content-Security-Policy and other security headers at the hosting/CDN layer.
- Don't rely on hiding a UI element as an access-control mechanism — the underlying route/data must be protected too.

## 8. Core Design Principles
- **KISS (Keep It Simple)** — reach for the simplest component/state shape that solves the current screen; don't build a generic system for a one-off UI.
- **DRY (Don't Repeat Yourself)** — extract repeated markup/logic into a shared component or hook, but don't merge two components just because they look alike today if they'll diverge for unrelated reasons.
- **YAGNI (You Aren't Gonna Need It)** — don't add config props or variants a component doesn't need yet "just in case."
- **Single Responsibility (SOLID – S)** — a component should own one concern (display, layout, or data-fetching); split it if it's doing more than one.
- **Open/Closed (SOLID – O)** — let components be extended via props/composition (slots, render props) rather than needing internal edits for every new use case.
- **Liskov Substitution (SOLID – L)** — a specialized component (e.g., `IconButton`) should honor the same contract as the general one (`Button`) so it can be swapped in without surprises.
- **Interface Segregation (SOLID – I)** — keep prop interfaces small and specific rather than one component accepting a huge, mostly-unused prop surface.
- **Dependency Inversion (SOLID – D)** — components should depend on abstractions (a passed-in callback/service) rather than importing a concrete API client or store directly.

## 9. Performance & Optimization
- Code-split routes and heavy components; lazy-load anything not needed for the initial view.
- Memoize expensive computations and stable callbacks (`useMemo`/`useCallback` or equivalent) where profiling shows it matters — not by default everywhere.
- Virtualize long lists/tables instead of rendering thousands of DOM nodes at once.
- Optimize images: correct format (WebP/AVIF), responsive sizes, and lazy-load below-the-fold images.
- Debounce or throttle handlers for high-frequency events (search input, scroll, resize).
- Watch bundle size; tree-shake unused code rather than importing a whole library for one function.
- Batch DOM reads/writes; avoid forcing synchronous layout reflow in a loop.

## 10. Error Handling & Resilience
- Wrap the app (or major sections) in error boundaries so one broken component doesn't blank the whole page.
- Always show a fallback UI on failure — never a blank screen or a raw stack trace.
- Degrade gracefully when JS is slow or fails to load; don't let critical content depend entirely on client-side rendering if avoidable.
- Send frontend errors to a monitoring service (Sentry or equivalent) with enough context (route, action, build version) to reproduce them.

## 11. Testing
- Test components by behavior and visible/accessible output, not internal implementation details.
- Write integration/e2e tests for critical user flows (checkout, signup, auth) end to end, not just isolated units.
- Query elements in tests the way a user or screen reader would (role, label, text) instead of brittle CSS selectors.
- Use snapshot tests sparingly — they're easy to rubber-stamp and often miss real regressions.
- Include automated accessibility assertions in the test suite, not just visual review.

## 12. Build, Tooling & Monitoring
- Lint and format automatically on commit/CI (ESLint, Prettier) so style debates don't happen in review.
- Use TypeScript (or equivalent static typing) to catch prop/shape errors before runtime.
- Track Core Web Vitals (LCP, INP, CLS) in production, not just local Lighthouse runs.
- Inject environment-specific config (API URLs, feature flags) at build time — never hardcode it in component logic.
- Automate the pipeline: lint → test → build → deploy, same discipline as the backend.

## 13. Documentation & Version Control
- Keep a README with setup, run, build, and environment-variable instructions that work cold.
- Document shared components (props, usage examples) where other developers will actually find them — Storybook or equivalent.
- Write commit messages that explain *why*, not just *what*; keep PRs small and focused.
- Require code review before merging to the main branch.
