# Architecture & Infrastructure Best Practices

A rule set for system architecture and infrastructure design — service boundaries, communication patterns, data architecture, and how a system is structured to scale and evolve. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.). Complements `devops-best-practices.md`, which covers the operational side (CI/CD, deployment, monitoring) of running that architecture in production.

## 1. Architectural Patterns & Service Boundaries
- Start with a monolith (or modular monolith) unless you have a clear, current reason for microservices — team size, independent scaling needs, or genuinely separate deployment cadences, not anticipated future scale.
- Draw service boundaries around business domains (bounded contexts), not technical layers — a "user service" and an "order service" age better than a "database service" and a "validation service."
- Avoid the distributed-monolith anti-pattern: services deployed separately but so tightly coupled they must ship together. If two services always deploy together, question whether they should be two services.
- Keep each service's internal implementation genuinely private; other services should depend only on its published API/contract, never its internal schema.
- Revisit service boundaries as the system evolves — a boundary that made sense at launch can become the wrong seam once real usage patterns clarify.

## 2. Service Communication
- Choose synchronous (REST/gRPC) vs. asynchronous (message queue/event bus) communication deliberately per interaction, based on whether the caller needs an immediate response or just needs the work to eventually happen.
- Use asynchronous messaging to decouple services and absorb load spikes, rather than forcing every interaction through a synchronous call chain.
- Design message consumers to be idempotent — messaging systems generally guarantee at-least-once delivery, so a message can and will arrive more than once.
- Avoid long synchronous call chains (A calls B calls C calls D); a single slow or failing link cascades latency and failure back through the whole chain.
- Use an API gateway to centralize cross-cutting concerns (authentication, rate limiting, routing) for externally-facing services instead of duplicating that logic in every service.
- Version service contracts (APIs and event schemas) explicitly, and support the previous version for a defined window — internal consumers deserve the same deprecation discipline as external ones.

## 3. Data Architecture
- Choose the database type per use case (relational for transactional integrity, document for flexible schema, key-value for simple fast lookups, columnar for analytics) rather than forcing one database to do everything.
- Give each service ownership of its own data in a microservices architecture; avoid multiple services reading and writing the same tables directly, which recreates tight coupling through the database.
- Design for eventual consistency where the business case tolerates it, rather than reaching for distributed transactions across services by default.
- Add caching layers deliberately, with an explicit invalidation strategy, rather than caching opportunistically wherever it seems to help.
- Use read replicas or a read/write split for read-heavy workloads instead of scaling the primary database vertically indefinitely.
- Plan data retention and archival from the start — an unbounded, ever-growing primary table is a future performance and cost problem.

## 4. Cloud & Network Architecture
- Design around the strengths of your actual cloud provider rather than paying for lowest-common-denominator portability you don't need and may never use.
- Prefer managed services (managed databases, queues, caches) over self-hosting the equivalent, unless self-hosting solves a specific, justified requirement.
- Design network topology deliberately — private subnets for internal resources, explicit security groups/firewall rules, and no public exposure by default.
- Apply least-privilege access between components at the network level (which services can even reach which others), not just at the application authentication level.
- Base multi-region or multi-AZ architecture on actual availability and latency requirements, not as a default checkbox — it adds real operational complexity that should be justified.

## 5. Environment & Deployment Topology
- Define a clear, minimal set of environments (e.g., dev, staging, prod) with a documented purpose for each, rather than an ever-growing pile of ad hoc environments nobody remembers the reason for.
- Support ephemeral/preview environments per branch or PR where feasible, so changes can be validated in isolation before merging.
- Define every environment from the same infrastructure-as-code modules with environment-specific variables, so environments don't structurally diverge from each other over time.
- Choose deployment topology (single region, multi-region active-active, multi-region active-passive) based on actual availability and latency needs, not by default.

## 6. Core Design Principles
- **KISS (Keep It Simple)** — pick the simplest architecture that meets today's actual scale and team size; don't adopt microservices, event sourcing, or multi-region infrastructure because of where you might be in five years.
- **DRY (Don't Repeat Yourself)** — share cross-cutting infrastructure (auth, logging, service discovery) through common libraries or platform services instead of reimplementing it per team or service.
- **YAGNI (You Aren't Gonna Need It)** — don't build for a scale, region, or compliance requirement you don't have yet; add the architecture when the requirement is real, not speculative.
- **Single Responsibility (SOLID – S)** — give each service, module, or infrastructure component one clear reason to change; a service that owns both orders and inventory will be pulled in two directions by two different teams' needs.
- **Open/Closed (SOLID – O)** — design integration points (APIs, event schemas, plugin interfaces) so new functionality can be added without modifying and redeploying every existing consumer.
- **Liskov Substitution (SOLID – L)** — if a component can be swapped for another implementation behind the same interface (a queue provider, a cache, a database), the rest of the system shouldn't need to change to accommodate it.
- **Interface Segregation (SOLID – I)** — expose narrow, purpose-specific APIs between services rather than one large shared interface that forces every consumer to depend on methods it doesn't use.
- **Dependency Inversion (SOLID – D)** — have services depend on abstractions (an interface, a contract, a schema) rather than being wired directly to another service's internal implementation details.

## 7. Resilience & Fault Tolerance
- Design every service boundary assuming the other side can fail — timeouts, retries with backoff, and circuit breakers belong on every external call, not just the ones that have already failed in production.
- Avoid single points of failure on critical paths; identify the one component whose failure takes down everything and treat it as an architectural problem to solve, not an acceptable risk.
- Design for graceful degradation — a non-critical dependency failing should degrade a feature, not take down the whole request.
- Set explicit timeout and concurrency budgets across a request's full call chain, so a slow downstream dependency can't silently exhaust upstream resources.
- Practice failure deliberately (chaos testing, game days) for systems where an unplanned outage would be costly, rather than discovering failure modes for the first time during a real incident.

## 8. Security Architecture
- Design security boundaries into the architecture itself (network segmentation, service-to-service authentication) rather than bolting security on after the system is built.
- Apply zero-trust principles between internal services — authenticate and authorize service-to-service calls (mTLS, scoped service tokens) rather than trusting anything inside the network perimeter by default.
- Design the credential/secret flow explicitly: how service A obtains and uses a credential to call service B, and what happens when that credential needs to be rotated.
- Isolate blast radius by design — a compromised low-privilege service shouldn't be able to reach high-value data or systems just because it's on the same network.
- Build audit logging into the architecture for privileged actions and cross-service data access, not as something bolted on after a security review flags the gap.

## 9. Scalability Architecture
- Design services to be stateless where possible, so any instance can be added, removed, or replaced without coordination.
- Identify architectural bottlenecks (a single database, a hot shard, a serial processing step) before they cause an incident, not after.
- Separate read and write paths (e.g., CQRS) only once read and write load or scaling needs genuinely diverge — it adds real complexity, so earn it first.
- Design capacity with headroom for realistic peak load, not just comfortably above average load.
- Load-test the architecture against realistic traffic patterns before a launch or expected spike, not just individual services in isolation.

## 10. Vendor & Technology Selection
- Prefer proven, well-supported technology for core infrastructure; reserve newer or more novel tools for the specific place they provide a clear, justified advantage.
- Evaluate build-vs-buy explicitly for each significant capability — a well-supported managed service is often cheaper overall than building and operating the equivalent yourself.
- Avoid adding abstraction layers purely for "in case we need to switch providers later" — that flexibility has an ongoing cost, so only pay for it where switching is a real, foreseeable possibility.
- Require a concrete justification tied to an actual problem before adopting a new technology into the stack, not novelty.
- Weigh the operational burden of a new technology (who owns running it, what the on-call story looks like) as part of the adoption decision, not an afterthought once it's already in production.

## 11. Evolvability & Technical Debt
- Design for change, not just for today's requirements — treat "how hard is this to reverse" as a first-class factor in any architectural decision.
- Isolate the parts of the system most likely to change (business rules, third-party integrations, UI-adjacent logic) behind stable interfaces, so volatility doesn't ripple through the whole system.
- Revisit major architectural decisions on a deliberate cadence as scale and requirements change — the right architecture at 10 users is often wrong at 10 million, and vice versa.
- Track architectural technical debt explicitly (not just code-level debt) and schedule time to address it, rather than letting shortcuts from an earlier, differently-scaled version of the system calcify permanently.

## 12. Architecture Documentation & Decision Records
- Maintain living architecture diagrams (e.g., a C4-style model) that reflect the current system, not a static diagram from the original kickoff meeting.
- Write an Architecture Decision Record (ADR) for significant decisions, capturing the context, the options considered, and why the chosen option won — future maintainers need the reasoning, not just the result.
- Keep architecture documentation close to the code it describes (in the repo) so it's versioned and reviewed the same way code is, instead of living in a wiki that quietly goes stale.
- Document the known tradeoffs and limitations of the current architecture explicitly, so the next person doesn't have to rediscover them the hard way.
