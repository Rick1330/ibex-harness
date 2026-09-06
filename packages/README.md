# packages/

Shared libraries and contract artifacts (not deployable as standalone processes). Deployable runtimes live under [`services/`](../services/README.md).

Names below mix **shipped** packages with **planned** libraries from the redesigned roadmap (Phases 2.5–5). Planned rows are orientation only — exact package boundaries may change during implementation. See [Changing this inventory](#changing-this-inventory).

Scaffold guidance: [web/engineering/FILE_STRUCTURE.md](../web/engineering/FILE_STRUCTURE.md). Package boundary rules: [ADR-0020](../web/content/docs/adr/0020-shared-package-boundaries.mdx).

---

## Shipped (Python)

| Directory | Role |
| --- | --- |
| `authclient/` | ValidateToken wire codec + insecure gRPC target guards for Python services (`services/memory`, `services/mcp-memory`). Extracted during milestone 3.C.5 because both services needed identical authclient wheel/Docker install paths; see PR #625. Used by `POST /v1/memories` auth boundary (3.C.5) and future MCP write tools (3.5). |
| `ibex_async_db/` | Shared libpq→asyncpg URL translation + TLS `connect_args` for SQLAlchemy + asyncpg (`services/worker`, `services/memory`). Package docs: [`ibex_async_db/README.md`](ibex_async_db/README.md). Extracted from duplicated worker/memory DB helpers during milestone 3.5.A.2; see PR [#673](https://github.com/Rick1330/ibex-harness/pull/673). |

---

## Shipped (Go / shared)

| Directory | Role |
| --- | --- |
| `proto/` | Protobuf source of truth + buf codegen — [proto/README.md](proto/README.md) |
| `permissions/` | 64-bit permission bitmap ([ADR-0009](../web/content/docs/adr/0009-permission-bitmap.mdx)) |
| `crypto/` | Approved cryptography — Argon2id PHC, random, constant-time compare ([ADR-0010](../web/content/docs/adr/0010-cryptography-policy.mdx)) |
| `ratelimit/` | Org-level Redis rate limiting — `Limiter`, `RedisSlider` ([ADR-0015](../web/content/docs/adr/0015-proxy-rate-limit-skeleton.mdx)) |
| `reqid/` | Request ID generation (UUID v7), context propagation ([ADR-0017](../web/content/docs/adr/0017-request-id-strategy.mdx)) |
| `shutdown/` | Graceful shutdown coordinator for auth and proxy ([ADR-0018](../web/content/docs/adr/0018-graceful-shutdown.mdx)) |
| `logger/` | Structured JSON logger with mandatory field schema ([AGENTS.md](../AGENTS.md) §10) |
| `telemetry/` | OpenTelemetry tracer/meter init, HTTP span middleware ([ADR-0019](../web/content/docs/adr/0019-opentelemetry-provider-configuration.mdx)) |
| `metrics/` | Canonical Prometheus metric registry ([ADR-0021](../web/content/docs/adr/0021-prometheus-metric-catalog.mdx)) |
| `config/` | Typed env loading with aggregated validation ([ADR-0020](../web/content/docs/adr/0020-shared-package-boundaries.mdx)) |
| `apierror/` | Canonical HTTP/gRPC error codes and envelope ([ADR-0020](../web/content/docs/adr/0020-shared-package-boundaries.mdx)) |
| `session/` | Session store contract (intentional multi-consumer API — [ARCHITECTURE_LAYERING.md](../web/engineering/ARCHITECTURE_LAYERING.md)) |
| `idempotency/` | Idempotency store contract (intentional multi-consumer API) |
| `directive/` | Directive resolver contract (intentional multi-consumer API; rollout helpers may extend this in Phase 4.5) |
| `injection/` | System-prompt injection strategies for chat messages ([ADR-0031](../web/content/docs/adr/0031-system-prompt-injection.mdx)) |
| `authcache/` | Token validation LRU + bloom of invalids ([ADR-0028](../web/content/docs/adr/0028-auth-cache-design.mdx)) |
| `revocation/` | Auth-cache revocation channel helpers ([ADR-0029](../web/content/docs/adr/0029-token-revocation-propagation.mdx)) |
| `redissub/` | Shared Redis SUBSCRIBE helpers for revocation fan-out |
| `healthcheck/` | Shared `/health` and `/ready` probe framework ([ADR-0022](../web/content/docs/adr/0022-health-check-contract.mdx)) |
| `provider/` | LLM provider abstraction and registry ([ADR-0025](../web/content/docs/adr/0025-llm-provider-abstraction.mdx)); OpenAI + Anthropic adapters ([ADR-0040](../web/content/docs/adr/0040-anthropic-provider-adapter.mdx)); capability registry; self-hosted adapter |
| `tokenizer/` | Per-family token counting registry ([ADR-0043](../web/content/docs/adr/0043-tokenizer-registry.mdx)); tiktoken OpenAI families + claude estimate |
| `responsepipeline/` | Non-streaming chat response decode / stage pipeline / re-encode ([ADR-0044](../web/content/docs/adr/0044-response-pipeline-non-streaming.mdx)); noop default, fail-open stages |
| `embedder/` | Embedding interface + profile registry + stub + geometry validation ([ADR-0046](../web/content/docs/adr/0046-embedder-interface-registry.mdx)); inference in `services/embedder/` |
| `clickhouse/` | ClickHouse writer/DSN helpers for `llm_traces` ([ADR-0033](../web/content/docs/adr/0033-clickhouse-schema.mdx)) |
| `chdsn/` | ClickHouse DSN flattening helpers |
| `circuitbreaker/` | Shared consecutive-failure breaker used by proxy provider paths ([ADR-0025](../web/content/docs/adr/0025-llm-provider-abstraction.mdx) family); optional wrap for context Assemble deferred |
| `contextclient/` | Fail-open Go gRPC client for `ContextAssemblyService.AssembleContext` (3.5.D.1 / [ADR-0071](../web/content/docs/adr/0071-context-grpc-degradation-deadline.mdx)): `Assemble` never returns a Go `error` (`Fallback` flag); default **45ms** `IBEX_CONTEXT_ASSEMBLE_TIMEOUT`; dial/wire in proxy bootstrap |

---

## Planned (redesigned roadmap)

Shared Go libraries previously listed here (`contextclient/`, `circuitbreaker/`) are now under **Shipped**. Remaining planned inventory is client SDKs / CLI below.

### Client SDKs / CLI (still planned)

| Directory | Role |
| --- | --- |
| `sdk-python/` | Python client SDK (planned) |
| `sdk-typescript/` | TypeScript client SDK (planned) |
| `sdk-go/` | Go client SDK (planned) |
| `cli/` | `ibex` CLI (Go) (planned) |

**TypeScript:** pnpm workspace members with a `package.json` (today `@ibex-harness/proto` for local codegen; future `sdk-typescript/`, shared UI tokens) live alongside Go packages. pnpm ignores directories without `package.json`.

---

## Changing this inventory

Packages are **open to change**. Adding, removing, renaming, merging, or splitting libraries — or moving logic between `packages/` and `services/` — is allowed when there is **strong evidence** (measured hot-path cost, clearer module boundaries, duplicated crypto/auth logic, proto ownership, etc.).

Prefer:

1. **Evidence** — why the current boundary fails (import cycles, latency, duplicated secrets handling, unclear ownership)
2. **Reasoning** — tradeoffs vs extending an existing package
3. **An ADR** — especially for new shared contracts, crypto, auth, provider boundaries, or anything multiple services will import
4. **README + roadmap updates** — keep this file and milestone references aligned with the decision

Do not invent a new top-level package for one-off service helpers; keep those under `services/<name>/internal` (Go) or the service’s private modules (Python) until a second consumer and an ADR justify promotion.
