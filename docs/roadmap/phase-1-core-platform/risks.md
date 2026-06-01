# Phase 1 — Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Migration tool fails on Windows Git Bash | Medium | Blocks local dev | Test in 1.1.1; document PowerShell alternative; CI migration smoke on Linux |
| RLS misconfiguration leaks tenant data | Low | Critical | Cross-tenant integration tests mandatory; explicit `org_id` in queries per AGENTS.md |
| Auth gRPC adds latency to proxy | Medium | SLO risk | Strict timeouts; cache layer in Phase 2 optional milestone |
| Scope creep into full DATABASE_SCHEMA | High | Schedule slip | Milestone 1.1.1 limits to orgs + tokens; extend in Phase 3 |
| Buf breaking on new auth proto | Low | CI fail | Follow ADR-0004; initial import may skip breaking once |
| Custom metrics vs Prometheus client drift | Medium | Ops confusion | Goal 1.3 migrates or documents parity |
| Solo dev bottleneck on Python later | Medium | Phase 3 delay | Phase 1 stays Go-only; Python scaffold deferred |

## Pivot triggers

| Condition | Action |
| --- | --- |
| Migrations cannot support pgvector extension in same DB | Split auth DB vs memory DB (ADR + FINDINGS) |
| gRPC auth too slow for proxy budget | Add LRU cache milestone before Phase 2 |
| OpenAI request shape unstable | Freeze internal normalized type in 1.2.2; adapter handles provider quirks in Phase 2 |

## Optional milestones (defer if schedule pressure)

- Bloom filter for revoked tokens (architecture mentions; Phase 2)
- JWT session tokens for dashboard (Phase 3+ / separate track)
- `make db-reset` destructive helper (only if safely documented)
