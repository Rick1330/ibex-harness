# Roadmap (public site)

Roadmap content lives at `web/content/roadmap/` and is published at [/roadmap](https://ibexharness.com/roadmap).

- **Contributor edits:** change MDX under `web/content/roadmap/`, then rebuild/typecheck the `web` package as usual.
- **After each milestone merges:** update `web/content/roadmap/current-state.mdx` via PR.
- **Agent guidance:** [AGENTS.md](../../../AGENTS.md), [CLAUDE.md](../../../CLAUDE.md).
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
| 3.5 | Extraction & Context Assembly | Complete |
| 4 | Operator Platform & Multi-Provider | **In progress** |
| 4.5 | Intelligence Layer | Planned |
| 5 | Advanced Retrieval & Graph Memory | Planned |

Key redesign points (details in [findings](https://ibexharness.com/roadmap/findings)):

- Phase 3 is memory substrate only; extraction + context assembly are **3.5**.
- Management API and the canonical `services/console` operator application are **Phase 4**; `services/dashboard` is a compatibility-only 4.P.0 shell.
- Intelligence is **4.5** (not a separate Phase 6).
- Org-wide production hardening is deferred **beyond Phase 5**.

Milestone pages are planning sketches: paths and libraries are orientation aids and may change with research during implementation. Service/package inventories: [`services/README.md`](../../../services/README.md), [`packages/README.md`](../../../packages/README.md).
