# Phase 3: Context and Memory

**Status:** Planned  
**Estimated duration:** 6–8 weeks  
**Depends on:** [Phase 2](../phase-2-single-provider/README.md) exit (authenticated proxy to one provider)

## Theme

Implement the **memory and context assembly** subsystems: store and retrieve memories, rank and pack context within token budgets, inject into LLM requests on the proxy critical path.

## Entry criteria

- Phase 2 E2E provider path stable
- Postgres migrations extended for memory tables (may start in late Phase 2)
- `ContextAssemblyService` proto stable (changes require buf breaking review)

## Exit criteria

- `services/memory` (Python FastAPI): CRUD + pgvector search with `org_id` enforcement
- `services/embedder` or embedder worker: embedding generation async
- `services/context` (gRPC): implements `AssembleContext` within latency budget
- Proxy calls context assembly with deadline; falls back to directive-only on timeout
- Worker: memory extraction job triggered async from proxy
- Cross-tenant tests for all data paths

## Goals

See [goals.md](goals.md).

## Milestones

Added when Phase 2 completes. Expected sequence:

1. Memory service scaffold + schema migrations
2. Embedder + vector index
3. Context assembly engine (gRPC)
4. Proxy integration + injection format
5. Extraction worker (Celery)

## Risks

- pgvector performance tuning
- Prompt-injection via memory content (quarantine + delimiters per SECURITY.md)
- Context assembly missing p95 budget → blocks proxy SLO
