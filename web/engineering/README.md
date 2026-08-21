# IBEX Harness — Documentation Index

Canonical **engineering** documentation for monorepo contributors. **Integrator-facing** docs ship on the public site at [ibexharness.com/docs](https://ibexharness.com/docs) (`web/content/docs/`).

## Living documentation (keep in sync)

Engineering docs, `services/README.md`, `packages/README.md`, and `web/content/roadmap/` must stay aligned when:

- phase scope changes,
- a service or package is added/removed/renamed,
- a latency or tenancy invariant changes,
- an ADR lands that alters architecture.

Prefer updating these in the same PR as the code/roadmap change (or an immediate follow-up docs PR). Inventories are **planning baselines** — they may change with evidence and an ADR.

## Start here

1. [web/content/roadmap/current-state.mdx](../content/roadmap/current-state.mdx) — living implementation snapshot (`/roadmap/current-state`)
2. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — vision, problem, capabilities, and **redesigned phases**
3. [ARCHITECTURE.md](ARCHITECTURE.md) — services, data flows, security, deployment topology
4. [FILE_STRUCTURE.md](FILE_STRUCTURE.md) — monorepo layout (current + planned)
5. [TECH_STACK.md](TECH_STACK.md) — approved technologies and rationale
6. [SECURITY.md](SECURITY.md) — threat model, tenant isolation, auth, and checklists
7. [TESTING_STRATEGY.md](TESTING_STRATEGY.md) — test pyramid, CI gates, and no-mock rules

Then use [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for day-to-day workflow, PR expectations, and the **session workspace** (§12 — sibling `ibex-harness-workspace/`, outside git).

**Service / package inventories:** [../../services/README.md](../../services/README.md), [../../packages/README.md](../../packages/README.md).

**Public docs mapping:** [web/content/roadmap/phase-1-5-docs-site/content-sources.mdx](../content/roadmap/phase-1-5-docs-site/content-sources.mdx) lists which engineering files feed each `/docs/*` page.

**Toolchain:** [TOOLCHAIN.md](TOOLCHAIN.md) lists required local tools, installation options, and sanity checks.

**Local dependencies:** [../../infra/compose/dev/README.md](../../infra/compose/dev/README.md) (Docker Compose). **Contracts:** [../../packages/proto/README.md](../../packages/proto/README.md) (Buf / protobuf).

**AI-assisted work:** read [../../AGENTS.md](../../AGENTS.md). Optional local workspace prompts stay outside the git repo.

---

## Public docs site (integrators)

| Section | URL | Engineering sources |
| --- | --- | --- |
| Getting Started | `/docs/getting-started` | `DEVELOPMENT_GUIDE.md`, quickstart Makefile targets |
| Architecture | `/docs/architecture` | `ARCHITECTURE.md`, `DATABASE_SCHEMA.md` (subset) |
| Proxy / Auth | `/docs/proxy`, `/docs/auth` | `services/*/README.md`, ADRs |
| Security | `/docs/security` | `SECURITY.md`, `ENVIRONMENT_VARIABLES.md` |
| Deployment | `/docs/deployment` | `DEVELOPMENT_GUIDE.md`, compose dev |
| Operations | `/docs/operations` | `OPS_GUIDE.md`, `TROUBLESHOOTING.md`, runbooks |
| API Reference | `/docs/api-reference` | Shipped surfaces — see content-sources |
| ADRs | `/docs/adr` | `web/content/docs/adr/` |
| Changelog / Glossary | `/docs/changelog`, `/docs/glossary` | `CHANGELOG.md`, `GLOSSARY.md` |
| Roadmap | `/roadmap` | `web/content/roadmap/` (phases 0–5 redesigned) |

---

## Full engineering table of contents

| Document | Description |
|----------|-------------|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | Product vision, non-goals, success metrics, redesigned roadmap phases |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design: services, storage, flows, security, monitoring, deployment |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | PostgreSQL (RLS), Redis key patterns, ClickHouse, migrations |
| [TECH_STACK.md](TECH_STACK.md) | Languages, frameworks, data stores, and operational tooling |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | REST, gRPC, and LLM proxy API contracts |
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Universal and Go/Python/TypeScript standards |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | Local dev, branches, PRs, CI, ADRs, AI-assisted development |
| [TOOLCHAIN.md](TOOLCHAIN.md) | Required tools, installation, sanity checks, and local command surface |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Unit, integration, contract, and performance testing |
| [SECURITY.md](SECURITY.md) | Multi-tenancy, cryptography, prompt injection, incident response |
| [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) | Env var registry and validation rules |
| [MONITORING.md](MONITORING.md) | Metrics, logs, traces, dashboards, alerts, SLOs |
| [PERFORMANCE.md](PERFORMANCE.md) | Latency budgets, benchmarking, and profiling |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Dependency admission, licenses, and security SLAs |
| [GOVERNANCE.md](GOVERNANCE.md) | Maintainers, roles, access review, OpenSSF baseline governance |
| [ASSURANCE_CASE.md](ASSURANCE_CASE.md) | Security claims mapped to evidence (Silver assurance_case) |
| [OPENSSF_BEST_PRACTICES.md](OPENSSF_BEST_PRACTICES.md) | Badge evidence map (Passing + Baseline + Silver/Gold) |
| [DEPLOYMENT.md](DEPLOYMENT.md) | CI/CD, environments, rollouts, rollbacks, migrations |
| [OPS_GUIDE.md](OPS_GUIDE.md) | Health probes, Kubernetes liveness/readiness configuration |
| [FILE_STRUCTURE.md](FILE_STRUCTURE.md) | Monorepo layout and service scaffolds |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Local/CI/staging triage and common failures |
| [runbooks/RUNBOOKS.md](runbooks/RUNBOOKS.md) | P1/P2 incident runbooks (proxy, auth, Redis, DB, workers) |
| [CHANGELOG.md](../../CHANGELOG.md) | Release history and changelog discipline |
| [GLOSSARY.md](GLOSSARY.md) | Domain terminology (agent, memory, directive, trace, etc.) |
| [UI_UX_GUIDELINES.md](UI_UX_GUIDELINES.md) | Dashboard UX, accessibility, and trace inspector |

### Roadmap (public site)

| Document | Description |
| --- | --- |
| [roadmap/README.md](roadmap/README.md) | Pointer + phase summary for `/roadmap` |
| [../content/roadmap/current-state.mdx](../content/roadmap/current-state.mdx) | Living snapshot (update after each merge) |
| [../content/roadmap/](../content/roadmap/) | Phase goals, milestones, decisions, risks |

---

## Related (repository root)

| Path | Description |
|------|-------------|
| [../../README.md](../../README.md) | Project entrypoint and quick start |
| [../../services/README.md](../../services/README.md) | Deployable service inventory |
| [../../packages/README.md](../../packages/README.md) | Shared package inventory |
| [../../infra/README.md](../../infra/README.md) | Infra / compose / migrations |
| [../../benchmarks/README.md](../../benchmarks/README.md) | Proxy/load benchmark pipeline |
| [../../AGENTS.md](../../AGENTS.md) | Agent / AI assistant workflow and invariants |
| [../../CLAUDE.md](../../CLAUDE.md) | Claude entrypoint → `@AGENTS.md` |

---

## ADRs

- [adr/README.md](adr/README.md) — pointer to public ADR index
- **Published ADRs:** [web/content/docs/adr/](../content/docs/adr/) (`/docs/adr` on the docs site)
- Contributor edits land under `web/content/docs/adr/`; the public site is the canonical reader-facing copy.
