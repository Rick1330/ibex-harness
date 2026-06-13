# Content sources — Phase 1.5 public docs

Maps public Fumadocs pages (`apps/docs/content/docs/`) to engineering sources in repo-root `docs/`. **Do not** wholesale-port future Phase 2+ API spec.

## Getting Started

| Public page | Source | Notes |
| --- | --- | --- |
| Introduction | `DEVELOPMENT_GUIDE.md`, `CURRENT_STATE.md` | Phase 1 honest scope |
| Concepts | `ARCHITECTURE.md` (overview only) | No memory/LLM forwarding yet |
| FAQ | New | Common Phase 1 questions |
| Quickstart (polish) | `Makefile`, `compose-dev`, `dev-smoke` | Wave 9; honest about 501 chat stub |

## Proxy

| Public page | Source |
| --- | --- |
| Overview | `services/proxy/README.md` |
| Configuration | `ENVIRONMENT_VARIABLES.md` (proxy vars) |
| Authentication | ADR-0011, `services/proxy/README.md` |
| Rate limiting | ADR-0015 |
| Request routing | ADR-0012, ADR-0013 |
| Provider adapters | Phase 2 placeholder note |

## Auth

| Public page | Source |
| --- | --- |
| Overview | `services/auth/README.md` |
| Issuing API keys | ADR-0007, token management docs |
| Org & project model | `DATABASE_SCHEMA.md`, ADR-0014 |
| Multi-tenant RLS | `SECURITY.md`, migration docs |

## Deployment

| Public page | Source |
| --- | --- |
| Docker Compose (dev) | `infra/compose/dev/`, `DEVELOPMENT_GUIDE.md` |
| Kubernetes | Stub — not implemented Phase 1 |
| Environment variables | `ENVIRONMENT_VARIABLES.md` (filtered) |
| Observability | `OPS_GUIDE.md`, ADR-0019, ADR-0021 |

## API Reference (manual, Wave 9)

| Surface | Source |
| --- | --- |
| Auth gRPC | `packages/proto`, `API_DOCUMENTATION.md` Phase 1 banner |
| Proxy HTTP probes | `services/proxy/README.md`, `CURRENT_STATE.md` |
| Chat completions stub | ADR-0012 (501 `PROVIDER_NOT_CONFIGURED`) |

**Deferred:** OpenAPI auto-gen from `openapi.yaml` — file does not exist until Phase 2.

## Stays internal only

- `docs/roadmap/` (except links from public site)
- `docs/adr/` (link selectively)
- `CI_AUDIT.md`, coverage registers, milestone prompts
