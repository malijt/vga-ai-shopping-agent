# SaaS Platform Best Practices

A rule set for building and operating a multi-tenant SaaS platform — tenancy architecture, billing, entitlements, and the operational practices unique to running software as a service. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.). Complements `backend-best-practices.md` with the concerns specific to multi-tenant, subscription-based products.

## 1. Multi-Tenancy Architecture
- Choose a tenancy model deliberately (pooled/shared schema with a tenant ID column, schema-per-tenant, or database-per-tenant) based on isolation, compliance, and cost needs — don't default to one without weighing the tradeoffs.
- Enforce tenant isolation at the data layer (row-level security, a mandatory `tenant_id` filter on every query) rather than trusting application code to remember it everywhere.
- Never derive the active tenant from client-supplied input alone (a query param, a hidden form field) — resolve it from the authenticated session/token on the server.
- Support tenant-level customization (branding, settings, custom domains) through configuration, not by forking the codebase per customer.
- Plan a migration path between tenancy models as you scale — moving a large customer from pooled to a dedicated schema/database shouldn't require a rewrite.
- Isolate noisy-neighbor tenants with per-tenant rate limits and resource quotas, so one account's load spike can't degrade the platform for everyone else.

## 2. Billing & Subscription Management
- Use a dedicated billing provider (Stripe, Chargebee, Paddle, etc.) rather than building payment processing and invoicing logic from scratch.
- Model plans, tiers, and entitlements explicitly in one place, not as scattered feature checks referencing plan names throughout the codebase.
- Handle the full subscription lifecycle explicitly — trial, active, past due, canceled, reactivated — with defined behavior for each state, not just "active" and "not active."
- Reconcile billing state from webhooks, not only at checkout — payments fail, cards expire, and subscriptions change asynchronously outside the initial flow.
- Support plan upgrades/downgrades with correct proration automatically, without requiring manual support intervention for routine changes.
- Keep a durable audit trail of billing events (charges, plan changes, refunds) for support, accounting, and dispute resolution.

## 3. Onboarding & Activation
- Design onboarding around time-to-first-value — get a new account to its key "aha" action quickly, not just through a signup form.
- Support self-serve signup for your core segment, but design a guided or assisted path for higher-touch/enterprise accounts that need it.
- Track activation milestones (did the account complete its key first action) as a core product metric, not signups alone.
- Make team invites and multi-user setup simple from day one — most SaaS accounts are used by teams, even if the first person to sign up is alone.
- Instrument the onboarding funnel itself so drop-off points are visible in the data, not just guessed at.

## 4. Feature Flags & Entitlements
- Gate features through a single, central entitlement check (e.g., `canAccess(tenant, feature)`), not scattered conditionals that reference plan names directly throughout the code.
- Use feature flags to separate deploying code from releasing a feature to users, and to support gradual or targeted rollouts.
- Enforce entitlements server-side on every request — a feature hidden only in the UI is not actually gated.
- Default new or unspecified plans to the most restrictive entitlement, not the most permissive, so a missing configuration fails safe instead of silently unlocking a paid feature.
- Review and remove stale flags on a regular cadence; a flag left in "temporary" for a year is undocumented technical debt.

## 5. Core Design Principles
- **KISS (Keep It Simple)** — start with the simplest tenancy and billing model that meets your actual compliance and scale needs; don't build database-per-tenant isolation before a customer requires it.
- **DRY (Don't Repeat Yourself)** — centralize entitlement checks, tenant-context resolution, and billing-state logic so they're defined once and reused everywhere, not reimplemented per feature.
- **YAGNI (You Aren't Gonna Need It)** — don't build enterprise SSO, custom contract support, or granular per-seat permissions before a real customer is asking for them.
- **Single Responsibility (SOLID – S)** — keep tenant provisioning, billing, and entitlement logic as separate concerns; a single "account service" that does all three becomes unmaintainable fast.
- **Open/Closed (SOLID – O)** — adding a new plan tier or feature flag should mean adding configuration, not editing every feature-gate check across the codebase.
- **Liskov Substitution (SOLID – L)** — every tenant, regardless of plan or size, should flow through the same core account abstraction; avoid special-casing "enterprise tenants" as a fundamentally different code path.
- **Interface Segregation (SOLID – I)** — keep tenant-facing APIs and webhooks narrow and purpose-specific rather than exposing one giant tenant/account object with every field for every use case.
- **Dependency Inversion (SOLID – D)** — depend on an abstraction for billing/plan logic (a provider interface) rather than hardcoding one vendor's SDK calls directly throughout the application.

## 6. Security & Compliance
- Encrypt tenant data at rest and in transit, with encryption boundaries that respect tenant isolation rather than one shared key for everything.
- Treat the compliance frameworks your customers require (SOC 2, GDPR, HIPAA, etc.) as a first-class product requirement once you sell to businesses, not a retrofit for one deal.
- Maintain an audit log of security-relevant actions per account (logins, permission changes, data exports, admin actions).
- Support SSO/SAML and role-based access control for enterprise customers — the identity and access bar rises quickly once you're selling into companies with an IT/security team.
- Have a tested process for permanently deleting a tenant's data across every system it landed in (primary DB, backups, analytics, search index), not just the main database, for churn or deletion requests.

## 7. Scalability & Performance for Multi-Tenant Systems
- Design for uneven tenant sizes from the start; a query pattern that's fine for a 10-user account can fall over for a 10,000-user account sharing the same infrastructure.
- Index and partition with `tenant_id` as the primary filter in mind, since nearly every query in a multi-tenant system filters by tenant first.
- Cap and isolate background/batch jobs per tenant (imports, exports, reports) so one large account's job can't starve the queue for everyone else.
- Track capacity and infrastructure cost per tenant, not only in aggregate, so you know the actual margin on your largest accounts.

## 8. Usage Tracking & Metering
- Instrument usage events consistently from day one — billing, quota enforcement, and product dashboards all end up depending on the same underlying event data.
- Enforce usage quotas against near-real-time counters if you gate on limits, rather than reconciling usage only at billing time.
- Surface usage and limits to the customer in-product, especially for usage-based pricing, instead of leaving it as a surprise on the invoice.
- Keep raw usage events and billed/aggregated usage as separate concerns, so billing can be recomputed or audited without re-deriving from scratch.

## 9. Public API & Integrations
- Version your public API deliberately and support old versions through a defined deprecation window — external integrators can't be forced to upgrade on your release schedule.
- Provide webhooks for key platform events so customers can build on top of your platform, not just consume it through the UI.
- Rate-limit the public API per tenant/API key and document the limits clearly (response headers, docs) so one customer's script can't degrade the platform for others.
- Offer a sandbox or test-mode environment for integrators to build and test against without touching real data or triggering real charges.

## 10. Customer Success & Support Enablement
- Give support and success teams a read view into account state (plan, usage, recent errors, billing status) without needing an engineer to query the database.
- Build internal tooling early — an account admin panel and an audited impersonation feature — so support can act on a customer's behalf safely and traceably.
- Track and alert on churn signals (usage decline, failed payments, support escalations) so at-risk accounts are visible before they cancel, not after.
- Make "what plan and limits does this account have, and why" answerable in seconds, not by spelunking through raw billing and entitlement tables.

## 11. Observability for Multi-Tenant Platforms
- Tag every metric, log line, and trace with tenant ID so a problem can be isolated to one account versus the whole platform.
- Track per-tenant health for your largest accounts specifically, not just aggregate platform metrics that can hide one important customer's bad experience.
- Alert on tenant-specific anomalies (a sudden usage spike or drop, elevated error rate for a single account) in addition to global thresholds.
- Correlate infrastructure alerts with the tenant(s) affected before paging, so on-call can immediately gauge blast radius instead of discovering it mid-incident.

## 12. Data Portability, Retention & Offboarding
- Support data export in an open, usable format at any time — customers should never feel locked in by an inability to get their own data out.
- Publish a clear data retention and deletion policy, and make account closure actually delete data on the schedule you promise, across every system that stores it.
- Maintain a status page and an incident-communication process; SaaS customers expect visibility into outages affecting them, not silence.
- Treat offboarding as a designed flow, not an edge case — a canceled account should be handled as deliberately as a signed-up one.
