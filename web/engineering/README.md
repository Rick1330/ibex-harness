# IBEX Harness — Documentation Index

Canonical **engineering** documentation for monorepo contributors. **Integrator-facing** docs ship on the public site at [docs.ibexharness.com](https://docs.ibexharness.com) (`web/content/docs/`).

## Start here

1. [web/content/roadmap/current-state.mdx](../content/roadmap/current-state.mdx) — living implementation snapshot (`/roadmap/current-state`)
2. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — vision, problem, capabilities, and phases
3. [ARCHITECTURE.md](ARCHITECTURE.md) — services, data flows, security, deployment topology
4. [TECH_STACK.md](TECH_STACK.md) — approved technologies and rationale
5. [SECURITY.md](SECURITY.md) — threat model, tenant isolation, auth, and checklists
6. [TESTING_STRATEGY.md](TESTING_STRATEGY.md) — test pyramid, CI gates, and no-mock rules

Then use [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for day-to-day workflow, PR expectations, and the **session workspace** (§12 — sibling `ibex-harness-workspace/`, outside git).

**Public docs mapping:** [web/content/roadmap/phase-1-5-docs-site/content-sources.mdx](../content/roadmap/phase-1-5-docs-site/content-sources.mdx) lists which engineering files feed each `/docs/*` page.

**Toolchain:** [TOOLCHAIN.md](TOOLCHAIN.md) lists required local tools, installation options, and sanity checks.

**Local dependencies:** [../infra/compose/dev/README.md](../infra/compose/dev/README.md) (Docker Compose). **Contracts:** [../packages/proto/README.md](../packages/proto/README.md) (Buf / protobuf).

**AI-assisted work:** read [../AGENTS.md](../AGENTS.md). Execution prompts live in the contributor workspace (not published on the docs site).

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
| API Reference | `/docs/api-reference` | Phase 1 surfaces only — see content-sources |
| ADRs | `/docs/adr` | Migrated from `docs/adr/` |
| Changelog / Glossary | `/docs/changelog`, `/docs/glossary` | `CHANGELOG.md`, `GLOSSARY.md` |

---

## Full engineering table of contents

| Document | Description |
|----------|-------------|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | Product vision, non-goals, success metrics, and roadmap phases |
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
| [DEPLOYMENT.md](DEPLOYMENT.md) | CI/CD, environments, rollouts, rollbacks, migrations |
| [OPS_GUIDE.md](OPS_GUIDE.md) | Health probes, Kubernetes liveness/readiness configuration |
| [FILE_STRUCTURE.md](FILE_STRUCTURE.md) | Monorepo layout and service scaffolds |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Local/CI/staging triage and common failures |
| [runbooks/RUNBOOKS.md](runbooks/RUNBOOKS.md) | P1/P2 incident runbooks (proxy, auth, Redis, DB, workers) |
| [CHANGELOG.md](CHANGELOG.md) | Release history and changelog discipline |
| [GLOSSARY.md](GLOSSARY.md) | Domain terminology (agent, memory, directive, trace, etc.) |
| [UI_UX_GUIDELINES.md](UI_UX_GUIDELINES.md) | Dashboard UX, accessibility, and trace inspector |

### Roadmap (public site)

| Document | Description |
| --- | --- |
| [roadmap/README.md](roadmap/README.md) | Pointer to public `/roadmap` on docs site |
| [app/content/roadmap/current-state.mdx](../content/roadmap/current-state.mdx) | Living snapshot (update after each merge) |
| [app/content/roadmap/](../content/roadmap/) | Phase goals, milestones, decisions, risks |

---

## Related (repository root)

| Path | Description |
|------|-------------|
| [../README.md](../README.md) | Project entrypoint and quick start |
| [../AGENTS.md](../AGENTS.md) | Global AI agent operating manual |
| [../.cursorrules](../.cursorrules) | Cursor IDE rules for this repo |

---

## ADRs

- [adr/README.md](adr/README.md) — pointer to public ADR index
- **Published ADRs:** [web/content/docs/adr/](../content/docs/adr/) (`/docs/adr` on the docs site)
- Source markdown remains in [adr/](adr/) for engineering workflow; public site is the canonical reader-facing copy after migration.
