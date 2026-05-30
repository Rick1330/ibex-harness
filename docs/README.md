# IBEX Harness — Documentation Index

Canonical documentation for the monorepo. Implementation has not started; these docs define the target system.

## Start here

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — vision, problem, capabilities, and phases
2. [ARCHITECTURE.md](ARCHITECTURE.md) — services, data flows, security, deployment topology
3. [TECH_STACK.md](TECH_STACK.md) — approved technologies and rationale
4. [SECURITY.md](SECURITY.md) — threat model, tenant isolation, auth, and checklists
5. [TESTING_STRATEGY.md](TESTING_STRATEGY.md) — test pyramid, CI gates, and no-mock rules

Then use [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for day-to-day workflow and PR expectations.

**Local dependencies:** [../infra/compose/dev/README.md](../infra/compose/dev/README.md) (Docker Compose). **Contracts:** [../packages/proto/README.md](../packages/proto/README.md) (Buf / protobuf).

**AI-assisted work:** read [../AGENTS.md](../AGENTS.md) and copy prompts from [../prompts/](../prompts/) (see [../PROMPTS.md](../PROMPTS.md)).

---

## Full table of contents

| Document | Description |
|----------|-------------|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | Product vision, non-goals, success metrics, and roadmap phases |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design: services, storage, flows, security, monitoring, deployment |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | PostgreSQL (RLS), Redis key patterns, ClickHouse, migrations |
| [TECH_STACK.md](TECH_STACK.md) | Languages, frameworks, data stores, and operational tooling |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | REST, gRPC, and LLM proxy API contracts |
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Universal and Go/Python/TypeScript standards |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | Local dev, branches, PRs, CI, ADRs, AI-assisted development |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Unit, integration, contract, and performance testing |
| [SECURITY.md](SECURITY.md) | Multi-tenancy, cryptography, prompt injection, incident response |
| [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) | Env var registry and validation rules |
| [MONITORING.md](MONITORING.md) | Metrics, logs, traces, dashboards, alerts, SLOs |
| [PERFORMANCE.md](PERFORMANCE.md) | Latency budgets, benchmarking, and profiling |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Dependency admission, licenses, and security SLAs |
| [DEPLOYMENT.md](DEPLOYMENT.md) | CI/CD, environments, rollouts, rollbacks, migrations |
| [FILE_STRUCTURE.md](FILE_STRUCTURE.md) | Monorepo layout and service scaffolds |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Local/CI/staging triage and common failures |
| [runbooks/RUNBOOKS.md](runbooks/RUNBOOKS.md) | P1/P2 incident runbooks (proxy, auth, Redis, DB, workers) |
| [CHANGELOG.md](CHANGELOG.md) | Release history and changelog discipline |
| [GLOSSARY.md](GLOSSARY.md) | Domain terminology (agent, memory, directive, trace, etc.) |
| [UI_UX_GUIDELINES.md](UI_UX_GUIDELINES.md) | Dashboard UX, accessibility, and trace inspector |

---

## Related (repository root)

| Path | Description |
|------|-------------|
| [../README.md](../README.md) | Project entrypoint and quick start |
| [../AGENTS.md](../AGENTS.md) | Global AI agent operating manual |
| [../PROMPTS.md](../PROMPTS.md) | Prompt library index |
| [../.cursorrules](../.cursorrules) | Cursor IDE rules for this repo |

---

## ADRs

- [adr/README.md](adr/README.md)
- [adr/ADR-0001-template.md](adr/ADR-0001-template.md)
- [adr/ADR-0002-repo-foundation-bootstrap.md](adr/ADR-0002-repo-foundation-bootstrap.md)
- [adr/ADR-0003-branch-protection-and-merge-policy.md](adr/ADR-0003-branch-protection-and-merge-policy.md)
- [adr/ADR-0004-protobuf-and-codegen-policy.md](adr/ADR-0004-protobuf-and-codegen-policy.md)
