# Failure Modes and Readiness

**Status:** `specified` target failure contract.

| Dependency | Class | Failure behavior |
|---|---|---|
| Auth/principal/policy | Authority | Deny or typed 503; no provider/tool work. |
| Budget/reservation | Authority/integrity | Deny or 503; no hard-budget claim. |
| Redis on protected path | Integrity/coordination | 503 under configured production profile; no permissive local fallback. |
| Context/memory quality | Quality | Directive-only or verified hot-cache context; never wider visibility. |
| Embedder/reranker/model | Quality/async | Queue, fallback, quarantine, or abstain. |
| Provider | External | Typed error, bounded retry/breaker/fallback. |
| Evidence outbox | Integrity | Durable buffer or uncertified response; never silent loss. |
| ClickHouse/OTel | Projection | Buffer or degraded analytics; canonical evidence remains. |
| Object storage | Artifact | Block artifact-dependent action or use verified retained reference. |
| Queue/worker | Async | Retry/DLQ/replay with operation status. |

`/health` is liveness. `/ready` means the selected profile’s required dependencies and contracts are available; optional quality services may be degraded and visibly reported. Readiness must not report healthy when security or evidence integrity is unavailable.

Graceful shutdown drains streams, stops new admissions, cancels bounded work, persists worker state, and reports completion. No process assumes a retry is safe unless the operation is idempotent.
