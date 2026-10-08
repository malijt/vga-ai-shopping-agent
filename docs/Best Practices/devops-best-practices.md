# DevOps Best Practices

A rule set for DevOps and infrastructure work — CI/CD pipelines, infrastructure as code, deployments, and production operations. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.) so it defaults to these patterns without needing a reminder every time. Trim anything that doesn't apply to your stack (cloud provider, orchestrator, CI tool, etc.).

## 1. CI/CD Pipelines
- Automate the full pipeline (lint → test → build → scan → deploy) — no manual steps in the critical path.
- Treat pipeline configuration as code (Jenkinsfile, GitHub Actions YAML, GitLab CI, etc.), version-controlled alongside the application.
- Build the deployable artifact once and promote that same artifact through every environment (dev → staging → prod) instead of rebuilding per environment — you want to test exactly what you ship.
- Fail the pipeline fast and loud on any failing test, lint error, or security scan — don't let a red pipeline become normal.
- Parallelize independent pipeline stages and cache dependencies to keep feedback loops short.
- Require the pipeline to pass before merge, not just before deploy — a broken `main` blocks everyone.
- Retain pipeline logs and build artifacts long enough to debug a failure after the fact.

## 2. Infrastructure as Code (IaC)
- Manage all infrastructure through code (Terraform, Pulumi, CloudFormation, etc.) — never through manual changes in a cloud console.
- Version-control infrastructure code the same way as application code, with PR review before changes apply.
- Always review the plan/diff before applying — never apply blind, especially against production.
- Store state remotely with locking so concurrent runs can't corrupt it or each other.
- Break infrastructure into reusable modules instead of copy-pasting the same resource definitions across environments.
- Prefer immutable infrastructure — replace instances/resources rather than patching them in place — so environments don't drift from what's defined in code.
- Define dev/staging/prod from the same modules with different variables, not hand-maintained separately.

## 3. Containerization & Orchestration
- Keep images small and minimal (multi-stage builds, slim/distroless base images) — smaller images pull faster and have a smaller attack surface.
- Never run a container process as root; drop privileges explicitly in the Dockerfile.
- Pin image versions or digests in production — never deploy on a moving `latest` tag.
- Run one primary process per container; use sidecars for auxiliary concerns instead of bundling everything into one image.
- Define liveness and readiness probes so the orchestrator knows when a container is actually healthy, not just running.
- Set explicit CPU/memory requests and limits on every workload so one service can't starve its neighbors.
- Scan images for known vulnerabilities in the pipeline, before they reach a registry that deploys from.

## 4. Core Design Principles
- **KISS (Keep It Simple)** — reach for the simplest infrastructure/pipeline that meets the actual requirement; don't stand up Kubernetes for a workload a single managed service would run just fine.
- **DRY (Don't Repeat Yourself)** — factor shared infrastructure patterns into reusable modules/templates instead of copy-pasting the same Terraform or pipeline config across every service.
- **YAGNI (You Aren't Gonna Need It)** — don't build multi-region failover, custom autoscaling logic, or elaborate abstraction layers for a scale or requirement you don't have yet.
- **Single Responsibility (SOLID – S)** — give each pipeline, module, and service one clearly defined job; a deploy script that also runs migrations, sends notifications, and cleans up old resources is three scripts wearing a trench coat.
- **Open/Closed (SOLID – O)** — design modules and pipelines so new environments or services are added via configuration/parameters, not by editing the shared module's internals each time.
- **Liskov Substitution (SOLID – L)** — if staging is meant to stand in for production, it should honor the same interfaces and behavior (same infra module, different variables) — not a parallel, differently-shaped setup that "mostly" matches.
- **Interface Segregation (SOLID – I)** — give services and pipelines narrow, specific permissions rather than one shared "do everything" IAM role or config file.
- **Dependency Inversion (SOLID – D)** — code and pipelines should depend on abstractions (a cloud-agnostic module interface, a standard deploy target) rather than being wired directly to one provider's specifics everywhere.

## 5. Deployment Strategies
- Aim for zero-downtime deploys by default (rolling updates at minimum); reserve maintenance windows for the exceptions, not the norm.
- Use canary or blue-green deployments for high-risk changes, and monitor error rates before shifting all traffic over.
- Decouple deployment from release using feature flags — you can ship code to production without exposing it to users yet.
- Always have a tested, fast rollback path; "we'll fix forward" is not a rollback plan.
- Deploy to an environment that mirrors production (same infra-as-code modules, similar data shape) before deploying to production itself.
- Automate deployments from a single, auditable pipeline — never let someone manually SSH in and push code.

## 6. Configuration & Secrets Management
- Keep all configuration in environment variables or a config service — never hardcoded in source or baked into an image.
- Store secrets in a dedicated secrets manager (Vault, cloud provider secret manager, etc.) — never in source control, CI logs, or plain environment files committed to git.
- Rotate secrets and credentials on a schedule, and immediately after any suspected exposure.
- Scope credentials narrowly (least privilege) per service, so one leaked credential doesn't expose everything.
- Keep environment-specific config out of the application image; inject it at deploy/runtime instead.

## 7. Security (DevSecOps)
- Shift security left: run SAST, dependency/vulnerability scanning, and secret-scanning in the pipeline, not as a separate pre-launch checklist.
- Apply least-privilege IAM policies to every service, pipeline, and human role — audit and prune unused permissions regularly.
- Patch base images, dependencies, and host OS on a defined cadence rather than "whenever someone remembers."
- Encrypt data at rest and in transit by default, not as an opt-in.
- Segment networks so a compromised service can't freely reach everything else (private subnets, security groups, service mesh policies).
- Log and alert on privileged actions (IAM changes, production access, secret reads) for audit purposes.

## 8. Monitoring, Logging & Observability
- Instrument the three pillars — metrics, logs, and traces — rather than relying on logs alone.
- Centralize logs from every service into one searchable place; logs stuck on individual instances are logs nobody will read during an incident.
- Alert on symptoms that affect users (error rate, latency, availability) rather than only raw resource metrics like CPU.
- Use distributed tracing across services so a slow or failing request can be followed end to end, not guessed at.
- Build dashboards around a small set of key health indicators per service, not an overwhelming wall of every metric available.
- Set alert thresholds tied to actual user impact (SLOs/error budgets) to avoid alert fatigue from noisy, low-value alerts.

## 9. Incident Response & Reliability
- Maintain runbooks for common failure modes and operational tasks — don't rely on one person's memory during an outage.
- Define an on-call rotation and escalation path before you need one, not after the first 2 a.m. page.
- Run blameless post-incident reviews and track the resulting action items to completion, not just to a document nobody revisits.
- Design for failure by default: timeouts, retries with backoff, and circuit breakers on every external dependency.
- Load-test critical paths before major launches or expected traffic spikes, not after the first outage reveals the limit.

## 10. Scaling & Resilience
- Auto-scale based on real load signals (queue depth, request latency, CPU/memory) rather than fixed instance counts.
- Design services to be stateless where possible so any instance can be replaced or scaled without coordination.
- Avoid single points of failure — replicate critical components across zones/regions appropriate to your availability target.
- Set sane timeouts and concurrency limits everywhere a service calls another, so one slow dependency can't cascade into a full outage.
- Practice graceful degradation — a non-critical dependency failing should degrade a feature, not take down the whole system.

## 11. Backup & Disaster Recovery
- Automate backups; a manual backup process is a backup process that eventually gets skipped.
- Regularly test restoring from backup — an untested backup is a hope, not a plan.
- Define RTO (recovery time objective) and RPO (recovery point objective) explicitly per system, and design backup frequency/architecture to meet them.
- Store backups in a separate location/account from the primary system so one compromised account can't take out both.
- Document and rehearse the disaster-recovery procedure itself, not just the backup mechanism.

## 12. Cost Management (FinOps)
- Tag every resource with owner/team/environment so cost can be attributed and unused spend can be found.
- Right-size resources based on actual utilization data rather than defaulting to oversized instances "to be safe."
- Set budget alerts before costs spike, not after the invoice arrives.
- Regularly audit for and remove orphaned resources — unattached volumes, idle load balancers, forgotten dev environments.
- Use auto-scaling and scheduled scale-down (e.g., non-prod environments off overnight) to avoid paying for idle capacity.

## 13. Documentation & Version Control
- Keep architecture diagrams and system documentation current — treat outdated docs as worse than no docs, since they actively mislead.
- Store all pipeline, infrastructure, and configuration changes in version control with PR review, the same discipline as application code.
- Write commit messages and PR descriptions that explain *why* a change was made, especially for infrastructure changes with non-obvious consequences.
- Document known operational quirks and one-off manual steps immediately — the next person (including future you) won't remember the context.
