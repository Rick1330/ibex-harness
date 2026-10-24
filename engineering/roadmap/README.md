# Roadmap (engineering planning)

Planning material lives at [`engineering/roadmap-archive/legacy-roadmap/`](../roadmap-archive/legacy-roadmap/). It is contributor context, not a public page.

- **Public status:** [Status and evidence](https://ibexharness.com/docs/architecture/status-and-evidence) is the current capability boundary.
- **Benchmarks:** [Benchmarks](https://ibexharness.com/benchmarks) publishes local measurements with their profiles and limitations.
- **Agent guidance:** [AGENTS.md](../../AGENTS.md), [CLAUDE.md](../../CLAUDE.md).
- **Engineering context:** [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md), [ARCHITECTURE.md](../ARCHITECTURE.md).

## Redesigned phase sequence (planning baseline)

| Phase | Name | Status |
| --- | --- | --- |
| 0 | Foundation | Complete |
| 1 | Core Platform | Complete |
| 1.5 | Public Web Product | Complete |
| 2 | Single Provider E2E | Complete |
| **2.5** | Provider Generalization & Foundation | Complete |
| 3 | Core Memory Substrate | Complete |
| 3.5 | Extraction & Context Assembly | Complete — capability status remains provisional for context and extraction |
| 4 | Operator Platform & Multi-Provider | **In progress** — A/B and C1-C3 local; C4/C5 and Track D open; E not started |
| 4.5 | Intelligence Layer | Planned |
| 5 | Advanced Retrieval & Graph Memory | Planned |

Key redesign points:

- Phase 3 is memory substrate only; extraction + context assembly are **3.5**.
- Management API and the canonical `services/console` operator application are **Phase 4**; `services/dashboard` is a compatibility-only 4.P.0 shell.
- Intelligence is **4.5** (not a separate Phase 6).
- Org-wide production hardening is deferred **beyond Phase 5**.

Milestone pages are planning sketches: paths and libraries are orientation aids and may change with research during implementation. Service/package inventories: [`services/README.md`](../../services/README.md), [`packages/README.md`](../../packages/README.md).
